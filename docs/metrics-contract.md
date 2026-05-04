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
| Custom: calibration error | `gen_ai_calibration_error{service}` | Expected Calibration Error | **NOT YET GENERATED** |
| Custom: feedback latency | `gen_ai_feedback_latency_seconds{service}` | Time to ground truth | **NOT YET GENERATED** |

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
