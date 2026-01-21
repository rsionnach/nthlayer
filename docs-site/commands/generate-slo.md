# nthlayer generate-slo

Generate SLO definitions from a service specification.

## Synopsis

```bash
nthlayer generate-slo <service-file> [options]
```

## Description

The `generate-slo` command creates SLO definitions from your service.yaml specification. It supports multiple output formats for different SLO tooling ecosystems.

## Options

| Option | Description |
|--------|-------------|
| `--output DIR` | Output directory for generated files |
| `--format FORMAT` | Output format: `sloth` (default), `prometheus`, `openslo` |
| `--env, --environment ENV` | Environment name (dev, staging, prod) |
| `--auto-env` | Auto-detect environment from CI/CD context |
| `--dry-run` | Preview without writing files |

## Examples

### Basic Generation

```bash
nthlayer generate-slo services/payment-api.yaml
```

Generates SLO definitions in the default Sloth format:

```yaml
# generated/slos/payment-api.yaml
version: prometheus/v1
service: payment-api
slos:
  - name: availability
    objective: 99.9
    description: "Payment API availability SLO"
    sli:
      events:
        error_query: sum(rate(http_requests_total{service="payment-api",status=~"5.."}[{{.window}}]))
        total_query: sum(rate(http_requests_total{service="payment-api"}[{{.window}}]))
    alerting:
      name: PaymentAPIAvailability
      page_alert:
        labels:
          severity: critical
      ticket_alert:
        labels:
          severity: warning
```

### Prometheus Native Format

```bash
nthlayer generate-slo services/api.yaml --format prometheus
```

Generates Prometheus recording rules directly:

```yaml
groups:
  - name: payment-api-slo
    rules:
      - record: slo:sli_error:ratio_rate5m
        expr: |
          sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="payment-api"}[5m]))
        labels:
          service: payment-api
          slo: availability
```

### OpenSLO Format

```bash
nthlayer generate-slo services/api.yaml --format openslo
```

```yaml
apiVersion: openslo/v1
kind: SLO
metadata:
  name: payment-api-availability
spec:
  service: payment-api
  indicator:
    metadata:
      name: availability-ratio
    spec:
      ratioMetric:
        counter: true
        good:
          metricSource:
            type: Prometheus
            spec:
              query: sum(rate(http_requests_total{service="payment-api",status!~"5.."}[{{.window}}]))
        total:
          metricSource:
            type: Prometheus
            spec:
              query: sum(rate(http_requests_total{service="payment-api"}[{{.window}}]))
  objectives:
    - displayName: 99.9% Availability
      target: 0.999
```

### Environment-Specific Generation

```bash
# Generate for production
nthlayer generate-slo services/api.yaml --env prod

# Auto-detect from CI/CD
nthlayer generate-slo services/api.yaml --auto-env
```

### Preview Mode

```bash
nthlayer generate-slo services/api.yaml --dry-run
```

Outputs the generated YAML to stdout without writing files.

## Output Structure

Default output directory structure:

```
generated/
└── slos/
    ├── payment-api.yaml
    ├── user-service.yaml
    └── order-service.yaml
```

## Service YAML Reference

SLOs are defined in the `slos` section of your service.yaml:

```yaml
service:
  name: payment-api
  tier: tier-1
  team: payments-team

slos:
  - name: availability
    objective: 99.9
    window: 30d
    indicator:
      type: availability
      query: "sum(rate(http_requests_total{status!~'5..'}[5m])) / sum(rate(http_requests_total[5m]))"

  - name: latency-p99
    objective: 99.0
    window: 30d
    indicator:
      type: latency
      threshold: 500ms
      query: "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"
```

## CI/CD Integration

```yaml
jobs:
  generate:
    steps:
      - name: Generate SLOs
        run: |
          nthlayer generate-slo services/api.yaml \
            --format sloth \
            --env ${{ github.ref == 'refs/heads/main' && 'prod' || 'staging' }}
```

## See Also

- [nthlayer apply](apply.md) - Generate all resources at once
- [SLOs & Error Budgets](../concepts/slos.md) - Understanding SLOs
- [Service YAML Schema](../reference/service-yaml.md) - Full schema reference
