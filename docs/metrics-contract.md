# NthLayer Metrics Contract

The three-column table mapping OTel semantic conventions → Prometheus metric names → nthlayer-generate recording rule references.

This is the integration contract between nthlayer-generate (produces rules), nthlayer-measure (queries metrics), and any service exporting metrics (fake or real).

## Traditional Service Metrics (API type)

These metrics are already OTel-aligned in generate templates.

| OTel Semantic Convention | Prometheus Metric Name | Generate Recording Rule Reference |
|--------------------------|----------------------|----------------------------------|
| `http.server.request.duration` (histogram) | `http_request_duration_seconds_bucket` | Input to `slo:latency_requests_fast:30d`, `slo:http_request_duration_seconds:p50/p95/p99` |
| `http.server.request.duration` (count) | `http_request_duration_seconds_count` | Input to `slo:latency_requests_total:30d` |
| `http.server.requests` (counter) | `http_requests_total{service, status}` | Input to `slo:requests_total:30d`, `slo:requests_success:30d` |

### Recording Rule Outputs (custom domain names — intentional)

| Recording Rule | PromQL Expression | Purpose |
|---------------|-------------------|---------|
`{w}` is the SLO's own window (`30d` when it declares none). Every `slo:*`
rule carries `service` and `slo`; the ratio rules also carry `objective`.

| Recording Rule | PromQL Expression | Purpose |
|---------------|-------------------|---------|
| `slo:requests_total:{w}` | `sum(increase(http_requests_total{service="X"}[{w}]))` | Availability denominator |
| `slo:requests_success:{w}` | `sum(increase(http_requests_total{service="X",status!~"5.."}[{w}]))` | Availability numerator |
| `slo:availability:ratio` | success / total | Availability SLO ratio (good) |
| `slo:latency_requests_total:{w}` | `sum(increase(http_request_duration_seconds_count{...}[{w}]))` | Latency denominator |
| `slo:latency_requests_fast:{w}` | `sum(increase(http_request_duration_seconds_bucket{...,le="<bound>"}[{w}]))` | Latency numerator: requests under the SLO's `threshold_ms` (see the budget note for SLOs that declare none) |
| `slo:latency:ratio` | fast / total | Latency SLO ratio (good) |
| `slo:error_requests_total:{w}`, `slo:error_requests_failed:{w}` | `sum(increase(http_requests_total{...}[{w}]))`, the same over `status=~"5.."` | Error-rate denominator and numerator |
| `slo:error_rate:ratio` | failed / total | Error-rate SLO ratio (**bad**: the budget uses `1 - ratio`) |
| `slo:sli_good:rate`, `slo:sli_total:rate` | the SLO's own good and total queries, as written | Only for an availability, latency or error_rate SLO that declares them (OpenSLO `ratioMetric`, or a legacy `indicators[]` `success_ratio`; a bad query becomes `total - bad`) |
| `slo:sli:ratio` | `sum_over_time(good[{w}]) / sum_over_time(total[{w}])` | That SLO's ratio (good); its budget comes from this, not from the canned ratio (ruling Z3) |
| `slo:error_budget_remaining:ratio` | `1 - ((1 - good_ratio) / (1 - objective/100))` | Remaining error budget, one per availability, latency and error_rate SLO (signed; see note) |
| `slo:throughput:rate5m`, `slo:throughput:compliance` | request rate; rate against the SLO's minimum | Throughput: written, but no budget (ruling D5) |
| `slo:http_request_duration_seconds:p50` | `histogram_quantile(0.5, rate(...[5m]))` | P50 latency |
| `slo:http_request_duration_seconds:p95` | `histogram_quantile(0.95, rate(...[5m]))` | P95 latency |
| `slo:http_request_duration_seconds:p99` | `histogram_quantile(0.99, rate(...[5m]))` | P99 latency |
| `service:http_requests:rate5m` | `sum(rate(http_requests_total{...}[5m]))` | Health: request rate |
| `service:http_errors:rate5m` | error rate / total rate | Health: error rate |
| `service:http_request_duration_seconds:p95` | `histogram_quantile(0.95, rate(...[5m]))` | Health: P95 latency |
| `service:http_request_duration_seconds:p99` | `histogram_quantile(0.99, rate(...[5m]))` | Health: P99 latency |

**Error budget.** `slo:error_budget_remaining:ratio` is signed: 1.0 is a full
budget, 0 spent, negative overspent. Labels: `service`, `slo` (the SLO name),
`objective`. Its name and labels are owned by nthlayer-common's
`ERROR_BUDGET_REMAINING` (`manifest/slo_series.py`; opensrm-h0at).

Since opensrm-zo0o (ruling Z1: every classical SLO is good/total against its
objective, as OpenSLO defines it), nthlayer-generate 4.1.0 writes one budget
per **availability, latency and error_rate** SLO, from that SLO's good ratio
(table above). Throughput, freshness, lag and custom SLOs get none (ruling D5;
time-slice budgets are opensrm-vcxm).

generate deliberately writes **no** budget when it cannot trust one, because a
reader treats a missing series as no data and a wrong one as an answer:

- the objective is not a success percentage in `[50, 100)` (srm/v1 keeps a
  latency bound or an error_rate maximum in `target`, opensrm-t13c);
- a latency SLO declares no `threshold_ms` and has no queries of its own
  (v2 reads the bound from the objective, opensrm-8jpp; the legacy
  `indicators[].threshold_ms` is not read, opensrm-s7b1).

Readers (nthlayer-workers 4.2.0):

- **measure** evaluates every availability, latency and error_rate SLO from
  its budget, `{service, slo}`, breaching below zero. A missing series is a
  warning and a `NO DATA` line in `evaluate-once`. Throughput, freshness, lag
  and custom SLOs are reported `NOT EVALUABLE` (no_data_source) and never
  queried.
- **correlate** takes the service's worst budget with `bottomk(1, ...)`, so
  its `error_budget_exhausted` event names the `slo`.
- **drift** analyses only SLOs Prometheus holds a budget for, found with
  `group by (slo)` over the service's budgets.

`test/test_error_budget_seam.py` checks, against the published packages, that
for every real manifest generate writes exactly the budgets measure reads. It
pins one witness per kind, and lists each budget measure asks for that
generate's guard skips, with its bead (correlate and drift build their
selectors from the same constant).

### Alert Inputs

| Prometheus Query | Source |
|-----------------|--------|
| `ALERTS{alertstate="firing"}` | Prometheus built-in alert state (nthlayer-measure reads this directly) |

## AI-Gate / Judgment SLO Metrics

### KNOWN GAP: No recording rules exist in nthlayer-generate for judgment SLOs yet.

The ai-gate spec (`examples/opensrm/ai-gate.reliability.yaml`) declares judgment SLOs (reversal_rate, high_confidence_failure) but nthlayer-generate does not yet produce recording rules for them. Calibration and feedback latency are judgment thresholds now, not SLOs (see "Judgment threshold metrics").

**Interim path for nthlayer-measure:** Query raw metrics directly until generate templates are extended.

| OTel GenAI Convention | Prometheus Metric Name (interim) | Purpose | Generate Rule |
|----------------------|----------------------------------|---------|---------------|
| `gen_ai.decision` event counter | `gen_ai_decisions_total{service, action}` | Decision count (reversal rate denominator) | **NOT YET GENERATED** |
| `gen_ai.override` event counter | `gen_ai_overrides_total{service}` | Human override count (reversal rate numerator) | **NOT YET GENERATED** |
| `gen_ai.override` with confidence > threshold | `gen_ai_overrides_hcf_total{service}` | High-confidence failure count | **NOT YET GENERATED** |
| `gen_ai.client.operation.duration` (histogram) | `gen_ai_client_operation_duration_seconds` | AI operation latency | **NOT YET GENERATED** |
| Custom: calibration error | `gen_ai_calibration_error{service}` | Expected Calibration Error | **superseded — now judgment thresholds, see 'Judgment threshold metrics'** |
| Custom: feedback latency | `gen_ai_feedback_latency_seconds{service}` | Time to ground truth | **superseded — now judgment thresholds, see 'Judgment threshold metrics'** |

### Interim Judgment SLO Queries (for nthlayer-measure Prometheus adapter)

Until generate templates produce recording rules for judgment SLOs, measure queries raw metrics:

```promql
# Reversal rate (7d window)
sum(increase(gen_ai_overrides_total{service="fraud-detect"}[7d]))
/
sum(increase(gen_ai_decisions_total{service="fraud-detect"}[7d]))

# High confidence failure rate (7d window)
sum(increase(gen_ai_overrides_hcf_total{service="fraud-detect"}[7d]))
/
sum(increase(gen_ai_decisions_total{service="fraud-detect",confidence_bucket="high"}[7d]))

# Error budget remaining (any availability, latency or error_rate SLO)
slo:error_budget_remaining:ratio{service="fraud-detect",slo="availability"}
```

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
  finite (`NaN`, `±Inf`), or the histogram has no `+Inf` bucket or no
  observations in the window.
- `beyond_top_bucket` — the quantile lies beyond the largest finite bucket
  boundary and that boundary is below the bound, so the true value is known
  only to exceed a number smaller than the limit (see below).
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
  otherwise not evaluable (`beyond_top_bucket`). PromQL's `histogram_quantile` would
  return the boundary itself and so read such a latency as within.
- Interpolation is linear within a bucket: include each declared bound
  (e.g. `3600`, `86400`) among the bucket boundaries.
- Feedback latency is observed when ground truth arrives, so the 30-day
  window is anchored on arrival (CORE §5.5.5). A young service is measured
  over the ground truth that has arrived; only when Prometheus's retention
  (`min(prometheus_tsdb_lowest_timestamp_seconds)`, queried once per cycle)
  is shorter than 30 days is the bound not evaluable
  (`insufficient_window`). The check allows one hour of slack, so a
  retention configured as exactly 30 days does not flap at block and scrape
  boundaries. When retention is unknown (Prometheus does not scrape itself,
  or reports no samples yet), the sampler measures what Prometheus returns.
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

## Labels Contract

All metrics must include at minimum:
- `service` — service name matching the OpenSRM manifest `metadata.name`

AI-gate metrics additionally include:
- `action` — decision action (approve, reject, escalate)
- `model` — model version identifier (optional but recommended)

## Fake Service Requirements (Part B)

Fake services must export metrics matching the "Prometheus Metric Name" column above. The simplest path is `prometheus_client` with matching metric names. No OTel Collector required for the initial integration.

## Migration Path

When nthlayer-generate is extended with ai-gate recording rule templates:
1. Add judgment SLO recording rules to generate output (e.g., `slo:reversal_rate:7d`, `slo:hcf_rate:7d`)
2. Update measure's Prometheus adapter to query recording rule outputs instead of raw metrics
3. Fake services continue exporting the same raw metrics (recording rules transform them)

This is a future enhancement, not a blocker for Part A integration.
