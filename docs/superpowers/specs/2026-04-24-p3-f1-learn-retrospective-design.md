# P3-F.1: Learn Module — Retrospective Analysis as Worker Module

**Date:** 2026-04-24
**Epic:** P3-F (Learn Module)
**Dependencies:** P3-A.1 (module runner)
**Spec:** NTHLAYER-LEARN-v1 §4.5 (outcome resolution), §7 (retrospective analysis)

## Summary

Split the learn module into two worker modules operating on different units at different cadences. Outcome resolution is continuous per-verdict maintenance. Retrospective generation is per-incident synthesis triggered by correlation snapshots.

| Module | Responsibility | Cycle | Unit |
|--------|---------------|-------|------|
| `LearnOutcomeModule` | Verdict outcome resolution + calibration signals | 60s | Per-verdict |
| `LearnRetrospectiveModule` | Incident retrospective synthesis | 30s | Per-correlation_snapshot |

This parallels the module-split pattern established in observe (3 modules), correlate (3 modules), and continues for learn (2 modules).

---

## Design Clarifications

### Retrospectives vs. Calibration

Different questions, different outputs:

- **Retrospectives** are narrative: "What happened during this incident?" — event timeline, blast radius, root cause, recommendations. Generated immediately when a correlation_snapshot closes an incident. Most verdicts in a fresh chain won't have outcomes resolved yet. That's fine — the retrospective describes decisions and events, not whether they were correct.

- **Calibration signals** are measurement: "Were these decisions good?" — confidence vs. outcome comparison, attribution weights. Produced as a side-effect of outcome resolution, which runs continuously. They feed measure's self-calibration pipeline (P3-C, deferred).

Both are outputs of learn but they answer different questions and operate on different timescales.

### Assessment vs. Verdict

Both `retrospective` and `calibration_signal` are **assessments** (observations), not verdicts (judgment-bearing decisions). A retrospective describes what happened; a calibration signal measures decision quality. Neither authorises action or changes system state. Submitted via `submit_assessment()`.

---

## CloudEvents Taxonomy

Add two new assessment kinds to `ASSESSMENT_KINDS` in `nthlayer_common/cloudevents.py`:

```python
ASSESSMENT_KINDS = frozenset({
    ...,
    "retrospective",        # NEW — P3-F.1
    "calibration_signal",   # NEW — P3-F.1
})
```

---

## Module 1: LearnOutcomeModule

**Purpose:** Continuous background maintenance of verdict outcome state. Polls for pending verdicts, attempts resolution via five paths, emits calibration signals when outcomes resolve, marks expired verdicts.

**Cycle interval:** 60 seconds (configurable: `workers.learn.outcome_interval_seconds`).

### Five Resolution Paths (§4.5)

Each cycle, for each pending verdict:

1. **Lineage:** Check if a downstream verdict explicitly references this one. If an execution verdict cites this approval verdict, resolve based on execution result.

2. **Calibration sampling:** Check if this verdict was selected for audit. If a ground-truth label exists (from human review or labelled dataset), resolve based on agreement.

3. **Downstream signal:** Check if an external event (contract breach, incident resolution) has been attributed to this decision via a verdict with `parent_ids` containing this verdict's ID.

4. **Score-outcome divergence:** For verdicts with expressed confidence, check if observed outcome diverges from expected. Populate `calibration_delta` on resolution.

5. **Expiry:** Verdicts pending beyond the configured threshold (default 7 days) resolve as "expired" — absence of signal, not positive or negative.

### Process Cycle

```python
async def process_cycle(self) -> None:
    # 1. Fetch pending verdicts — single pass for both resolution and expiry.
    #    Minimum age floor: skip verdicts younger than minimum_resolution_age
    #    because downstream signals may not have arrived yet. Premature
    #    resolution attempts always return "no signal found" and waste cycles.
    age_cutoff = now - timedelta(hours=self.minimum_resolution_age_hours)
    result = await self.client.get_verdicts(created_before=age_cutoff.isoformat(), limit=100)

    # 2. Single iteration: attempt resolution first, expiry fallback second.
    for verdict in pending_verdicts:
        resolution = await self._attempt_resolution(verdict)
        if resolution:
            await self.client.resolve_outcome(verdict["id"], resolution)
            await self._emit_calibration_signal(verdict, resolution)
            continue
        # Expiry fallback: verdicts past threshold with no resolution signal
        if self._is_past_expiry(verdict):
            await self.client.resolve_outcome(verdict["id"], {
                "outcome_status": "expired",
                "resolution": "No outcome signal within threshold",
            })
```

**Minimum resolution age:** configurable via `workers.learn.minimum_resolution_age_hours` in `nthlayer.yaml` (default 1). Verdicts younger than this are skipped because downstream signals (lineage, external events) haven't had time to arrive.

**Note:** The core API's `GET /verdicts` may not support filtering by outcome status directly in v1.5. The module fetches recent verdicts and filters client-side for `outcome.status == "pending"`. Same pattern as correlate's assessment cursor filtering — documented as a v1.5 constraint.

**resolve_outcome endpoint:** `POST /verdicts/{id}/outcome` exists in core (P1-B.3) and `CoreAPIClient.resolve_outcome()` is implemented (P1-A.3). No new endpoint work needed.

### Calibration Signal Output

Emitted as a side-effect when an outcome resolves:

```python
assessment = {
    "id": f"cal-{verdict_id}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "kind": "calibration_signal",
    "service": verdict.get("service", "unknown"),
    "data": {
        "verdict_id": verdict["id"],
        "verdict_type": verdict.get("type"),
        "expressed_confidence": judgment.get("confidence"),
        "observed_outcome": resolution["outcome_status"],  # confirmed | overridden | partial
        "calibration_delta": _compute_delta(judgment, resolution),
        "resolution_path": resolution["path"],  # lineage | sampling | downstream | divergence | expiry
        "producer_system": verdict.get("producer", {}).get("system"),
    },
}
```

**Only emitted for non-expiry resolutions.** Expired verdicts don't produce calibration signals — absence of data is not a quality signal.

### Calibration Delta Semantics

```
observed_outcome_score:
  confirmed  → 1.0  (decision was correct)
  overridden → 0.0  (decision was wrong, human intervened)
  partial    → 0.5  (partially correct)

calibration_delta = |expressed_confidence - observed_outcome_score|
```

**Examples:**
- Verdict with confidence 0.9, outcome confirmed → delta = |0.9 - 1.0| = 0.1 (well calibrated)
- Verdict with confidence 0.9, outcome overridden → delta = |0.9 - 0.0| = 0.9 (badly calibrated)
- Verdict with confidence 0.5, outcome partial → delta = |0.5 - 0.5| = 0.0 (perfectly calibrated for uncertainty)
- Verdict with no expressed confidence → `calibration_delta: None` (no signal)

The measure module's self-calibration pipeline (v2) consumes these. Explicit formula prevents migration issues between v1.5 signal production and v2 consumption.

**Expiry threshold:** configurable via `workers.learn.expiry_threshold_days` in `nthlayer.yaml` (default 7). Expiry is handled in the single-pass process cycle — `_is_past_expiry(verdict)` is the fallback when resolution returns no signal.

---

## Module 2: LearnRetrospectiveModule

**Purpose:** Generate retrospective assessments when correlation snapshots indicate incident closure.

**Cycle interval:** 30 seconds (configurable: `workers.learn.retrospective_interval_seconds`). Faster than outcome resolution because retrospectives should feel timely after incident close.

### Process Cycle

```python
async def process_cycle(self) -> None:
    # 1. Poll core for new correlation_snapshot assessments since cursor
    result = await self.client.get_assessments(
        kind="correlation_snapshot",
        # client-side cursor filtering (same pattern as correlate)
    )

    # 2. For each new snapshot, generate retrospective
    for snapshot in new_snapshots:
        await self._generate_retrospective(snapshot)

    # 3. Update cursor
```

### Retrospective Generation

For each correlation_snapshot:

1. Extract affected services and event context from snapshot data
2. Query core for the verdict chain via lineage: `get_ancestors(snapshot_id)` + `get_descendants(snapshot_id)`
3. Build timeline from the chain (capped at 20 entries, matching existing `_build_timeline`)
4. Compute duration, blast radius, root cause from chain data
5. Generate recommendations (SLO gate, dependency review, change control)
6. Submit retrospective assessment

### Retrospective Assessment Output

```python
assessment = {
    "id": f"retro-{service}-{uuid4().hex[:8]}",
    "created_at": now.isoformat(),
    "kind": "retrospective",
    "service": snapshot_data["domain"]["service"],
    "data": {
        "correlation_snapshot_id": snapshot["id"],
        "duration_minutes": duration,
        "decisions_affected": decisions_count,
        "verdict_count": len(chain),
        "root_cause": root_cause_dict,
        "blast_radius": affected_services,
        "timeline": timeline[:20],
        "recommendations": recommendations,
        "outcome_coverage": {
            "resolved": resolved_count,
            "pending": pending_count,
            "total": len(chain),
        },
    },
}
```

`outcome_coverage` explicitly reports how many verdicts in the chain have resolved outcomes vs. pending. This makes incomplete-outcome retrospectives transparent — downstream consumers know how much outcome data was available.

### Existing Code Reuse

`build_retrospective()` in `learn/retrospective.py` already does most of this work. The worker module wraps it with:
- Core API reads instead of local store reads
- Assessment submission instead of local verdict creation
- Cursor-based polling instead of CLI trigger

The existing `_build_timeline`, `_generate_recommendations`, `_compute_financial_impact` functions are reusable. The main adaptation is swapping `VerdictStore` reads for `CoreAPIClient` calls.

### v2 Deferred: Retrospective Filtering

v1.5 generates retrospectives for every `correlation_snapshot`. At scale, most short-lived session windows produce trivial retrospectives ("one slo_status assessment arrived, window closed, 1 verdict in chain"). v2 should filter trivial snapshots: only generate retrospectives for snapshots that meet significance thresholds (event count > N, peak severity > X, duration > Y minutes, cross-service blast radius). Not in v1.5 scope.

---

## Module Registration

```python
# In nthlayer-workers CLI serve command:
outcome = LearnOutcomeModule(client=client, expiry_threshold_days=7)
retrospective = LearnRetrospectiveModule(client=client)

runner.register(outcome, interval_seconds=args.outcome_interval)
runner.register(retrospective, interval_seconds=args.retrospective_interval)
```

CLI flags:
- `--outcome-interval` (new, default 60s)
- `--retrospective-interval` (new, default 30s)
- `--expiry-threshold-days` (new, default 7)
- `--min-resolution-age-hours` (new, default 1)

---

## Test Strategy

### LearnOutcomeModule
- `test_outcome_module_protocol` — satisfies WorkerModule
- `test_resolution_via_lineage` — downstream verdict resolves parent
- `test_resolution_via_expiry` — old pending verdict marked expired
- `test_calibration_signal_emitted` — resolution produces calibration_signal assessment
- `test_expiry_no_calibration_signal` — expired verdicts don't emit calibration
- `test_no_pending_verdicts_noop` — empty poll, no work
- `test_resolution_failure_continues` — one verdict fails, others still processed

### LearnRetrospectiveModule
- `test_retrospective_module_protocol` — satisfies WorkerModule
- `test_snapshot_triggers_retrospective` — new correlation_snapshot → retrospective assessment
- `test_outcome_coverage_reported` — retrospective includes resolved/pending counts
- `test_no_snapshots_noop` — nothing to process
- `test_empty_chain_produces_minimal_retrospective` — snapshot with no lineage → retrospective contains snapshot reference, `verdict_count: 0`, `timeline: []`, note "verdict chain not available"
- `test_cursor_persisted` — state roundtrip

### Existing tests
All existing learn tests pass unchanged. Worker module code is additive — doesn't modify `retrospective.py` or CLI.

---

## Acceptance Criteria

From the epic tree:
1. Reads all verdict types from core
2. Outcome resolution via 5 paths: lineage, calibration sampling, downstream signal, score-outcome divergence, expiry
3. Calibration signals produced and queryable by measure module
4. Retrospective assessments submitted to core
5. Test: create verdict chain with resolvable outcomes, verify retrospective produced

Added:
6. Two modules, not one (outcome + retrospective)
7. `retrospective` and `calibration_signal` added to `ASSESSMENT_KINDS`
8. Expiry threshold configurable (default 7 days)
9. `outcome_coverage` in retrospective data (transparent about incomplete outcomes)
10. Expired verdicts don't produce calibration signals

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Add `retrospective` and `calibration_signal` to `ASSESSMENT_KINDS` | `pytest nthlayer-common/ -x` |
| 2 | Implement `LearnOutcomeModule` — five-path resolution + calibration signals + expiry | New outcome tests pass |
| 3 | Implement `LearnRetrospectiveModule` — snapshot-triggered retrospective generation | New retrospective tests pass |
| 4 | Register both modules in workers CLI | Full suite passes |
