# P3-C.2: Measure Module — Five Named Autonomy Levels

**Date:** 2026-04-24
**Epic:** P3-C (Measure Module)
**Dependencies:** P3-C.1
**Spec:** NTHLAYER-MEASURE-v1 §6 (autonomy governance)

## Summary

Replace the existing four-level autonomy ladder with five named levels and severity-based reduction rules. Governance decisions are fully deterministic in v1.5 — no LLM calls. Manual elevation only.

**Current:** `full → supervised → advisory_only → suspended` (4 levels, always drop by 1)
**New:** `fully_autonomous → autonomous → limited_autonomous → advisor → observer` (5 levels, severity-based drop)

---

## Autonomy Levels

```python
class AutonomyLevel(str, Enum):
    FULLY_AUTONOMOUS = "fully_autonomous"
    AUTONOMOUS = "autonomous"
    LIMITED_AUTONOMOUS = "limited_autonomous"
    ADVISOR = "advisor"
    OBSERVER = "observer"
```

Ordered from most to least autonomous. The ladder is one-way down — automatic reduction only, manual elevation only.

---

## Severity Classification

Severity is per-SLO-type, dispatched on `slo.judgment_type`. Different judgment SLO types need different classifiers.

### Classification Table

| Judgment SLO Type | Low | High | Critical |
|---|---|---|---|
| `reversal_rate` | <200% budget consumed | 200-500% budget consumed | >500% budget consumed |
| `high_confidence_failure` | <200% budget consumed | 200-500% budget consumed | >500% budget consumed |
| `escalation` | <200% budget consumed | 200-500% budget consumed | >500% budget consumed |
| `outcomes` | <200% budget consumed | 200-500% budget consumed | >500% budget consumed |
| `audit_sampling` | <200% budget consumed | 200-500% budget consumed | >500% budget consumed |
| `stability` | Any breach = high | Sustained (>1 cycle) = critical | — |
| `segments` | <2x baseline variance | 2-5x baseline variance | >5x baseline variance |
| `calibration` | delta <0.1 | delta 0.1-0.3 | delta >0.3 |

**Budget consumption** = `(target - current_value) / (1 - target)` × 100 for ratio-based SLOs. Example: target=0.985, value=0.92 → `(0.985-0.92)/(1-0.985)` = 433% → high.

**Default for unknown types:** Distance heuristic with `severity: "unknown"` flagged in the `quality_breach` verdict, treated as `"high"` by governance for safety.

### Implementation

```python
def classify_severity(
    judgment_type: str | None,
    target: float,
    current_value: float,
) -> str:
    """Classify breach severity. Returns 'low', 'high', or 'critical'."""
    if judgment_type in _BUDGET_CONSUMPTION_TYPES:
        return _classify_budget_consumption(target, current_value)
    if judgment_type == "stability":
        return "high"  # any breach; sustained→critical tracked via consecutive cycles
    if judgment_type == "segments":
        return _classify_variance(target, current_value)
    if judgment_type == "calibration":
        return _classify_calibration_delta(target, current_value)
    # Unknown type → "high" for safety
    return "high"

_BUDGET_CONSUMPTION_TYPES = {
    "reversal_rate", "high_confidence_failure", "escalation",
    "outcomes", "audit_sampling",
}
```

---

## Governance Decision Logic

Fully deterministic. No LLM calls in v1.5.

```python
async def _evaluate_governance(self, service: str) -> tuple[str, int]:
    """Determine governance action. Returns (action, steps_to_drop).

    action: "reduced" | "no_change"
    steps_to_drop: number of levels to drop (1, 2, or "to_advisor"/"to_observer")
    """
    # Count currently breaching SLOs for this service
    breaching = [
        key for key, status in self._slo_status.items()
        if key.startswith(f"{service}:") and status == "breach"
    ]

    if not breaching:
        return "no_change", 0

    if len(breaching) > 1:
        # Multiple simultaneous breaches
        any_critical = any(
            self._breach_severities.get(key) == "critical"
            for key in breaching
        )
        if any_critical:
            return "reduced", -1  # -1 = drop to observer
        return "reduced", -2  # -2 = drop to advisor

    # Single breach
    severity = self._breach_severities.get(breaching[0], "high")
    if severity == "low":
        return "reduced", 1
    if severity == "high":
        return "reduced", 2
    if severity == "critical":
        return "reduced", -1  # drop to observer

    return "reduced", 1  # fallback
```

### Reduction Function

```python
AUTONOMY_LADDER = [
    "fully_autonomous", "autonomous", "limited_autonomous", "advisor", "observer"
]

def _reduce_autonomy(current_level: str, steps: int) -> str:
    """Reduce autonomy by steps. Negative steps have special meaning:
    -1 = drop to observer, -2 = drop to advisor.
    """
    if steps == -1:
        return "observer"
    if steps == -2:
        return "advisor"
    try:
        idx = AUTONOMY_LADDER.index(current_level)
        return AUTONOMY_LADDER[min(idx + steps, len(AUTONOMY_LADDER) - 1)]
    except ValueError:
        return "advisor"  # unknown level → advisor for safety
```

---

## Multi-Breach Detection

Uses current breach state, not temporal windows:

```
breaching_slos = count of SLOs currently in "breach" state for this service
if breaching_slos == 0: no governance change
elif breaching_slos == 1:
    severity = classify_severity(slo_type, value, target)
    low → drop 1 level
    high → drop 2 levels
    critical → drop to observer
elif breaching_slos > 1:
    if any breach is critical → drop to observer
    else → drop to advisor
```

This avoids timing sensitivity — three breaches across 60 seconds produce the same decision regardless of cycle alignment. The breach state tracking from P3-C.1 (`_slo_status` in component_state) already maintains per-SLO status.

---

## State Changes

New state field `_breach_severities` tracks severity per breaching SLO:

```python
{
    "slo_status": {"fraud-detect:reversal_rate": "breach", ...},
    "breach_decisions": {...},
    "autonomy_levels": {"fraud-detect": "autonomous"},
    "breach_severities": {"fraud-detect:reversal_rate": "high"},  # NEW
}
```

Severity is computed during Phase 2 (breach detection) and stored for Phase 3 (governance). Cleared on recovery (same lifecycle as `breach_decisions`).

---

## v1.5 Determinism Note

v1.5 governance decisions are fully deterministic — no LLM calls. Predictability and reliability are more important than nuance for the autonomy ratchet. v2 may incorporate LLM reasoning for borderline severity cases.

v1.5's conservative deterministic rules may produce some unnecessary autonomy reductions. Manual elevation handles those cases. This is acceptable given the one-way-ratchet philosophy: easier to manually elevate than to recover from autonomy that should have been reduced but wasn't.

---

## quality_breach Verdict Enhancement

Add `severity` field to quality_breach verdict data:

```python
breach_verdict = {
    ...,
    "data": {
        "slo_name": slo_name,
        "slo_key": slo_key,
        "severity": severity,  # "low" | "high" | "critical"
        "judgment_type": slo.get("judgment_type"),
        "target": target,
        "current_value": current_value,
    },
}
```

---

## Test Strategy

### Autonomy levels
- `test_five_levels_exist` — enum has all five values
- `test_reduce_one_step` — fully_autonomous → autonomous
- `test_reduce_two_steps` — fully_autonomous → limited_autonomous
- `test_reduce_to_advisor` — steps=-2 → advisor regardless of current level
- `test_reduce_to_observer` — steps=-1 → observer regardless of current level
- `test_observer_stays_observer` — can't go below observer

### Severity classification
- `test_budget_consumption_low` — 150% consumed → low
- `test_budget_consumption_high` — 300% consumed → high
- `test_budget_consumption_critical` — 600% consumed → critical
- `test_stability_breach_is_high` — any stability breach → high
- `test_calibration_delta_low` — delta 0.05 → low
- `test_unknown_type_defaults_high` — unknown → high

### Governance decisions
- `test_single_breach_low_drops_one` — one SLO, low severity → drop 1
- `test_single_breach_high_drops_two` — one SLO, high severity → drop 2
- `test_single_breach_critical_to_observer` — critical → observer
- `test_multi_breach_to_advisor` — 2+ SLOs breaching → advisor
- `test_multi_breach_critical_to_observer` — 2+ SLOs, one critical → observer

### Existing tests
Update existing `TestReduceAutonomy` and `TestAutonomyGovernance` for new level names and severity-based logic.

---

## Acceptance Criteria

From the epic tree:
1. Five named levels implemented as enum
2. Reduction rules match spec exactly
3. Automatic reduction on breach, manual elevation only
4. Autonomy state persisted to core

Added:
5. Severity classification per judgment SLO type
6. Multi-breach uses current breach state (not temporal window)
7. All governance decisions are deterministic (no LLM in v1.5)
8. `quality_breach` verdict carries severity field
9. Unknown SLO types default to "high" severity

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Replace `AutonomyLevel` enum with five levels in `types.py` | Existing governance tests updated |
| 2 | Implement `classify_severity()` per judgment SLO type | Severity tests pass |
| 3 | Update `_evaluate_governance` + `_reduce_autonomy` with severity-based rules | Governance tests pass |
| 4 | Update `quality_breach` verdict to include severity field | Full suite passes |
