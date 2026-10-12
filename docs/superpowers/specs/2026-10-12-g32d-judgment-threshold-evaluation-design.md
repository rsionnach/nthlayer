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
   - operator switch `MEASURE_RETENTION_CHECK` (default on; §6);
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
| feedback_latency | `maximum_p50` | `gen_ai_feedback_latency_seconds` (histogram): its 0.5 quantile over the `_bucket` series' 30d increase | `service` |
| feedback_latency | `maximum_p90` | same histogram, 0.9 quantile, from the same bucket query | `service` |

Rules:

- Calibration series carry the parameters they were computed with. The
  sampler selects only the series whose `bins` and `window` match the
  manifest's `measurement`; no match → `no_data`. A gauge computed with
  other parameters is never used.
- Feedback latency is observed at ground-truth arrival, so the 30-day window
  is anchored on arrival (CORE §5.5.5).
- The histogram MUST have a finite bucket boundary strictly greater than
  every declared bound. Quantiles are computed by the sampler from the
  bucket counts with Prometheus's classic bucket-interpolation algorithm,
  except that a quantile beyond the largest finite boundary (its rank falls
  in the `+Inf` bucket) is reported as a **lower bound**, `AtLeast(boundary)`:
  a breach if that boundary already reaches the bound, otherwise not
  evaluable (`no_data`). PromQL's `histogram_quantile` is not used: it returns
  the largest finite boundary for such a quantile, so a latency far above
  the top bucket (OpenTelemetry's default top boundary is 10000s, below a
  `1d` bound) would read as within.
- Bucket boundaries should include the declared bounds, because
  interpolation within a bucket is linear. This is guidance; the evaluator
  cannot detect it.
- Label values are the manifest's literal strings, escaped for PromQL.
  Exactly one series per `service`/`bins`/`window` is expected; the query's
  `max()` over several is a conservative fallback, not a supported shape.
- The single gauges `gen_ai_calibration_error{service}` and
  `gen_ai_feedback_latency_seconds{service}` are documented as superseded.
  The latter's base name is reused by the histogram above, which must be
  exposed as a histogram (`_bucket` including `le="+Inf"`, `_count`, `_sum`
  series); a plain gauge of that name is not read. Sharing the base name
  means an exporter cannot register both: it cuts over in one release.
- segments, stability, audit_backlog: no series yet (`no_data_source`).

## 5. Evaluator and outcome model (nthlayer-common 5.2)

All types are frozen dataclasses in `nthlayer_common.manifest.evaluation`:

```python
Status = Literal["within", "breach", "not_evaluable"]
MissingReason = Literal["no_data_source", "no_data", "insufficient_window"]

Missing(reason: MissingReason, detail: str = "")      # rejects an unknown reason
AtLeast(value: float)                                 # a lower bound: true value > value; finite
Samples(bounds: Mapping[str, float | Missing | AtLeast] = {},  # every type except segments: bound -> value
        overall: float | Missing | None = None,       # segments: the overall rate
        segments: Mapping[str, float | Missing] = {}) # segments: segment value -> its rate

BoundResult(bound: str, status: Status, measured: float | None, limit: float | str, reason: str | None)
SegmentResult(segment: str, status: Status, measured: float | None, reason: str | None)
ThresholdOutcome(type: str, status: Status, bounds: tuple[BoundResult, ...],
                 segments: tuple[SegmentResult, ...] = ())   # + to_dict() / from_dict()

combine(statuses: Iterable[Status]) -> Status         # E4; empty -> "not_evaluable"
evaluate_threshold(threshold: JudgmentThreshold, samples: Samples) -> ThresholdOutcome
```

A bound absent from `samples.bounds` (or a segment absent from
`samples.segments`) is treated as `Missing("no_data")`. A hand-built
threshold with a bound its type does not define, or a segments threshold
without exactly one bound, raises `ValueError` (the parsers reject both).

- **E1:** breach iff `measured > limit`; equal is within. Holds for a limit
  of 0. A lower bound `AtLeast(v)` means the measured value is strictly
  greater than `v`: it is a breach (measured `v`, reason `lower_bound`) iff
  `v >= limit`; otherwise it decides nothing and is `not_evaluable`
  (`no_data`).
- **E2:** duration limits and measured durations are compared in seconds via
  `duration_seconds`.
- **E3:** a `Missing` sample makes that bound (or segment) `not_evaluable`,
  carrying the reason; so does a non-finite value (`NaN`, `±inf`), with reason
  `no_data`. For segments the samples carry `overall` and one rate per listed
  segment value; each segment is decided independently, and a missing overall
  makes every segment `not_evaluable` with the overall's reason. For
  `metric: outcomes` a segment whose population has no elapsed outcome
  window is `not_evaluable` (CORE §5.5.1); the sampler reports it as
  `no_data`.
- **E4:** the entry's status combines bounds (and segments) with breach >
  not_evaluable > within.
- `ThresholdOutcome.to_dict()` / `from_dict()` define the assessment payload;
  a round-trip test pins them. Every emitter and reader uses them.

## 6. Sampler (workers)

`async sample(provider, service: str, threshold: JudgmentThreshold, *, now: float | None = None, retention: float | Missing | None = None, retention_check: bool = True) -> Samples`
(`provider` is a `PrometheusProvider`; `now` defaults to the current time
and exists so tests can fix it; `retention` is the cycle's one
`fetch_retention` result, `None` meaning fetch it here):

- builds each query from `THRESHOLD_SERIES` and the threshold's
  `measurement`, escaping label values (`\`, `"`, newline);
- feedback latency: ONE query per threshold,
  `sum by (le) (increase(gen_ai_feedback_latency_seconds_bucket{service="S"}[30d]))`;
  every declared quantile is computed from that bucket vector (§4), a rank in
  the `+Inf` bucket giving `AtLeast(largest finite le)`; no `+Inf` bucket or
  no observations (or a degenerate bucket set: a zero-width rank, an `le` of
  `-Inf` as the top finite boundary) → `Missing("no_data")`;
- maps each Prometheus result to its bound; tests assert the mapping from
  realistic response JSON, not just the query string (the gap that hid this
  bug: only the calibration query string was ever tested);
- an empty result or a non-finite value → `Missing("no_data")`, whose detail
  names the labels looked for (e.g. `bins`/`window`);
- a Prometheus error or timeout → `Missing("no_data", <error>)`; it never
  raises;
- a 30-day query that Prometheus cannot answer over the whole window
  (its retention, `min(prometheus_tsdb_lowest_timestamp_seconds)`, is
  shorter than the window) → `Missing("insufficient_window")`. A *young
  series* is measured: CORE §5.5.5 defines p50/p90 over ground truth that
  arrived in the last 30 days, and for a 3-day-old service that is exactly
  what the 3 days hold. Unknown retention (Prometheus not scraping itself)
  measures what it can. Retention is queried once per cycle (the phase
  passes it into `sample`), and the operator switch
  `MEASURE_RETENTION_CHECK` (default on; `off`/`false`/`0` disable, read at
  startup) skips it: behind Thanos sidecar, Mimir or Cortex that metric
  describes a local TSDB, not what the query path can see.
- segments → `Samples(overall=Missing("no_data_source"))`, which the
  evaluator turns into every listed segment `not_evaluable`;
- stability, audit_backlog → every declared bound
  `Missing("no_data_source")`. No query is sent for any of the three.

## 7. Worker loop: data flow, state, errors

Per cycle:

1. `GET /manifests`. If the call fails, the whole threshold phase is skipped
   for this cycle: no assessments, no state change, no garbage collection.
2. For each service `i` and entry `j`:
   `threshold_from_v2_entry(item, where=f"/manifests[{i}].judgment_thresholds[{j}]")`.
   A parse error logs `threshold_parse_failed` (once per change, not per
   cycle) and skips only that entry.
3. **Identity key:** `service` + `type` + a content hash of the identifying
   fields — the sorted bound *names*, `metric` and its parameter (`source`,
   `confidence_threshold`, `outcome_signal`), `segment_dimension`, sorted
   `segment_values`, `probe` (input set and frequency), measurement
   `window` / `bins`. Bound *values* are excluded, so tightening a bound
   keeps the key, and a p50 entry and a p90 entry get different keys. CORE
   §5.5 allows several entries of one type, so two entries of one service
   can still share a key (same identifying fields, different bound values).
   Within one service, in declared order:
   - the first entry with a given key keeps the bare key;
   - a later entry identical to one already seen (same canonical v2 form) is
     not evaluated again; the duplicate is logged once per change;
   - each later non-identical entry with that key gets `#1`, `#2`, … in
     declared order (`<key>#1`, `<key>#2`).

   So every declared bound of every distinct entry is evaluated (E1).
4. Sample (§6), evaluate (§5). Entries are evaluated concurrently, at most
   `MeasureModule.eval_concurrency` at a time. An entry that raises is logged
   once (`threshold_eval_failed`) and skipped; if the whole phase raises,
   the cycle logs it and runs the SLO phases with no threshold breaches.
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
   - the verdict is `quality_breach`, severity `high` for every threshold
     breach, referencing the assessment. Downstream knows only
     `low | high | critical` (bench toasts on high/critical; correlate treats
     every quality_breach as high), so no new severity value is introduced;
     graded severity belongs to the ratchet-configuration bead;
   - leaving `breach` and entering `not_evaluable` raise no verdict;
   - a key's new state is committed only once its breach verdict (if one
     fires) is accepted by core; a rejected verdict leaves the state as it
     was, so the next cycle raises it again. A rejected assessment is logged
     and does not stop evaluation (the verdict's `parent_ids` then name an
     assessment core did not store);
   - restored state is untrusted: a non-dict `threshold_state`, a non-dict
     entry, or an entry whose `service` is not a string is dropped, and a
     wrong-typed field takes its default (armed, no streak) — a corrupt entry
     can re-raise a breach, never silence one. Likewise a `/manifests` item
     that is not an object, or whose `name` is not a non-empty string, is
     skipped (logged once), never raised out of the phase;
   - the autonomy ratchet is reached only when `MEASURE_THRESHOLD_AUTONOMY`
     is on; a threshold breach then enters the existing governance phase as a
     `high`-severity breach, under the same rules as an SLO breach — including
     that an *open* threshold breach keeps counting toward later governance
     decisions (e.g. it plus a new SLO breach is a multiple-breach case). Turning it
     on does not apply the ratchet to breaches already open.
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
   BREAKING CHANGE footer and an upgrade note in workers' docs
   (`docs/upgrading-3.0.md`; workers is at 2.0.1, so the major is 3.0.0).

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
  `no_data_source`; hand-computed bucket quantiles (interpolation, a rank on
  a boundary, unsorted / duplicate / non-monotonic buckets); a rank in
  `+Inf` → lower bound, and buckets `[…, 3600, 86400, +Inf]` with most mass
  in `+Inf` against a `1d` bound → breach end to end; a label value
  containing `"` is escaped; `MEASURE_RETENTION_CHECK` off sends no
  retention query;
- cycle (real `Store`): one `quality_breach` per breach transition;
  `breach → not_evaluable → breach` raises once; flapping does not re-raise
  before 3 within cycles; absent service keeps state; removed entry retires;
  core unreachable touches nothing; a parse failure isolates one entry;
  restart does not re-raise; toggle off → no ratchet, on → ratchet; identity
  stable under segment reordering and bound changes; a rejected breach
  verdict re-raises next cycle; one raising entry, or a raising phase, does
  not stop the others or the SLO phases; corrupt restored state still runs
  the cycle; retention queried once per cycle;
- end to end: a high ECE breaches the ECE bound and only that bound;
- served-shape: a fixture built with `threshold_to_v2_entry` from the spec
  examples (exactly what core 3.0 serves) drives a cycle;
- regression: no calibration or segments threshold reaches SLO code; the old
  strict xfails are replaced by tests asserting correct behaviour.
