# nthlayer generate-recording-rules

Generate Prometheus recording rules from a service specification.

## Synopsis

```bash
nthlayer generate-recording-rules <service-file> [options]
```

## Description

The `generate-recording-rules` command creates Prometheus recording rules that pre-compute expensive queries. This dramatically improves dashboard performance and enables efficient SLO calculations.

Recording rules pre-aggregate metrics so dashboards load in milliseconds instead of seconds, especially for high-cardinality data.

## Options

| Option | Description |
|--------|-------------|
| `--output, -o PATH` | Output file path (default: `generated/recording-rules/{service}.yaml`) |
| `--env, --environment ENV` | Environment name (dev, staging, prod) |
| `--auto-env` | Auto-detect environment from CI/CD context |
| `--dry-run` | Print YAML without writing file |

## Examples

### Basic Generation

```bash
nthlayer generate-recording-rules services/payment-api.yaml
```

Generates recording rules:

```yaml
# generated/recording-rules/payment-api.yaml
groups:
  - name: payment-api-recording-rules
    interval: 30s
    rules:
      # Request rate (pre-aggregated)
      - record: service:http_requests:rate5m
        expr: sum(rate(http_requests_total{service="payment-api"}[5m]))
        labels:
          service: payment-api

      # Error rate
      - record: service:http_errors:rate5m
        expr: sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))
        labels:
          service: payment-api

      # Error ratio (for SLO)
      - record: service:http_errors:ratio_rate5m
        expr: |
          service:http_errors:rate5m{service="payment-api"}
          /
          service:http_requests:rate5m{service="payment-api"}
        labels:
          service: payment-api

      # Latency percentiles
      - record: service:http_request_duration_seconds:p50
        expr: histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le))
        labels:
          service: payment-api

      - record: service:http_request_duration_seconds:p95
        expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le))
        labels:
          service: payment-api

      - record: service:http_request_duration_seconds:p99
        expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le))
        labels:
          service: payment-api

      # Error budget remaining
      - record: slo:error_budget_remaining:ratio
        expr: |
          1 - (
            sum_over_time(service:http_errors:ratio_rate5m{service="payment-api"}[30d])
            /
            (30 * 24 * 12)  # 30 days of 5-minute windows
          ) / (1 - 0.999)  # 99.9% SLO target
        labels:
          service: payment-api
          slo: availability
```

### Preview Mode

```bash
nthlayer generate-recording-rules services/api.yaml --dry-run
```

### Environment-Specific

```bash
nthlayer generate-recording-rules services/api.yaml --env prod
```

## Generated Metrics

| Metric | Description | Use Case |
|--------|-------------|----------|
| `service:http_requests:rate5m` | Request rate | Traffic monitoring |
| `service:http_errors:rate5m` | Error rate | Error tracking |
| `service:http_errors:ratio_rate5m` | Error ratio | SLO calculation |
| `service:http_request_duration_seconds:p50` | p50 latency | Performance baseline |
| `service:http_request_duration_seconds:p95` | p95 latency | Performance monitoring |
| `service:http_request_duration_seconds:p99` | p99 latency | SLO calculation |
| `slo:error_budget_remaining:ratio` | Budget remaining | Error budget tracking |

## Performance Impact

Recording rules provide **10x dashboard performance improvement** by:

1. **Pre-aggregation**: Expensive `rate()` and `histogram_quantile()` computed once
2. **Reduced cardinality**: Results stored with minimal labels
3. **Instant queries**: Dashboards query pre-computed metrics

**Before recording rules:**
```
Dashboard load time: 3-5 seconds
Query complexity: High (full aggregation on each load)
```

**After recording rules:**
```
Dashboard load time: 200-500ms
Query complexity: Low (simple metric lookup)
```

## Output Structure

```
generated/
└── recording-rules/
    ├── payment-api.yaml
    ├── user-service.yaml
    └── order-service.yaml
```

## Loading into Prometheus

### File-based

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/*.yaml
```

Copy generated files to your Prometheus rules directory:

```bash
cp generated/recording-rules/*.yaml /etc/prometheus/rules/
# Reload Prometheus
curl -X POST http://prometheus:9090/-/reload
```

### Mimir/Cortex Ruler API

```bash
nthlayer apply services/api.yaml --push-ruler \
  --ruler-url http://mimir:8080
```

## CI/CD Integration

```yaml
jobs:
  generate:
    steps:
      - name: Generate Recording Rules
        run: |
          nthlayer generate-recording-rules services/api.yaml

      - name: Deploy to Prometheus
        run: |
          kubectl create configmap prometheus-rules \
            --from-file=generated/recording-rules/ \
            --dry-run=client -o yaml | kubectl apply -f -

          # Trigger Prometheus reload
          kubectl rollout restart deployment/prometheus
```

## See Also

- [nthlayer apply](apply.md) - Generate all resources at once
- [nthlayer generate-dashboard](generate-dashboard.md) - Dashboard generation
- [Prometheus Integration](../integrations/prometheus.md) - Prometheus setup
- [Mimir Integration](../integrations/mimir.md) - Mimir ruler API
