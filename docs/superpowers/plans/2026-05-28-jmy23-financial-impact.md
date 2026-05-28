# jmy.23 `financial_impact` Propagation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate the existing `_compute_financial_impact` figure from the retrospective's `metadata.custom["financial_impact"]` onto the `SpecRecommendation` document's `metadata.financial_impact`. No new compute. Drop the unpopulated string field that jmy.2 placed on `Recommendation`.

**Architecture:** Single-repo change in `nthlayer-workers`. `Recommendation.financial_impact` (the per-rec stub) is removed; `SpecRecommendation` gains `financial_impact: FinancialImpact | None = None`. `analyze_incident()` reads from `retrospective_data["financial_impact"]` and reconstructs the dataclass. The CLI's `_build_plan_from_incident` stub plumbs the figure from retrospective `metadata.custom` into `retrospective_data`. `_to_dict` emits under `metadata.financial_impact` only when present.

**Tech Stack:** Python 3.11+. No new runtime deps; uses existing `FinancialImpact` import from `nthlayer_common.outcomes`.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-28-jmy23-financial-impact-design.md`.

**Bead:** `opensrm-jmy.23`. Parent `opensrm-jmy.6` (Learn → Spec loop) already shipped; this is the additive enrichment.

---

## File structure

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` | Import `FinancialImpact` from `nthlayer_common.outcomes`; drop `financial_impact: str \| None` from `Recommendation` (line 106); add `financial_impact: FinancialImpact \| None = None` to `SpecRecommendation`; update `_to_dict()` to emit under `metadata.financial_impact` when present; update `analyze_incident()` to read `retrospective_data.get("financial_impact")` and reconstruct via `FinancialImpact(**data)`; update `parse_plan_file()` to reconstruct from metadata dict. |
| `nthlayer-workers/src/nthlayer_workers/learn/cli.py` | In `_build_plan_from_incident` (lines 215–226), include `financial_impact` from the retrospective verdict's `metadata.custom` when assembling `retrospective_data`. |
| `nthlayer-workers/tests/learn/test_recommendations.py` | Update `test_to_yaml_drops_empty_optional_fields` (line 95) — assertion that `financial_impact not in rec` is still correct (per-rec absence) but no longer the only check; add tests for SpecRecommendation-level emission, propagation, and round-trip. |

### Files NOT modified

- `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py` — `_compute_financial_impact` is the upstream contract; jmy.23 consumes it unchanged.
- `nthlayer-common/src/nthlayer_common/outcomes.py` — `FinancialImpact` dataclass is reused as-is.
- All callers of `Recommendation(...)` outside tests — the dropped field had no producer, so call sites are unaffected.

---

## Phase A — `recommendations.py` changes

### Task A1: Drop per-rec `financial_impact`; add `SpecRecommendation.financial_impact`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_recommendations.py`:

```python
class TestSpecRecommendationFinancialImpact:
    """jmy.23: financial_impact at document-level metadata."""

    def test_default_is_none(self):
        from nthlayer_workers.learn.recommendations import SpecRecommendation
        from datetime import datetime, timezone

        sr = SpecRecommendation(
            incident="inc-x",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            confidence=0.5,
            recommendations=[],
        )
        assert sr.financial_impact is None

    def test_field_accepts_financial_impact(self):
        from nthlayer_workers.learn.recommendations import SpecRecommendation
        from nthlayer_common.outcomes import FinancialImpact
        from datetime import datetime, timezone

        fi = FinancialImpact(
            estimated=5400.0,
            currency="USD",
            decisions_affected=1200,
            failure_mode="false_negative",
            volume_source="metric",
        )
        sr = SpecRecommendation(
            incident="inc-x",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            confidence=0.5,
            recommendations=[],
            financial_impact=fi,
        )
        assert sr.financial_impact is fi

    def test_recommendation_no_longer_has_financial_impact_field(self):
        """jmy.23: per-rec stub field dropped."""
        from nthlayer_workers.learn.recommendations import Recommendation
        import dataclasses

        names = {f.name for f in dataclasses.fields(Recommendation)}
        assert "financial_impact" not in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_recommendations.py::TestSpecRecommendationFinancialImpact -v
```

Expected: 3 FAILED. `SpecRecommendation` has no `financial_impact`; `Recommendation.financial_impact` still present.

- [ ] **Step 3: Edit dataclasses**

In `src/nthlayer_workers/learn/recommendations.py`:

1. Add import near the top: `from nthlayer_common.outcomes import FinancialImpact`.
2. Remove `financial_impact: str | None = None` from `Recommendation` (line 106).
3. Add `financial_impact: FinancialImpact | None = None` to `SpecRecommendation` (after `requires_human_review: bool = True`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py::TestSpecRecommendationFinancialImpact -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): move financial_impact to SpecRecommendation metadata · opensrm-jmy.23

Drops the unpopulated per-rec stub financial_impact: str | None
that jmy.2 placed on Recommendation. Adds typed
financial_impact: FinancialImpact | None to SpecRecommendation
(document-level metadata) matching the upstream retrospective
shape from _compute_financial_impact."
```

---

### Task A2: Emit `metadata.financial_impact` in `_to_dict`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_recommendations.py`:

```python
class TestFinancialImpactSerialisation:
    """jmy.23: YAML emission under metadata.financial_impact."""

    def test_to_yaml_omits_when_none(self):
        from nthlayer_workers.learn.recommendations import SpecRecommendation
        from datetime import datetime, timezone

        sr = SpecRecommendation(
            incident="inc-x",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            confidence=0.5,
            recommendations=[],
        )
        text = sr.to_yaml()
        assert "financial_impact" not in text

    def test_to_yaml_emits_under_metadata(self):
        from nthlayer_workers.learn.recommendations import SpecRecommendation
        from nthlayer_common.outcomes import FinancialImpact
        from datetime import datetime, timezone
        import yaml

        fi = FinancialImpact(
            estimated=5400.0,
            currency="USD",
            decisions_affected=1200,
            failure_mode="false_negative",
            volume_source="metric",
        )
        sr = SpecRecommendation(
            incident="inc-x",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            confidence=0.5,
            recommendations=[],
            financial_impact=fi,
        )
        data = yaml.safe_load(sr.to_yaml())
        assert "financial_impact" in data["metadata"]
        assert data["metadata"]["financial_impact"] == {
            "estimated": 5400.0,
            "currency": "USD",
            "decisions_affected": 1200,
            "failure_mode": "false_negative",
            "volume_source": "metric",
        }
```

Also update existing `test_to_yaml_drops_empty_optional_fields` (line 95): the assertion that per-rec `financial_impact` is absent is still correct (per-rec field removed entirely), but the test should add an assertion that `metadata.financial_impact` is also absent when `SpecRecommendation.financial_impact is None`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_recommendations.py::TestFinancialImpactSerialisation -v
```

Expected: `test_to_yaml_emits_under_metadata` FAILS — `_to_dict` doesn't emit the field yet.

- [ ] **Step 3: Update `_to_dict`**

In `_to_dict` (line 144), extend the metadata block:

```python
def _to_dict(self) -> dict[str, Any]:
    recs: list[dict[str, Any]] = []
    for r in self.recommendations:
        d = asdict(r)
        d = {k: v for k, v in d.items() if v not in (None, [], "")}
        recs.append(d)
    metadata: dict[str, Any] = {
        "incident": self.incident,
        "generated_by": self.generated_by,
        "generated_at": self.generated_at.isoformat(),
        "confidence": self.confidence,
        "requires_human_review": self.requires_human_review,
    }
    if self.financial_impact is not None:
        metadata["financial_impact"] = asdict(self.financial_impact)
    return {
        "apiVersion": "nthlayer.io/learn/v1",
        "kind": "RecommendationPlan",
        "metadata": metadata,
        "recommendations": recs,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: all PASS, including the new serialisation tests and the updated `test_to_yaml_drops_empty_optional_fields`.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): emit metadata.financial_impact in plan YAML · opensrm-jmy.23

_to_dict() includes financial_impact in the metadata block when
SpecRecommendation.financial_impact is set; omitted entirely when
None (absent != zero, matches the retrospective contract)."
```

---

### Task A3: Propagate in `analyze_incident` + reconstruct in `parse_plan_file`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
class TestFinancialImpactPropagation:
    """jmy.23: analyze_incident propagates from retrospective_data."""

    def test_propagates_when_present(self):
        from nthlayer_workers.learn.recommendations import analyze_incident
        from nthlayer_common.outcomes import FinancialImpact

        retro = {
            "verdicts": [],
            "blast_radius": [],
            "root_cause": None,
            "duration_minutes": 30.0,
            "financial_impact": {
                "estimated": 5400.0,
                "currency": "USD",
                "decisions_affected": 1200,
                "failure_mode": "false_negative",
                "volume_source": "metric",
            },
        }
        plan = analyze_incident(retro, "inc-x")
        assert plan.financial_impact == FinancialImpact(
            estimated=5400.0,
            currency="USD",
            decisions_affected=1200,
            failure_mode="false_negative",
            volume_source="metric",
        )

    def test_absent_when_not_in_retrospective(self):
        from nthlayer_workers.learn.recommendations import analyze_incident

        retro = {"verdicts": [], "blast_radius": [], "root_cause": None}
        plan = analyze_incident(retro, "inc-x")
        assert plan.financial_impact is None

    def test_parse_plan_file_round_trips_financial_impact(self, tmp_path):
        from nthlayer_workers.learn.recommendations import (
            SpecRecommendation, parse_plan_file,
        )
        from nthlayer_common.outcomes import FinancialImpact
        from datetime import datetime, timezone

        fi = FinancialImpact(
            estimated=5400.0,
            currency="USD",
            decisions_affected=1200,
            failure_mode="false_negative",
            volume_source="metric",
        )
        original = SpecRecommendation(
            incident="inc-x",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            confidence=0.5,
            recommendations=[],
            financial_impact=fi,
        )
        plan_path = tmp_path / "plan.yaml"
        plan_path.write_text(original.to_yaml())

        loaded = parse_plan_file(plan_path)
        assert loaded.financial_impact == fi
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_recommendations.py::TestFinancialImpactPropagation -v
```

Expected: 3 FAILED.

- [ ] **Step 3: Wire propagation + reconstruction**

In `analyze_incident()`, near the return site that constructs `SpecRecommendation`, reconstruct from the dict:

```python
fi_data = retrospective_data.get("financial_impact")
financial_impact = FinancialImpact(**fi_data) if fi_data else None
return SpecRecommendation(
    ...,
    financial_impact=financial_impact,
)
```

In `parse_plan_file()` (the existing jmy.6 function), extend the `SpecRecommendation(...)` construction:

```python
fi_data = metadata.get("financial_impact")
financial_impact = FinancialImpact(**fi_data) if fi_data else None
return SpecRecommendation(
    ...,
    financial_impact=financial_impact,
)
```

`FinancialImpact(**data)` accepts the dict produced by `asdict(self.financial_impact)` in step A2 — no manual field-by-field unpacking required.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): propagate financial_impact through analyze_incident · opensrm-jmy.23

analyze_incident reads retrospective_data['financial_impact'] (the
shape produced by retrospective._compute_financial_impact) and
reconstructs FinancialImpact onto SpecRecommendation. parse_plan_file
round-trips the same shape. No new compute path."
```

---

## Phase B — CLI plumbing

### Task B1: Surface `financial_impact` in `_build_plan_from_incident`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py` (or whichever test file covers the CLI `recommendations` subcommand path)

- [ ] **Step 1: Write failing test**

Add a CLI-level test asserting that when `_build_plan_from_incident` runs against a retrospective whose verdict carries `metadata.custom["financial_impact"]`, the resulting plan includes it. The exact form depends on how `_build_plan_from_incident` is filled in (it is a stub at `cli.py:215–226` today); the test must mock `CoreAPIClient.get_retrospective_for_incident` to return a retrospective verdict shape with `metadata.custom["financial_impact"]` populated, then assert `plan.financial_impact is not None` and matches the expected `FinancialImpact`.

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — the stub does not plumb `financial_impact`.

- [ ] **Step 3: Wire `_build_plan_from_incident`**

Fill in the stub at `cli.py:215–226` so that the dict it constructs as `retrospective_data` (passed to `analyze_incident`) includes the `financial_impact` key from the retrospective verdict's `metadata.custom`:

```python
custom = (retro_verdict.metadata.custom or {})
retrospective_data = {
    ...,
    "financial_impact": custom.get("financial_impact"),
}
```

If `_build_plan_from_incident` remains a `NotImplementedError` stub (per the existing comment "fetching from --incident requires CoreAPIClient integration"), defer the wiring to whichever bead closes that integration (jmy.6's `--incident` path) and document the contract here so the closer threads the field through. Either way, the plumbing requirement is captured.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): plumb financial_impact from retrospective metadata · opensrm-jmy.23

_build_plan_from_incident reads metadata.custom['financial_impact']
from the retrospective verdict and includes it in retrospective_data
so analyze_incident can propagate onto the SpecRecommendation."
```

---

## Phase C — Gates + R5

### Task C1: Local gates

- [ ] **pytest**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest -q
```

Expected: all green; new tests pass; no regressions in the 1508-test baseline.

- [ ] **ruff**

```bash
uv run ruff check src/ tests/
```

- [ ] **mypy** (if configured in the repo's CI)

```bash
uv run mypy src/
```

- [ ] **Integration smoke**

If `nthlayer/test/learn-recommendations-integration.sh` exists (jmy.6 deliverable) and exercises the plan YAML shape end-to-end, run it. The `metadata.financial_impact` block is additive — existing assertions should be unaffected, but a new assertion that the field round-trips through the audited two-step workflow would close the loop.

### Task C2: R5 supervise

- [ ] Run `/r5-supervise jmy.23` to drive the 4-pass Rule-of-Five review (Correctness / Clarity / Edge Cases / Excellence) sequentially per the ecosystem-root protocol. Each pass: review → fix findings → commit → next pass. The supervisor coordinates via `.claude/r5-state.json` and the parallel-block hook prevents cross-session reviewer dispatches while state is in flight.

---

## References

- Spec: `nthlayer/docs/superpowers/specs/2026-05-28-jmy23-financial-impact-design.md`
- Bead: `opensrm-jmy.23`
- Upstream compute: `nthlayer-workers/src/nthlayer_workers/learn/retrospective.py::_compute_financial_impact`
- Canonical dataclass: `nthlayer-common/src/nthlayer_common/outcomes.py::FinancialImpact`
- Parent bead: `opensrm-jmy.6` (Learn → Spec loop, foundation already shipped)
