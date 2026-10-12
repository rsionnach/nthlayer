# Judgment-Threshold Evaluation (opensrm-g32d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** nthlayer-workers evaluates judgment thresholds per OPENSRM-CORE-v2 §5.5.6 (E1–E4) instead of mis-evaluating error magnitudes as SLOs.

**Architecture:** A pure, I/O-free evaluator and outcome model live in nthlayer-common 5.2.0 alongside the bound→series metric contract. nthlayer-workers samples Prometheus per that contract, evaluates, emits one `judgment_threshold_evaluation` assessment per threshold per cycle, and raises `quality_breach` on armed breach transitions; feeding the autonomy ratchet is an operator toggle, default off.

**Tech Stack:** Python ≥3.11, `uv`, pytest (asyncio auto mode in workers), structlog, httpx-based `nthlayer_common.providers.PrometheusProvider`, release-please.

**Spec:** `nthlayer/docs/superpowers/specs/2026-10-12-g32d-judgment-threshold-evaluation-design.md`

## Global Constraints

- Release order, each R5-gated before merge, shared repo first: front door docs → nthlayer-common **5.2.0** (minor, additive) → nthlayer-workers **major**.
- nthlayer-workers pins `nthlayer-common>=5.2.0,<6.0.0`.
- E1: breach iff measured > limit; equal is within; holds for a limit of 0.
- E2: Duration limits compared in seconds via `nthlayer_common.manifest.duration_seconds`.
- E3: missing data → `not_evaluable` with a reason in `{"no_data_source", "no_data", "insufficient_window"}`; never `within`.
- E4: breach > not_evaluable > within, across bounds and across segments.
- Threshold `quality_breach` severity is the string `"high"` (downstream knows only `low | high | critical`).
- Re-arm after **3** consecutive `within` cycles.
- Operator toggle env var: `MEASURE_THRESHOLD_AUTONOMY` (truthy: `1`, `true`, `yes`, `on`, case-insensitive), default off.
- Assessment kind string: `judgment_threshold_evaluation`.
- Identity key: `f"{service}:{type}:{sha256(identifying fields)[:12]}"`, identifying fields = sorted bound NAMES, `metric`, `source`, `confidence_threshold`, `outcome_signal`, `segment_dimension`, sorted `segment_values`, `probe` (input set + frequency), measurement `window`, `bins`; bound VALUES excluded. Identical entries evaluate once; other same-key entries get `#n` ordinals in declared order.
- Workers worktrees MUST be siblings (`.claude/bin/eco-worktree.sh`), never `claude --worktree` / agent `isolation: worktree`.
- Tests assert structured data (statuses, dataclass fields, dict keys), never captured log text.
- Lint floor is frozen; run `uv run ruff check src/ tests/` and check its exit status (do not pipe it).

## Review Focus

1. A Prometheus series that exists with *other* `bins`/`window` labels → the bound is `not_evaluable("no_data")`, never evaluated against the wrong computation. Pinned in Task 9 (`test_mismatched_bins_label_is_no_data`).
2. `histogram_quantile` returning `NaN` (no observations in the window) → `not_evaluable("no_data")`, not a float comparison against NaN (which is always False → silently `within`). Pinned in Task 9 (`test_nan_quantile_is_no_data`) and Task 4 (`test_non_finite_sample_is_not_evaluable`).
3. A manifest with two identical threshold entries → evaluated once, one assessment, one verdict. Pinned in Task 10 (`test_identical_entries_share_a_key`) and Task 11 (`test_duplicate_entries_emit_once`).
4. A segment value listed twice in `segment_values` → one `SegmentResult`. Pinned in Task 5 (`test_duplicate_segment_value_evaluated_once`).
5. Core returns `/manifests` ok but with a service that has no `judgment_thresholds` key at all (older core) → that service contributes no thresholds and does not crash or retire state of other services. Pinned in Task 11 (`test_service_without_thresholds_key_is_ignored`).

---

## Phase A — front door (repo `nthlayer`, branch `docs/g32d-threshold-evaluation`)

### Task 1: Threshold metric contract in `metrics-contract.md`

**Files:**
- Modify: `nthlayer/docs/metrics-contract.md` (the "AI-Gate / Judgment SLO Metrics" section and the interim-queries table)

**Interfaces:**
- Produces: the documented contract that Task 2's `THRESHOLD_SERIES` encodes.

- [ ] **Step 1: Add a "Judgment threshold metrics (opensrm-g32d)" section** after the judgment-SLO section, with exactly this content:

```markdown
## Judgment threshold metrics (opensrm-g32d)

Judgment thresholds (OPENSRM-CORE-v2 §5.5) are bounds on error magnitudes,
evaluated by nthlayer-workers per §5.5.6. The bound → series table below is
defined in code as `nthlayer_common.manifest.THRESHOLD_SERIES`; that table is
the source of truth and this section documents it.

| Threshold | Bound | Series | Labels | Query |
|---|---|---|---|---|
| calibration | `maximum_expected_calibration_error` | `gen_ai_calibration_ece` (gauge) | `service`, `bins`, `window` | `max(gen_ai_calibration_ece{service="S",bins="B",window="W"})` |
| calibration | `maximum_brier_score` | `gen_ai_calibration_brier` (gauge) | `service`, `bins`, `window` | `max(gen_ai_calibration_brier{service="S",bins="B",window="W"})` |
| feedback_latency | `maximum_p50` | `gen_ai_feedback_latency_seconds` (histogram) | `service` | `histogram_quantile(0.5, sum by (le) (increase(gen_ai_feedback_latency_seconds_bucket{service="S"}[30d])))` |
| feedback_latency | `maximum_p90` | same histogram | `service` | `histogram_quantile(0.9, …)` |
| segments, stability, audit_backlog | — | no series yet | — | evaluated as not evaluable (`no_data_source`) |

- Calibration gauges carry the `bins` and `window` they were computed with.
  The sampler reads only the series whose `bins`/`window` labels equal the
  manifest's `measurement.bins` / `measurement.window`; any other series is
  ignored (`no_data`).
- Feedback latency is observed when ground truth arrives, so the 30-day
  window is anchored on arrival (CORE §5.5.5). A young service is measured
  over the ground truth that has arrived; only when Prometheus's retention
  (`prometheus_tsdb_lowest_timestamp_seconds`) is shorter than 30 days is the
  bound not evaluable (`insufficient_window`).
- `histogram_quantile` interpolates within a bucket: include each declared
  bound (e.g. `3600`, `86400`) among the bucket boundaries.
- Superseded: the single gauges `gen_ai_calibration_error{service}` and
  `gen_ai_feedback_latency_seconds{service}` are no longer read.
```

- [ ] **Step 2: In the interim judgment-SLO query table, mark the calibration and feedback_latency rows "superseded — now judgment thresholds, see 'Judgment threshold metrics'".**

- [ ] **Step 3: Commit**

```bash
git -C nthlayer add docs/metrics-contract.md
git -C nthlayer commit -m "docs(metrics): judgment threshold metric contract (opensrm-g32d)"
```

**Checkpoint A:** R5-gate the front-door branch (spec + plan + contract), open the PR, hold. Ask before merging.

---

## Phase B — nthlayer-common 5.2.0 (branch `feat/g32d-threshold-evaluation`)

### Task 2: `THRESHOLD_SERIES` — the bound → series contract

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/manifest/threshold_series.py`
- Test: `nthlayer-common/tests/test_threshold_series.py`

**Interfaces:**
- Consumes: `THRESHOLD_BOUNDS` from `nthlayer_common.manifest.thresholds`.
- Produces: `ThresholdSeries` (frozen dataclass: `metric: str`, `kind: Literal["gauge", "histogram_quantile"]`, `labels: tuple[str, ...]`, `quantile: float | None = None`), `THRESHOLD_SERIES: dict[str, dict[str, ThresholdSeries]]`, `FEEDBACK_LATENCY_WINDOW: str = "30d"`.

- [ ] **Step 1: Write the failing tests**

```python
"""THRESHOLD_SERIES: the bound -> metric contract (opensrm-g32d)."""

from nthlayer_common.manifest.threshold_series import (
    FEEDBACK_LATENCY_WINDOW,
    THRESHOLD_SERIES,
    ThresholdSeries,
)
from nthlayer_common.manifest.thresholds import THRESHOLD_BOUNDS

# The types with no data source yet (spec §2). Pinned: when a source is
# added, this set and the metrics contract change together.
_UNSOURCED = {"segments", "stability", "audit_backlog"}


def test_covers_every_threshold_type():
    assert set(THRESHOLD_SERIES) == set(THRESHOLD_BOUNDS)


def test_every_series_names_a_real_bound():
    for t, series in THRESHOLD_SERIES.items():
        assert set(series) <= set(THRESHOLD_BOUNDS[t]), t


def test_a_sourced_type_covers_all_its_bounds():
    for t, series in THRESHOLD_SERIES.items():
        if t not in _UNSOURCED:
            assert set(series) == set(THRESHOLD_BOUNDS[t]), t


def test_unsourced_types_are_exactly_these():
    assert {t for t, s in THRESHOLD_SERIES.items() if not s} == _UNSOURCED


def test_calibration_series_carry_bins_and_window():
    for s in THRESHOLD_SERIES["calibration"].values():
        assert s.kind == "gauge"
        assert s.labels == ("service", "bins", "window")


def test_feedback_latency_is_one_histogram_two_quantiles():
    p50 = THRESHOLD_SERIES["feedback_latency"]["maximum_p50"]
    p90 = THRESHOLD_SERIES["feedback_latency"]["maximum_p90"]
    assert p50.metric == p90.metric == "gen_ai_feedback_latency_seconds"
    assert (p50.kind, p50.quantile) == ("histogram_quantile", 0.5)
    assert (p90.kind, p90.quantile) == ("histogram_quantile", 0.9)
    assert FEEDBACK_LATENCY_WINDOW == "30d"


def test_quantile_set_only_for_histograms():
    for series in THRESHOLD_SERIES.values():
        for s in series.values():
            assert isinstance(s, ThresholdSeries)
            assert (s.quantile is not None) == (s.kind == "histogram_quantile")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_threshold_series.py`
Expected: FAIL — `ModuleNotFoundError: nthlayer_common.manifest.threshold_series`

- [ ] **Step 3: Implement**

```python
"""The judgment-threshold metric contract (opensrm-g32d).

Which Prometheus series measures each threshold bound. This table is the
source of truth: nthlayer-workers builds its queries from it and the front
door's docs/metrics-contract.md documents it. Pinned against THRESHOLD_BOUNDS
in tests/test_threshold_series.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# CORE §5.5.5: feedback latency is computed over the last 30 days, anchored on
# ground-truth arrival; a manifest cannot change it.
FEEDBACK_LATENCY_WINDOW = "30d"


@dataclass(frozen=True)
class ThresholdSeries:
    """One bound's series. ``labels`` are the labels a sampler must match
    (``bins``/``window`` take the manifest's measurement values); ``quantile``
    is set only for a ``histogram_quantile`` series."""

    metric: str
    kind: Literal["gauge", "histogram_quantile"]
    labels: tuple[str, ...]
    quantile: float | None = None


_CALIBRATION_LABELS = ("service", "bins", "window")

THRESHOLD_SERIES: dict[str, dict[str, ThresholdSeries]] = {
    "calibration": {
        "maximum_expected_calibration_error": ThresholdSeries(
            "gen_ai_calibration_ece", "gauge", _CALIBRATION_LABELS
        ),
        "maximum_brier_score": ThresholdSeries(
            "gen_ai_calibration_brier", "gauge", _CALIBRATION_LABELS
        ),
    },
    "feedback_latency": {
        "maximum_p50": ThresholdSeries(
            "gen_ai_feedback_latency_seconds", "histogram_quantile", ("service",), 0.5
        ),
        "maximum_p90": ThresholdSeries(
            "gen_ai_feedback_latency_seconds", "histogram_quantile", ("service",), 0.9
        ),
    },
    # No data source yet (opensrm-g32d follow-up beads): evaluated as
    # not evaluable, reason no_data_source.
    "segments": {},
    "stability": {},
    "audit_backlog": {},
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_threshold_series.py`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git -C nthlayer-common add src/nthlayer_common/manifest/threshold_series.py tests/test_threshold_series.py
git -C nthlayer-common commit -m "feat(manifest): THRESHOLD_SERIES, the judgment-threshold metric contract (opensrm-g32d)"
```

### Task 3: Outcome model and its payload

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/manifest/evaluation.py`
- Test: `nthlayer-common/tests/test_threshold_evaluation_model.py`

**Interfaces:**
- Produces (all in `nthlayer_common.manifest.evaluation`):
  - `Status = Literal["within", "breach", "not_evaluable"]`
  - `MissingReason = Literal["no_data_source", "no_data", "insufficient_window"]`
  - `Missing(reason: MissingReason, detail: str = "")` — frozen dataclass
  - `Samples(bounds: Mapping[str, float | Missing] = {}, overall: float | Missing | None = None, segments: Mapping[str, float | Missing] = {})` — frozen dataclass (use `field(default_factory=dict)`)
  - `BoundResult(bound: str, status: Status, measured: float | None, limit: float | str, reason: str | None)` — frozen
  - `SegmentResult(segment: str, status: Status, measured: float | None, reason: str | None)` — frozen
  - `ThresholdOutcome(type: str, status: Status, bounds: tuple[BoundResult, ...], segments: tuple[SegmentResult, ...] = ())` — frozen, with `to_dict() -> dict[str, Any]` and `@classmethod from_dict(d) -> ThresholdOutcome`
  - `combine(statuses: Iterable[Status]) -> Status` — E4; empty → `"not_evaluable"`

- [ ] **Step 1: Write the failing tests**

```python
"""Outcome model for threshold evaluation (opensrm-g32d)."""

import pytest

from nthlayer_common.manifest.evaluation import (
    BoundResult,
    Missing,
    SegmentResult,
    ThresholdOutcome,
    combine,
)


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["within"], "within"),
        (["within", "within"], "within"),
        (["within", "not_evaluable"], "not_evaluable"),
        (["not_evaluable", "within"], "not_evaluable"),
        (["within", "breach"], "breach"),
        (["not_evaluable", "breach"], "breach"),
        (["breach", "not_evaluable", "within"], "breach"),
        (["not_evaluable"], "not_evaluable"),
        ([], "not_evaluable"),
    ],
)
def test_combine_is_e4_precedence(statuses, expected):
    assert combine(statuses) == expected


def test_combine_rejects_an_unknown_status():
    with pytest.raises(ValueError):
        combine(["fine"])


def _outcome():
    return ThresholdOutcome(
        type="segments",
        status="breach",
        bounds=(BoundResult("maximum_variance_from_overall", "breach", 0.2, 0.05, None),),
        segments=(
            SegmentResult("eu", "breach", 0.2, None),
            SegmentResult("us", "not_evaluable", None, "no_data"),
        ),
    )


def test_to_dict_from_dict_round_trip():
    o = _outcome()
    assert ThresholdOutcome.from_dict(o.to_dict()) == o


def test_to_dict_is_json_serialisable_and_shaped():
    import json

    d = _outcome().to_dict()
    json.dumps(d)
    assert d["status"] == "breach"
    assert d["bounds"][0] == {
        "bound": "maximum_variance_from_overall",
        "status": "breach",
        "measured": 0.2,
        "limit": 0.05,
        "reason": None,
    }
    assert d["segments"][1]["reason"] == "no_data"


def test_missing_rejects_an_unknown_reason():
    with pytest.raises(ValueError):
        Missing("because")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_threshold_evaluation_model.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Judgment-threshold evaluation per OPENSRM-CORE-v2 §5.5.6 (opensrm-g32d).

Pure and deterministic: no I/O. A sampler (nthlayer-workers) supplies the raw
measurements the spec defines; evaluate_threshold applies E1-E4 and returns a
ThresholdOutcome, whose to_dict() is the judgment_threshold_evaluation
assessment payload.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

Status = Literal["within", "breach", "not_evaluable"]
MissingReason = Literal["no_data_source", "no_data", "insufficient_window"]

_STATUSES: tuple[str, ...] = get_args(Status)
_REASONS: tuple[str, ...] = get_args(MissingReason)
# E4: breach > not_evaluable > within.
_PRECEDENCE = {"within": 0, "not_evaluable": 1, "breach": 2}


@dataclass(frozen=True)
class Missing:
    """A measurement that could not be taken (E3)."""

    reason: MissingReason
    detail: str = ""

    def __post_init__(self) -> None:
        if self.reason not in _REASONS:
            raise ValueError(f"Missing.reason must be one of {_REASONS}, got {self.reason!r}")


@dataclass(frozen=True)
class Samples:
    """The raw measurements for one threshold.

    ``bounds`` maps a bound name to its measured value for every type except
    segments. For segments, ``overall`` is the overall rate and ``segments``
    maps each listed segment value to its rate; the evaluator computes the
    variance itself (CORE §5.5.1).
    """

    bounds: Mapping[str, float | Missing] = field(default_factory=dict)
    overall: float | Missing | None = None
    segments: Mapping[str, float | Missing] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundResult:
    bound: str
    status: Status
    measured: float | None
    limit: float | str  # as declared: a ratio, or a Duration string
    reason: str | None


@dataclass(frozen=True)
class SegmentResult:
    segment: str
    status: Status
    measured: float | None  # |segment rate - overall rate|
    reason: str | None


def combine(statuses: Iterable[str]) -> Status:
    """E4: breach > not_evaluable > within. Nothing decided -> not_evaluable."""
    best: Status = "within"
    seen = False
    for s in statuses:
        if s not in _PRECEDENCE:
            raise ValueError(f"unknown status {s!r}")
        seen = True
        if _PRECEDENCE[s] > _PRECEDENCE[best]:
            best = s  # type: ignore[assignment]
    return best if seen else "not_evaluable"


@dataclass(frozen=True)
class ThresholdOutcome:
    type: str
    status: Status
    bounds: tuple[BoundResult, ...]
    segments: tuple[SegmentResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "status": self.status,
            "bounds": [
                {"bound": b.bound, "status": b.status, "measured": b.measured,
                 "limit": b.limit, "reason": b.reason}
                for b in self.bounds
            ],
            "segments": [
                {"segment": s.segment, "status": s.status, "measured": s.measured,
                 "reason": s.reason}
                for s in self.segments
            ],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ThresholdOutcome:
        return cls(
            type=d["type"],
            status=d["status"],
            bounds=tuple(BoundResult(**b) for b in d["bounds"]),
            segments=tuple(SegmentResult(**s) for s in d.get("segments", ())),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_threshold_evaluation_model.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git -C nthlayer-common add src/nthlayer_common/manifest/evaluation.py tests/test_threshold_evaluation_model.py
git -C nthlayer-common commit -m "feat(manifest): threshold outcome model and assessment payload (opensrm-g32d)"
```

### Task 4: `evaluate_threshold` for non-segments types (E1–E4)

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/evaluation.py` (append)
- Test: `nthlayer-common/tests/test_evaluate_threshold.py`

**Interfaces:**
- Consumes: Task 3's types; `THRESHOLD_BOUNDS`, `DURATION`, `duration_seconds` from `nthlayer_common.manifest.thresholds`; `JudgmentThreshold`, `ThresholdMeasurement` from `nthlayer_common.manifest.models`.
- Produces: `evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome`. Raises `ValueError` for a type not in `THRESHOLD_BOUNDS`.

- [ ] **Step 1: Write the failing tests**

```python
"""evaluate_threshold: E1-E4 for calibration, stability, audit_backlog,
feedback_latency (opensrm-g32d). Expected outcomes follow CORE §5.5.6."""

import math

import pytest

from nthlayer_common.manifest.evaluation import Missing, Samples, evaluate_threshold
from nthlayer_common.manifest.models import JudgmentThreshold, ThresholdMeasurement


def _cal(**bounds):
    return JudgmentThreshold("calibration", dict(bounds), ThresholdMeasurement(bins=10, window="30d"))


def _lat(**bounds):
    return JudgmentThreshold("feedback_latency", dict(bounds))


# E1 ---------------------------------------------------------------------

@pytest.mark.parametrize("measured,expected", [(0.05, "within"), (0.0500001, "breach"), (0.01, "within")])
def test_e1_ratio_bound_is_strict(measured, expected):
    o = evaluate_threshold(_cal(maximum_expected_calibration_error=0.05),
                           Samples(bounds={"maximum_expected_calibration_error": measured}))
    assert o.status == expected
    assert o.bounds[0].measured == measured
    assert o.bounds[0].limit == 0.05


@pytest.mark.parametrize("measured,expected", [(0.0, "within"), (1e-9, "breach")])
def test_e1_limit_zero(measured, expected):
    o = evaluate_threshold(_cal(maximum_brier_score=0.0), Samples(bounds={"maximum_brier_score": measured}))
    assert o.status == expected


# E2 ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "limit,measured,expected",
    [("1h", 3600.0, "within"), ("1h", 3600.001, "breach"), ("60m", 3600.0, "within"),
     ("1d", 86400.0, "within"), ("1w", 604800.5, "breach"), ("500ms", 0.5, "within")],
)
def test_e2_duration_bounds_compare_in_seconds(limit, measured, expected):
    o = evaluate_threshold(_lat(maximum_p50=limit), Samples(bounds={"maximum_p50": measured}))
    assert o.status == expected
    assert o.bounds[0].limit == limit  # kept as declared


# E3 ---------------------------------------------------------------------

@pytest.mark.parametrize("reason", ["no_data_source", "no_data", "insufficient_window"])
def test_e3_missing_sample_is_not_evaluable_with_its_reason(reason):
    o = evaluate_threshold(_lat(maximum_p50="1h"), Samples(bounds={"maximum_p50": Missing(reason)}))
    assert o.status == "not_evaluable"
    assert o.bounds[0].reason == reason
    assert o.bounds[0].measured is None


def test_e3_absent_sample_is_no_data():
    o = evaluate_threshold(_lat(maximum_p50="1h"), Samples())
    assert (o.status, o.bounds[0].reason) == ("not_evaluable", "no_data")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_sample_is_not_evaluable(bad):
    o = evaluate_threshold(_cal(maximum_brier_score=0.1), Samples(bounds={"maximum_brier_score": bad}))
    assert (o.status, o.bounds[0].reason) == ("not_evaluable", "no_data")


# E4 ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "p50,p90,expected",
    [(10.0, 10.0, "within"), (10.0, Missing("no_data"), "not_evaluable"),
     (99999.0, Missing("no_data"), "breach"), (10.0, 99999.0, "breach"),
     (Missing("no_data"), Missing("no_data"), "not_evaluable")],
)
def test_e4_combines_bounds(p50, p90, expected):
    o = evaluate_threshold(_lat(maximum_p50="1h", maximum_p90="1h"),
                           Samples(bounds={"maximum_p50": p50, "maximum_p90": p90}))
    assert o.status == expected
    assert [b.bound for b in o.bounds] == ["maximum_p50", "maximum_p90"]  # declared order


def test_every_declared_bound_is_evaluated_and_only_those():
    o = evaluate_threshold(_cal(maximum_brier_score=0.1),
                           Samples(bounds={"maximum_brier_score": 0.05,
                                           "maximum_expected_calibration_error": 0.9}))
    assert [b.bound for b in o.bounds] == ["maximum_brier_score"]
    assert o.status == "within"


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        evaluate_threshold(JudgmentThreshold("vibes", {"x": 1.0}), Samples())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_evaluate_threshold.py`
Expected: FAIL — `ImportError: cannot import name 'evaluate_threshold'`

- [ ] **Step 3: Implement (append to evaluation.py)**

```python
import math

from nthlayer_common.manifest.models import JudgmentThreshold
from nthlayer_common.manifest.thresholds import DURATION, THRESHOLD_BOUNDS, duration_seconds


def _limit_value(threshold_type: str, bound: str, limit: float | str) -> float:
    if THRESHOLD_BOUNDS[threshold_type][bound] == DURATION:
        return duration_seconds(limit)  # type: ignore[arg-type]
    return float(limit)


def _decide(measured: float | Missing | None, limit: float) -> tuple[Status, float | None, str | None]:
    """E1 for one measured value; E3 for a missing or non-finite one."""
    if measured is None:
        return "not_evaluable", None, "no_data"
    if isinstance(measured, Missing):
        return "not_evaluable", None, measured.reason
    if not math.isfinite(measured):
        return "not_evaluable", None, "no_data"
    return ("breach" if measured > limit else "within"), measured, None


def evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome:
    """Apply CORE §5.5.6 E1-E4 to one threshold. Pure; raises ValueError for
    a type that is not a judgment threshold type."""
    t = threshold.type
    if t not in THRESHOLD_BOUNDS:
        raise ValueError(f"not a judgment threshold type: {t!r}")
    if t == "segments":
        return _evaluate_segments(threshold, samples)
    results = []
    for bound, limit in threshold.bounds.items():
        status, measured, reason = _decide(samples.bounds.get(bound), _limit_value(t, bound, limit))
        results.append(BoundResult(bound, status, measured, limit, reason))
    return ThresholdOutcome(t, combine(r.status for r in results), tuple(results))
```

Also add a temporary stub so the module imports until Task 5 (Task 5 replaces it):

```python
def _evaluate_segments(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome:
    raise NotImplementedError("segments: Task 5")
```

Move the new imports to the top of the module with the existing ones (ruff `I`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_evaluate_threshold.py tests/test_threshold_evaluation_model.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git -C nthlayer-common add -A src/nthlayer_common/manifest/evaluation.py tests/test_evaluate_threshold.py
git -C nthlayer-common commit -m "feat(manifest): evaluate_threshold E1-E4 for bound-valued thresholds (opensrm-g32d)"
```

### Task 5: `evaluate_threshold` for segments, and the spec examples

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/evaluation.py` (replace the `_evaluate_segments` stub)
- Test: `nthlayer-common/tests/test_evaluate_threshold_segments.py`

**Interfaces:**
- Consumes: Task 4's `_decide`, `combine`.
- Produces: segments evaluation. `ThresholdOutcome.segments` has one `SegmentResult` per distinct listed segment value, in declared order; the single bound's `BoundResult.measured` is the largest evaluated variance (or `None` when none evaluated), its status the E4 combination of the segments.

- [ ] **Step 1: Write the failing tests**

```python
"""Segments evaluation (CORE §5.5.1 + §5.5.6) and every spec example."""

from pathlib import Path

import pytest
import yaml

from nthlayer_common.manifest.evaluation import Missing, Samples, evaluate_threshold
from nthlayer_common.manifest.models import JudgmentThreshold, ThresholdMeasurement
from nthlayer_common.manifest.parser.v2 import threshold_from_v2_entry


def _seg(limit=0.05, values=("eu", "us")):
    return JudgmentThreshold(
        "segments", {"maximum_variance_from_overall": limit},
        ThresholdMeasurement(metric="escalation", segment_dimension="region",
                             segment_values=list(values), window="30d"),
    )


@pytest.mark.parametrize("eu,expected", [(0.15, "within"), (0.150001, "breach"),
                                         (0.05, "within"), (0.049999, "breach")])
def test_variance_is_absolute_in_both_directions(eu, expected):
    o = evaluate_threshold(_seg(values=("eu",)), Samples(overall=0.1, segments={"eu": eu}))
    assert o.status == expected
    assert o.segments[0].measured == pytest.approx(abs(eu - 0.1))


def test_each_segment_decided_independently():
    o = evaluate_threshold(_seg(), Samples(overall=0.1, segments={"eu": 0.3, "us": Missing("no_data")}))
    assert [(s.segment, s.status) for s in o.segments] == [("eu", "breach"), ("us", "not_evaluable")]
    assert o.status == "breach"
    assert o.bounds[0].measured == pytest.approx(0.2)


def test_missing_overall_makes_every_segment_not_evaluable():
    o = evaluate_threshold(_seg(), Samples(overall=Missing("no_data_source"),
                                           segments={"eu": 0.3, "us": 0.1}))
    assert {s.status for s in o.segments} == {"not_evaluable"}
    assert {s.reason for s in o.segments} == {"no_data_source"}
    assert o.status == "not_evaluable"
    assert o.bounds[0].measured is None


def test_unsampled_segment_is_no_data():
    o = evaluate_threshold(_seg(), Samples(overall=0.1, segments={"eu": 0.1}))
    assert [(s.segment, s.reason) for s in o.segments] == [("eu", None), ("us", "no_data")]


def test_duplicate_segment_value_evaluated_once():
    o = evaluate_threshold(_seg(values=("eu", "eu", "us")),
                           Samples(overall=0.1, segments={"eu": 0.1, "us": 0.1}))
    assert [s.segment for s in o.segments] == ["eu", "us"]


_SPEC_V2 = Path(__file__).resolve().parents[2] / "opensrm" / "spec" / "v2"
# Every shipped example that declares judgment thresholds (spec §9: every one).
_EXAMPLES = sorted(
    p for p in (_SPEC_V2 / "examples").rglob("*.yaml")
    if "judgment_threshold" in (yaml.safe_load(p.read_text()) or {}).get("spec", {})
) if _SPEC_V2.is_dir() else []


def test_the_threshold_examples_are_present():
    assert len(_EXAMPLES) >= 3, _EXAMPLES  # all-five-types, segments-two-dimensions, ai-gate


@pytest.mark.parametrize("source", _EXAMPLES, ids=lambda p: p.name)
def test_every_spec_example_threshold_evaluates(source):
    """Every threshold the spec ships is evaluable: all-within when each
    measured value equals its bound (E1: equal is within), all-breach just
    above it, all-not_evaluable when nothing is measured. Entries are parsed
    one by one (threshold_from_v2_entry), so a manifest that does not parse
    whole for unrelated reasons (ai-gate.yaml, opensrm-a742) still counts."""
    entries = yaml.safe_load(source.read_text())["spec"]["judgment_threshold"]
    for t in (threshold_from_v2_entry(e) for e in entries):
        at, above, none = _samples_at(t, 0.0), _samples_at(t, 1e-6), Samples()
        assert evaluate_threshold(t, at).status == "within", t
        assert evaluate_threshold(t, above).status == "breach", t
        assert evaluate_threshold(t, none).status == "not_evaluable", t


def _samples_at(t, delta):
    from nthlayer_common.manifest.thresholds import DURATION, THRESHOLD_BOUNDS, duration_seconds

    if t.type == "segments":
        limit = float(t.bounds["maximum_variance_from_overall"])
        return Samples(overall=0.0, segments={v: limit + delta for v in t.measurement.segment_values})
    vals = {}
    for bound, limit in t.bounds.items():
        base = duration_seconds(limit) if THRESHOLD_BOUNDS[t.type][bound] == DURATION else float(limit)
        vals[bound] = base + delta
    return Samples(bounds=vals)
```


- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_evaluate_threshold_segments.py`
Expected: FAIL — `NotImplementedError: segments: Task 5`

- [ ] **Step 3: Implement (replace the stub)**

```python
def _evaluate_segments(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome:
    """CORE §5.5.1: each listed segment's rate is compared with the overall
    rate; the bound caps |segment - overall| in either direction."""
    (bound, limit), = threshold.bounds.items()
    limit_v = float(limit)
    overall = samples.overall
    results: list[SegmentResult] = []
    for value in dict.fromkeys(threshold.measurement.segment_values):  # distinct, in order
        if overall is None or isinstance(overall, Missing) or not math.isfinite(overall):
            reason = overall.reason if isinstance(overall, Missing) else "no_data"
            results.append(SegmentResult(value, "not_evaluable", None, reason))
            continue
        rate = samples.segments.get(value)
        variance: float | Missing | None
        if rate is None or isinstance(rate, Missing):
            variance = rate
        else:
            variance = abs(rate - overall)
        status, measured, reason = _decide(variance, limit_v)
        results.append(SegmentResult(value, status, measured, reason))
    status = combine(s.status for s in results)
    evaluated = [s.measured for s in results if s.measured is not None]
    reason = None if status != "not_evaluable" else next(
        (x.reason for x in results if x.reason), "no_data"
    )
    bound_result = BoundResult(bound, status, max(evaluated) if evaluated else None, limit, reason)
    return ThresholdOutcome("segments", status, (bound_result,), tuple(results))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_evaluate_threshold_segments.py tests/test_evaluate_threshold.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git -C nthlayer-common add -A src/nthlayer_common/manifest/evaluation.py tests/test_evaluate_threshold_segments.py
git -C nthlayer-common commit -m "feat(manifest): evaluate segments thresholds per segment (opensrm-g32d)"
```

### Task 6: Public API, assessment kind, docs

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/__init__.py` (imports + `__all__`)
- Modify: `nthlayer-common/src/nthlayer_common/cloudevents.py:35-48` (`ASSESSMENT_KINDS`)
- Modify: `nthlayer-common/docs/upgrading-5.0.md`, `nthlayer-common/docs/architecture.md`, `nthlayer-common/CLAUDE.md` (hard rule 1 thresholds bullet)
- Test: `nthlayer-common/tests/test_threshold_evaluation_public.py`

**Interfaces:**
- Produces: public names `evaluate_threshold`, `ThresholdOutcome`, `BoundResult`, `SegmentResult`, `Samples`, `Missing`, `THRESHOLD_SERIES`, `ThresholdSeries`, `FEEDBACK_LATENCY_WINDOW` from `nthlayer_common.manifest`; `"judgment_threshold_evaluation" in ASSESSMENT_KINDS`.

- [ ] **Step 1: Write the failing tests**

```python
import nthlayer_common.manifest as manifest
from nthlayer_common.cloudevents import ASSESSMENT_KINDS, _ce_type_for_assessment

_PUBLIC = ["evaluate_threshold", "ThresholdOutcome", "BoundResult", "SegmentResult",
           "Samples", "Missing", "THRESHOLD_SERIES", "ThresholdSeries", "FEEDBACK_LATENCY_WINDOW"]


def test_evaluation_api_is_public():
    for name in _PUBLIC:
        assert name in manifest.__all__, name
        assert hasattr(manifest, name), name


def test_assessment_kind_is_canonical():
    assert "judgment_threshold_evaluation" in ASSESSMENT_KINDS
    assert _ce_type_for_assessment("judgment_threshold_evaluation") == (
        "io.nthlayer.assessment.judgment_threshold_evaluation.v1"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_threshold_evaluation_public.py`
Expected: FAIL

- [ ] **Step 3: Implement**
  - In `manifest/__init__.py` add
    `from nthlayer_common.manifest.evaluation import BoundResult, Missing, Samples, SegmentResult, ThresholdOutcome, evaluate_threshold`
    and `from nthlayer_common.manifest.threshold_series import FEEDBACK_LATENCY_WINDOW, THRESHOLD_SERIES, ThresholdSeries`, and add all nine names to `__all__` (keep its existing ordering style).
  - In `cloudevents.py` add `"judgment_threshold_evaluation",` to `ASSESSMENT_KINDS` directly after `"judgment_slo_evaluation",`.
  - `docs/upgrading-5.0.md`: add a "**New in 5.2.0:**" bullet to "What consumers must change": evaluate thresholds with `evaluate_threshold(threshold, Samples(...))` (pure; consumers supply measurements per `THRESHOLD_SERIES`), emit `ThresholdOutcome.to_dict()` as a `judgment_threshold_evaluation` assessment.
  - `docs/architecture.md` and `CLAUDE.md` hard rule 1: name `manifest/evaluation.py` (E1–E4) and `manifest/threshold_series.py` (metric contract) beside `manifest/thresholds.py`.

- [ ] **Step 4: Run the full suite and lint**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= ; uv run ruff check src/ tests/; echo ruff=$?`
Expected: all passed (7 xfailed as before), `ruff=0`

- [ ] **Step 5: Commit**

```bash
git -C nthlayer-common add -A src tests docs CLAUDE.md
git -C nthlayer-common commit -m "feat(manifest): public threshold evaluation API and judgment_threshold_evaluation assessment kind (opensrm-g32d)"
```

**Checkpoint B:** R5-gate nthlayer-common (base = branch point, head = Task 6 commit). Push, open PR, hold. On approval: merge with the default "Merge pull request" subject (a typed PR title duplicates the changelog entry), check release notes, release **5.2.0**, verify on PyPI. Only then start Phase C.

---

## Phase C — nthlayer-workers major (sibling worktree via `.claude/bin/eco-worktree.sh nthlayer-workers g32d-thresholds`)

### Task 7: Pin nthlayer-common 5.2 and relock

**Files:**
- Modify: `nthlayer-workers/pyproject.toml:50` (pin + WHY comment above it)
- Modify: `nthlayer-workers/uv.lock` (relock)
- Modify: `nthlayer-workers/tests/test_dependency_declarations.py` (port the exact-ceiling guard)

**Interfaces:**
- Produces: workers resolving `nthlayer-common` 5.2.x.

- [ ] **Step 1: Record the red baseline**

Run: `cd nthlayer-workers && git status --short && uv run pytest -q -o addopts= 2>&1 | tail -3`
Expected: `uv.lock` may already show the sibling relock; 4 failed (2 in `tests/test_dependency_declarations.py`, `test_a_calibration_slo_is_loaded_and_evaluated`, `test_a_miscalibrated_service_breaches`). Tasks 7–8 fix all four.

- [ ] **Step 2: Port the exact-ceiling guard** — append `test_declared_ceiling_is_exactly_the_next_major` verbatim from `nthlayer-core/tests/test_dependency_declarations.py` (the block starting `@pytest.mark.parametrize("name", SIBLINGS)` above that function). Its docstring's example must read "`<N+2.0.0` while N.x is under test" (major-agnostic).

- [ ] **Step 3: Change the pin** to `"nthlayer-common>=5.2.0,<6.0.0",` and add above it:

```toml
    # WHY 5.2.0 (opensrm-g32d): judgment thresholds are evaluated with
    # nthlayer-common's evaluate_threshold (CORE §5.5.6) and read from core 3.0's
    # /manifests via threshold_from_v2_entry; error magnitudes are no longer
    # SLOs (decision 3c, common 4.0/5.0). See nthlayer-common/docs/upgrading-5.0.md.
```

- [ ] **Step 4: Relock and run the dependency guards**

Run: `cd nthlayer-workers && uv lock && uv run pytest -q -o addopts= tests/test_dependency_declarations.py`
Expected: all passed. `git diff uv.lock` touches only nthlayer-common (and the self-version line).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_dependency_declarations.py
git commit -m "deps!: require nthlayer-common 5.2.0 (opensrm-g32d)

BREAKING CHANGE: nthlayer-common 4.0/5.0 moved judgment error magnitudes out of
SLOs; a v2 manifest declaring calibration, segments or stability under
judgment_slo now fails to load in the CLI path. Declare them under
spec.judgment_threshold. See nthlayer-common/docs/upgrading-5.0.md."
```

### Task 8: Remove the SLO-path error-magnitude branches

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/adapters/prometheus.py` (`_JUDGMENT_SLO_QUERIES`, `_JUDGMENT_QUERY_KINDS` around lines 184-215; any `judgment_duration` breach branch)
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/worker.py:381-461` (`classify_severity`)
- Modify: `nthlayer-workers/tests/measure/test_prometheus.py` (~840-1095), `nthlayer-workers/tests/measure/test_measure_worker.py` (~451-520)

**Interfaces:**
- Produces: `classify_severity(judgment_type, target, current_value)` handles only the five judgment SLO types (budget consumption) and unknown → `"high"`.

- [ ] **Step 1: Write the replacement tests (failing)** in `tests/measure/test_prometheus.py`, replacing `test_a_calibration_slo_is_loaded_and_evaluated`, `test_a_miscalibrated_service_breaches` (strict xfail) and `test_feedback_latency_cannot_reach_its_own_branch` (strict xfail):

```python
def test_error_magnitudes_have_no_slo_query():
    from nthlayer_workers.measure.adapters.prometheus import _JUDGMENT_QUERY_KINDS, _JUDGMENT_SLO_QUERIES

    for t in ("calibration", "feedback_latency", "segments", "stability", "audit_backlog"):
        assert t not in _JUDGMENT_SLO_QUERIES, t
        assert t not in _JUDGMENT_QUERY_KINDS, t


def test_a_calibration_judgment_slo_is_a_load_failure(tmp_path):
    """Error magnitudes are thresholds now (decision 3c): a v2 manifest that
    still declares calibration under judgment_slo fails to load, so it can
    never reach SLO breach code."""
    (tmp_path / "m.yaml").write_text(_CALIBRATION_MANIFEST)
    loaded = load_specs(tmp_path)
    assert loaded.slos == []
    assert len(loaded.parse_failures) == 1
```

Use the module's existing `_CALIBRATION_MANIFEST` fixture and its existing `load_specs` import; if `load_specs` returns a different structure, assert on its actual fields for "no SLOs" and "one parse failure" (read `observe/slo/spec_loader.py` / `measure/adapters/prometheus.py:87`).

In `tests/measure/test_measure_worker.py`, replace the stability / segments / calibration `classify_severity` tests with:

```python
@pytest.mark.parametrize("t", ["stability", "segments", "calibration"])
def test_error_magnitudes_are_not_slo_severity_types(t):
    # Thresholds have their own fixed severity (high) in the threshold phase;
    # classify_severity only knows the five judgment SLO types.
    assert classify_severity(t, 0.05, 0.5) == "high"  # the unknown-type fallback
```

- [ ] **Step 2: Run to verify the new query test fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/test_prometheus.py -k "no_slo_query or load_failure"`
Expected: `test_error_magnitudes_have_no_slo_query` FAILS (calibration still present)

- [ ] **Step 3: Implement**
  - Delete the `"calibration"` and `"feedback_latency"` entries from `_JUDGMENT_SLO_QUERIES` and `_JUDGMENT_QUERY_KINDS`, the comment block about `feedback_latency` being unreachable, and any breach branch for query kind `"judgment_duration"` that is now unreachable (and `_target_seconds` if only that branch used it).
  - In `measure/worker.py` delete the `stability`, `segments` and `calibration` branches of `classify_severity` and the functions `_classify_variance` and `_classify_calibration`.

- [ ] **Step 4: Run the full suite and lint**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= ; uv run ruff check src/ tests/; echo ruff=$?`
Expected: 0 failed; `ruff=0`

- [ ] **Step 5: Commit**

```bash
git add -A src tests
git commit -m "fix(measure): error magnitudes never reach SLO breach code (opensrm-g32d)"
```

### Task 9: Threshold sampler

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/measure/thresholds/__init__.py` (empty docstring module)
- Create: `nthlayer-workers/src/nthlayer_workers/measure/thresholds/sampler.py`
- Test: `nthlayer-workers/tests/measure/thresholds/test_sampler.py` (+ empty `__init__.py` if the test tree uses packages)

**Interfaces:**
- Consumes: `THRESHOLD_SERIES`, `FEEDBACK_LATENCY_WINDOW`, `Samples`, `Missing`, `JudgmentThreshold`, `duration_seconds` from `nthlayer_common.manifest`; `PrometheusProvider.query(query: str) -> dict` (raises `PrometheusProviderError` / httpx errors).
- Produces: `async def sample(provider, service: str, threshold: JudgmentThreshold, *, now: float | None = None) -> Samples`. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
"""Threshold sampler: Prometheus responses -> Samples (opensrm-g32d).

These tests feed realistic Prometheus response JSON and assert which bound
each value lands on - not just the query string (the gap that hid g32d)."""

from unittest.mock import AsyncMock

import pytest
from nthlayer_common.manifest import JudgmentThreshold, Missing, ThresholdMeasurement
from nthlayer_common.manifest.models import ProbeConfig

from nthlayer_workers.measure.thresholds.sampler import sample

NOW = 1_800_000_000.0
DAY = 86400.0


def _vector(value):
    return {"status": "success", "data": {"resultType": "vector",
            "result": [{"metric": {}, "value": [NOW, str(value)]}]}}


_EMPTY = {"status": "success", "data": {"resultType": "vector", "result": []}}


def _provider(responses):
    """responses: list of (substring, response) — the first whose substring
    occurs in the query answers it."""
    async def query(q, time=None):
        for needle, resp in responses:
            if needle in q:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return _EMPTY
    p = AsyncMock()
    p.query = AsyncMock(side_effect=query)
    return p


def _cal(**bounds):
    return JudgmentThreshold("calibration", dict(bounds), ThresholdMeasurement(bins=10, window="30d"))


async def test_ece_and_brier_land_on_their_own_bounds():
    p = _provider([("gen_ai_calibration_ece", _vector(0.2)), ("gen_ai_calibration_brier", _vector(0.03))])
    s = await sample(p, "svc", _cal(maximum_expected_calibration_error=0.05, maximum_brier_score=0.1), now=NOW)
    assert s.bounds == {"maximum_expected_calibration_error": 0.2, "maximum_brier_score": 0.03}


async def test_calibration_query_selects_declared_bins_and_window():
    p = _provider([])
    await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    q = p.query.await_args.args[0]
    assert 'service="svc"' in q and 'bins="10"' in q and 'window="30d"' in q


async def test_mismatched_bins_label_is_no_data():
    # Prometheus has a series only for bins=15; the label matcher for bins=10
    # returns an empty vector.
    p = _provider([('bins="15"', _vector(0.9))])
    s = await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    assert s.bounds["maximum_brier_score"] == Missing("no_data", s.bounds["maximum_brier_score"].detail)


def _lat():
    return JudgmentThreshold("feedback_latency", {"maximum_p50": "1h", "maximum_p90": "1d"})


def _retention(start):
    # Prometheus's own oldest-sample timestamp (seconds).
    return ("prometheus_tsdb_lowest_timestamp_seconds", _vector(start))


async def test_latency_quantiles_land_on_p50_and_p90():
    p = _provider([_retention(NOW - 31 * DAY), ("histogram_quantile(0.5", _vector(1200)),
                   ("histogram_quantile(0.9", _vector(50000))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 1200.0, "maximum_p90": 50000.0}


async def test_nan_quantile_is_no_data():
    p = _provider([_retention(NOW - 31 * DAY), ("histogram_quantile", _vector("NaN"))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert all(isinstance(v, Missing) and v.reason == "no_data" for v in s.bounds.values())


async def test_short_retention_is_insufficient_window():
    # Prometheus keeps only 3 days: it cannot see the 30-day window.
    p = _provider([_retention(NOW - 3 * DAY), ("histogram_quantile", _vector(10))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert {v.reason for v in s.bounds.values()} == {"insufficient_window"}


async def test_young_series_is_measured():
    # CORE §5.5.5: p50/p90 over ground truth that ARRIVED in the last 30 days.
    # A service that started 3 days ago has exactly that quantity; only a
    # Prometheus that cannot see 30 days back makes it unmeasurable.
    p = _provider([_retention(NOW - 90 * DAY), ("histogram_quantile(0.5", _vector(10)),
                   ("histogram_quantile(0.9", _vector(20))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 10.0, "maximum_p90": 20.0}


async def test_unknown_retention_still_measures():
    # prometheus_tsdb_lowest_timestamp_seconds not scraped: retention unknown,
    # so measure what Prometheus returns rather than hide the bound.
    p = _provider([("histogram_quantile(0.5", _vector(10)), ("histogram_quantile(0.9", _vector(20))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 10.0, "maximum_p90": 20.0}


async def test_quantile_is_aggregated_across_instances():
    p = _provider([])
    await sample(p, "svc", _lat(), now=NOW)
    qs = [c.args[0] for c in p.query.await_args_list]
    assert any(q.startswith("histogram_quantile(0.5, sum by (le)") for q in qs)


async def test_prometheus_error_is_no_data_and_does_not_raise():
    p = _provider([("", RuntimeError("connection refused"))])
    s = await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    v = s.bounds["maximum_brier_score"]
    assert v.reason == "no_data" and "connection refused" in v.detail


@pytest.mark.parametrize("t,bounds,measurement", [
    ("segments", {"maximum_variance_from_overall": 0.05},
     ThresholdMeasurement(metric="escalation", segment_dimension="region", segment_values=["eu"], window="30d")),
    ("audit_backlog", {"maximum_age": "24h"}, ThresholdMeasurement()),
])
async def test_unsourced_types_are_no_data_source(t, bounds, measurement):
    p = _provider([])
    s = await sample(p, "svc", JudgmentThreshold(t, bounds, measurement), now=NOW)
    if t == "segments":
        assert s.overall.reason == "no_data_source"
    else:
        assert {v.reason for v in s.bounds.values()} == {"no_data_source"}
    p.query.assert_not_awaited()
```

Add a stability case to the parametrize list: `("stability", {"maximum_drift": 0.02}, ThresholdMeasurement(probe=ProbeConfig("s3://p", "daily")))`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_sampler.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Prometheus sampler for judgment thresholds (opensrm-g32d).

Builds queries from nthlayer_common's THRESHOLD_SERIES and maps each result to
the bound it measures. Never computes spec semantics (the evaluator does) and
never raises: any failure becomes a Missing sample (CORE §5.5.6 E3).
"""

from __future__ import annotations

import math
import time as _time
from typing import Any

from nthlayer_common.manifest import (
    FEEDBACK_LATENCY_WINDOW,
    THRESHOLD_SERIES,
    JudgmentThreshold,
    Missing,
    Samples,
    ThresholdSeries,
    duration_seconds,
)

# CORE §5.5.5 defines p50/p90 over ground truth that arrived in the last 30
# days, so a young series is measurable. Only a Prometheus whose retention is
# shorter than the window cannot see it: that is insufficient_window. Unknown
# retention (Prometheus not scraping itself) measures what it can.
_RETENTION_QUERY = "min(prometheus_tsdb_lowest_timestamp_seconds)"
_RETENTION_SLACK_SECONDS = 3600.0


def _scalar(resp: dict[str, Any]) -> float | None:
    result = resp.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _gauge_query(s: ThresholdSeries, service: str, t: JudgmentThreshold) -> str:
    m = t.measurement
    values = {"service": service, "bins": str(m.bins), "window": str(m.window)}
    matchers = ",".join(f'{label}="{values[label]}"' for label in s.labels)
    return f"max({s.metric}{{{matchers}}})"


def _quantile_query(s: ThresholdSeries, service: str) -> str:
    return (
        f"histogram_quantile({s.quantile}, sum by (le) "
        f'(increase({s.metric}_bucket{{service="{service}"}}[{FEEDBACK_LATENCY_WINDOW}])))'
    )


async def _value(provider: Any, query: str) -> float | Missing:
    try:
        v = _scalar(await provider.query(query))
    except Exception as exc:  # noqa: BLE001 - a sampler never raises (E3)
        return Missing("no_data", f"{type(exc).__name__}: {exc}")
    if v is None or not math.isfinite(v):
        return Missing("no_data", "no series" if v is None else "non-finite value")
    return v


async def sample(
    provider: Any, service: str, threshold: JudgmentThreshold, *, now: float | None = None
) -> Samples:
    """The raw measurements for *threshold* on *service*. Never raises."""
    series = THRESHOLD_SERIES.get(threshold.type, {})
    if threshold.type == "segments":
        return Samples(overall=Missing("no_data_source", "no segments series yet"))
    if not series:
        return Samples(bounds={b: Missing("no_data_source", f"no {threshold.type} series yet")
                               for b in threshold.bounds})
    now = _time.time() if now is None else now
    out: dict[str, float | Missing] = {}
    retention: float | Missing | None = None  # queried once, on first histogram bound
    for bound in threshold.bounds:
        s = series.get(bound)
        if s is None:
            out[bound] = Missing("no_data_source", f"no series for {bound}")
            continue
        if s.kind == "gauge":
            out[bound] = await _value(provider, _gauge_query(s, service, threshold))
            continue
        if retention is None:
            retention = await _value(provider, _RETENTION_QUERY)
        window = duration_seconds(FEEDBACK_LATENCY_WINDOW)
        if not isinstance(retention, Missing) and now - retention < window - _RETENTION_SLACK_SECONDS:
            out[bound] = Missing("insufficient_window",
                                 f"Prometheus retention starts {(now - retention) / 86400:.1f}d ago")
            continue
        out[bound] = await _value(provider, _quantile_query(s, service))
    return Samples(bounds=out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_sampler.py; uv run ruff check src/ tests/; echo ruff=$?`
Expected: all passed, `ruff=0`

- [ ] **Step 5: Commit**

```bash
git add -A src/nthlayer_workers/measure/thresholds tests/measure/thresholds
git commit -m "feat(measure): Prometheus sampler for judgment thresholds (opensrm-g32d)"
```

### Task 10: Threshold identity and per-key state machine

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/measure/thresholds/state.py`
- Test: `nthlayer-workers/tests/measure/thresholds/test_state.py`

**Interfaces:**
- Produces:
  - `REARM_WITHIN_CYCLES = 3`
  - `threshold_key(service: str, t: JudgmentThreshold) -> str`
  - `@dataclass KeyState(last_evaluable: str | None = None, armed: bool = True, within_streak: int = 0)` with `to_dict()` / `from_dict()`
  - `advance(state: KeyState, status: str) -> tuple[KeyState, bool]` — returns the new state and whether a `quality_breach` fires.

- [ ] **Step 1: Write the failing tests**

```python
from nthlayer_common.manifest import JudgmentThreshold, ThresholdMeasurement

from nthlayer_workers.measure.thresholds.state import (
    REARM_WITHIN_CYCLES,
    KeyState,
    advance,
    threshold_key,
)


def _seg(values, limit=0.05):
    return JudgmentThreshold("segments", {"maximum_variance_from_overall": limit},
                             ThresholdMeasurement(metric="escalation", segment_dimension="region",
                                                  segment_values=list(values), window="30d"))


def test_key_is_service_type_and_hash():
    k = threshold_key("svc", _seg(["eu", "us"]))
    svc, typ, digest = k.split(":")
    assert (svc, typ, len(digest)) == ("svc", "segments", 12)


def test_segment_order_and_bounds_do_not_change_the_key():
    assert threshold_key("svc", _seg(["eu", "us"])) == threshold_key("svc", _seg(["us", "eu"], limit=0.2))


def test_identifying_fields_change_the_key():
    assert threshold_key("svc", _seg(["eu"])) != threshold_key("svc", _seg(["us"]))
    assert threshold_key("a", _seg(["eu"])) != threshold_key("b", _seg(["eu"]))


def test_identical_entries_share_a_key():
    assert threshold_key("svc", _seg(["eu"])) == threshold_key("svc", _seg(["eu"]))


def test_entries_bounding_different_quantiles_get_different_keys():
    # CORE §5.5: several entries of one type are allowed; a p50 entry and a
    # p90 entry must both be evaluated.
    p50 = JudgmentThreshold("feedback_latency", {"maximum_p50": "1h"})
    p90 = JudgmentThreshold("feedback_latency", {"maximum_p90": "1d"})
    assert threshold_key("svc", p50) != threshold_key("svc", p90)


def test_metric_parameters_change_the_key():
    a = JudgmentThreshold("segments", {"maximum_variance_from_overall": 0.05},
                          ThresholdMeasurement(metric="reversal_rate", source="lineage", segment_dimension="r",
                                               segment_values=["eu"], window="30d"))
    b = JudgmentThreshold("segments", {"maximum_variance_from_overall": 0.05},
                          ThresholdMeasurement(metric="reversal_rate", source="downstream_signal",
                                               segment_dimension="r", segment_values=["eu"], window="30d"))
    assert threshold_key("svc", a) != threshold_key("svc", b)


def _run(statuses):
    st, fired = KeyState(), []
    for s in statuses:
        st, f = advance(st, s)
        fired.append(f)
    return fired


def test_first_breach_fires_once():
    assert _run(["breach", "breach"]) == [True, False]


def test_not_evaluable_gap_does_not_refire():
    assert _run(["breach", "not_evaluable", "breach"]) == [True, False, False]


def test_flapping_does_not_refire_until_rearmed():
    assert _run(["breach", "within", "breach", "within", "within", "within", "breach"]) == [
        True, False, False, False, False, False, True]
    assert REARM_WITHIN_CYCLES == 3


def test_not_evaluable_alone_never_fires():
    assert _run(["not_evaluable", "not_evaluable"]) == [False, False]


def test_within_then_breach_fires():
    assert _run(["within", "breach"]) == [False, True]


def test_state_round_trip():
    st, _ = advance(KeyState(), "breach")
    assert KeyState.from_dict(st.to_dict()) == st
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_state.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Identity and breach-transition state for judgment thresholds (opensrm-g32d)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from nthlayer_common.manifest import JudgmentThreshold

# Re-arm after this many consecutive within cycles following a breach (the
# CLI path's 3-window hysteresis). Tuning belongs to ratchet configuration.
REARM_WITHIN_CYCLES = 3


def threshold_key(service: str, t: JudgmentThreshold) -> str:
    """service:type:hash of what identifies the entry: its measurement fields,
    the metric's parameters, and the NAMES of its bounds. Bound VALUES are
    excluded, so tightening a bound keeps the key; segment order is irrelevant.
    Two entries can still share a key (same names, different values): the
    phase deduplicates identical entries and gives the rest an ordinal."""
    m = t.measurement
    signal = m.outcome_signal
    ident = {
        "bounds": sorted(t.bounds),
        "metric": m.metric,
        "source": m.source,
        "confidence_threshold": m.confidence_threshold,
        "outcome_signal": [signal.source, signal.window] if signal else None,
        "segment_dimension": m.segment_dimension,
        "segment_values": sorted(m.segment_values),
        "probe": [m.probe.frozen_input_set, m.probe.frequency] if m.probe else None,
        "window": m.window,
        "bins": m.bins,
    }
    digest = hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:12]
    return f"{service}:{t.type}:{digest}"


@dataclass
class KeyState:
    last_evaluable: str | None = None  # last "within" or "breach"; not_evaluable never sets it
    armed: bool = True
    within_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KeyState:
        return cls(**{k: d[k] for k in ("last_evaluable", "armed", "within_streak") if k in d})


def advance(state: KeyState, status: str) -> tuple[KeyState, bool]:
    """Apply one cycle's combined status. Returns (new state, fire a breach?)."""
    if status == "not_evaluable":
        return state, False
    if status == "within":
        streak = state.within_streak + 1
        armed = state.armed or streak >= REARM_WITHIN_CYCLES
        return KeyState("within", armed, streak), False
    # breach
    fire = state.armed and state.last_evaluable != "breach"
    return KeyState("breach", state.armed and not fire, 0), fire
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_state.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add -A src/nthlayer_workers/measure/thresholds/state.py tests/measure/thresholds/test_state.py
git commit -m "feat(measure): threshold identity key and breach re-arm state (opensrm-g32d)"
```

### Task 11: Threshold phase in `MeasureModule.process_cycle`

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/measure/thresholds/phase.py`
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/worker.py` (`__post_init__`, `restore_state`, `process_cycle`, `get_state`)
- Modify: `nthlayer-workers/.github/workflows/test.yml` (check out opensrm as a sibling)
- Test: `nthlayer-workers/tests/measure/thresholds/test_phase.py`

**Interfaces:**
- Consumes: `sample` (Task 9), `threshold_key`, `KeyState`, `advance` (Task 10), `evaluate_threshold`, `threshold_from_v2_entry`, `OpenSRMV2ParseError` from `nthlayer_common.manifest`, `wrap_assessment`, `wrap_verdict` from `nthlayer_common.cloudevents`.
- Produces: `async def run_threshold_phase(*, client, provider, manifests: list[dict], state: dict[str, dict], seen_problems: set[str]) -> list[tuple[str, str, str]]` — mutates `state` (key → `KeyState.to_dict()`), returns new breaches as `(key, service, breach_verdict_id)`. `MeasureModule` gains state key `threshold_state` (and `threshold_problems`, the once-per-change log memory).

- [ ] **Step 1: Write the failing tests** (pattern: `tests/measure/test_measure_worker.py` — `AsyncMock` client, patched `PrometheusProvider`)

```python
"""Threshold phase of MeasureModule (opensrm-g32d)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from nthlayer_common.api_client import APIResult
from nthlayer_common.manifest import threshold_from_v2_entry, threshold_to_v2_entry

from nthlayer_workers.measure.worker import MeasureModule

_CAL = {"type": "calibration", "measurement": {"bins": 10, "window": "30d"},
        "bounds": {"maximum_expected_calibration_error": 0.05}}


def _manifests(*services):
    return APIResult(ok=True, status_code=200, data=[
        {"name": name, "type": "ai-gate", "slos": [], "judgment_thresholds": entries}
        for name, entries in services
    ])


def _vector(v):
    return {"status": "success", "data": {"result": [{"metric": {}, "value": [0, str(v)]}]}}


def _module(prom_values, manifests):
    """prom_values: list of ECE values returned on successive cycles."""
    client = AsyncMock()
    client.get_manifests = AsyncMock(side_effect=manifests if isinstance(manifests, list) else None,
                                     return_value=None if isinstance(manifests, list) else manifests)
    assessments, verdicts = [], []
    client.submit_assessment = AsyncMock(side_effect=lambda a: (assessments.append(a["data"]),
                                         APIResult(ok=True, status_code=201, data={}))[1])
    client.submit_verdict = AsyncMock(side_effect=lambda v: (verdicts.append(v["data"]),
                                      APIResult(ok=True, status_code=201, data={}))[1])
    prov = AsyncMock()
    prov.query = AsyncMock(side_effect=[_vector(v) for v in prom_values])
    prov.aclose = AsyncMock()
    return MeasureModule(client=client, prometheus_url="http://prom:9090"), prov, assessments, verdicts


def _breaches(verdicts):
    return [v for v in verdicts if v.get("type") == "quality_breach"]


async def _cycles(module, prov, n):
    with patch("nthlayer_workers.measure.worker.PrometheusProvider", return_value=prov):
        for _ in range(n):
            await module.process_cycle()


async def test_breach_emits_assessment_and_one_high_verdict():
    m, prov, a, v = _module([0.2, 0.2], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 2)
    evals = [x for x in a if x["kind"] == "judgment_threshold_evaluation"]
    assert len(evals) == 2 and evals[0]["data"]["outcome"]["status"] == "breach"
    assert len(_breaches(v)) == 1
    assert _breaches(v)[0]["data"]["severity"] == "high"
    assert _breaches(v)[0]["parent_ids"] == [evals[0]["id"]]


async def test_high_ece_breaches_only_the_ece_bound():
    entry = dict(_CAL, bounds={"maximum_expected_calibration_error": 0.05, "maximum_brier_score": 0.5})
    m, prov, a, v = _module([0.2, 0.01], _manifests(("svc", [entry])))  # ECE then Brier
    await _cycles(m, prov, 1)
    bounds = {b["bound"]: b["status"] for b in a[0]["data"]["outcome"]["bounds"]}
    assert bounds == {"maximum_expected_calibration_error": "breach", "maximum_brier_score": "within"}


async def test_not_evaluable_is_reported_but_never_breaches():
    entry = {"type": "audit_backlog", "bounds": {"maximum_age": "24h"}}
    m, prov, a, v = _module([], _manifests(("svc", [entry])))
    await _cycles(m, prov, 1)
    assert a[0]["data"]["outcome"]["status"] == "not_evaluable"
    assert a[0]["data"]["outcome"]["bounds"][0]["reason"] == "no_data_source"
    assert _breaches(v) == []


async def test_same_type_entries_with_different_bounds_are_both_evaluated():
    other = dict(_CAL, bounds={"maximum_expected_calibration_error": 0.2})
    m, prov, a, v = _module([0.1, 0.1], _manifests(("svc", [_CAL, other])))
    await _cycles(m, prov, 1)
    statuses = sorted(x["data"]["outcome"]["status"] for x in a)
    assert statuses == ["breach", "within"]
    assert len({x["data"]["threshold_key"] for x in a}) == 2


async def test_duplicate_entries_emit_once():
    m, prov, a, v = _module([0.2], _manifests(("svc", [_CAL, dict(_CAL)])))
    await _cycles(m, prov, 1)
    assert len([x for x in a if x["kind"] == "judgment_threshold_evaluation"]) == 1


async def test_unparseable_entry_is_isolated():
    m, prov, a, v = _module([0.2], _manifests(("svc", [{"type": "segments"}, _CAL])))
    await _cycles(m, prov, 1)
    assert len(a) == 1 and a[0]["data"]["outcome"]["type"] == "calibration"


async def test_core_unreachable_touches_nothing():
    m, prov, a, v = _module([0.2], APIResult(ok=False, status_code=503, data=None))
    m._threshold_state = {"svc:calibration:abc": {"last_evaluable": "breach", "armed": False, "within_streak": 0}}
    await _cycles(m, prov, 1)
    assert a == [] and v == []
    assert "svc:calibration:abc" in m._threshold_state


async def test_absent_service_keeps_state_and_removed_entry_retires():
    m, prov, a, v = _module([0.2, 0.2], [
        _manifests(("svc", [_CAL]), ("other", [])),
        _manifests(("other", [])),           # svc absent -> keep its state
    ])
    await _cycles(m, prov, 2)
    assert any(k.startswith("svc:") for k in m._threshold_state)
    m2, prov2, *_ = _module([0.2], [_manifests(("svc", [_CAL])), _manifests(("svc", []))])
    await _cycles(m2, prov2, 2)
    assert not any(k.startswith("svc:") for k in m2._threshold_state)


async def test_service_without_thresholds_key_is_ignored():
    data = APIResult(ok=True, status_code=200, data=[{"name": "old", "type": "ai-gate", "slos": []}])
    m, prov, a, v = _module([], data)
    await _cycles(m, prov, 1)
    assert a == [] and v == []


async def test_restart_does_not_refire():
    m, prov, a, v = _module([0.2], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 1)
    saved = await m.get_state()
    m2, prov2, a2, v2 = _module([0.2], _manifests(("svc", [_CAL])))
    await m2.restore_state(saved)
    await _cycles(m2, prov2, 1)
    assert _breaches(v2) == []


_SPEC_V2 = Path(__file__).resolve().parents[4] / "opensrm" / "spec" / "v2"


async def test_served_shape_drives_a_cycle():
    """Exactly what core 3.0 serves: threshold_to_v2_entry of the spec examples."""
    src = _SPEC_V2 / "examples" / "judgment-thresholds" / "all-five-types.yaml"
    assert src.is_file(), src
    served = [threshold_to_v2_entry(t) for t in
              (threshold_from_v2_entry(e)
               for e in yaml.safe_load(src.read_text())["spec"]["judgment_threshold"])]
    m, prov, a, v = _module([0.01] * 10, _manifests(("svc", served)))
    await _cycles(m, prov, 1)
    assert len(a) == len(served)
```

Check the `parents[N]` depth for `tests/measure/thresholds/` against the repo layout (workers is `<eco>/nthlayer-workers/tests/measure/thresholds/test_phase.py` → `parents[4]` is `<eco>`); assert `src.is_file()` so a wrong depth fails loudly.

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_phase.py`
Expected: FAIL (no threshold assessments emitted)

- [ ] **Step 3: Implement `phase.py`**

```python
"""The judgment-threshold phase of the measure cycle (opensrm-g32d)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from nthlayer_common.cloudevents import wrap_assessment, wrap_verdict
from nthlayer_common.manifest import (
    OpenSRMV2ParseError,
    evaluate_threshold,
    threshold_from_v2_entry,
    threshold_to_v2_entry,
)

from nthlayer_workers.measure.thresholds.sampler import sample
from nthlayer_workers.measure.thresholds.state import KeyState, advance, threshold_key

logger = structlog.get_logger()

THRESHOLD_BREACH_SEVERITY = "high"


def _log_once(seen: set[str], token: str, event: str, **kw: Any) -> None:
    if token not in seen:
        seen.add(token)
        logger.warning(event, **kw)


async def run_threshold_phase(
    *, client: Any, provider: Any, manifests: list[dict], state: dict[str, dict],
    seen_problems: set[str],
) -> list[tuple[str, str, str]]:
    """Evaluate every served threshold; mutate *state*; return new breaches as
    (key, service, breach_verdict_id). Caller guarantees *manifests* came from a
    successful /manifests response."""
    new_breaches: list[tuple[str, str, str]] = []
    present_services: set[str] = set()
    live_keys: set[str] = set()
    by_base: dict[str, list[dict]] = {}
    for i, m in enumerate(manifests):
        service = m.get("name")
        if not service:
            continue
        present_services.add(service)
        for j, item in enumerate(m.get("judgment_thresholds") or []):
            where = f"/manifests[{i}].judgment_thresholds[{j}]"
            try:
                t = threshold_from_v2_entry(item, where=where)
            except OpenSRMV2ParseError as exc:
                _log_once(seen_problems, f"parse:{service}:{item!r}", "threshold_parse_failed",
                          service=service, where=where, error=str(exc))
                continue
            base = threshold_key(service, t)
            canonical = threshold_to_v2_entry(t)
            same_base = by_base.setdefault(base, [])
            if canonical in same_base:  # an identical entry: evaluate once
                _log_once(seen_problems, f"dup:{base}", "threshold_duplicate", service=service, key=base)
                continue
            # Same identity but different bound values: a distinct entry, kept
            # apart by its ordinal among such entries (declared order).
            key = base if not same_base else f"{base}#{len(same_base)}"
            same_base.append(canonical)
            live_keys.add(key)
            outcome = evaluate_threshold(t, await sample(provider, service, t))
            assessment_id = f"jte-{service}-{t.type}-{uuid.uuid4().hex[:8]}"
            assessment = {
                "id": assessment_id,
                "created_at": datetime.now(UTC).isoformat(),
                "kind": "judgment_threshold_evaluation",
                "service": service,
                "data": {"threshold_key": key, "outcome": outcome.to_dict()},
            }
            result = await client.submit_assessment(wrap_assessment(assessment, component="measure"))
            if not result.ok:
                logger.warning("threshold_assessment_submit_failed", service=service, key=key)
            new_state, fire = advance(KeyState.from_dict(state.get(key, {})), outcome.status)
            state[key] = {**new_state.to_dict(), "service": service}
            if fire:
                breach_id = f"vrd-tbreach-{service}-{t.type}-{uuid.uuid4().hex[:8]}"
                verdict = {
                    "id": breach_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "type": "quality_breach",
                    "service": service,
                    "parent_ids": [assessment_id],
                    "data": {"threshold_key": key, "threshold_type": t.type,
                             "severity": THRESHOLD_BREACH_SEVERITY, "outcome": outcome.to_dict()},
                }
                await client.submit_verdict(wrap_verdict(verdict, component="measure"))
                new_breaches.append((key, service, breach_id))
    # Retire only keys of services present in this (successful) response.
    for key in [k for k, v in state.items() if v.get("service") in present_services and k not in live_keys]:
        del state[key]
        logger.info("threshold_retired", key=key)
    return new_breaches
```

- [ ] **Step 4: Wire it into `MeasureModule`**
  - `__post_init__`: add `self._threshold_state: dict[str, dict] = {}` and `self._threshold_problems: set[str] = set()`.
  - `restore_state`: `self._threshold_state = state.get("threshold_state", {})`.
  - `get_state`: add `"threshold_state": self._threshold_state`.
  - `process_cycle`: after the existing Phase 1 SLO evaluation (still inside the `try`, before Phase 3 governance), add:

```python
            # Threshold phase (opensrm-g32d): manifests is from a successful response.
            threshold_breaches = await run_threshold_phase(
                client=self.client, provider=provider, manifests=manifests,
                state=self._threshold_state, seen_problems=self._threshold_problems,
            )
```

  and import `run_threshold_phase` from `nthlayer_workers.measure.thresholds.phase`. The early `return` on `not result.ok` already guarantees "core unreachable touches nothing"; change `if not result.ok or not result.data:` only if `[]` must still retire state (it should not: an empty list is treated as "no services present", so leave the early return).

- [ ] **Step 4b: Let CI see the spec.** `test_served_shape_drives_a_cycle` reads `../opensrm`, which workers CI does not check out today. In `.github/workflows/test.yml`, after "Checkout nthlayer-common (sibling)", add:

```yaml
      # The served-shape test reads the spec's examples from ../opensrm
      # (opensrm-g32d). Floats on opensrm main, like nthlayer-common's CI:
      # a spec commit can turn this red with no change here.
      - name: Checkout opensrm (sibling, for spec examples)
        uses: actions/checkout@v7
        with:
          repository: rsionnach/opensrm
          path: opensrm
```

- [ ] **Step 5: Run the phase tests, the full suite, and lint**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= ; uv run ruff check src/ tests/; echo ruff=$?`
Expected: 0 failed, `ruff=0`

- [ ] **Step 6: Commit**

```bash
git add -A src/nthlayer_workers/measure tests/measure/thresholds
git commit -m "feat(measure): evaluate judgment thresholds each cycle (opensrm-g32d)"
```

### Task 12: Operator toggle — threshold breaches feed the autonomy ratchet

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/worker.py` (field + Phase 3)
- Test: `nthlayer-workers/tests/measure/thresholds/test_autonomy_toggle.py`

**Interfaces:**
- Consumes: `threshold_breaches` from Task 11.
- Produces: `MeasureModule.threshold_autonomy: bool` (default from `MEASURE_THRESHOLD_AUTONOMY`); when true, each new threshold breach enters Phase 3 governance as a breaching key with severity `"high"`.

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import AsyncMock, patch

import pytest
from nthlayer_common.api_client import APIResult

from nthlayer_workers.measure.worker import MeasureModule

_CAL = {"type": "calibration", "measurement": {"bins": 10, "window": "30d"},
        "bounds": {"maximum_expected_calibration_error": 0.05}}


def _setup(monkeypatch, env):
    if env is None:
        monkeypatch.delenv("MEASURE_THRESHOLD_AUTONOMY", raising=False)
    else:
        monkeypatch.setenv("MEASURE_THRESHOLD_AUTONOMY", env)
    client = AsyncMock()
    client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "slos": [], "judgment_thresholds": [_CAL]}]))
    client.submit_assessment = AsyncMock(return_value=APIResult(ok=True, status_code=201, data={}))
    verdicts = []
    client.submit_verdict = AsyncMock(side_effect=lambda v: (verdicts.append(v["data"]),
                                      APIResult(ok=True, status_code=201, data={}))[1])
    prov = AsyncMock()
    prov.query = AsyncMock(return_value={"data": {"result": [{"value": [0, "0.2"]}]}})
    prov.aclose = AsyncMock()
    return MeasureModule(client=client, prometheus_url="http://p"), prov, verdicts


async def _cycle(m, prov):
    with patch("nthlayer_workers.measure.worker.PrometheusProvider", return_value=prov):
        await m.process_cycle()


@pytest.mark.parametrize("env", [None, "", "0", "false", "off"])
async def test_off_by_default_no_ratchet(monkeypatch, env):
    m, prov, verdicts = _setup(monkeypatch, env)
    await _cycle(m, prov)
    assert [v for v in verdicts if v["type"] == "autonomy_change"] == []
    assert m._autonomy_levels.get("svc", "fully_autonomous") == "fully_autonomous"


@pytest.mark.parametrize("env", ["1", "true", "YES", "on"])
async def test_on_feeds_the_ratchet_as_a_high_breach(monkeypatch, env):
    m, prov, verdicts = _setup(monkeypatch, env)
    await _cycle(m, prov)
    changes = [v for v in verdicts if v["type"] == "autonomy_change"]
    assert len(changes) == 1
    assert m._autonomy_levels["svc"] == "limited_autonomous"  # high single breach: 2 steps


async def test_enabling_later_does_not_ratchet_an_open_breach(monkeypatch):
    m, prov, verdicts = _setup(monkeypatch, None)
    await _cycle(m, prov)
    m.threshold_autonomy = True
    await _cycle(m, prov)
    assert [v for v in verdicts if v["type"] == "autonomy_change"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_autonomy_toggle.py`
Expected: FAIL — `test_on_feeds_the_ratchet_as_a_high_breach`

- [ ] **Step 3: Implement**

```python
def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
```

Add to `MeasureModule`: `threshold_autonomy: bool = field(default_factory=lambda: _env_flag("MEASURE_THRESHOLD_AUTONOMY"))` (import `os`, `field`). In Phase 3, before building `breaching_services`, when `self.threshold_autonomy` is true:

```python
            governed_threshold_keys: list[str] = []
            if self.threshold_autonomy:
                # Open threshold breaches count toward governance every cycle,
                # exactly as an open SLO breach stays in current_status - so a
                # later SLO breach sees "multiple breaches" (spec: same rules).
                for key, st in self._threshold_state.items():
                    if st.get("last_evaluable") == "breach" and self._breach_decisions.get(key):
                        current_status[key] = "breach"
                        governed_threshold_keys.append(key)
                # New threshold breaches this cycle enter as new high breaches.
                for key, _svc, breach_id in threshold_breaches:
                    current_status[key] = "breach"
                    new_breaches.append(key)
                    breach_verdict_ids[key] = breach_id
                    self._breach_severities[key] = "high"
                    governed_threshold_keys.append(key)
```

and after Phase 3 (before the carry-forward loop) remove them from `current_status` so `_slo_status` stays SLO-only:

```python
            for key in governed_threshold_keys:
                current_status.pop(key, None)
```

Threshold keys are `service:type:hash` (three parts), so `key.split(":", 1)[0]` in Phase 3 still yields the service.

Track which governance keys are threshold keys: add `self._threshold_governed: set[str] = set()` in `__post_init__`, persist it in `get_state` as `"threshold_governed": sorted(self._threshold_governed)` and restore it in `restore_state` (`set(state.get("threshold_governed", []))`). Add every key in `governed_threshold_keys` to it. After the existing recovered-SLO cleanup, run the threshold cleanup over THAT SET ONLY (never over all `_breach_decisions` keys, which also hold SLO keys):

```python
            for key in list(self._threshold_governed):
                st = self._threshold_state.get(key)
                if st is None or st.get("last_evaluable") == "within":   # retired or recovered
                    self._breach_decisions.pop(key, None)
                    self._breach_severities.pop(key, None)
                    self._threshold_governed.discard(key)
```

Add to the Step 1 tests:

```python
async def test_open_threshold_breach_counts_in_later_governance(monkeypatch):
    """An open threshold breach plus a later SLO breach is a multiple-breach
    case (advisor floor), as two SLO breaches would be."""
    m, prov, verdicts = _setup(monkeypatch, "1")
    await _cycle(m, prov)                     # threshold breach decided (open)
    # Reset the level so the outcome separates the two behaviours:
    # with re-injection 2 breaches -> advisor floor; without, 1 low breach -> autonomous.
    m._autonomy_levels["svc"] = "fully_autonomous"
    m.client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "judgment_thresholds": [_CAL], "slos": [
            {"name": "rr", "target": 98.5, "judgment_type": "reversal_rate", "window": "30d",
             "indicator_query": "q"}]}]))
    # A mild SLO breach (98.0 < 98.5 target; 33% budget consumption = low), so
    # the advisor floor below comes from the breach COUNT, not from severity.
    prov.get_sli_value = AsyncMock(return_value=0.98)
    await _cycle(m, prov)
    assert m._autonomy_levels["svc"] == "advisor"    # multiple breaches, none critical
    last_change = [v for v in verdicts if v["type"] == "autonomy_change"][-1]
    assert last_change["data"]["breaching_slo_count"] == 2


async def test_open_slo_breach_keeps_its_governance_memory(monkeypatch):
    """Threshold cleanup must touch only threshold keys: an open SLO breach's
    decision survives a cycle with the toggle on."""
    m, prov, verdicts = _setup(monkeypatch, "1")
    m.client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "judgment_thresholds": [], "slos": [
            {"name": "rr", "target": 98.5, "judgment_type": "reversal_rate", "window": "30d",
             "indicator_query": "q"}]}]))
    prov.get_sli_value = AsyncMock(return_value=0.98)
    await _cycle(m, prov)
    await _cycle(m, prov)
    assert m._breach_decisions.get("svc:rr", {}).get("decided")


async def test_retired_threshold_leaves_no_governance_memory(monkeypatch):
    m, prov, verdicts = _setup(monkeypatch, "1")
    await _cycle(m, prov)
    m.client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "slos": [], "judgment_thresholds": []}]))
    await _cycle(m, prov)
    assert not any(":calibration:" in k for k in m._breach_decisions)
    assert not any(":calibration:" in k for k in m._breach_severities)
```

- [ ] **Step 4: Run the toggle tests, full suite, lint**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= ; uv run ruff check src/ tests/; echo ruff=$?`
Expected: 0 failed, `ruff=0`

- [ ] **Step 5: Commit**

```bash
git add -A src tests
git commit -m "feat(measure): MEASURE_THRESHOLD_AUTONOMY lets threshold breaches reduce autonomy (opensrm-g32d)"
```

### Task 13: Docs and hard rule 7

**Files:**
- Modify: `nthlayer-workers/CLAUDE.md` (hard rule 7 and the measure description)
- Create or modify: `nthlayer-workers/docs/upgrading-3.0.md` (or the repo's existing upgrade-notes location; check `ls nthlayer-workers/docs`)

- [ ] **Step 1: Update CLAUDE.md hard rule 7** to state: severity is deterministic, no LLM; the five judgment SLO types use budget consumption; every judgment-threshold breach is `high` (thresholds are not SLOs — decision 3c); threshold breaches reach the autonomy ratchet only with `MEASURE_THRESHOLD_AUTONOMY` on.

- [ ] **Step 2: Write the upgrade note** covering: common 5.2 pin; calibration/segments/stability under `judgment_slo` now fail to load (move them to `spec.judgment_threshold`); thresholds are evaluated from core ≥3.0's `/manifests`; new assessment kind; the `MEASURE_THRESHOLD_AUTONOMY` toggle; the metric contract (link the front door's `docs/metrics-contract.md`).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs
git commit -m "docs: judgment thresholds, upgrade notes and hard rule 7 (opensrm-g32d)"
```

**Checkpoint C:** R5-gate nthlayer-workers (base = branch point, head = Task 13). Push, open PR, hold. On approval: merge with the default merge subject, verify the release PR is a **major** with the BREAKING note, release, verify on PyPI with a clean co-install of common 5.2 + core 3.0 + workers. Close opensrm-g32d; file the out-of-scope beads listed in the spec §2.
