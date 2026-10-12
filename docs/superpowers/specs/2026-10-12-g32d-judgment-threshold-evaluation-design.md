# Judgment-threshold evaluation in nthlayer-workers — design (opensrm-g32d)

Status: approved in conversation 2026-10-12; awaiting written-spec review.
Bead: `opensrm-g32d` (P1 bug). Depends on: nthlayer-common 5.1.0
(`threshold_from_v2_entry`, opensrm-908x), nthlayer-core 3.0.0 (`/manifests`
serves `judgment_thresholds` as v2 entries, opensrm-7zpz).

## 1. Problem

nthlayer-workers pins nthlayer-common 3.x and still evaluates judgment error
magnitudes as SLOs:

- `calibration` is dispatched to the `judgment_rate` breach branch, an
  SLI-floor comparison that a declared-space ceiling (e.g. `0.05`) can only
  breach at an error above 0.9995 — it effectively **never breaches**.
- `segments` and `stability` fall through to the `ratio` branch and are
  **inverted**: a healthy service raises a high-severity breach and a
  drifting one reads clean.

Decision 3c (opensrm-l33e) moved these magnitudes out of SLOs into
`spec.judgment_threshold`; nthlayer-common 5.x models them as
`JudgmentThreshold`, and core 3.0 serves them on `/manifests` under
`judgment_thresholds`. Workers neither reads that key nor evaluates any
threshold. Moving workers to common 5 alone would stop the wrong alarms but
leave thresholds silently unmonitored. This design evaluates them per
OPENSRM-CORE-v2 §5.5.6:

- **E1** a breach is a measured value strictly exceeding a bound;
- **E2** durations are compared after unit normalisation;
- **E3** an unmeasurable bound is *not evaluable* and MUST be reported, per
  bound and, for segments, per listed segment;
- **E4** combined outcome precedence: breach > not evaluable > within.

## 2. Scope

In scope (this bead):

- workers moves to `nthlayer-common>=5.2,<6`; the SLO-path branches for
  calibration and feedback_latency are removed, so no error magnitude can
  reach SLO code;
- a shared, pure E1–E4 evaluator and outcome model in nthlayer-common 5.2;
- a metric contract and sampler for the two types that have (or will have)
  metrics: `calibration` and `feedback_latency`;
- evaluation in the worker loop (`MeasureModule.process_cycle`) only;
- `segments`, `stability`, `audit_backlog`: evaluated, reported
  `not_evaluable` with reason `no_data_source` — never silently skipped.

Out of scope, filed as new beads:

- data sources and metric contract for segments, stability, audit_backlog;
- whatever those sources need in core or bench;
- making the autonomy ratchet configurable as a whole (signals, counts,
  re-arm, severity grading);
- threshold evaluation in the CLI path (`measure evaluate-once`);
- a cross-repo front-door integration test (core 3.0 → workers).

## 3. Architecture

Three repos, released shared-first, each R5-gated:

1. **Front door (`nthlayer`)** — `docs/metrics-contract.md` documents the
   threshold metric contract (§4), citing nthlayer-common's
   `THRESHOLD_SERIES` as the source of truth.
2. **nthlayer-common 5.2.0** (additive):
   - `THRESHOLD_SERIES` — the bound → series table (§4), pinned both ways
     against `THRESHOLD_BOUNDS`;
   - `ThresholdOutcome` with `to_dict()` / `from_dict()` (§5);
   - `evaluate_threshold(threshold, samples) -> ThresholdOutcome` — pure,
     deterministic, no I/O (§5);
   - `judgment_threshold_evaluation` added to `ASSESSMENT_KINDS`.
3. **nthlayer-workers** (major release, §8):
   - pin `nthlayer-common>=5.2,<6`; remove the dead calibration /
     feedback_latency SLO branches and their strict xfails;
   - `measure/thresholds/sampler.py` — builds queries from
     `THRESHOLD_SERIES`, returns samples (§6);
   - a threshold phase in `MeasureModule.process_cycle` (§7);
   - operator toggle `MEASURE_THRESHOLD_AUTONOMY` (default off);
   - CLAUDE.md hard rule 7 updated (thresholds are not SLOs).

The evaluator receives **what the spec says is measured** and derives the
rest; the sampler never computes spec semantics. For segments that means the
overall rate and each listed segment's rate go in, and the evaluator computes
`|segment − overall|` itself.

## 4. Metric contract

Defined once in nthlayer-common as `THRESHOLD_SERIES`; documented in the
front door's `metrics-contract.md`.

| Threshold | Bound | Series | Labels |
|---|---|---|---|
| calibration | `maximum_expected_calibration_error` | `gen_ai_calibration_ece` (gauge) | `service`, `bins`, `window` |
| calibration | `maximum_brier_score` | `gen_ai_calibration_brier` (gauge) | `service`, `bins`, `window` |
| feedback_latency | `maximum_p50` | `gen_ai_feedback_latency_seconds_bucket` (histogram), `histogram_quantile(0.5, …)` over 30d | `service` |
| feedback_latency | `maximum_p90` | same histogram, `histogram_quantile(0.9, …)` | `service` |

Rules:

- Calibration series carry the parameters they were computed with. The
  sampler selects only the series whose `bins` and `window` match the
  manifest's `measurement`; no match → `no_data`. A gauge computed with
  other parameters is never used.
- Feedback latency is observed at ground-truth arrival, so the 30-day window
  is anchored on arrival (CORE §5.5.5).
- Histogram bucket boundaries should include the declared bounds, because
  `histogram_quantile` interpolates within a bucket. This is guidance; the
  evaluator cannot detect it.
- The single gauges `gen_ai_calibration_error` and
  `gen_ai_feedback_latency_seconds` are documented as superseded.
- segments, stability, audit_backlog: no series yet (`no_data_source`).

## 5. Evaluator and outcome model (nthlayer-common 5.2)

```python
Missing(reason: Literal["no_data_source", "no_data", "insufficient_window"], detail: str = "")
Samples = Mapping[str, float | Missing]          # keyed by bound; segments: see below

BoundResult(bound: str, status: Status, measured: float | None, limit: float | str, reason: str | None)
SegmentResult(segment: str, status: Status, measured: float | None, reason: str | None)
ThresholdOutcome(type: str, status: Status, bounds: tuple[BoundResult, ...],
                 segments: tuple[SegmentResult, ...] = ())
Status = Literal["within", "breach", "not_evaluable"]

evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome
```

- **E1:** breach iff `measured > limit`; equal is within. Holds for a limit
  of 0.
- **E2:** duration limits and measured durations are compared in seconds via
  `duration_seconds`.
- **E3:** a `Missing` sample makes that bound (or segment) `not_evaluable`,
  carrying the reason. For segments the samples carry `overall` and one value
  per listed segment value; each segment is decided independently, and a
  missing overall makes every segment `not_evaluable`. For `metric: outcomes`
  a segment whose population has no elapsed outcome window is
  `not_evaluable` (CORE §5.5.1); the sampler reports it as `no_data`.
- **E4:** the entry's status combines bounds (and segments) with breach >
  not_evaluable > within.
- `ThresholdOutcome.to_dict()` / `from_dict()` define the assessment payload;
  a round-trip test pins them. Every emitter and reader uses them.

## 6. Sampler (workers)

`sample(service: str, threshold: JudgmentThreshold) -> Samples`:

- builds each query from `THRESHOLD_SERIES` and the threshold's
  `measurement`;
- maps each Prometheus result to its bound; tests assert the mapping from
  realistic response JSON, not just the query string (the gap that hid this
  bug: only the calibration query string was ever tested);
- a Prometheus error or timeout → `Missing("no_data", <error>)`; it never
  raises;
- a 30-day query whose data does not span the window (retention shorter
  than the window, or the series younger than it) →
  `Missing("insufficient_window")`, never a partial-window value presented as
  30 days;
- segments, stability, audit_backlog → `Missing("no_data_source")` for every
  bound.

## 7. Worker loop: data flow, state, errors

Per cycle:

1. `GET /manifests`. If the call fails, the whole threshold phase is skipped
   for this cycle: no assessments, no state change, no garbage collection.
2. For each service `i` and entry `j`:
   `threshold_from_v2_entry(item, where=f"/manifests[{i}].judgment_thresholds[{j}]")`.
   A parse error logs `threshold_parse_failed` (once per change, not per
   cycle) and skips only that entry.
3. **Identity key:** `service` + `type` + a content hash of the identifying
   fields — `metric`, `segment_dimension`, sorted `segment_values`,
   `probe.frozen_input_set`, measurement `window` / `bins`. Bounds are
   excluded, so tightening a bound keeps the key. Identical entries share a
   key: evaluated once, the duplicate logged once per change.
4. Sample (§6), evaluate (§5).
5. Emit one `judgment_threshold_evaluation` assessment per key per cycle,
   payload `ThresholdOutcome.to_dict()` plus the key and service. This
   includes `not_evaluable` entries (E3 requires reporting; the reason code
   lets dashboards filter `no_data_source`).
6. **Transitions** (`component_state`, per key):
   - `last_evaluable` — the last `within` or `breach`; `not_evaluable` never
     changes it;
   - `within_streak` — consecutive `within` cycles since the last breach;
   - a verdict fires when the status is `breach`, `last_evaluable` is not
     `breach`, and the key is armed. A key is armed initially and re-arms
     after 3 consecutive `within` cycles. So `breach → not_evaluable →
     breach` raises once, and flapping at the bound does not re-raise until
     the value has stayed within for 3 cycles;
   - the verdict is `quality_breach`, severity `medium` for every threshold
     breach (graded severity belongs to the ratchet-configuration bead),
     referencing the assessment;
   - leaving `breach` and entering `not_evaluable` raise no verdict;
   - the autonomy ratchet is reached only when `MEASURE_THRESHOLD_AUTONOMY`
     is on. Turning it on does not apply the ratchet to breaches already open.
7. **Garbage collection:** a key is retired (`threshold_retired`) only when
   its service is present in a successful `/manifests` response and the entry
   is gone. An absent service keeps its state (core skips manifests it fails
   to load).

Principles: one bad threshold affects only itself; nothing turns missing data
into `within`; nothing raises out of the cycle; state lives in
`component_state`, so a restart does not re-raise open breaches.

## 8. Release

1. Front door: `metrics-contract.md` (docs).
2. nthlayer-common **5.2.0** (minor, additive).
3. nthlayer-workers **major**: the pin moves from common 3.x to 5.2, which
   brings 4.0's and 5.0's manifest rejections to workers — a v2 manifest with
   calibration under `judgment_slo` now fails to parse in the CLI path.
   BREAKING CHANGE footer and an upgrade note in workers' docs.

## 9. Testing

nthlayer-common:

- E1 boundary (equal = within, just above = breach, limit 0) for every bound
  of every type; E2 mixed units; E3 each reason, per bound and per segment,
  missing overall; E4 full truth tables across bounds, across segments, both;
- segments variance in both directions; a segment exactly at the bound is
  within;
- every threshold in `opensrm/spec/v2/examples` evaluated with synthetic
  samples; expected outcomes derived from CORE §5.5.6 wording, not the code;
- `THRESHOLD_SERIES` ↔ `THRESHOLD_BOUNDS` parity both ways;
  `ThresholdOutcome` dict round trip.

nthlayer-workers:

- sampler: realistic Prometheus response JSON → correct bound; mismatched
  `bins`/`window` labels → `no_data`; error/timeout → `no_data`, no raise;
  short retention → `insufficient_window`; unsourced types →
  `no_data_source`;
- cycle (real `Store`): one `quality_breach` per breach transition;
  `breach → not_evaluable → breach` raises once; flapping does not re-raise
  before 3 within cycles; absent service keeps state; removed entry retires;
  core unreachable touches nothing; a parse failure isolates one entry;
  restart does not re-raise; toggle off → no ratchet, on → ratchet; identity
  stable under segment reordering and bound changes;
- end to end: a high ECE breaches the ECE bound and only that bound;
- served-shape: a fixture built with `threshold_to_v2_entry` from the spec
  examples (exactly what core 3.0 serves) drives a cycle;
- regression: no calibration or segments threshold reaches SLO code; the old
  strict xfails are replaced by tests asserting correct behaviour.
