# P3-C.1: Measure Module — Three-Type Output Refactor

**Date:** 2026-04-24
**Epic:** P3-C (Measure Module)
**Dependencies:** P3-A.1 (module runner), P1-A.6 (v1.5 verdict types)
**Spec:** NTHLAYER-MEASURE-v1 §9 (output verdicts)

## Summary

Adapt the existing measure evaluation pipeline as a single `MeasureModule` worker module producing three distinct output types from one `process_cycle()`:

1. **`judgment_slo_evaluation`** assessment — continuous SLO status per service+SLO (deterministic)
2. **`quality_breach`** verdict — emitted on healthy→breach transition only (trigger event)
3. **`autonomy_change`** verdict — emitted when governance reduces autonomy (LLM decision)

Single module, not split — phases are tightly coupled (each consumes the previous phase's output), computationally cheap after phase 1, and want the same 60s cycle interval.

**Name:** `MeasureModule` — no prefix/suffix since there's only one. Renamed if split is needed later (unlikely).

---

## Output Types

| Type | Category | When Emitted | CloudEvents |
|------|----------|-------------|-------------|
| `judgment_slo_evaluation` | Assessment | Every cycle, per SLO | Already in `ASSESSMENT_KINDS` |
| `quality_breach` | Verdict | On healthy→breach transition only | Already in `_VERDICT_TYPES` |
| `autonomy_change` | Verdict | On autonomy reduction (once per breach) | Already in `_VERDICT_TYPES` |

No taxonomy changes needed — all three types are already in the correct sets.

---

## Process Cycle

```
MeasureModule.process_cycle()
  │
  ├─ 1. Fetch manifests from core (judgment SLOs for each service)
  │
  ├─ 2. For each service+SLO:
  │     a. Query Prometheus for current SLI value
  │     b. Compare against target → determine status (HEALTHY/BREACH)
  │     c. Submit judgment_slo_evaluation assessment to core
  │
  ├─ 3. Detect breach transitions (compare current vs previous status):
  │     - HEALTHY→BREACH: emit quality_breach verdict
  │     - BREACH→HEALTHY: no verdict (recovery is implicit)
  │     - BREACH→BREACH: no verdict (already breaching)
  │     - HEALTHY→HEALTHY: no verdict
  │
  ├─ 4. For each new breach: check governance (one decision per breach):
  │     - If autonomy decision not yet made for this breach:
  │       call governance engine → emit autonomy_change verdict if reduced
  │     - Mark breach as "decided" in state
  │
  └─ 5. Persist state to core component_state
```

---

## State Tracking

Component state for measure tracks four concerns. Schema is explicit — persistent state vs. per-cycle compute is clear.

```python
{
    # Per-SLO last evaluation status (for transition detection)
    "slo_status": {
        "fraud-detect:reversal_rate": "breach",
        "fraud-detect:availability": "healthy",
        "payment-api:availability": "healthy",
    },

    # Per-breach autonomy decision state
    "breach_decisions": {
        "fraud-detect:reversal_rate": {
            "decided": true,
            "decided_at": "2026-04-24T12:00:00+00:00",
            "autonomy_action": "reduced",  # or "no_change"
        },
    },

    # Per-agent current autonomy level (single source of truth)
    "autonomy_levels": {
        "fraud-detect": "supervised",
    },

    # Cursor for time-based polling
    "cursor": "2026-04-24T12:00:00+00:00",
}
```

### State On Restart

On worker restart, `restore_state()` restores from core's `component_state`:
- `slo_status` restored → breach transitions detected correctly on next cycle
- `breach_decisions` restored → no duplicate autonomy decisions
- `autonomy_levels` restored → governance engine has correct starting level

If `component_state` is empty (first run or state lost): treat all SLOs as "unknown" status. On first evaluation cycle, any breaching SLO fires a `quality_breach` verdict (one false positive per pre-existing breach on cold start). This is acceptable — a false positive on restart is better than silently missing a real breach.

---

## Phase 1: Judgment SLO Evaluation

Each cycle, for each service with judgment SLOs in manifests:

1. Query Prometheus for the SLI value using the SLO's indicator expression
2. Compare against target threshold
3. Produce `judgment_slo_evaluation` assessment

```python
assessment = {
    "id": f"jse-{service}-{slo_name}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "kind": "judgment_slo_evaluation",
    "service": service,
    "data": {
        "slo_name": slo_name,
        "slo_type": slo.judgment_type,  # reversal_rate, high_confidence_failure, etc.
        "target": slo.target,
        "current_value": current_value,  # ratio (0.0-1.0)
        "status": "breach" if breaching else "healthy",
        "window": slo.window,
    },
}
```

Submitted via `client.submit_assessment()`. Emitted every cycle regardless of status — continuous SLO monitoring.

### Reuse from evaluate-once

The existing `evaluate-once` CLI command already does Prometheus polling + threshold comparison. The worker module reuses the same query and comparison logic but outputs assessment format instead of verdicts.

---

## Phase 2: Breach Transition Detection

Compare current cycle's status against previous cycle's status from `state["slo_status"]`:

```python
def _detect_transitions(
    current: dict[str, str],   # {slo_key: "breach"|"healthy"}
    previous: dict[str, str],  # from state
) -> list[str]:
    """Return SLO keys that transitioned HEALTHY→BREACH."""
    transitions = []
    for key, status in current.items():
        prev = previous.get(key, "unknown")
        if status == "breach" and prev != "breach":
            transitions.append(key)
    return transitions
```

For each transition, emit `quality_breach` verdict:

```python
verdict = {
    "id": f"vrd-breach-{service}-{slo_name}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "type": "quality_breach",
    "service": service,
    "parent_ids": [evaluation_assessment_id],  # references the triggering evaluation
    "data": {
        "slo_name": slo_name,
        "slo_type": slo.judgment_type,
        "target": slo.target,
        "current_value": current_value,
        "previous_status": previous_status,
    },
}
```

Submitted via `client.submit_verdict()`. Only on transitions — not every cycle while breaching.

**BREACH→HEALTHY:** No verdict emitted. Recovery is implicit — the continuous `judgment_slo_evaluation` assessments show the SLO returning to healthy. The `slo_status` state updates to "healthy", so a subsequent breach will fire a new transition.

---

## Phase 3: Autonomy Governance

For each **new** breach (not previously decided), evaluate whether autonomy should be reduced:

```python
for breach_key in new_breaches:
    if state["breach_decisions"].get(breach_key, {}).get("decided"):
        continue  # already decided for this breach

    # Governance decision (may involve LLM call)
    action = await self._evaluate_governance(service, breach_key)

    state["breach_decisions"][breach_key] = {
        "decided": True,
        "decided_at": now.isoformat(),
        "autonomy_action": action,
    }

    if action == "reduced":
        # Emit autonomy_change verdict
        verdict = {
            "id": f"vrd-auto-{service}-{uuid4().hex[:8]}",
            "type": "autonomy_change",
            "service": service,
            "parent_ids": [breach_verdict_id],
            ...
        }
        await self.client.submit_verdict(verdict)
```

**One decision per breach.** Subsequent cycles see the ongoing breach but don't re-decide. The `breach_decisions` state tracks which breaches have been evaluated.

**Re-decision triggers:** A breach_decision is cleared when:
- The SLO recovers (transitions BREACH→HEALTHY) — the `breach_decisions` entry is removed
- A new, more severe breach occurs (different SLO on the same service) — evaluated independently

**Governance engine reuse:** The existing `ErrorBudgetGovernance.check_agent()` in `governance/engine.py` already implements the LLM-based autonomy decision. The worker module calls it, but only on breach transitions (not every cycle).

### Autonomy Levels

v1.5 uses the existing four levels: `FULL → SUPERVISED → ADVISORY_ONLY → SUSPENDED`. P3-C.2 (deferred to next task) adds the five named levels from the spec. The worker module uses whatever levels the governance engine supports.

---

## Module Registration

```python
measure = MeasureModule(
    client=client,
    prometheus_url=url,
)
runner.register(measure, interval_seconds=args.measure_interval)
```

CLI flag: `--measure-interval` (new, default 60s).

---

## Existing Code Reuse

| Component | Current Location | Reuse Strategy |
|-----------|-----------------|----------------|
| Prometheus SLO query | `evaluate-once` in cli.py | Extract query logic into shared function |
| Threshold comparison | `evaluate-once` + `detection/detector.py` | Reuse detector logic |
| Governance engine | `governance/engine.py` | Call `check_agent()` on breach transitions |
| Manifest loading | `manifest.py` | Switch from local files to core API manifests |
| Verdict creation | `pipeline/router.py` | Reuse verdict creation pattern |

The existing `evaluate-once` CLI command stays for on-demand use (same as observe's CLI commands). The worker module is the periodic equivalent.

---

## Test Strategy

### MeasureModule protocol
- `test_measure_module_protocol` — satisfies WorkerModule
- `test_restore_state_restores_slo_status` — previous SLO status restored
- `test_get_state_includes_all_fields` — slo_status + breach_decisions + autonomy_levels + cursor

### Phase 1: Evaluation
- `test_evaluation_produces_assessment` — mock Prometheus + manifests → judgment_slo_evaluation submitted
- `test_evaluation_healthy` — SLI above target → status: healthy
- `test_evaluation_breach` — SLI below target → status: breach

### Phase 2: Breach transitions
- `test_healthy_to_breach_emits_verdict` — transition fires quality_breach
- `test_breach_to_breach_no_verdict` — no duplicate verdict while breaching
- `test_breach_to_healthy_no_verdict` — recovery doesn't emit verdict
- `test_cold_start_breach_emits_verdict` — unknown→breach on first cycle

### Phase 3: Autonomy
- `test_breach_triggers_governance_once` — governance called on first breach
- `test_subsequent_cycles_no_governance` — breach continues, no re-decision
- `test_recovery_clears_breach_decision` — BREACH→HEALTHY clears decided state
- `test_governance_no_change_no_verdict` — governance decides "no reduction" → no autonomy_change

### Failure modes
- `test_prometheus_failure_no_crash` — Prometheus down, cycle continues
- `test_manifest_fetch_failure_no_crash` — core API down
- `test_governance_failure_no_crash` — LLM call fails, no autonomy change emitted

---

## Acceptance Criteria

From the epic tree:
1. Each evaluation cycle produces judgment_slo_evaluation assessments
2. Breach produces quality_breach verdict with references to triggering evaluations
3. Autonomy reduction produces autonomy_change verdict with breach references
4. All three types have distinct CloudEvents type attributes
5. Existing measure tests pass (adapted to new output types, zero loss of coverage)

Added:
6. Breach detection is transition-based (HEALTHY→BREACH), not continuous
7. Autonomy decision is one-per-breach, not one-per-cycle
8. State tracking: slo_status + breach_decisions + autonomy_levels + cursor
9. Cold start treats all SLOs as "unknown" (one false positive per pre-existing breach)
10. Breach decision cleared on SLO recovery

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Implement `MeasureModule` with Phase 1 (evaluation → judgment_slo_evaluation assessments) | Evaluation tests pass |
| 2 | Add Phase 2 (breach transition detection → quality_breach verdicts) | Transition tests pass |
| 3 | Add Phase 3 (governance → autonomy_change verdicts, one-per-breach) | Governance tests pass |
| 4 | Implement state persistence (slo_status, breach_decisions, autonomy_levels) | State roundtrip tests pass |
| 5 | Register in workers CLI | Full suite passes |
