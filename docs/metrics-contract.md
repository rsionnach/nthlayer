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
| `slo:requests_total:30d` | `sum(increase(http_requests_total{service="X"}[30d]))` | Availability denominator |
| `slo:requests_success:30d` | `sum(increase(http_requests_total{service="X",status!~"5.."}[30d]))` | Availability numerator |
| `slo:availability:ratio` | success / total | Availability SLO ratio |
| `slo:error_budget:ratio` | `1 - ((1 - availability) / (1 - objective))` | Remaining error budget |
| `slo:latency_requests_total:30d` | `sum(increase(http_request_duration_seconds_count{...}[30d]))` | Latency denominator |
| `slo:latency_requests_fast:30d` | `sum(increase(http_request_duration_seconds_bucket{...,le="0.5"}[30d]))` | Latency numerator (requests under threshold) |
| `slo:latency:ratio` | fast / total | Latency SLO ratio |
| `slo:http_request_duration_seconds:p50` | `histogram_quantile(0.5, rate(...[5m]))` | P50 latency |
| `slo:http_request_duration_seconds:p95` | `histogram_quantile(0.95, rate(...[5m]))` | P95 latency |
| `slo:http_request_duration_seconds:p99` | `histogram_quantile(0.99, rate(...[5m]))` | P99 latency |
| `service:http_requests:rate5m` | `sum(rate(http_requests_total{...}[5m]))` | Health: request rate |
| `service:http_errors:rate5m` | error rate / total rate | Health: error rate |
| `service:http_request_duration_seconds:p95` | `histogram_quantile(0.95, rate(...[5m]))` | Health: P95 latency |
| `service:http_request_duration_seconds:p99` | `histogram_quantile(0.99, rate(...[5m]))` | Health: P99 latency |

### Alert Inputs

| Prometheus Query | Source |
|-----------------|--------|
| `ALERTS{alertstate="firing"}` | Prometheus built-in alert state (nthlayer-measure reads this directly) |

## AI-Gate / Judgment SLO Metrics

### KNOWN GAP: No recording rules exist in nthlayer-generate for judgment SLOs yet.

The ai-gate spec (`examples/opensrm/ai-gate.reliability.yaml`) declares judgment SLOs (reversal_rate, high_confidence_failure, calibration, feedback_latency) but nthlayer-generate does not yet produce recording rules for them.

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

# Error budget remaining (availability)
slo:error_budget:ratio{service="fraud-detect", slo="availability"}
```

## Judgment threshold metrics (opensrm-g32d)

Judgment thresholds (OPENSRM-CORE-v2 §5.5) are bounds on error magnitudes,
evaluated by nthlayer-workers per §5.5.6. The bound → series table below is
defined in code as `nthlayer_common.manifest.THRESHOLD_SERIES`; that table is
the source of truth and this section documents it. Each threshold is
evaluated every measure cycle and the result is emitted as a
`judgment_threshold_evaluation` assessment, including when it is not
evaluable.

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
  `_sum` series; the query reads `_bucket`.
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
