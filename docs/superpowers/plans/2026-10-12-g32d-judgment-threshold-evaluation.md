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
- A lower bound `AtLeast(v)` (the true value is strictly greater than `v`) breaches iff `v >= limit`; otherwise it is `not_evaluable("beyond_top_bucket")`. It is what a histogram quantile in the `+Inf` bucket yields: the sampler computes quantiles from bucket counts itself and never uses PromQL `histogram_quantile`, which reports such a quantile as the largest finite `le` (and so as `within`).
- PromQL label values are always escaped (`\` → `\\`, `"` → `\"`, newline → `\n`) via the sampler's `_label`.
- Operator switch `MEASURE_RETENTION_CHECK` (default ON; `off`/`false`/`0`, case-insensitive, disable it) controls the Prometheus retention check. Like `MEASURE_THRESHOLD_AUTONOMY` it is read once, when `MeasureModule` is constructed.
- One threshold never affects another, and the threshold phase never stops the SLO phases: per-entry and whole-phase exceptions are logged and contained.
- Threshold `quality_breach` severity is the string `"high"` (downstream knows only `low | high | critical`).
- Thresholds run on their own cadence: `MEASURE_THRESHOLD_INTERVAL` seconds (default 900) since the last threshold run; open threshold breaches still reach governance every measure cycle. An assessment is emitted on first sight, when the outcome signature (outcome minus measured values) changes, every `MEASURE_THRESHOLD_HEARTBEAT` seconds (default 3600), and whenever a breach fires. Timing env values must be finite and in (0, 7d]; anything else (not a number, zero, negative, non-finite, over 604800) falls back to the default with a log. Retirement of removed entries runs every measure cycle, threshold run or not.
- Re-arm needs BOTH a duration and a count: a disarmed key re-arms only once its current `within` run is at least `REARM_INTERVALS` (**3**) × the threshold interval old AND holds at least 3 consecutive `within` evaluations; `not_evaluable` neither starts, extends nor ends the run; a run that starts in the future (clock went back) restarts at now.
- Operator toggle env var: `MEASURE_THRESHOLD_AUTONOMY` (truthy: `1`, `true`, `yes`, `on`, case-insensitive), default off.
- Assessment kind string: `judgment_threshold_evaluation`.
- Identity key: `f"{service}:{type}:{sha256(identifying fields)[:12]}"`, identifying fields = sorted bound NAMES, `metric`, `source`, `confidence_threshold`, `outcome_signal`, `segment_dimension`, sorted `segment_values`, `probe` (input set + frequency), measurement `window`, `bins`; bound VALUES excluded. Identical entries evaluate once; when a key has more than one distinct entry in a service, EVERY such entry's key is `f"{key}~{sha256(json.dumps(sorted bound items))[:8]}"` — keys never depend on position, so reordering moves no state.
- Workers worktrees MUST be siblings (`.claude/bin/eco-worktree.sh`), never `claude --worktree` / agent `isolation: worktree`.
- Tests assert structured data (statuses, dataclass fields, dict keys), never captured log text.
- Lint floor is frozen (the ruff `select` set in each repo's `pyproject.toml` is fixed — do not change it and add no per-file ignores or `noqa` beyond those the plan's code shows; nthlayer-workers CLAUDE.md hard rule 12); run `uv run ruff check src/ tests/` and check its exit status (do not pipe it).

## Review Focus

1. A Prometheus series that exists with *other* `bins`/`window` labels → the bound is `not_evaluable("no_data")`, never evaluated against the wrong computation. Pinned in Task 9 (`test_mismatched_bins_label_is_no_data`).
2. A histogram with no observations in the window (or no `+Inf` bucket), or a `NaN` gauge → `not_evaluable("no_data")`, not a float comparison against NaN (which is always False → silently `within`). Pinned in Task 9 (`test_unmeasurable_histogram_is_no_data`, `test_nan_gauge_is_no_data`) and Task 4 (`test_non_finite_sample_is_not_evaluable`).
3. A manifest with two identical threshold entries → evaluated once, one assessment, one verdict; two same-identity entries with different bound values → two `~<digest>` keys that follow their entries when the manifest reorders them. Pinned in Task 10 (`test_identical_entries_share_a_key`, `test_bounds_digest_depends_on_values_not_order`) and Task 11 (`test_duplicate_entries_emit_once`, `test_same_identity_entries_get_value_suffixed_keys`, `test_reordering_same_identity_entries_keeps_each_entrys_state`).
4. A segment value listed twice in `segment_values` → one `SegmentResult`. Pinned in Task 5 (`test_duplicate_segment_value_evaluated_once`).
5. Core returns `/manifests` ok but with a service that has no `judgment_thresholds` key at all (older core) → that service contributes no thresholds and does not crash or retire state of other services. Pinned in Task 11 (`test_service_without_thresholds_key_is_ignored`).
6. A latency quantile beyond the largest finite bucket boundary (rank in the `+Inf` bucket) → a lower bound, never that boundary as a value: buckets `[…, 3600, 86400, +Inf]` with most mass in `+Inf` and a `1d` bound → `breach`; a top boundary below the bound (OTel's default 10000s vs `1d`) → `not_evaluable`. Pinned in Task 9 (`test_latency_beyond_a_1d_top_bucket_breaches_a_1d_bound`, `test_latency_beyond_a_top_bucket_below_the_bound_is_not_evaluable`) and Task 4 (`test_lower_bound_breaches_only_when_it_reaches_the_limit`).
7. A `quality_breach` verdict that core does not accept leaves the key's state unchanged, so the next cycle raises it again. Pinned in Task 11 (`test_failed_breach_verdict_refires_next_cycle`).
8. Corrupt restored state (`threshold_state` of `None`, a non-dict entry, wrong-typed fields) → the cycle runs and SLO breaches are still detected. Pinned in Task 10 (`test_from_dict_tolerates_a_corrupt_or_old_restored_state`) and Task 11 (`test_corrupt_restored_state_does_not_stop_the_cycle`).
9. Cadence and emission: two measure cycles inside the threshold interval run the threshold phase once, yet an open threshold breach still counts in the second cycle's governance; an unchanged outcome is re-emitted only on the heartbeat, a breach that fires always emits the assessment its verdict names. Pinned in Task 11 (`test_the_phase_runs_on_its_own_interval`, `test_unchanged_outcome_is_reemitted_only_on_the_heartbeat`, `test_a_firing_breach_always_emits_its_parent_assessment`) and Task 12 (`test_open_threshold_breach_counts_in_later_governance`).
10. Re-arm needs 3 threshold intervals of `within` AND 3 `within` evaluations: 2 intervals stay disarmed, and so do 2 evaluations far apart. A backward clock delays but never stops re-arming, emitting or running. Pinned in Task 10 (`test_within_for_less_than_the_rearm_duration_does_not_rearm`, `test_rearm_needs_both_the_duration_and_three_within_evaluations`, `test_a_run_starting_in_the_future_restarts_now`) and Task 11 (`test_rearm_is_three_threshold_intervals`, `test_rearm_needs_three_within_evaluations_even_when_far_apart`, `test_a_backward_clock_still_runs_emits_and_rearms`).

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
the source of truth and this section documents it. Each threshold is
evaluated every `MEASURE_THRESHOLD_INTERVAL` seconds (default 900, so the
series are queried at most that often) and the result is emitted as a
`judgment_threshold_evaluation` assessment — including when it is not
evaluable — on first sight, when its status or reasons change, and at least
every `MEASURE_THRESHOLD_HEARTBEAT` seconds (default 3600).

In the queries, `S` is the service name (the manifest's `metadata.name`),
`B` is the threshold's `measurement.bins` and `W` its `measurement.window`.
Label values are the manifest's literal strings (`bins="10"`,
`window="30d"`, not `30 days` or `720h`), escaped for PromQL (`\` → `\\`,
`"` → `\"`, newline → `\n`).

| Threshold | Bound | Series | Labels | Query |
|---|---|---|---|---|
| calibration | `maximum_expected_calibration_error` | `gen_ai_calibration_ece` (gauge) | `service`, `bins`, `window` | `max(gen_ai_calibration_ece{service="S",bins="B",window="W"})` |
| calibration | `maximum_brier_score` | `gen_ai_calibration_brier` (gauge) | `service`, `bins`, `window` | `max(gen_ai_calibration_brier{service="S",bins="B",window="W"})` |
| feedback_latency | `maximum_p50`, `maximum_p90` | `gen_ai_feedback_latency_seconds` (histogram) | `service` | `sum by (le) (increase(gen_ai_feedback_latency_seconds_bucket{service="S"}[30d]))` — one query; p50 and p90 are computed by the sampler from the bucket counts |
| segments, stability, audit_backlog | — | no series yet | — | none sent; evaluated as not evaluable (`no_data_source`) |

A bound that cannot be measured is reported as not evaluable, with one of
these reasons:

- `no_data` — the series is absent, its labels do not match (e.g. other
  `bins`/`window`), the query errored or timed out, the value is not
  finite (`NaN`, `±Inf`), the histogram has no `+Inf` bucket or no
  observations in the window, or the quantile lies beyond the largest finite
  bucket boundary and that boundary is below the bound (see below).
- `insufficient_window` — Prometheus's retention is shorter than the 30-day
  window.
- `no_data_source` — no series is defined for this threshold type yet.

Rules:

- Calibration gauges carry the `bins` and `window` they were computed with.
  The sampler reads only the series whose `bins`/`window` labels equal the
  manifest's `measurement.bins` / `measurement.window`; any other series is
  ignored (`no_data`). Export exactly one series per
  `service`/`bins`/`window`; if several match (e.g. one per instance), the
  query's `max()` takes the worst, a conservative fallback rather than a
  supported shape.
- `gen_ai_feedback_latency_seconds` must be exposed as a Prometheus classic
  histogram, i.e. with `_bucket` (including `le="+Inf"`) and `_count` /
  `_sum` series; the query reads `_bucket`. Prometheus native
  (sparse) histograms have no `_bucket` series and are not supported: the
  bound reads as not evaluable (`no_data`). Expose classic buckets (alone or
  alongside native ones).
- The histogram MUST have a finite bucket boundary strictly greater than
  every declared bound (e.g. a `1d` bound needs a boundary above `86400`;
  OpenTelemetry's default top boundary, `10000`, is not enough). Quantiles
  are computed with Prometheus's classic bucket-interpolation algorithm, with
  one difference: a quantile beyond the largest finite boundary (its rank
  falls in the `+Inf` bucket) is reported as a lower bound, not as that
  boundary. It is a breach if that boundary already reaches the bound,
  otherwise not evaluable (`no_data`). PromQL's `histogram_quantile` would
  return the boundary itself and so read such a latency as within.
- Interpolation is linear within a bucket: include each declared bound
  (e.g. `3600`, `86400`) among the bucket boundaries.
- Feedback latency is observed when ground truth arrives, so the 30-day
  window is anchored on arrival (CORE §5.5.5). A young service is measured
  over the ground truth that has arrived; only when Prometheus's retention
  (`min(prometheus_tsdb_lowest_timestamp_seconds)`, queried once per cycle)
  is shorter than 30 days is the bound not evaluable
  (`insufficient_window`). When retention is unknown (Prometheus does not
  scrape itself), the sampler measures what Prometheus returns.
- `MEASURE_RETENTION_CHECK` (nthlayer-workers; default on, `off` / `false` /
  `0` disable it, read at startup) turns the retention check off. Turn it off
  when the queried endpoint is not the TSDB that metric describes — Thanos
  sidecar, Mimir, Cortex: there, the local head's lowest timestamp says
  nothing about what the query path can see, and would wrongly report
  `insufficient_window`.
- Superseded: the single gauges `gen_ai_calibration_error{service}` and
  `gen_ai_feedback_latency_seconds{service}` are no longer read. The
  histogram above reuses the latter's base name, so an exporter cannot
  register both: cut over from the gauge to the histogram in one release. A
  plain gauge of that name is not read.
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
    is set only for a ``histogram_quantile`` series: a quantile of a classic
    histogram, which the sampler computes from the ``_bucket`` counts (it
    does not send PromQL's histogram_quantile, which hides a quantile in the
    +Inf bucket)."""

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
  - `AtLeast(value: float)` — frozen dataclass: a lower bound, the true value is strictly greater than `value`; rejects a non-finite `value` (`ValueError`). A sampler returns it for a histogram quantile in the `+Inf` bucket.
  - `Samples(bounds: Mapping[str, float | Missing | AtLeast] = {}, overall: float | Missing | None = None, segments: Mapping[str, float | Missing] = {})` — frozen dataclass (use `field(default_factory=dict)`)
  - `BoundResult(bound: str, status: Status, measured: float | None, limit: float | str, reason: str | None)` — frozen
  - `SegmentResult(segment: str, status: Status, measured: float | None, reason: str | None)` — frozen
  - `ThresholdOutcome(type: str, status: Status, bounds: tuple[BoundResult, ...], segments: tuple[SegmentResult, ...] = ())` — frozen, with `to_dict() -> dict[str, Any]` and `@classmethod from_dict(d) -> ThresholdOutcome`
  - `combine(statuses: Iterable[Status]) -> Status` — E4; empty → `"not_evaluable"`

- [ ] **Step 1: Write the failing tests**

```python
"""Outcome model for threshold evaluation (opensrm-g32d)."""

import pytest

from nthlayer_common.manifest.evaluation import (
    AtLeast,
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


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_lower_bound_must_be_finite(bad):
    with pytest.raises(ValueError):
        AtLeast(bad)
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

import math
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
class AtLeast:
    """A lower bound: the true value is strictly greater than ``value``.

    What a classic Prometheus histogram yields when a quantile falls in the
    ``+Inf`` bucket: the value lies beyond the largest finite boundary, which
    PromQL's histogram_quantile would report as the value itself."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError(f"AtLeast.value must be finite, got {self.value!r}")


@dataclass(frozen=True)
class Samples:
    """The raw measurements for one threshold.

    ``bounds`` maps a bound name to its measured value for every type except
    segments; a value may be a lower bound (``AtLeast``). For segments,
    ``overall`` is the overall rate and ``segments`` maps each listed segment
    value to its rate; the evaluator computes the variance itself (CORE §5.5.1).
    """

    bounds: Mapping[str, float | Missing | AtLeast] = field(default_factory=dict)
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
- Consumes: Task 3's types (incl. `Missing`, `AtLeast`, `Samples`); `THRESHOLD_BOUNDS`, `DURATION`, `duration_seconds` from `nthlayer_common.manifest.thresholds`; `JudgmentThreshold`, `ThresholdMeasurement` from `nthlayer_common.manifest.models`.
- Produces: `evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome`. Raises `ValueError` (never `KeyError`) for a type not in `THRESHOLD_BOUNDS` or a bound that type does not define (parsed thresholds never have one; hand-built ones can). A sample `AtLeast(v)` is a `breach` with `measured=v`, `reason="lower_bound"` when `v >= limit` (the true value is > v ≥ limit), else `not_evaluable` with reason `beyond_top_bucket`.
- Also produces the helpers Task 5 consumes: `_limit_value(threshold_type, bound, limit) -> float` (raises `ValueError` for an undefined bound) and `_decide(measured, limit) -> (status, measured, reason)`.

- [ ] **Step 1: Write the failing tests**

```python
"""evaluate_threshold: E1-E4 for calibration, stability, audit_backlog,
feedback_latency (opensrm-g32d). Expected outcomes follow CORE §5.5.6."""

import math

import pytest

from nthlayer_common.manifest.evaluation import AtLeast, Missing, Samples, evaluate_threshold
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


def test_unknown_bound_for_the_type_raises_value_error():
    # Hand-built (the parsers reject it): a ValueError, not a KeyError.
    with pytest.raises(ValueError):
        evaluate_threshold(_cal(maximum_p50="1h"), Samples())


# A lower bound: what a histogram quantile in the +Inf bucket yields --------

@pytest.mark.parametrize("lower,limit,expected", [
    # The true value is > 86400 = 1d: a breach.
    (86400.0, "1d", ("breach", 86400.0, "lower_bound")),
    # > 3600 = 1h, equal at the boundary: still strictly above the limit.
    (3600.0, "1h", ("breach", 3600.0, "lower_bound")),
    # > 10000 (OTel's default top bucket) says nothing about a 1d limit.
    (10000.0, "1d", ("not_evaluable", None, "no_data")),
])
def test_lower_bound_breaches_only_when_it_reaches_the_limit(lower, limit, expected):
    o = evaluate_threshold(_lat(maximum_p90=limit), Samples(bounds={"maximum_p90": AtLeast(lower)}))
    b = o.bounds[0]
    assert (b.status, b.measured, b.reason) == expected
    assert o.status == expected[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-common && uv run pytest -q -o addopts= tests/test_evaluate_threshold.py`
Expected: FAIL — `ImportError: cannot import name 'evaluate_threshold'`

- [ ] **Step 3: Implement (append to evaluation.py)**

```python
from nthlayer_common.manifest.models import JudgmentThreshold
from nthlayer_common.manifest.thresholds import DURATION, THRESHOLD_BOUNDS, duration_seconds


def _limit_value(threshold_type: str, bound: str, limit: float | str) -> float:
    kinds = THRESHOLD_BOUNDS[threshold_type]
    if bound not in kinds:
        # Parsed thresholds never get here (parse_bounds rejects it); a
        # hand-built one gets a ValueError, not a KeyError.
        raise ValueError(f"{threshold_type} has no bound {bound!r}; expected one of {sorted(kinds)}")
    if kinds[bound] == DURATION:
        return duration_seconds(limit)  # type: ignore[arg-type]
    return float(limit)


def _decide(
    measured: float | Missing | AtLeast | None, limit: float
) -> tuple[Status, float | None, str | None]:
    """E1 for one measured value; E3 for a missing or non-finite one.

    A lower bound (AtLeast) breaches when it already reaches the limit: the
    true value is strictly greater than it, so strictly greater than the
    limit. Below the limit it decides nothing, so it is not evaluable."""
    if measured is None:
        return "not_evaluable", None, "no_data"
    if isinstance(measured, Missing):
        return "not_evaluable", None, measured.reason
    if isinstance(measured, AtLeast):
        if measured.value >= limit:
            return "breach", measured.value, "lower_bound"
        return "not_evaluable", None, "no_data"
    if not math.isfinite(measured):
        return "not_evaluable", None, "no_data"
    return ("breach" if measured > limit else "within"), measured, None


def evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome:
    """Apply CORE §5.5.6 E1-E4 to one threshold. Pure; raises ValueError for
    a type that is not a judgment threshold type, a bound that type does not
    define, or a segments threshold without exactly one bound."""
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

Move the new imports to the top of the module with the existing ones (ruff `I`; `math` is already imported there by Task 3).

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
- Consumes: Task 4's `_decide`, `_limit_value` (raises `ValueError` for a bound the type does not define), Task 3's `combine`.
- Produces: segments evaluation. Raises `ValueError` when a (hand-built) segments threshold does not have exactly one bound. `ThresholdOutcome.segments` has one `SegmentResult` per distinct listed segment value, in declared order; the single bound's `BoundResult.measured` is the largest evaluated variance (or `None` when none evaluated), its status the E4 combination of the segments.

- [ ] **Step 1: Write the failing tests**

```python
"""Segments evaluation (CORE §5.5.1 + §5.5.6) and every spec example."""

from pathlib import Path

import pytest
import yaml

from nthlayer_common.manifest import threshold_from_v2_entry
from nthlayer_common.manifest.evaluation import Missing, Samples, evaluate_threshold
from nthlayer_common.manifest.models import JudgmentThreshold, ThresholdMeasurement


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


@pytest.mark.parametrize("bounds", [
    {},
    {"maximum_variance_from_overall": 0.05, "maximum_drift": 0.1},
    {"maximum_drift": 0.1},  # one bound, but not a segments bound
])
def test_segments_without_exactly_its_one_bound_raises_value_error(bounds):
    # Hand-built (the parsers reject all three).
    t = JudgmentThreshold("segments", bounds,
                          ThresholdMeasurement(metric="escalation", segment_dimension="region",
                                               segment_values=["eu"], window="30d"))
    with pytest.raises(ValueError):
        evaluate_threshold(t, Samples(overall=0.1, segments={"eu": 0.1}))


_SPEC_V2 = Path(__file__).resolve().parents[2] / "opensrm" / "spec" / "v2"
# Every shipped example that declares judgment thresholds (spec §9: every one).
_EXAMPLES = sorted(
    p for p in (_SPEC_V2 / "examples").rglob("*.yaml")
    if "judgment_threshold" in (yaml.safe_load(p.read_text()) or {}).get("spec", {})
) if _SPEC_V2.is_dir() else []


def test_the_threshold_examples_are_present():
    # 8 at the time of writing (opensrm main, 2026-10-12): the six in
    # examples/judgment-thresholds/, service-manifest-full.yaml and
    # services/ai-gate.yaml. A floor, not an equality: new examples are welcome,
    # but a glob or filter that silently drops some must fail here.
    names = {p.relative_to(_SPEC_V2 / "examples").as_posix() for p in _EXAMPLES}
    assert {"judgment-thresholds/all-five-types.yaml",
            "judgment-thresholds/segments-two-dimensions.yaml",
            "services/ai-gate.yaml"} <= names, names
    assert len(_EXAMPLES) >= 8, names


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
    if len(threshold.bounds) != 1:
        raise ValueError(f"a segments threshold has exactly one bound, got {sorted(threshold.bounds)}")
    ((bound, limit),) = threshold.bounds.items()
    limit_v = _limit_value("segments", bound, limit)
    overall = samples.overall
    results: list[SegmentResult] = []
    for value in dict.fromkeys(threshold.measurement.segment_values):  # distinct, in order
        if overall is None or isinstance(overall, Missing) or not math.isfinite(overall):
            reason = overall.reason if isinstance(overall, Missing) else "no_data"
            results.append(SegmentResult(value, "not_evaluable", None, reason))
            continue
        rate = samples.segments.get(value)
        variance = rate if rate is None or isinstance(rate, Missing) else abs(rate - overall)
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
- Produces: public names `evaluate_threshold`, `ThresholdOutcome`, `BoundResult`, `SegmentResult`, `Samples`, `Missing`, `AtLeast`, `THRESHOLD_SERIES`, `ThresholdSeries`, `FEEDBACK_LATENCY_WINDOW` from `nthlayer_common.manifest`; `"judgment_threshold_evaluation" in ASSESSMENT_KINDS`.

- [ ] **Step 1: Write the failing tests**

```python
import nthlayer_common.manifest as manifest
from nthlayer_common.cloudevents import ASSESSMENT_KINDS, _ce_type_for_assessment

_PUBLIC = ["evaluate_threshold", "ThresholdOutcome", "BoundResult", "SegmentResult",
           "Samples", "Missing", "AtLeast", "THRESHOLD_SERIES", "ThresholdSeries",
           "FEEDBACK_LATENCY_WINDOW"]


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
    `from nthlayer_common.manifest.evaluation import AtLeast, BoundResult, Missing, Samples, SegmentResult, ThresholdOutcome, evaluate_threshold`
    and `from nthlayer_common.manifest.threshold_series import FEEDBACK_LATENCY_WINDOW, THRESHOLD_SERIES, ThresholdSeries`, and add all ten names to `__all__` (keep its existing ordering style).
  - In `cloudevents.py` add `"judgment_threshold_evaluation",` to `ASSESSMENT_KINDS` directly after `"judgment_slo_evaluation",`.
  - `docs/upgrading-5.0.md`: add a "**New in 5.2.0:**" bullet to "What consumers must change": evaluate thresholds with `evaluate_threshold(threshold, Samples(...))` (pure; consumers supply measurements per `THRESHOLD_SERIES`), emit `ThresholdOutcome.to_dict()` as a `judgment_threshold_evaluation` assessment; a sampler that can only bound a value from below (a histogram quantile in the `+Inf` bucket) supplies `AtLeast(v)`, which breaches iff `v >= limit`.
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

- [ ] **Step 2: Port the exact-ceiling guard** — append this test (ported from `nthlayer-core/tests/test_dependency_declarations.py`, docstring made major-agnostic) to the end of `nthlayer-workers/tests/test_dependency_declarations.py`. Everything it uses (`pytest`, `version`, `Version`, `_siblings`, `SIBLINGS`) is already defined or imported in that file.

```python
@pytest.mark.parametrize("name", SIBLINGS)
def test_declared_ceiling_is_exactly_the_next_major(name):
    """The ceiling must exclude the first release of the NEXT major, and nothing more.

    test_declared_range_has_an_upper_bound only asks that SOME bound exists, so
    `<N+2.0.0` while N.x is under test passes it (measured: suite stays green) and
    admits all of major N+1, which nothing here has run. Mirror image of the floor
    test: the floor admits nothing below the tested version, this admits nothing
    above its major. Like the floor, it must be bumped deliberately when the
    sibling's major advances.
    """
    specifier = _siblings()[name].specifier
    installed = Version(version(name))

    ceilings = [s.version for s in specifier if s.operator == "<"]
    assert len(ceilings) == 1, (
        f"'{name}{specifier}' declares {len(ceilings)} '<' bounds; this guard "
        f"reads exactly one"
    )
    expected = Version(f"{installed.major + 1}.0.0")
    assert Version(ceilings[0]) == expected, (
        f"{name} ceiling is declared '<{ceilings[0]}' but the installed version "
        f"is {installed}, so the ceiling must be '<{expected}'. A wider ceiling "
        f"publishes a major nothing here has run."
    )
```

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
    assert loaded.parse_failures == 1
```

`load_specs` (`measure/adapters/prometheus.py:87`) returns `LoadedSpecs(slos: list[SLODefinition], parse_failures: int)` — `parse_failures` is a COUNT of files that failed to load, not a list. `_CALIBRATION_MANIFEST` (a v2 manifest with `judgment_type: calibration` under `judgment_slo`) and the `load_specs` import already exist in `tests/measure/test_prometheus.py`; keep the fixture and its comment ("Shared by the pair below…") updated to say it now pins a load failure.

Also delete `test_judgment_query_builder_calibration_window_agnostic` (it indexes `_JUDGMENT_SLO_QUERIES["calibration"]`, which Step 3 removes).

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
  - In `measure/adapters/prometheus.py`:
    - delete the `"calibration"` and `"feedback_latency"` entries from `_JUDGMENT_SLO_QUERIES` (~line 181) and from `_JUDGMENT_QUERY_KINDS` (~line 201), together with the `# Unreachable today: feedback_latency …` comment block above the `"feedback_latency": "judgment_duration"` entry;
    - delete the `elif slo.query_kind == "judgment_duration":` branch in `evaluate_slos` (~line 432: its comment `# Seconds, and lower is better…` and `raw_breach = current_value > slo.target`) — no remaining builder produces that kind;
    - **keep `_target_seconds`**: it is also called by the `"latency_seconds"` branch (~line 442) and tested directly by `test_duration_units_are_matched_leniently` and `test_a_non_string_unit_warns_rather_than_aborting_the_cycle`;
    - update the comment above `_JUDGMENT_SLO_QUERIES` (drop the sentence about `_window` on calibration/feedback_latency) and the builder counts in two comments: in `_query_for`, "Only 4 of the 8 JUDGMENT_SLO_TYPES have a builder" → 2 of the 8; in `evaluate_slos`, "4 of the 8 JUDGMENT_SLO_TYPES have no builder" → 6 of the 8.
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
- Test: `nthlayer-workers/tests/measure/thresholds/test_sampler.py` (+ an empty `tests/measure/thresholds/__init__.py`: the test tree is a package — `tests/measure/__init__.py` exists)

**Interfaces:**
- Consumes: `THRESHOLD_SERIES`, `FEEDBACK_LATENCY_WINDOW`, `Samples`, `Missing`, `AtLeast`, `JudgmentThreshold`, `ThresholdSeries`, `duration_seconds` from `nthlayer_common.manifest` (and `evaluate_threshold` in the tests); `PrometheusProvider.query(query: str) -> dict` (raises `PrometheusProviderError` / httpx errors).
- Produces (all in `nthlayer_workers.measure.thresholds.sampler`):
  - `async def sample(provider, service: str, threshold: JudgmentThreshold, *, now: float | None = None, retention: float | Missing | None = None, retention_check: bool = True) -> Samples` — never raises. `retention` is `fetch_retention`'s result, passed in so a cycle queries it once; `None` fetches it inside `sample` when a bound needs it. `retention_check=False` (the `MEASURE_RETENTION_CHECK=off` switch, wired in Task 11) sends no retention query and measures.
  - `async def fetch_retention(provider) -> float | Missing` — Prometheus's oldest-sample timestamp; `Missing("no_data")` when unknown. Never raises.
  - `def needs_retention(threshold: JudgmentThreshold) -> bool` — whether sampling it checks retention (it has a `histogram_quantile` bound).
  - `def _quantile(q: float, buckets: list[tuple[float, float]]) -> float | AtLeast | None` — Prometheus's classic `bucketQuantile` over `(le, cumulative count)` pairs, except a rank in the `+Inf` bucket returns `AtLeast(largest finite le)`; `None` = nothing to measure (no `+Inf` bucket, no finite bucket, no observations, a zero-width rank such as `q=0` over an empty first bucket, or a largest non-`+Inf` `le` of `-Inf`). Never raises.
  - `def _label(value: str) -> str` — PromQL label-value escaping.
- Feedback latency sends ONE query per threshold, `sum by (le) (increase(gen_ai_feedback_latency_seconds_bucket{service="S"}[30d]))`, and computes every declared quantile from it. `histogram_quantile` is never sent: it reports a rank in the `+Inf` bucket as the largest finite `le`, so a latency far beyond the top bucket reads as `within`.

- [ ] **Step 1: Write the failing tests**

```python
"""Threshold sampler: Prometheus responses -> Samples (opensrm-g32d).

These tests feed realistic Prometheus response JSON and assert which bound
each value lands on - not just the query string (the gap that hid g32d)."""

import math
from unittest.mock import AsyncMock

import pytest
from nthlayer_common.manifest import (
    AtLeast,
    JudgmentThreshold,
    Missing,
    ThresholdMeasurement,
    evaluate_threshold,
)
from nthlayer_common.manifest.models import ProbeConfig

from nthlayer_workers.measure.thresholds.sampler import _quantile, fetch_retention, sample

NOW = 1_800_000_000.0
DAY = 86400.0
INF = math.inf


def _vector(value):
    return {"status": "success", "data": {"resultType": "vector",
            "result": [{"metric": {}, "value": [NOW, str(value)]}]}}


def _buckets(*pairs):
    """A `sum by (le) (increase(..._bucket[30d]))` response: one sample per
    bucket, cumulative counts, `le` formatted as Prometheus writes it."""
    return {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": {"le": le}, "value": [NOW, str(count)]} for le, count in pairs]}}


_EMPTY = {"status": "success", "data": {"resultType": "vector", "result": []}}

# A needle for _provider that matches every query ("" is a substring of any
# string): use it to make every query answer the same way.
_ANY = ""
# The feedback-latency query reads the histogram's buckets.
_BUCKETS = "gen_ai_feedback_latency_seconds_bucket"


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


def _queries(p):
    return [c.args[0] for c in p.query.await_args_list]


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


async def test_gauge_query_takes_the_max_across_series():
    # One series per service/bins/window is the contract; max() is the
    # conservative fallback when an exporter sends several (e.g. per instance).
    p = _provider([])
    await sample(p, "svc", _cal(maximum_expected_calibration_error=0.05, maximum_brier_score=0.1), now=NOW)
    assert [q.split("{")[0] for q in _queries(p)] == [
        "max(gen_ai_calibration_ece", "max(gen_ai_calibration_brier"]


async def test_mismatched_bins_label_is_no_data():
    # Prometheus has a series only for bins=15; the label matcher for bins=10
    # returns an empty vector.
    p = _provider([('bins="15"', _vector(0.9))])
    s = await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    v = s.bounds["maximum_brier_score"]
    assert isinstance(v, Missing) and v.reason == "no_data"
    assert 'bins="10"' in v.detail and 'window="30d"' in v.detail  # names what it looked for


async def test_label_values_are_escaped():
    p = _provider([])
    await sample(p, 'we"ird\\svc', _cal(maximum_brier_score=0.1), now=NOW)
    assert 'service="we\\"ird\\\\svc"' in p.query.await_args.args[0]


def _lat(p50="1h", p90="1d"):
    return JudgmentThreshold("feedback_latency", {"maximum_p50": p50, "maximum_p90": p90})


def _retention(start):
    # Prometheus's own oldest-sample timestamp (seconds).
    return ("prometheus_tsdb_lowest_timestamp_seconds", _vector(start))


_OLD = _retention(NOW - 31 * DAY)


# Prometheus's bucketQuantile, worked by hand (rank = q * total; first bucket
# whose cumulative count >= rank; linear between its lower and upper le).
@pytest.mark.parametrize("q,buckets,expected", [
    # total 10. q.5: rank 5 -> le=10 (count 5), lower 0: 0 + 10 * 5/5 = 10.
    (0.5, [(10, 5), (100, 10), (INF, 10)], 10.0),
    # q.9: rank 9 -> le=100: 10 + (100 - 10) * (9 - 5)/(10 - 5) = 82.
    (0.9, [(10, 5), (100, 10), (INF, 10)], 82.0),
    # total 100. q.5: rank 50 -> le=86400: 3600 + 82800 * (50 - 40)/(90 - 40) = 20160.
    (0.5, [(3600, 40), (86400, 90), (INF, 100)], 20160.0),
    # q.9: rank 90 lands exactly on le=86400's count: 3600 + 82800 * 50/50 = 86400.
    (0.9, [(3600, 40), (86400, 90), (INF, 100)], 86400.0),
    # rank 50 > 20 = every finite count: the +Inf bucket -> a lower bound.
    (0.5, [(3600, 10), (86400, 20), (INF, 100)], AtLeast(86400.0)),
    # Unsorted input, and a duplicate le (10 and 10.0) summed, as Prometheus does.
    (0.5, [(INF, 10), (100, 10), (10, 2), (10.0, 3)], 10.0),
    # Non-monotonic counts are repaired (le=100 -> 5): rank 9 is past every finite bucket.
    (0.9, [(10, 5), (100, 4), (INF, 10)], AtLeast(100.0)),
    # Nothing to measure: no observations, no +Inf bucket, no finite bucket.
    (0.5, [(10, 0), (INF, 0)], None),
    (0.5, [(10, 5), (100, 10)], None),
    (0.5, [(INF, 5)], None),
    # q=0 with an empty first bucket: Prometheus divides 0/0 (NaN), not a value.
    (0.0, [(10, 0), (100, 5), (INF, 5)], None),
    # le="-Inf" is the largest finite-side boundary: no finite lower bound exists.
    (0.5, [(-INF, 1), (INF, 10)], None),
])
def test_quantile_is_prometheus_bucket_quantile(q, buckets, expected):
    assert _quantile(q, buckets) == expected


async def test_latency_quantiles_land_on_p50_and_p90():
    # total 100: p50 rank 50 -> 3600 + 82800 * (50 - 40)/50 = 20160;
    # p90 rank 90 -> exactly 86400.
    p = _provider([_OLD, (_BUCKETS, _buckets(("3600", 40), ("86400", 90), ("+Inf", 100)))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 20160.0, "maximum_p90": 86400.0}


async def test_one_bucket_query_serves_both_quantiles():
    p = _provider([_OLD, (_BUCKETS, _buckets(("10", 5), ("+Inf", 10)))])
    await sample(p, "svc", _lat(), now=NOW)
    bucket_queries = [q for q in _queries(p) if _BUCKETS in q]
    assert bucket_queries == [
        'sum by (le) (increase(gen_ai_feedback_latency_seconds_bucket{service="svc"}[30d]))'
    ]
    assert not any("histogram_quantile" in q for q in _queries(p))


async def test_quantile_beyond_the_top_bucket_is_a_lower_bound():
    # Most ground truth arrives after more than a day: the rank falls in +Inf.
    p = _provider([_OLD, (_BUCKETS, _buckets(("3600", 5), ("86400", 10), ("+Inf", 100)))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": AtLeast(86400.0), "maximum_p90": AtLeast(86400.0)}


async def test_latency_beyond_a_1d_top_bucket_breaches_a_1d_bound():
    """End to end through evaluate_threshold: histogram_quantile would report
    86400 here, equal to the bound and so within. The true p90 is above it."""
    p = _provider([_OLD, (_BUCKETS, _buckets(("60", 1), ("3600", 5), ("86400", 10), ("+Inf", 100)))])
    t = _lat(p50="1d", p90="1d")
    o = evaluate_threshold(t, await sample(p, "svc", t, now=NOW))
    assert o.status == "breach"
    assert [(b.status, b.measured, b.reason) for b in o.bounds] == [
        ("breach", 86400.0, "lower_bound"), ("breach", 86400.0, "lower_bound")]


async def test_latency_beyond_a_top_bucket_below_the_bound_is_not_evaluable():
    # OTel's default top boundary is 10000s (< 1d): "more than 10000s" says
    # nothing about a 1d bound.
    p = _provider([_OLD, (_BUCKETS, _buckets(("5000", 1), ("10000", 2), ("+Inf", 10)))])
    t = _lat(p50="1d", p90="1d")
    o = evaluate_threshold(t, await sample(p, "svc", t, now=NOW))
    assert [(b.status, b.reason) for b in o.bounds] == [("not_evaluable", "beyond_top_bucket")] * 2


@pytest.mark.parametrize("response", [
    _buckets(("10", 0), ("+Inf", 0)),       # no ground truth arrived in 30d
    _buckets(("10", 5), ("100", 10)),       # no +Inf bucket: not a histogram
    _EMPTY,                                 # no series at all
])
async def test_unmeasurable_histogram_is_no_data(response):
    p = _provider([_OLD, (_BUCKETS, response)])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert all(isinstance(v, Missing) and v.reason == "no_data" for v in s.bounds.values())


async def test_no_bucket_series_names_the_selector():
    p = _provider([_OLD])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert 'service="svc"' in s.bounds["maximum_p50"].detail


async def test_short_retention_is_insufficient_window():
    # Prometheus keeps only 3 days: it cannot see the 30-day window.
    p = _provider([_retention(NOW - 3 * DAY), (_BUCKETS, _buckets(("10", 5), ("+Inf", 10)))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert {v.reason for v in s.bounds.values()} == {"insufficient_window"}
    assert not any(_BUCKETS in q for q in _queries(p))


async def test_young_series_is_measured():
    # CORE §5.5.5: p50/p90 over ground truth that ARRIVED in the last 30 days.
    # A service that started 3 days ago has exactly that quantity; only a
    # Prometheus that cannot see 30 days back makes it unmeasurable.
    p = _provider([_retention(NOW - 90 * DAY), (_BUCKETS, _buckets(("10", 5), ("100", 10), ("+Inf", 10)))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 10.0, "maximum_p90": 82.0}


async def test_unknown_retention_still_measures():
    # prometheus_tsdb_lowest_timestamp_seconds not scraped: retention unknown,
    # so measure what Prometheus returns rather than hide the bound.
    p = _provider([(_BUCKETS, _buckets(("10", 5), ("100", 10), ("+Inf", 10)))])
    s = await sample(p, "svc", _lat(), now=NOW)
    assert s.bounds == {"maximum_p50": 10.0, "maximum_p90": 82.0}


async def test_retention_check_off_sends_no_retention_query():
    # MEASURE_RETENTION_CHECK=off (Thanos sidecar / Mimir / Cortex, where the
    # metric does not describe what the query path can see).
    p = _provider([_retention(NOW - 3 * DAY), (_BUCKETS, _buckets(("10", 5), ("100", 10), ("+Inf", 10)))])
    s = await sample(p, "svc", _lat(), now=NOW, retention_check=False)
    assert s.bounds == {"maximum_p50": 10.0, "maximum_p90": 82.0}
    assert not any("prometheus_tsdb" in q for q in _queries(p))


async def test_prefetched_retention_is_used_not_requeried():
    p = _provider([_retention(NOW - 90 * DAY)])
    short = await fetch_retention(_provider([_retention(NOW - 3 * DAY)]))
    s = await sample(p, "svc", _lat(), now=NOW, retention=short)
    assert {v.reason for v in s.bounds.values()} == {"insufficient_window"}
    assert not any("prometheus_tsdb" in q for q in _queries(p))


async def test_prometheus_error_is_no_data_and_does_not_raise():
    p = _provider([(_ANY, RuntimeError("connection refused"))])
    s = await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    v = s.bounds["maximum_brier_score"]
    assert v.reason == "no_data" and "connection refused" in v.detail


async def test_nan_gauge_is_no_data():
    p = _provider([(_ANY, _vector("NaN"))])
    s = await sample(p, "svc", _cal(maximum_brier_score=0.1), now=NOW)
    assert s.bounds["maximum_brier_score"].reason == "no_data"


@pytest.mark.parametrize("t,bounds,measurement", [
    ("segments", {"maximum_variance_from_overall": 0.05},
     ThresholdMeasurement(metric="escalation", segment_dimension="region", segment_values=["eu"], window="30d")),
    ("stability", {"maximum_drift": 0.02},
     ThresholdMeasurement(probe=ProbeConfig("s3://p", "daily"))),
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

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_sampler.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Prometheus sampler for judgment thresholds (opensrm-g32d).

Builds queries from nthlayer_common's THRESHOLD_SERIES and maps each result to
the bound it measures. Never decides a bound (the evaluator does) and never
raises: any failure becomes a Missing sample (CORE §5.5.6 E3).

Histogram quantiles are computed here from the bucket counts rather than by
PromQL's histogram_quantile, which reports a quantile in the +Inf bucket as
the largest finite boundary - a value far beyond the top bucket would read as
that boundary and so as within. _quantile reports it as AtLeast(boundary).
"""

from __future__ import annotations

import math
import time as _time
from typing import Any

from nthlayer_common.manifest import (
    FEEDBACK_LATENCY_WINDOW,
    THRESHOLD_SERIES,
    AtLeast,
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


def _label(value: str) -> str:
    """A PromQL double-quoted label value: escape backslash, quote, newline."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _selector(labels: dict[str, str]) -> str:
    return ",".join(f'{name}="{_label(value)}"' for name, value in labels.items())


def _result(resp: Any) -> list[Any]:
    if not isinstance(resp, dict):
        return []
    data = resp.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    return result if isinstance(result, list) else []


def _scalar(resp: Any) -> float | None:
    result = _result(resp)
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _buckets(resp: Any) -> list[tuple[float, float]]:
    """(le, cumulative count) pairs from a `sum by (le)` vector; entries
    without a parseable ``le`` or a finite count are dropped."""
    out = []
    for r in _result(resp):
        try:
            le = float(r["metric"]["le"])  # Prometheus writes the last one "+Inf"
            count = float(r["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not math.isnan(le) and math.isfinite(count):
            out.append((le, count))
    return out


def _quantile(q: float, buckets: list[tuple[float, float]]) -> float | AtLeast | None:
    """Prometheus's classic-histogram bucketQuantile, except that a rank in
    the +Inf bucket is AtLeast(largest finite le) instead of that le.

    None when there is nothing to measure: no +Inf bucket, no finite bucket,
    or no observations. Duplicate ``le`` values are summed and the counts made
    monotonic, as Prometheus does."""
    merged: dict[float, float] = {}
    for le, count in buckets:
        merged[le] = merged.get(le, 0.0) + count
    ordered = sorted(merged.items())
    if len(ordered) < 2 or ordered[-1][0] != math.inf:
        return None
    cumulative: list[tuple[float, float]] = []
    running = 0.0
    for le, count in ordered:
        running = max(running, count)
        cumulative.append((le, running))
    total = cumulative[-1][1]
    if total <= 0:
        return None
    rank = q * total
    b = next(i for i, (_, count) in enumerate(cumulative) if count >= rank)
    if b == len(cumulative) - 1:
        top = cumulative[-2][0]
        # le="-Inf" as the only finite-side bucket bounds nothing.
        return AtLeast(top) if math.isfinite(top) else None
    upper, count = cumulative[b]
    if b == 0 and upper <= 0:
        return upper
    lower, below = cumulative[b - 1] if b > 0 else (0.0, 0.0)
    if count - below <= 0:  # q=0 over an empty first bucket (Prometheus: NaN)
        return None
    return lower + (upper - lower) * (rank - below) / (count - below)


async def _query(provider: Any, query: str) -> Any:
    """The response, or Missing("no_data") carrying the error. Never raises."""
    try:
        return await provider.query(query)
    except Exception as exc:  # a sampler never raises (E3)
        return Missing("no_data", f"{type(exc).__name__}: {exc}")


async def fetch_retention(provider: Any) -> float | Missing:
    """Prometheus's oldest-sample timestamp (seconds), or Missing when it is
    unknown. One query; the threshold phase calls it once per cycle."""
    resp = await _query(provider, _RETENTION_QUERY)
    if isinstance(resp, Missing):
        return resp
    v = _scalar(resp)
    if v is None or not math.isfinite(v):
        return Missing("no_data", "retention unknown")
    return v


def needs_retention(threshold: JudgmentThreshold) -> bool:
    """Whether sampling *threshold* checks Prometheus's retention."""
    series = THRESHOLD_SERIES.get(threshold.type, {})
    return any(
        series[b].kind == "histogram_quantile" for b in threshold.bounds if b in series
    )


async def _gauge(provider: Any, s: ThresholdSeries, service: str, t: JudgmentThreshold) -> float | Missing:
    m = t.measurement
    available = {"service": service, "bins": str(m.bins), "window": str(m.window)}
    selector = _selector({label: available[label] for label in s.labels})
    resp = await _query(provider, f"max({s.metric}{{{selector}}})")
    if isinstance(resp, Missing):
        return resp
    v = _scalar(resp)
    if v is None:
        return Missing("no_data", f"no {s.metric} series with {selector}")
    if not math.isfinite(v):
        return Missing("no_data", "non-finite value")
    return v


async def _histogram(
    provider: Any, metric: str, quantiles: dict[str, float], service: str
) -> dict[str, float | AtLeast | Missing]:
    """Every quantile of one histogram, from ONE bucket query."""
    selector = _selector({"service": service})
    resp = await _query(
        provider,
        f"sum by (le) (increase({metric}_bucket{{{selector}}}[{FEEDBACK_LATENCY_WINDOW}]))",
    )
    if isinstance(resp, Missing):
        return dict.fromkeys(quantiles, resp)
    buckets = _buckets(resp)
    if not buckets:
        return dict.fromkeys(quantiles, Missing("no_data", f"no {metric}_bucket series with {selector}"))
    out: dict[str, float | AtLeast | Missing] = {}
    for bound, q in quantiles.items():
        v = _quantile(q, buckets)
        out[bound] = Missing("no_data", "no observations in the window, or no +Inf bucket") if v is None else v
    return out


async def sample(
    provider: Any,
    service: str,
    threshold: JudgmentThreshold,
    *,
    now: float | None = None,
    retention: float | Missing | None = None,
    retention_check: bool = True,
) -> Samples:
    """The raw measurements for *threshold* on *service*. Never raises.

    *retention* is fetch_retention's result, passed in so a cycle queries it
    once; None fetches it here if a bound needs it. retention_check=False
    (MEASURE_RETENTION_CHECK=off) skips the check and measures what
    Prometheus returns."""
    series = THRESHOLD_SERIES.get(threshold.type, {})
    if threshold.type == "segments":
        return Samples(overall=Missing("no_data_source", "no segments series yet"))
    if not series:
        return Samples(bounds={b: Missing("no_data_source", f"no {threshold.type} series yet")
                               for b in threshold.bounds})
    out: dict[str, float | AtLeast | Missing] = {}
    histograms: dict[str, dict[str, float]] = {}  # metric -> {bound: quantile}
    for bound in threshold.bounds:
        s = series.get(bound)
        if s is None:
            out[bound] = Missing("no_data_source", f"no series for {bound}")
        elif s.kind == "gauge":
            out[bound] = await _gauge(provider, s, service, threshold)
        else:
            histograms.setdefault(s.metric, {})[bound] = s.quantile  # type: ignore[assignment]
    if histograms and retention_check:
        if retention is None:
            retention = await fetch_retention(provider)
        now = _time.time() if now is None else now
        window = duration_seconds(FEEDBACK_LATENCY_WINDOW)
        if not isinstance(retention, Missing) and now - retention < window - _RETENTION_SLACK_SECONDS:
            short = Missing("insufficient_window",
                            f"Prometheus retention starts {(now - retention) / 86400:.1f}d ago")
            out.update({b: short for qs in histograms.values() for b in qs})
            histograms = {}
    for metric, quantiles in histograms.items():
        out.update(await _histogram(provider, metric, quantiles, service))
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
- Consumes: `JudgmentThreshold` (and, in tests, `ThresholdMeasurement`) from `nthlayer_common.manifest`.
- Produces:
  - `REARM_INTERVALS = 3` — a disarmed key re-arms only after BOTH `REARM_INTERVALS` threshold intervals of `within` (`MeasureModule`, Task 11, passes `rearm_seconds = REARM_INTERVALS * threshold_interval_seconds`) AND at least `REARM_INTERVALS` consecutive `within` evaluations.
  - `threshold_key(service: str, t: JudgmentThreshold) -> str` — `service:type:sha256(identifying fields)[:12]`; bound VALUES excluded.
  - `bounds_digest(t: JudgmentThreshold) -> str` — `sha256(json.dumps(sorted bound items))[:8]`; Task 11 suffixes `~<digest>` onto the keys of same-identity entries.
  - `as_timestamp(v: Any) -> float | None` — a finite `int`/`float` (not `bool`) as `float`, else `None`; used to read persisted timestamps.
  - `@dataclass KeyState(last_evaluable: str | None = None, armed: bool = True, within_since: float | None = None, within_count: int = 0)` with `to_dict()` / `from_dict(d: Any)`. `within_since` is when the current `within` run began, `within_count` how many `within` evaluations it holds. `from_dict` never raises: restored `component_state` is untrusted, so a non-dict, or a field of the wrong type or value (`last_evaluable` not `"within"`/`"breach"`, `armed` not a `bool`, `within_since` not `as_timestamp`-valid, `within_count` not a non-negative `int`), takes the default; state from before this design (`within_streak`, no `within_since`) reads as no within run.
  - `advance(state: KeyState, status: str, now: float, rearm_seconds: float) -> tuple[KeyState, bool]` — the new state and whether a `quality_breach` fires. `within` starts a run (if none, or if `within_since > now` — the clock went back — it restarts at `now`) and, when disarmed, arms only once BOTH `now - within_since >= rearm_seconds` AND `within_count >= REARM_INTERVALS`; `not_evaluable` returns the state unchanged (neither starts, extends nor ends a run); `breach` ends the run (`within_since=None`, `within_count=0`) and fires iff armed and `last_evaluable != "breach"` (the second condition stops a restored armed+breach state re-firing).

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from nthlayer_common.manifest import JudgmentThreshold, ThresholdMeasurement

from nthlayer_workers.measure.thresholds.state import (
    REARM_INTERVALS,
    KeyState,
    advance,
    bounds_digest,
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


def test_bounds_digest_depends_on_values_not_order():
    a = JudgmentThreshold("calibration", {"maximum_brier_score": 0.1, "maximum_expected_calibration_error": 0.05})
    b = JudgmentThreshold("calibration", {"maximum_expected_calibration_error": 0.05, "maximum_brier_score": 0.1})
    c = JudgmentThreshold("calibration", {"maximum_brier_score": 0.2, "maximum_expected_calibration_error": 0.05})
    assert bounds_digest(a) == bounds_digest(b) != bounds_digest(c)
    assert len(bounds_digest(a)) == 8


INTERVAL = 900.0
REARM = REARM_INTERVALS * INTERVAL  # 2700s, what MeasureModule passes by default


def _run(statuses, interval=INTERVAL):
    """One status per threshold interval, starting at t=0."""
    st, fired = KeyState(), []
    for i, s in enumerate(statuses):
        st, f = advance(st, s, i * interval, REARM)
        fired.append(f)
    return fired


def test_first_breach_fires_once():
    assert _run(["breach", "breach"]) == [True, False]


def test_not_evaluable_gap_does_not_refire():
    assert _run(["breach", "not_evaluable", "breach"]) == [True, False, False]


def test_within_for_less_than_the_rearm_duration_does_not_rearm():
    # within at 900, 1800, 2700: the run is 1800s old at 2700 (< 2700).
    assert _run(["breach", "within", "within", "within", "breach"]) == [True, False, False, False, False]


def test_within_for_the_rearm_duration_rearms():
    # within from 900 to 3600: 2700s >= REARM, so the breach at 4500 fires.
    assert _run(["breach", "within", "within", "within", "within", "breach"]) == [
        True, False, False, False, False, True]
    assert REARM_INTERVALS == 3


def test_rearm_needs_both_the_duration_and_three_within_evaluations():
    # Far apart: two evaluations 2700s apart are not enough; the third is.
    st, _ = advance(KeyState(), "breach", 0.0, REARM)
    st, _ = advance(st, "within", 100.0, REARM)
    st, _ = advance(st, "within", 2800.0, REARM)
    assert not st.armed
    st, _ = advance(st, "within", 2900.0, REARM)
    assert st.armed
    # Close together: four evaluations within 300s are not enough.
    st, _ = advance(KeyState(), "breach", 0.0, REARM)
    for t in (100.0, 200.0, 300.0, 400.0):
        st, _ = advance(st, "within", t, REARM)
    assert not st.armed


def test_a_run_starting_in_the_future_restarts_now():
    # The clock went back: the run restarts instead of never re-arming.
    st, _ = advance(KeyState(), "breach", 10_000.0, REARM)
    st, _ = advance(st, "within", 10_900.0, REARM)
    for t in (100.0, 1000.0, 1900.0, 2800.0):
        st, _ = advance(st, "within", t, REARM)
    assert (st.within_since, st.within_count, st.armed) == (100.0, 4, True)


def test_flapping_does_not_refire_until_rearmed():
    # A breach ends the within run: flapping restarts the clock each time.
    assert _run(["breach", "within", "breach", "within", "within", "within", "within", "breach"]) == [
        True, False, False, False, False, False, False, True]


def test_not_evaluable_neither_starts_nor_ends_a_within_run():
    st, _ = advance(KeyState(), "breach", 0.0, REARM)
    st, _ = advance(st, "within", 900.0, REARM)
    st, _ = advance(st, "not_evaluable", 1800.0, REARM)
    assert (st.within_since, st.within_count) == (900.0, 1)
    st, _ = advance(st, "within", 2700.0, REARM)
    st, _ = advance(st, "within", 3600.0, REARM)
    assert st.armed  # 3600 - 900 = 2700, and 3 within evaluations
    st, _ = advance(KeyState(), "not_evaluable", 0.0, REARM)
    assert st.within_since is None


def test_not_evaluable_alone_never_fires():
    assert _run(["not_evaluable", "not_evaluable"]) == [False, False]


def test_within_then_breach_fires():
    assert _run(["within", "breach"]) == [False, True]


def test_restored_armed_breach_does_not_refire():
    assert advance(KeyState("breach", True, None), "breach", 0.0, REARM)[1] is False


def test_state_round_trip():
    st, _ = advance(KeyState(), "within", 5.0, REARM)
    assert KeyState.from_dict(st.to_dict()) == st


@pytest.mark.parametrize("raw,expected", [
    (None, KeyState()),
    ("garbage", KeyState()),
    ({"last_evaluable": 7, "armed": "no", "within_since": "x"}, KeyState()),
    ({"last_evaluable": "breach", "armed": 0, "within_since": True}, KeyState("breach", True, None)),
    ({"last_evaluable": "within", "armed": False, "within_since": 5, "within_count": True},
     KeyState("within", False, 5.0, 0)),
    ({"last_evaluable": "within", "armed": False, "within_since": 5, "within_count": -1},
     KeyState("within", False, 5.0, 0)),
    ({"last_evaluable": "within", "armed": False, "within_since": 5, "within_count": 2},
     KeyState("within", False, 5.0, 2)),
    ({"last_evaluable": "within", "armed": False, "within_since": float("nan")}, KeyState("within", False, None)),
    ({"last_evaluable": "within", "armed": False, "within_since": 12, "service": "svc"},
     KeyState("within", False, 12.0)),
    # State written before within_since existed.
    ({"last_evaluable": "within", "armed": False, "within_streak": 2}, KeyState("within", False, None)),
])
def test_from_dict_tolerates_a_corrupt_or_old_restored_state(raw, expected):
    assert KeyState.from_dict(raw) == expected
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
import math
from dataclasses import asdict, dataclass
from typing import Any

from nthlayer_common.manifest import JudgmentThreshold

# After a breach, a key re-arms only when BOTH hold: it has been within for
# rearm_seconds (MeasureModule passes REARM_INTERVALS * threshold_interval_seconds)
# AND it was evaluated within at least REARM_INTERVALS times in a row (the CLI
# path's 3-window hysteresis). The count keeps hysteresis when evaluations
# are close together; the duration keeps it when they are far apart.
# Tuning belongs to ratchet configuration.
REARM_INTERVALS = 3


def threshold_key(service: str, t: JudgmentThreshold) -> str:
    """service:type:hash of what identifies the entry: its measurement fields,
    the metric's parameters, and the NAMES of its bounds. Bound VALUES are
    excluded, so tightening a bound keeps the key; segment order is irrelevant.
    Two distinct entries of one service can still share it (same names,
    different values): the phase then suffixes each with bounds_digest."""
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


def bounds_digest(t: JudgmentThreshold) -> str:
    """8 hex chars of sha256 over the sorted (name, value) bound items: what
    tells apart entries that share a threshold_key. Depends on the entry
    alone, never on its position, so reordering cannot move state."""
    items = sorted(t.bounds.items(), key=lambda kv: kv[0])
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:8]


def as_timestamp(v: Any) -> float | None:
    """A finite int/float (not bool), else None."""
    if type(v) in (int, float) and math.isfinite(v):
        return float(v)
    return None


@dataclass
class KeyState:
    last_evaluable: str | None = None  # last "within" or "breach"; not_evaluable never sets it
    armed: bool = True
    within_since: float | None = None  # when the current within run began; None outside one
    within_count: int = 0  # within evaluations in the current run; not_evaluable leaves it

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Any) -> KeyState:
        """Read a persisted state. Restored component_state is not trusted: a
        non-dict, or a field of the wrong type, takes the default (armed, no
        within run), so a corrupt entry can re-raise a breach but never
        silences one. State written before within_since existed (it carried
        within_streak) reads as no within run."""
        if not isinstance(d, dict):
            return cls()
        last, armed, count = d.get("last_evaluable"), d.get("armed"), d.get("within_count")
        return cls(
            last_evaluable=last if last in ("within", "breach") else None,
            armed=armed if isinstance(armed, bool) else True,
            within_since=as_timestamp(d.get("within_since")),
            within_count=count if type(count) is int and count >= 0 else 0,
        )


def advance(state: KeyState, status: str, now: float, rearm_seconds: float) -> tuple[KeyState, bool]:
    """Apply one evaluation's combined status at time *now*. Returns (new
    state, fire a breach?).

    A disarmed key re-arms when its current within run is at least
    *rearm_seconds* old AND holds at least REARM_INTERVALS within
    evaluations. not_evaluable neither starts, extends nor ends a run; a
    breach ends it. A run that starts in the future (the clock went back)
    restarts now, so a backward clock delays re-arming but cannot stop it."""
    if status == "not_evaluable":
        return state, False
    if status == "within":
        restart = state.within_since is None or state.within_since > now
        since = now if restart else state.within_since
        count = 1 if restart else state.within_count + 1
        armed = state.armed or (now - since >= rearm_seconds and count >= REARM_INTERVALS)
        return KeyState("within", armed, since, count), False
    # breach. last_evaluable also guards a restored armed+breach state.
    fire = state.armed and state.last_evaluable != "breach"
    return KeyState("breach", state.armed and not fire, None, 0), fire
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_state.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add -A src/nthlayer_workers/measure/thresholds/state.py tests/measure/thresholds/test_state.py
git commit -m "feat(measure): threshold identity key and duration re-arm state (opensrm-g32d)"
```

### Task 11: Threshold phase in `MeasureModule.process_cycle`

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/measure/thresholds/phase.py`
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/worker.py` (imports, module-level `_env_flag_default_on` and `_env_seconds`, the `retention_check` / `threshold_interval_seconds` / `threshold_heartbeat_seconds` / `clock` fields, `__post_init__`, `restore_state`, `process_cycle`, `get_state`)
- Modify: `nthlayer-workers/.github/workflows/test.yml` (check out opensrm as a sibling)
- Test: `nthlayer-workers/tests/measure/thresholds/test_phase.py`

**Interfaces:**
- Consumes:
  - from `nthlayer_workers.measure.thresholds.sampler` (Task 9): `sample(provider, service, threshold, *, now=None, retention: float | Missing | None = None, retention_check: bool = True) -> Samples` (never raises; `retention=None` fetches it inside), `fetch_retention(provider) -> float | Missing` (never raises), `needs_retention(threshold) -> bool`;
  - from `nthlayer_workers.measure.thresholds.state` (Task 10): `REARM_INTERVALS = 3`; `threshold_key(service, t) -> str`; `bounds_digest(t) -> str` (8 hex chars over the sorted bound items); `as_timestamp(v) -> float | None`; `KeyState(last_evaluable, armed, within_since)` with `to_dict()` / `from_dict(d: Any)` (never raises: a non-dict or wrong-typed field takes the default); `advance(state, status, now, rearm_seconds) -> (KeyState, fire: bool)`;
  - from `nthlayer_common.manifest`: `JudgmentThreshold`, `Missing`, `ThresholdOutcome` (`to_dict()` → `{"type", "status", "bounds": [{"bound", "status", "measured", "limit", "reason"}], "segments": [{"segment", "status", "measured", "reason"}]}`), `evaluate_threshold`, `threshold_from_v2_entry(entry, where: str = ...) -> JudgmentThreshold`, `threshold_to_v2_entry(t) -> dict`, `OpenSRMV2ParseError`;
  - from `nthlayer_common.cloudevents`: `wrap_assessment(assessment: dict, *, component: str = "unknown", deployment_id: str | None = None) -> dict` and `wrap_verdict(verdict: dict, *, component: str = "unknown", deployment_id: str | None = None) -> dict` — each wraps the dict in a CloudEvents envelope whose `data` is the original dict;
  - `CoreAPIClient` (`nthlayer_common.api_client`, `MeasureModule.client`): `await client.get_manifests() -> APIResult`, `await client.submit_assessment(envelope: dict) -> APIResult`, `await client.submit_verdict(envelope: dict) -> APIResult`; `APIResult(ok: bool, status_code: int, data=None, error=None, detail=None)` — check `ok` before using `data`.
  - existing `MeasureModule` (`measure/worker.py`): dataclass fields `client`, `prometheus_url`, `eval_concurrency: int = 5` (copied to `self._eval_concurrency` in `__post_init__`; the SLO phase already uses it for its `asyncio.Semaphore`); `restore_state(state)` returns early on a falsy `state`; `process_cycle` returns early unless `/manifests` is ok, then opens `provider = PrometheusProvider(...)` and runs, inside one `try … finally: await provider.aclose()`, Phase 1 (SLO evaluation, ending in `await asyncio.gather(...)`), Phase 2 (SLO breach transitions, starting `new_breaches = _detect_transitions(...)`), Phase 3 (governance).
- Produces (`nthlayer_workers.measure.thresholds.phase`):
  - `DEFAULT_THRESHOLD_INTERVAL_SECONDS = 900.0`, `DEFAULT_THRESHOLD_HEARTBEAT_SECONDS = 3600.0`, `THRESHOLD_BREACH_SEVERITY = "high"`.
  - `outcome_signature(outcome: ThresholdOutcome) -> str` — the outcome without measured values (type, combined status, per-bound `[bound, status, reason, limit]` sorted by bound, per-segment `[segment, status, reason]` sorted by segment) as a `sort_keys` JSON string; the declared `limit` is included so tightening a bound is reported.
  - `retire_thresholds(*, manifests, state, seen_problems) -> None` — garbage collection alone (parses, sends no query), for measure cycles on which the phase does not run; same rule as the phase's own retirement.
  - `async def run_threshold_phase(*, client, provider, manifests: list[dict], state: dict[str, dict], seen_problems: set[str], eval_concurrency: int = 5, retention_check: bool = True, now: float | None = None, rearm_seconds: float = 2700.0, heartbeat_seconds: float = 3600.0) -> list[tuple[str, str, str]]` — evaluates entries concurrently (at most `eval_concurrency` at a time), queries retention at most once (only if `retention_check` and an entry needs it), returns new breaches as `(key, service, breach_verdict_id)`, and mutates `state`: key → `KeyState.to_dict()` plus `"service"`, `"last_signature"` (the last emitted `outcome_signature`, or `None`) and `"last_emitted_at"` (seconds, or `None`).
    - **Keys:** each entry's base is `threshold_key`; identical entries (equal `threshold_to_v2_entry` once `segment_values` is sorted — their order means nothing) are evaluated once; when a base has more than one distinct entry, EVERY such entry's key is `f"{base}~{bounds_digest(t)}"`, otherwise the bare base. Keys never depend on position, so reordering moves no state; adding or removing a same-identity sibling changes keys (fresh state, which may re-raise: the safe direction).
    - **Emission:** the assessment is submitted on first sight, when `outcome_signature` differs from `last_signature`, when `now - last_emitted_at >= heartbeat_seconds`, and whenever a breach fires (the verdict's `parent_ids` name it). A rejected assessment is logged and not recorded as emitted.
    - **Failure:** an entry that raises is logged once (`threshold_eval_failed`) and skipped; a manifest that is not a dict, whose `"name"` is not a non-empty `str`, or whose `"judgment_thresholds"` is neither absent/`None` nor a list is logged once (`threshold_manifest_skipped`) and skipped (its service is not treated as present, so its state is not retired); a state entry whose `"service"` is not a `str` is dropped. `state[key]` changes only when the entry's breach verdict (if one fires) was accepted (`ok`), so a rejected verdict (and its assessment) is raised again next run.
- `MeasureModule` gains:
  - `retention_check: bool` — default from `MEASURE_RETENTION_CHECK` via `_env_flag_default_on` (`off`/`false`/`0`, any case, disable it);
  - `threshold_interval_seconds: float` (env `MEASURE_THRESHOLD_INTERVAL`, default 900) and `threshold_heartbeat_seconds: float` (env `MEASURE_THRESHOLD_HEARTBEAT`, default 3600), via `_env_seconds` (valid only when finite and in (0, 604800] — zero would collapse hysteresis; anything else → default, logged `measure_env_invalid`). All three are read once at construction (restart to change);
  - `clock: Callable[[], float] = time.time` — injectable for tests;
  - `self._threshold_state` — persisted under `threshold_state` (`get_state` / `restore_state`; restore drops a non-dict value, non-dict entries and entries whose `"service"` is not a `str`);
  - `self._threshold_last_run: float | None` — persisted under `threshold_last_run` (restored via `as_timestamp`); the phase runs when it is `None`, the clock went back, or `threshold_interval_seconds` have passed. `threshold_breaches` is `[]` on cycles where it does not run, and those cycles call `retire_thresholds` so a removed entry retires at once. `run_threshold_phase` passes `now` to `sample`; a `last_emitted_at` in the future (clock went back) re-emits;
  - `self._threshold_problems: set[str]` — the once-per-change log memory; in-memory only, NOT persisted (after a restart each problem is logged once more).

- [ ] **Step 1: Write the failing tests** (pattern: `tests/measure/test_measure_worker.py` — `AsyncMock` client, patched `PrometheusProvider`)

```python
"""Threshold phase of MeasureModule (opensrm-g32d)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from nthlayer_common.api_client import APIResult
from nthlayer_common.manifest import threshold_from_v2_entry, threshold_to_v2_entry

from nthlayer_workers.measure.thresholds.state import bounds_digest, threshold_key
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


NOW = 1_800_000_000.0


class _Clock:
    """A settable clock for MeasureModule.clock: advance with `m.clock.t += s`."""

    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def _module(prom_values, manifests, **module_kw):
    """prom_values: list of ECE values returned on successive queries.
    Defaults: a 1s threshold interval, and _cycles advances the clock by the
    interval after each cycle, so every cycle is a threshold run. A test that
    needs exact times sets m.clock.t itself before each cycle."""
    module_kw.setdefault("threshold_interval_seconds", 1.0)
    module_kw.setdefault("clock", _Clock())
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
    module = MeasureModule(client=client, prometheus_url="http://prom:9090", **module_kw)
    return module, prov, assessments, verdicts


def _breaches(verdicts):
    return [v for v in verdicts if v.get("type") == "quality_breach"]


async def _cycles(module, prov, n):
    with patch("nthlayer_workers.measure.worker.PrometheusProvider", return_value=prov):
        for _ in range(n):
            await module.process_cycle()
            module.clock.t += module.threshold_interval_seconds


async def test_breach_emits_assessment_and_one_high_verdict():
    m, prov, a, v = _module([0.2, 0.2], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 2)
    evals = [x for x in a if x["kind"] == "judgment_threshold_evaluation"]
    # The second, unchanged outcome inside the heartbeat is not re-emitted.
    assert len(evals) == 1 and evals[0]["data"]["outcome"]["status"] == "breach"
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


_CAL_02 = dict(_CAL, bounds={"maximum_expected_calibration_error": 0.2})


def _suffixed(entry):
    t = threshold_from_v2_entry(entry)
    return f"{threshold_key('svc', t)}~{bounds_digest(t)}"


async def test_same_identity_entries_get_value_suffixed_keys():
    m, prov, a, v = _module([0.1, 0.1], _manifests(("svc", [_CAL, _CAL_02])))
    await _cycles(m, prov, 1)
    by_key = {x["data"]["threshold_key"]: x["data"]["outcome"]["status"] for x in a}
    # EVERY entry sharing the identity is suffixed, not just the later ones.
    assert by_key == {_suffixed(_CAL): "breach", _suffixed(_CAL_02): "within"}


async def test_reordering_same_identity_entries_keeps_each_entrys_state():
    m, prov, a, v = _module([0.1, 0.1, 0.1, 0.1], [
        _manifests(("svc", [_CAL, _CAL_02])),
        _manifests(("svc", [_CAL_02, _CAL])),  # same entries, swapped
    ])
    await _cycles(m, prov, 1)
    before = {k: dict(st) for k, st in m._threshold_state.items()}
    await _cycles(m, prov, 1)
    assert set(m._threshold_state) == set(before) == {_suffixed(_CAL), _suffixed(_CAL_02)}
    assert m._threshold_state[_suffixed(_CAL)]["last_evaluable"] == "breach"   # 0.1 > 0.05
    assert m._threshold_state[_suffixed(_CAL_02)]["last_evaluable"] == "within"  # 0.1 <= 0.2
    assert len(_breaches(v)) == 1  # the swap re-raised nothing


async def test_a_lone_entry_keeps_the_bare_key():
    m, prov, a, v = _module([0.1], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 1)
    assert set(m._threshold_state) == {threshold_key("svc", threshold_from_v2_entry(_CAL))}


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
    m._threshold_state = {"svc:calibration:abc": {"last_evaluable": "breach", "armed": False, "within_since": None,
                                                 "service": "svc"}}
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
    m2.clock.t = m.clock.t           # one interval after the saved run
    await _cycles(m2, prov2, 1)
    assert prov2.query.await_count == 1  # the phase ran...
    assert _breaches(v2) == []           # ...and did not re-raise


_SPEC_V2 = Path(__file__).resolve().parents[4] / "opensrm" / "spec" / "v2"


async def test_served_shape_drives_a_cycle():
    """Exactly what core 3.0 serves: threshold_to_v2_entry of the spec examples."""
    src = _SPEC_V2 / "examples" / "judgment-thresholds" / "all-five-types.yaml"
    assert src.is_file(), src
    served = [threshold_to_v2_entry(t) for t in
              (threshold_from_v2_entry(e)
               for e in yaml.safe_load(src.read_text())["spec"]["judgment_threshold"])]
    m, _, a, v = _module([], _manifests(("svc", served)))

    def answer(q):
        if "_bucket" in q:
            # 10 latencies: 5 <= 1h, 5 in (1h, 1d]. p50 rank 5 -> exactly 3600
            # (within 1h); p90 rank 9 -> 3600 + 82800 * 4/5 = 69840 (within 24h).
            return {"status": "success", "data": {"result": [
                {"metric": {"le": le}, "value": [0, n]}
                for le, n in (("3600", "5"), ("86400", "10"), ("+Inf", "10"))]}}
        return _vector(0.01)  # Brier 0.01 (bound 0.05); retention start 0.01 (decades back)

    prov = _recording_provider(answer)
    await _cycles(m, prov, 1)
    outcomes = {x["data"]["outcome"]["type"]: x["data"]["outcome"] for x in a}
    assert len(a) == len(served) and set(outcomes) == {t["type"] for t in served}
    assert {t: o["status"] for t, o in outcomes.items()} == {
        "segments": "not_evaluable", "stability": "not_evaluable", "audit_backlog": "not_evaluable",
        "calibration": "within", "feedback_latency": "within"}
    for t in ("segments", "stability", "audit_backlog"):
        assert {b["reason"] for b in outcomes[t]["bounds"]} == {"no_data_source"}, t
    assert v == []


# --- Failure containment and delivery (R5 edge-cases) ----------------------

_RR_SLO = {"name": "rr", "target": 98.5, "judgment_type": "reversal_rate", "window": "30d",
           "indicator_query": "q"}
_LAT = {"type": "feedback_latency", "bounds": {"maximum_p50": "1h"}}
_EMPTY = {"status": "success", "data": {"result": []}}


def _with_slo_breach(m, prov):
    """svc also declares an SLO that breaches (98.0 < 98.5)."""
    m.client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "slos": [_RR_SLO], "judgment_thresholds": [_CAL]}]))
    prov.get_sli_value = AsyncMock(return_value=0.98)


def _slo_breaches(verdicts):
    return [x["data"].get("slo_name") for x in _breaches(verdicts) if "slo_name" in x["data"]]


async def test_failed_breach_verdict_refires_next_cycle():
    m, prov, a, v = _module([0.2, 0.2, 0.2], _manifests(("svc", [_CAL])))
    answers = [APIResult(ok=False, status_code=503), APIResult(ok=True, status_code=201, data={}),
               APIResult(ok=True, status_code=201, data={})]
    m.client.submit_verdict = AsyncMock(side_effect=lambda env: (v.append(env["data"]), answers.pop(0))[1])
    await _cycles(m, prov, 3)
    # cycle 1 rejected -> state unchanged; cycle 2 raises it again; cycle 3 nothing new.
    assert len(_breaches(v)) == 2


async def test_failed_assessment_still_raises_the_verdict():
    m, prov, a, v = _module([0.2], _manifests(("svc", [_CAL])))
    m.client.submit_assessment = AsyncMock(return_value=APIResult(ok=False, status_code=503))
    await _cycles(m, prov, 1)
    assert len(_breaches(v)) == 1


async def test_one_failing_entry_does_not_stop_the_others():
    from nthlayer_workers.measure.thresholds import phase

    real = phase.evaluate_threshold

    def flaky(t, samples):
        if t.type == "audit_backlog":
            raise RuntimeError("boom")
        return real(t, samples)

    backlog = {"type": "audit_backlog", "bounds": {"maximum_age": "24h"}}
    m, prov, a, v = _module([0.2], _manifests(("svc", [backlog, _CAL])))
    with patch("nthlayer_workers.measure.thresholds.phase.evaluate_threshold", side_effect=flaky):
        await _cycles(m, prov, 1)
    assert [x["data"]["outcome"]["type"] for x in a] == ["calibration"]
    assert len(_breaches(v)) == 1


async def test_a_raising_entry_is_contained_inside_the_phase():
    """The phase itself returns the good entry's breach and commits its state:
    the failure must not escape run_threshold_phase (which would cost this
    cycle's threshold breaches in governance), not merely spare a sibling."""
    from nthlayer_workers.measure.thresholds import phase

    real = phase.evaluate_threshold

    def flaky(t, samples):
        if t.type == "audit_backlog":
            raise RuntimeError("boom")
        return real(t, samples)

    backlog = {"type": "audit_backlog", "bounds": {"maximum_age": "24h"}}
    m, prov, a, v = _module([0.2], _manifests())
    state, problems = {}, set()
    with patch("nthlayer_workers.measure.thresholds.phase.evaluate_threshold", side_effect=flaky):
        breaches = await phase.run_threshold_phase(
            client=m.client, provider=prov, state=state, seen_problems=problems,
            manifests=[{"name": "svc", "judgment_thresholds": [backlog, _CAL]}],
        )
    good = threshold_key("svc", threshold_from_v2_entry(_CAL))
    assert [k for k, _svc, _id in breaches] == [good]
    assert set(state) == {good} and state[good]["last_evaluable"] == "breach"
    assert any(p.startswith("eval:") for p in problems)


async def test_threshold_phase_failure_does_not_stop_slo_phases():
    m, prov, a, v = _module([], _manifests(("svc", [_CAL])))
    _with_slo_breach(m, prov)
    with patch("nthlayer_workers.measure.worker.run_threshold_phase",
               AsyncMock(side_effect=RuntimeError("boom"))):
        await _cycles(m, prov, 1)
    assert _slo_breaches(v) == ["rr"]


@pytest.mark.parametrize("threshold_state", [
    None,
    "garbage",
    {"svc:calibration:abc": "not-a-dict"},
    {"svc:calibration:abc": {"last_evaluable": 7, "armed": "yes", "within_since": "x", "service": "svc",
                             "last_signature": 3, "last_emitted_at": True}},
    {"svc:calibration:abc": {"last_evaluable": "breach", "service": ["svc"]}},  # unhashable service
    {"svc:calibration:abc": {"last_evaluable": "breach"}},                      # no service
])
async def test_corrupt_restored_state_does_not_stop_the_cycle(threshold_state):
    m, prov, a, v = _module([0.2], _manifests(("svc", [_CAL])))
    _with_slo_breach(m, prov)
    await m.restore_state({"slo_status": {}, "threshold_state": threshold_state})
    await _cycles(m, prov, 1)
    assert _slo_breaches(v) == ["rr"]
    assert any(x["data"].get("threshold_type") == "calibration" for x in _breaches(v))
    assert all(isinstance(st, dict) and isinstance(st.get("service"), str)
               for st in m._threshold_state.values())
    assert "svc:calibration:abc" not in m._threshold_state


async def test_non_conforming_state_entry_is_dropped_by_the_phase():
    # Injected after restore (restore_state already filters it): the phase
    # itself must not raise on it, and must drop it.
    m, prov, a, v = _module([0.2], _manifests(("svc", [_CAL])))
    m._threshold_state = {"bad": {"service": ["svc"]}}
    await _cycles(m, prov, 1)
    assert "bad" not in m._threshold_state
    assert len(_breaches(v)) == 1


@pytest.mark.parametrize("bad", ["not-a-dict", None, {"name": ["svc"]}, {"name": ""}, {"type": "ai-gate"}])
async def test_malformed_manifest_is_skipped(bad):
    # Called directly: MeasureModule's existing SLO phase reads the same list
    # and is outside this bead; the threshold phase must not raise on it.
    from nthlayer_workers.measure.thresholds.phase import run_threshold_phase

    m, prov, a, v = _module([0.2], _manifests())
    problems: set[str] = set()
    breaches = await run_threshold_phase(
        client=m.client, provider=prov, state={}, seen_problems=problems,
        manifests=[bad, {"name": "svc", "type": "ai-gate", "slos": [], "judgment_thresholds": [_CAL]}],
    )
    assert [x["data"]["outcome"]["type"] for x in a] == ["calibration"]
    assert len(breaches) == 1
    assert any(p.startswith("manifest:0:") for p in problems)


@pytest.mark.parametrize("items", [5, True, "x", {"a": 1}])
async def test_non_list_thresholds_are_skipped_and_keep_state(items):
    from nthlayer_workers.measure.thresholds.phase import run_threshold_phase

    m, prov, a, v = _module([0.2], _manifests())
    state = {"bad:calibration:abc": {"last_evaluable": "breach", "service": "bad"}}
    breaches = await run_threshold_phase(
        client=m.client, provider=prov, state=state, seen_problems=set(),
        manifests=[{"name": "bad", "judgment_thresholds": items},
                   {"name": "svc", "judgment_thresholds": [_CAL]}],
    )
    assert len(breaches) == 1
    assert "bad:calibration:abc" in state  # not retired on a malformed response


def _recording_provider(answer):
    prov = AsyncMock()
    prov.seen = []

    async def query(q, time=None):
        prov.seen.append(q)
        return answer(q)

    prov.query = AsyncMock(side_effect=query)
    prov.aclose = AsyncMock()
    return prov


@pytest.mark.parametrize("env,expected", [(None, 1), ("on", 1), ("off", 0), ("FALSE", 0), ("0", 0)])
async def test_retention_is_queried_once_per_cycle_unless_switched_off(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("MEASURE_RETENTION_CHECK", raising=False)
    else:
        monkeypatch.setenv("MEASURE_RETENTION_CHECK", env)
    m, _, a, v = _module([], _manifests(("a", [_LAT]), ("b", [_LAT])))  # reads the env
    prov = _recording_provider(lambda q: _EMPTY)
    await _cycles(m, prov, 1)
    assert sum("prometheus_tsdb_lowest_timestamp_seconds" in q for q in prov.seen) == expected
    assert len(a) == 2


async def test_entries_are_evaluated_concurrently_up_to_eval_concurrency():
    active = peak = 0

    async def slow(q, time=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return _vector(0.01)

    m, _, a, v = _module([], _manifests(*[(f"s{i}", [_CAL]) for i in range(6)]), eval_concurrency=2)
    prov = AsyncMock()
    prov.query = AsyncMock(side_effect=slow)
    prov.aclose = AsyncMock()
    await _cycles(m, prov, 1)
    assert len(a) == 6 and peak == 2


# --- Cadence, on-change emission, re-arm duration (Checkpoint A decisions) --

def _evals(assessments):
    return [x for x in assessments if x["kind"] == "judgment_threshold_evaluation"]


async def test_unchanged_outcome_is_reemitted_only_on_the_heartbeat():
    m, prov, a, v = _module([0.01] * 4, _manifests(("svc", [_CAL])), threshold_heartbeat_seconds=3600.0)
    for t in (0, 900, 3600, 4500):
        m.clock.t = NOW + t
        await _cycles(m, prov, 1)
    # first sight (t=0) and the heartbeat (t=3600); 900 and 4500 are unchanged.
    assert len(_evals(a)) == 2
    assert m._threshold_state[threshold_key("svc", threshold_from_v2_entry(_CAL))]["last_emitted_at"] == NOW + 3600


async def test_a_changed_outcome_is_emitted_at_once():
    m, prov, a, v = _module([0.01, 0.2, 0.2], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 3)
    assert [x["data"]["outcome"]["status"] for x in _evals(a)] == ["within", "breach"]


async def test_measured_value_changes_alone_do_not_emit():
    m, prov, a, v = _module([0.01, 0.02, 0.03], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 3)
    assert len(_evals(a)) == 1


async def test_a_firing_breach_always_emits_its_parent_assessment():
    """Even with the same signature as the last emission and inside the
    heartbeat: the verdict's parent_ids must name an assessment from this run."""
    m, prov, a, v = _module([0.2, 0.2], _manifests(("svc", [_CAL])))
    await _cycles(m, prov, 1)
    key = threshold_key("svc", threshold_from_v2_entry(_CAL))
    m._threshold_state[key].update(last_evaluable="within", armed=True)  # re-armed since
    await _cycles(m, prov, 1)
    evals, breaches = _evals(a), _breaches(v)
    assert len(evals) == 2 and len(breaches) == 2
    assert breaches[1]["parent_ids"] == [evals[1]["id"]]


async def test_the_phase_runs_on_its_own_interval():
    m, prov, a, v = _module([0.01, 0.01], _manifests(("svc", [_CAL])), threshold_interval_seconds=900.0)
    await _cycles(m, prov, 1)        # first cycle after start: runs
    m.clock.t = NOW + 300
    await _cycles(m, prov, 1)        # inside the interval: does not run
    assert prov.query.await_count == 1
    m.clock.t = NOW + 900
    await _cycles(m, prov, 1)        # 900s after the last run: runs
    assert prov.query.await_count == 2


async def test_the_interval_survives_a_restart():
    m, prov, a, v = _module([0.01], _manifests(("svc", [_CAL])), threshold_interval_seconds=900.0)
    await _cycles(m, prov, 1)
    saved = await m.get_state()
    m2, prov2, *_ = _module([0.01], _manifests(("svc", [_CAL])), threshold_interval_seconds=900.0)
    await m2.restore_state(saved)
    m2.clock.t = NOW + 300
    await _cycles(m2, prov2, 1)
    assert prov2.query.await_count == 0


@pytest.mark.parametrize("last_run", [None, "x", True, float("nan")])
async def test_a_corrupt_last_run_runs_the_phase(last_run):
    m, prov, a, v = _module([0.01], _manifests(("svc", [_CAL])), threshold_interval_seconds=900.0)
    await m.restore_state({"slo_status": {}, "threshold_last_run": last_run})
    await _cycles(m, prov, 1)
    assert prov.query.await_count == 1


@pytest.mark.parametrize("statuses,expected_breaches", [
    # One evaluation per 100s interval; re-arm needs 3 x 100s within.
    ([0.2, 0.01, 0.01, 0.01, 0.2], 1),          # within 100..300: 200s, not re-armed
    ([0.2, 0.01, 0.01, 0.01, 0.01, 0.2], 2),    # within 100..400: 300s, re-armed
])
async def test_rearm_is_three_threshold_intervals(statuses, expected_breaches):
    m, prov, a, v = _module(statuses, _manifests(("svc", [_CAL])), threshold_interval_seconds=100.0)
    await _cycles(m, prov, len(statuses))  # _cycles moves the clock 100s per cycle
    assert len(_breaches(v)) == expected_breaches


async def test_rearm_needs_three_within_evaluations_even_when_far_apart():
    """A 1s interval makes the 3s duration pass at once when evaluations are
    10s apart; the within count still holds the key disarmed."""
    m, prov, a, v = _module([0.2, 0.01, 0.01, 0.2], _manifests(("svc", [_CAL])),
                            threshold_interval_seconds=1.0)
    for t in (0, 10, 20, 30):
        m.clock.t = NOW + t
        await _cycles(m, prov, 1)
    assert len(_breaches(v)) == 1


async def test_a_backward_clock_still_runs_emits_and_rearms():
    m, prov, a, v = _module([0.2, 0.01, 0.01, 0.01, 0.01, 0.01, 0.2], _manifests(("svc", [_CAL])),
                            threshold_interval_seconds=60.0)
    times = [10_000, 10_060, 100, 160, 220, 280, 340]  # the clock goes back ~10000s
    for t in times:
        m.clock.t = NOW + t
        await _cycles(m, prov, 1)
    # (c) every cycle was a threshold run, the backward jump included (now < last run).
    assert prov.query.await_count == len(times)
    # (b) the jump re-emitted the unchanged within outcome (its last emission is in the future).
    assert [x["data"]["outcome"]["status"] for x in _evals(a)] == ["breach", "within", "within", "breach"]
    # (a) the within run restarted at 100: by 280 it is 180s = 3 x 60s old with 4 evaluations,
    # so the key re-armed and the breach at 340 fires.
    assert len(_breaches(v)) == 2


async def test_tightening_a_bound_emits_without_a_status_change():
    tighter = dict(_CAL, bounds={"maximum_expected_calibration_error": 0.03})
    m, prov, a, v = _module([0.01, 0.01], [_manifests(("svc", [_CAL])), _manifests(("svc", [tighter]))])
    await _cycles(m, prov, 2)
    assert [(x["data"]["outcome"]["status"], x["data"]["outcome"]["bounds"][0]["limit"]) for x in _evals(a)] == [
        ("within", 0.05), ("within", 0.03)]


async def test_a_removed_entry_retires_on_a_non_threshold_cycle():
    m, prov, a, v = _module([0.2], [_manifests(("svc", [_CAL])), _manifests(("svc", []))],
                            threshold_interval_seconds=900.0)
    await _cycles(m, prov, 1)
    m.clock.t = NOW + 60             # inside the interval: no threshold run...
    await _cycles(m, prov, 1)
    assert prov.query.await_count == 1
    assert m._threshold_state == {}  # ...but the removed entry retired


_SEG = {"type": "segments", "metric": "escalation", "segment_dimension": "region",
        "segment_values": ["eu", "us"], "bounds": {"maximum_variance_from_overall": 0.05}}


async def test_segment_value_order_does_not_make_a_distinct_entry():
    m, prov, a, v = _module([], _manifests(("svc", [_SEG, dict(_SEG, segment_values=["us", "eu"])])))
    await _cycles(m, prov, 1)
    assert len(_evals(a)) == 1
    assert set(m._threshold_state) == {threshold_key("svc", threshold_from_v2_entry(_SEG))}


@pytest.mark.parametrize("name,default", [("MEASURE_THRESHOLD_INTERVAL", 900.0),
                                          ("MEASURE_THRESHOLD_HEARTBEAT", 3600.0)])
@pytest.mark.parametrize("raw,expected", [
    (None, None), ("60", 60.0), ("604800", 604800.0),                    # None: the default
    ("abc", None), ("0", None), ("-5", None), ("nan", None), ("inf", None),
    ("1e308", None), ("604801", None),
])
def test_threshold_timing_env(monkeypatch, name, default, raw, expected):
    if raw is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw)
    m = MeasureModule(client=AsyncMock(), prometheus_url="http://p")
    field = {"MEASURE_THRESHOLD_INTERVAL": m.threshold_interval_seconds,
             "MEASURE_THRESHOLD_HEARTBEAT": m.threshold_heartbeat_seconds}[name]
    assert field == (default if expected is None else expected)
```

Check the `parents[N]` depth for `tests/measure/thresholds/` against the repo layout (workers is `<eco>/nthlayer-workers/tests/measure/thresholds/test_phase.py` → `parents[4]` is `<eco>`); assert `src.is_file()` so a wrong depth fails loudly.

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_phase.py`
Expected: FAIL (no threshold assessments emitted)

- [ ] **Step 3: Implement `phase.py`**

```python
"""The judgment-threshold phase of the measure cycle (opensrm-g32d)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from nthlayer_common.cloudevents import wrap_assessment, wrap_verdict
from nthlayer_common.manifest import (
    JudgmentThreshold,
    Missing,
    OpenSRMV2ParseError,
    ThresholdOutcome,
    evaluate_threshold,
    threshold_from_v2_entry,
    threshold_to_v2_entry,
)

from nthlayer_workers.measure.thresholds.sampler import fetch_retention, needs_retention, sample
from nthlayer_workers.measure.thresholds.state import (
    REARM_INTERVALS,
    KeyState,
    advance,
    as_timestamp,
    bounds_digest,
    threshold_key,
)

logger = structlog.get_logger()

THRESHOLD_BREACH_SEVERITY = "high"
# Defaults for MeasureModule's MEASURE_THRESHOLD_INTERVAL / _HEARTBEAT.
DEFAULT_THRESHOLD_INTERVAL_SECONDS = 900.0
DEFAULT_THRESHOLD_HEARTBEAT_SECONDS = 3600.0

_Entry = tuple[str, str, JudgmentThreshold]  # (key, service, threshold)


def _log_once(seen: set[str], token: str, event: str, **kw: Any) -> None:
    if token not in seen:
        seen.add(token)
        logger.warning(event, **kw)


def outcome_signature(outcome: ThresholdOutcome) -> str:
    """The outcome without its measured values, as a JSON string with sorted
    keys and sorted bound/segment lists: an assessment is re-emitted when
    this changes (or on the heartbeat). A bound's declared limit is part of
    it, so tightening a bound is reported even when no status changes."""
    d = outcome.to_dict()
    return json.dumps({
        "type": d["type"],
        "status": d["status"],
        "bounds": sorted(([b["bound"], b["status"], b["reason"], b["limit"]] for b in d["bounds"]),
                         key=lambda row: row[0]),
        "segments": sorted(([s["segment"], s["status"], s["reason"]] for s in d["segments"]),
                           key=lambda row: row[0]),
    }, sort_keys=True)


def _canonical(t: JudgmentThreshold) -> dict:
    """The entry's v2 form for the identical-entry check, with segment_values
    sorted: their order is not part of an entry's meaning (or its key)."""
    entry = threshold_to_v2_entry(t)
    if isinstance(entry.get("segment_values"), list):
        entry = {**entry, "segment_values": sorted(entry["segment_values"], key=str)}
    return entry


def _entries(manifests: list[dict], seen_problems: set[str]) -> tuple[set[str], list[_Entry]]:
    """Parse and key every served threshold: (services present, entries).

    Identical entries are kept once. A threshold_key shared by several
    distinct entries of a service (same identity, other bound values) is
    suffixed for EVERY such entry with ~bounds_digest, so a key depends on
    the entry, never on its position: reordering moves no state."""
    present: set[str] = set()
    by_base: dict[str, list[tuple[dict, str, JudgmentThreshold]]] = {}  # base -> distinct entries
    for i, m in enumerate(manifests):
        service = m.get("name") if isinstance(m, dict) else None
        if not isinstance(service, str) or not service:
            _log_once(seen_problems, f"manifest:{i}:{type(m).__name__}", "threshold_manifest_skipped",
                      where=f"/manifests[{i}]")
            continue
        items = m.get("judgment_thresholds")
        if items is None:  # an older core serves no key: no thresholds
            items = []
        if not isinstance(items, list):
            # Not marked present: a malformed response must not retire state.
            _log_once(seen_problems, f"thresholds:{service}:{type(items).__name__}",
                      "threshold_manifest_skipped", where=f"/manifests[{i}].judgment_thresholds")
            continue
        present.add(service)
        for j, item in enumerate(items):
            where = f"/manifests[{i}].judgment_thresholds[{j}]"
            try:
                t = threshold_from_v2_entry(item, where=where)
            except OpenSRMV2ParseError as exc:
                _log_once(seen_problems, f"parse:{service}:{item!r}", "threshold_parse_failed",
                          service=service, where=where, error=str(exc))
                continue
            base = threshold_key(service, t)
            canonical = _canonical(t)
            same_base = by_base.setdefault(base, [])
            if any(c == canonical for c, _, _ in same_base):  # identical: evaluate once
                _log_once(seen_problems, f"dup:{base}", "threshold_duplicate", service=service, key=base)
                continue
            same_base.append((canonical, service, t))
    entries: list[_Entry] = []
    for base, distinct in by_base.items():
        if len(distinct) == 1:
            _, service, t = distinct[0]
            entries.append((base, service, t))
            continue
        used: set[str] = set()
        for _, service, t in distinct:
            key = f"{base}~{bounds_digest(t)}"
            if key in used:  # a digest collision: keep the first, never merge state
                _log_once(seen_problems, f"collision:{key}", "threshold_key_collision",
                          service=service, key=key)
                continue
            used.add(key)
            entries.append((key, service, t))
    return present, entries


async def _evaluate(
    *, client: Any, provider: Any, key: str, service: str, t: JudgmentThreshold,
    state: dict[str, dict], retention: float | Missing | None, retention_check: bool,
    now: float, rearm_seconds: float, heartbeat_seconds: float,
) -> tuple[str, str, str] | None:
    """Sample, evaluate, report one entry; returns its new breach, if any.
    state[key] changes only once everything this run owes is delivered."""
    outcome = evaluate_threshold(
        t, await sample(provider, service, t, now=now, retention=retention,
                        retention_check=retention_check)
    )
    prev = state.get(key) or {}
    new_state, fire = advance(KeyState.from_dict(prev), outcome.status, now, rearm_seconds)
    signature = outcome_signature(outcome)
    last_signature = prev.get("last_signature")
    last_emitted_at = as_timestamp(prev.get("last_emitted_at"))
    # A firing breach always emits: its verdict's parent_ids name this assessment.
    # A last emission in the future (the clock went back) emits too, so a
    # backward clock cannot silence the heartbeat.
    emit = (
        fire
        or signature != last_signature
        or last_emitted_at is None
        or last_emitted_at > now
        or now - last_emitted_at >= heartbeat_seconds
    )
    assessment_id = f"jte-{service}-{t.type}-{uuid.uuid4().hex[:8]}"
    if emit:
        assessment = {
            "id": assessment_id,
            "created_at": datetime.now(UTC).isoformat(),
            "kind": "judgment_threshold_evaluation",
            "service": service,
            "data": {"threshold_key": key, "outcome": outcome.to_dict()},
        }
        result = await client.submit_assessment(wrap_assessment(assessment, component="measure"))
        if result.ok:
            last_signature, last_emitted_at = signature, now
        else:
            # Not recorded as emitted, so the next run emits again. A breach
            # still raises its verdict, whose parent_ids then name an
            # assessment core did not store.
            logger.warning("threshold_assessment_submit_failed", service=service, key=key,
                           assessment_id=assessment_id, status_code=result.status_code)
    breach: tuple[str, str, str] | None = None
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
        sent = await client.submit_verdict(wrap_verdict(verdict, component="measure"))
        if not sent.ok:
            # Keep the previous state, so the next run sees the same
            # transition and raises the verdict (and its assessment) again.
            logger.warning("threshold_breach_submit_failed", service=service, key=key,
                           status_code=sent.status_code)
            return None
        breach = (key, service, breach_id)
    state[key] = {**new_state.to_dict(), "service": service,
                  "last_signature": last_signature, "last_emitted_at": last_emitted_at}
    return breach


async def run_threshold_phase(
    *, client: Any, provider: Any, manifests: list[dict], state: dict[str, dict],
    seen_problems: set[str], eval_concurrency: int = 5, retention_check: bool = True,
    now: float | None = None,
    rearm_seconds: float = REARM_INTERVALS * DEFAULT_THRESHOLD_INTERVAL_SECONDS,
    heartbeat_seconds: float = DEFAULT_THRESHOLD_HEARTBEAT_SECONDS,
) -> list[tuple[str, str, str]]:
    """Evaluate every served threshold; mutate *state*; return new breaches as
    (key, service, breach_verdict_id). Caller guarantees *manifests* came from a
    successful /manifests response. Entries are evaluated concurrently, at most
    *eval_concurrency* at a time; one that raises is logged and skipped. An
    assessment is emitted on first sight, when the outcome's signature
    changes, after *heartbeat_seconds*, or whenever a breach fires."""
    now = time.time() if now is None else now
    present_services, entries = _entries(manifests, seen_problems)
    # Prometheus's retention, queried once per run and only if needed.
    retention: float | Missing | None = None
    if retention_check and any(needs_retention(t) for _, _, t in entries):
        retention = await fetch_retention(provider)
    sem = asyncio.Semaphore(eval_concurrency)
    new_breaches: list[tuple[str, str, str]] = []

    async def one(key: str, service: str, t: JudgmentThreshold) -> None:
        async with sem:
            try:
                breach = await _evaluate(client=client, provider=provider, key=key, service=service,
                                         t=t, state=state, retention=retention,
                                         retention_check=retention_check, now=now,
                                         rearm_seconds=rearm_seconds,
                                         heartbeat_seconds=heartbeat_seconds)
            except Exception as exc:  # one bad threshold affects only itself
                _log_once(seen_problems, f"eval:{key}:{type(exc).__name__}", "threshold_eval_failed",
                          service=service, key=key, error=f"{type(exc).__name__}: {exc}")
                return
        if breach is not None:
            new_breaches.append(breach)

    await asyncio.gather(*(one(*e) for e in entries))
    _retire(state, present_services, {key for key, _, _ in entries})
    return new_breaches


def _retire(state: dict[str, dict], present_services: set[str], live_keys: set[str]) -> None:
    """Retire only keys of services present in a successful response whose
    entry is gone. An entry without a str service (corrupt state) can never
    match a manifest: drop it rather than let it fail every run."""
    for key in [k for k, v in state.items()
                if not isinstance(v.get("service"), str)
                or (v["service"] in present_services and k not in live_keys)]:
        del state[key]
        logger.info("threshold_retired", key=key)


def retire_thresholds(*, manifests: list[dict], state: dict[str, dict], seen_problems: set[str]) -> None:
    """Garbage collection alone, for measure cycles on which the threshold
    phase does not run: /manifests is fetched every cycle, so a removed
    entry retires (and leaves governance) without waiting for the next
    threshold run. Same rule as the phase: successful response, service
    present, entry gone. Parses only; sends no query."""
    present_services, entries = _entries(manifests, seen_problems)
    _retire(state, present_services, {key for key, _, _ in entries})
```

- [ ] **Step 4: Wire it into `MeasureModule`** (`measure/worker.py`)
  - Imports: `import math`, `import os`, `import time`; `from collections.abc import Callable`; `from dataclasses import dataclass, field`; `from nthlayer_workers.measure.thresholds.phase import DEFAULT_THRESHOLD_HEARTBEAT_SECONDS, DEFAULT_THRESHOLD_INTERVAL_SECONDS, retire_thresholds, run_threshold_phase`; `from nthlayer_workers.measure.thresholds.state import REARM_INTERVALS, as_timestamp`.
  - Module-level helpers (above the class, below `logger = structlog.get_logger()`):

```python
def _env_flag_default_on(name: str) -> bool:
    """A default-on operator switch: only off / false / 0 (any case) disable it."""
    return os.environ.get(name, "").strip().lower() not in ("off", "false", "0")


# Upper bound for the threshold timing settings (7 days). Zero is rejected:
# a zero interval would evaluate every cycle and collapse re-arm hysteresis.
_MAX_TIMING_SECONDS = 7 * 86400.0


def _env_seconds(name: str, default: float) -> float:
    """Seconds from the environment, in (0, 7d]. Unset: the default. Not a
    number, non-finite, zero, negative or over 7d: the default, with a warning."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and 0 < value <= _MAX_TIMING_SECONDS):
        logger.warning("measure_env_invalid", name=name, value=raw, default=default)
        return default
    return value
```

  - Dataclass fields, after `eval_concurrency`:

```python
    # Operator settings, read once at construction: changing one needs a restart.
    retention_check: bool = field(
        default_factory=lambda: _env_flag_default_on("MEASURE_RETENTION_CHECK")
    )
    threshold_interval_seconds: float = field(
        default_factory=lambda: _env_seconds(
            "MEASURE_THRESHOLD_INTERVAL", DEFAULT_THRESHOLD_INTERVAL_SECONDS
        )
    )
    threshold_heartbeat_seconds: float = field(
        default_factory=lambda: _env_seconds(
            "MEASURE_THRESHOLD_HEARTBEAT", DEFAULT_THRESHOLD_HEARTBEAT_SECONDS
        )
    )
    # Wall-clock seconds; injectable so tests control the threshold cadence.
    clock: Callable[[], float] = time.time
```

  - `__post_init__`: add `self._threshold_state: dict[str, dict] = {}`, `self._threshold_problems: set[str] = set()` and `self._threshold_last_run: float | None = None`.
  - `restore_state` (restored component_state is untrusted; `KeyState.from_dict` handles wrong-typed fields):

```python
        raw = state.get("threshold_state")
        self._threshold_state = (
            {k: v for k, v in raw.items()
             if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("service"), str)}
            if isinstance(raw, dict) else {}
        )
        self._threshold_last_run = as_timestamp(state.get("threshold_last_run"))
```

  - `get_state`: add `"threshold_state": self._threshold_state` and `"threshold_last_run": self._threshold_last_run`.
  - `process_cycle`: directly after Phase 1's `await asyncio.gather(...)` and before Phase 2 (`new_breaches = _detect_transitions(...)`), still inside the `try`, add:

```python
            # Threshold phase (opensrm-g32d), on its own cadence: it runs when
            # threshold_interval_seconds have passed since it last ran (or it
            # never has, or the clock went back). Open threshold breaches still
            # reach governance every cycle, from _threshold_state (Task 12).
            # It must never stop Phases 2-3: on failure, log and go on with no
            # threshold breaches this cycle.
            threshold_breaches: list[tuple[str, str, str]] = []
            now = self.clock()
            last = self._threshold_last_run
            if last is None or now < last or now - last >= self.threshold_interval_seconds:
                self._threshold_last_run = now
                try:
                    threshold_breaches = await run_threshold_phase(
                        client=self.client, provider=provider, manifests=manifests,
                        state=self._threshold_state, seen_problems=self._threshold_problems,
                        eval_concurrency=self._eval_concurrency,
                        retention_check=self.retention_check, now=now,
                        rearm_seconds=REARM_INTERVALS * self.threshold_interval_seconds,
                        heartbeat_seconds=self.threshold_heartbeat_seconds,
                    )
                except Exception as exc:
                    logger.warning("threshold_phase_failed", error=f"{type(exc).__name__}: {exc}")
            else:
                # Not a threshold run: still retire removed entries, since
                # /manifests is fresh every cycle.
                try:
                    retire_thresholds(manifests=manifests, state=self._threshold_state,
                                      seen_problems=self._threshold_problems)
                except Exception as exc:
                    logger.warning("threshold_retire_failed", error=f"{type(exc).__name__}: {exc}")
            if threshold_breaches:
                logger.info("threshold_breaches", count=len(threshold_breaches))
```

  `provider` and `manifests` are the existing locals of `process_cycle` (the `PrometheusProvider` it opens and `result.data`). Do not change the existing early return (`if not result.ok or not result.data: return`). The `threshold_breaches` local is read by Task 12's governance block; the `logger.info` keeps it read (ruff `F841`) until then.

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
- Modify: `nthlayer-workers/src/nthlayer_workers/measure/worker.py` (field, `__post_init__`, `get_state`, `restore_state`, `process_cycle` Phase 3)
- Test: `nthlayer-workers/tests/measure/thresholds/test_autonomy_toggle.py`

**Interfaces:**
- Consumes, from Task 11: the local `threshold_breaches: list[tuple[str, str, str]]` (`(key, service, breach_verdict_id)` for each threshold whose `quality_breach` verdict core accepted this cycle; `[]` when the threshold phase raised or did not run — it runs on its own `threshold_interval_seconds` cadence, so most measure cycles are non-threshold cycles), which Task 11 sets in `process_cycle` between Phase 1 and Phase 2; the module-level `_env_flag_default_on` helper and the `os` / `dataclasses.field` imports Task 11 added to `measure/worker.py`; and `self._threshold_state: dict[str, dict]` (threshold key → `KeyState.to_dict()` plus `"service"`, `"last_signature"`, `"last_emitted_at"`; `last_evaluable` is `"within"`, `"breach"` or `None`), which persists between threshold runs — so the re-inject block below reads it EVERY measure cycle, threshold run or not. Also `MeasureModule.clock` (injectable `Callable[[], float]`) and `threshold_interval_seconds` (default 900). Threshold keys look like `service:type:hash` (optionally `~<digest>`), so `key.split(":", 1)[0]` is the service, as for SLO keys.
- Consumes, existing `MeasureModule` internals in `measure/worker.py` (read `process_cycle` before editing):
  - `current_status: dict[str, str]` — `process_cycle` local filled in Phase 1: SLO key (`service:slo_name`) → `"healthy"` / `"breach"`. Phase 3 groups its `"breach"` keys by service into `breaching_services`; at the end of the cycle it becomes `self._slo_status` (after a carry-forward loop that copies keys from the previous `_slo_status` missing this cycle).
  - `new_breaches: list[str]` — Phase 2 local: keys that transitioned to breach this cycle. Phase 3 acts only on a service that has at least one key in it.
  - `breach_verdict_ids: dict[str, str]` — Phase 2 local: key → its `quality_breach` verdict id; Phase 3 uses them as the `autonomy_change` verdict's `parent_ids`.
  - `self._breach_severities: dict[str, str]` — key → `"low"` / `"high"` / `"critical"`; read by `_compute_governance`.
  - `self._breach_decisions: dict[str, dict]` — key → `{"decided": True, "decided_at": ..., "autonomy_action": ...}` once Phase 3 has governed it; a decided key is not governed again; the existing "recovered-SLO cleanup" loop after Phase 3 deletes entries whose `current_status` is `"healthy"`.
  - `self._autonomy_levels: dict[str, str]` — service → level on `AUTONOMY_LADDER` (absent means `"fully_autonomous"`); a one-way ratchet.
  - `self._compute_governance(service, breaching_keys) -> (action, steps)` — more than one breaching key → floor `advisor` (`observer` if any is `critical`); a single key → drop by its severity (`high` = 2 steps).
- Produces: `MeasureModule.threshold_autonomy: bool` (default from `MEASURE_THRESHOLD_AUTONOMY`); when true, each new threshold breach enters Phase 3 governance as a breaching key with severity `"high"`, and an open (decided) threshold breach keeps counting in later cycles' governance. `MeasureModule` gains `self._threshold_governed: set[str]`, persisted under state key `threshold_governed`.

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
    clock = _Clock()
    return MeasureModule(client=client, prometheus_url="http://p", clock=clock), prov, verdicts


class _Clock:
    """MeasureModule.clock: the threshold phase reruns only after
    threshold_interval_seconds (default 900), so tests move it explicitly."""

    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


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
    m.clock.t += 900                          # a threshold run: the breach is still open
    await _cycle(m, prov)
    assert [v for v in verdicts if v["type"] == "autonomy_change"] == []


async def test_open_threshold_breach_counts_in_later_governance(monkeypatch):
    """An open threshold breach plus a later SLO breach is a multiple-breach
    case (advisor floor), as two SLO breaches would be."""
    m, prov, verdicts = _setup(monkeypatch, "1")
    await _cycle(m, prov)                     # threshold breach decided (open)
    # Reset the level so the outcome separates the two behaviours:
    # with re-injection 2 breaches -> advisor floor; without, 1 low breach -> autonomous.
    m._autonomy_levels["svc"] = "fully_autonomous"
    queries_before = prov.query.await_count
    m.clock.t += 60                           # inside the interval: a non-threshold cycle
    m.client.get_manifests = AsyncMock(return_value=APIResult(ok=True, status_code=200, data=[
        {"name": "svc", "type": "ai-gate", "judgment_thresholds": [_CAL], "slos": [
            {"name": "rr", "target": 98.5, "judgment_type": "reversal_rate", "window": "30d",
             "indicator_query": "q"}]}]))
    # A mild SLO breach (98.0 < 98.5 target; 33% budget consumption = low), so
    # the advisor floor below comes from the breach COUNT, not from severity.
    prov.get_sli_value = AsyncMock(return_value=0.98)
    await _cycle(m, prov)
    assert prov.query.await_count == queries_before  # the threshold phase did not run...
    assert m._autonomy_levels["svc"] == "advisor"    # ...yet its open breach counted
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
    # No clock move: a non-threshold cycle retires the removed entry too
    # (retire_thresholds runs on every cycle the phase does not).
    await _cycle(m, prov)
    assert not any(":calibration:" in k for k in m._breach_decisions)
    assert not any(":calibration:" in k for k in m._breach_severities)


@pytest.mark.parametrize("raw,expected", [
    (None, set()), ("svc:calibration:abc", set()), ({"k": 1}, set()),
    (["svc:calibration:abc", 7], {"svc:calibration:abc"}),
])
async def test_corrupt_threshold_governed_is_coerced(monkeypatch, raw, expected):
    m, prov, verdicts = _setup(monkeypatch, "1")
    await m.restore_state({"slo_status": {}, "threshold_governed": raw})
    assert m._threshold_governed == expected
    await _cycle(m, prov)  # and the cycle still runs
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd nthlayer-workers && uv run pytest -q -o addopts= tests/measure/thresholds/test_autonomy_toggle.py`
Expected: FAIL — `test_on_feeds_the_ratchet_as_a_high_breach`

- [ ] **Step 3: Implement** — in `measure/worker.py`, in this order:

1. **Toggle field.** Add a module-level helper beside Task 11's `_env_flag_default_on` (`os` and `field` are already imported):

```python
def _env_flag(name: str) -> bool:
    """A default-off operator switch: 1 / true / yes / on (any case) enable it."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
```

   and a dataclass field on `MeasureModule`, after `threshold_heartbeat_seconds` (read once, at construction):
   `threshold_autonomy: bool = field(default_factory=lambda: _env_flag("MEASURE_THRESHOLD_AUTONOMY"))`.

2. **`_threshold_governed`** — the set of governance keys that are threshold keys, so cleanup never touches SLO keys:
   - `__post_init__`: `self._threshold_governed: set[str] = set()`;
   - `get_state`: add `"threshold_governed": sorted(self._threshold_governed)`;
   - `restore_state` (untrusted, like `threshold_state`; a non-list becomes empty):

```python
        raw_governed = state.get("threshold_governed")
        self._threshold_governed = (
            {k for k in raw_governed if isinstance(k, str)} if isinstance(raw_governed, list) else set()
        )
```

3. **Re-inject block** — in `process_cycle`, immediately after the Phase 2 loop (`for slo_key in new_breaches: ...`) ends and before Phase 3 builds `breaching_services`:

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
            self._threshold_governed.update(governed_threshold_keys)
```

4. **Cleanup block** — directly after the existing recovered-SLO cleanup loop (`for slo_key in list(self._breach_decisions): if current_status.get(slo_key) == "healthy": ...`). It iterates `_threshold_governed` ONLY, never all `_breach_decisions` keys (which also hold SLO keys):

```python
            for key in list(self._threshold_governed):
                st = self._threshold_state.get(key)
                if st is None or st.get("last_evaluable") == "within":   # retired or recovered
                    self._breach_decisions.pop(key, None)
                    self._breach_severities.pop(key, None)
                    self._threshold_governed.discard(key)
```

5. **Pop block** — directly after the cleanup block and before the carry-forward loop (`for key, status in self._slo_status.items(): ...`), so `_slo_status` stays SLO-only:

```python
            for key in governed_threshold_keys:
                current_status.pop(key, None)
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
- Create: `nthlayer-workers/docs/upgrading-3.0.md` (workers is at 2.0.1 in `.release-please-manifest.json`, and this release is the next major, 3.0.0; `docs/` holds only `architecture.md` today, so this is the first upgrade note)

- [ ] **Step 1: Update CLAUDE.md hard rule 7** to state: severity is deterministic, no LLM; the five judgment SLO types use budget consumption; every judgment-threshold breach is `high` (thresholds are not SLOs — decision 3c); threshold breaches reach the autonomy ratchet only with `MEASURE_THRESHOLD_AUTONOMY` on. In the measure description, name `MEASURE_RETENTION_CHECK` beside it.

- [ ] **Step 2: Write the upgrade note** (`docs/upgrading-3.0.md`) covering: common 5.2 pin; calibration/segments/stability under `judgment_slo` now fail to load (move them to `spec.judgment_threshold`); thresholds are evaluated from core ≥3.0's `/manifests`; new assessment kind; the metric contract (link the front door's `docs/metrics-contract.md`), calling out that `gen_ai_feedback_latency_seconds` is now a histogram sharing the old gauge's base name (an exporter cannot register both: cut over in one release) and that its buckets need a finite boundary strictly above every declared bound (OTel's default top, 10000s, is below `1d`; a quantile beyond the top boundary is reported as a lower bound); and the operator settings:
  - `MEASURE_THRESHOLD_AUTONOMY` (default off) — threshold breaches feed the autonomy ratchet;
  - `MEASURE_RETENTION_CHECK` (default on; `off`/`false`/`0` disable) — set it **off** behind Thanos sidecar, Mimir or Cortex, where `prometheus_tsdb_lowest_timestamp_seconds` describes a local TSDB, not what the query path can see, and would wrongly report `insufficient_window`;
  - `MEASURE_THRESHOLD_INTERVAL` (seconds, default 900) — how often thresholds are evaluated, independent of the measure cycle; re-arm after a breach takes 3 intervals of `within` AND 3 `within` evaluations;
  - `MEASURE_THRESHOLD_HEARTBEAT` (seconds, default 3600) — an unchanged `judgment_threshold_evaluation` is re-emitted this often; a changed one (any bound/segment status or reason, or a bound's declared limit) is emitted at once. Dashboards should read the latest assessment per key, not count them;
  - a timing value must be in (0, 604800] (7 days); anything else (not a number, zero, negative, non-finite, larger) is logged and the default used;
  - all four are read once at startup: restart the worker to change them.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs
git commit -m "docs: judgment thresholds, upgrade notes and hard rule 7 (opensrm-g32d)"
```

**Checkpoint C:** R5-gate nthlayer-workers (base = branch point, head = Task 13). Push, open PR, hold. On approval: merge with the default merge subject, verify the release PR is a **major** with the BREAKING note, release, verify on PyPI with a clean co-install of common 5.2 + core 3.0 + workers. Close opensrm-g32d; file the out-of-scope beads listed in the spec §2.
