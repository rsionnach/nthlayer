# nthlayer validate-slo

Validate that SLO metrics exist in Prometheus before deployment.

This command checks that all metrics referenced in SLO definitions actually exist and are queryable, preventing broken SLO dashboards and alerts.

## Usage

```bash
nthlayer validate-slo <service.yaml> [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--env ENVIRONMENT` | Environment name (dev, staging, prod) |
| `--format {table,json}` | Output format (default: table) |
| `--prometheus-url URL` | Prometheus server URL |
| `--demo` | Show demo output with sample data |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PROMETHEUS_URL` | Default Prometheus URL |
| `PROMETHEUS_USERNAME` | Basic auth username |
| `PROMETHEUS_PASSWORD` | Basic auth password |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All SLO metrics exist and are valid |
| `1` | Some metrics missing (deployment may fail) |
| `2` | Critical SLO metrics missing (block deployment) |

## Examples

### Basic Validation

```bash
nthlayer validate-slo checkout-service.yaml --prometheus-url http://prometheus:9090
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ SLO Validation: checkout-service                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

Target: http://prometheus:9090
Environment: production

SLO: availability (99.95% target)
  Indicator: success_ratio
  ✓ total_query: sum(rate(http_requests_total{service="checkout"}[5m]))
    └─ Metric: http_requests_total ✓ exists (1.2M samples)
  ✓ good_query: sum(rate(http_requests_total{service="checkout",status!~"5.."}[5m]))
    └─ Metric: http_requests_total ✓ exists

SLO: latency (p99 < 200ms)
  Indicator: latency
  ✓ query: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{...}[5m]))
    └─ Metric: http_request_duration_seconds_bucket ✓ exists

Summary:
  SLOs validated: 2
  Metrics checked: 3
  All metrics exist ✓

✓ SLO validation passed - safe to deploy
```

### Missing Metrics

When metrics are missing:

```
SLO: availability (99.95% target)
  Indicator: success_ratio
  ✗ total_query: sum(rate(api_requests_total{service="checkout"}[5m]))
    └─ Metric: api_requests_total ✗ NOT FOUND

    Suggestions:
    • Did you mean: http_requests_total?
    • Check metric name in application instrumentation
    • Ensure service label matches: service="checkout"

Summary:
  SLOs validated: 2
  Metrics checked: 3
  Missing: 1 (critical)

✗ SLO validation failed - missing critical metrics
```

### JSON Output

```bash
nthlayer validate-slo service.yaml --format json
```

```json
{
  "service": "checkout-service",
  "prometheus_url": "http://prometheus:9090",
  "valid": true,
  "slos": [
    {
      "name": "availability",
      "target": 99.95,
      "valid": true,
      "metrics": [
        {
          "name": "http_requests_total",
          "exists": true,
          "sample_count": 1200000
        }
      ]
    }
  ],
  "summary": {
    "slos_validated": 2,
    "metrics_checked": 3,
    "metrics_missing": 0
  }
}
```

### Demo Mode

```bash
nthlayer validate-slo service.yaml --demo
```

## What Gets Validated

### SLO Indicator Metrics

All metrics referenced in SLO indicator queries:

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      indicators:
        - type: availability
          success_ratio:
            total_query: sum(rate(http_requests_total{service="checkout"}[5m]))
            good_query: sum(rate(http_requests_total{service="checkout",status!~"5.."}[5m]))
```

### Recording Rule Dependencies

If SLOs use recording rules, validates those exist too:

```yaml
# If SLO references a recording rule
total_query: checkout:requests:rate5m
# Validates that checkout:requests:rate5m exists
```

### Label Consistency

Checks that label selectors match existing label values:

```yaml
# Validates that service="checkout" exists in the metric
total_query: sum(rate(http_requests_total{service="checkout"}[5m]))
```

## Validation vs Verification

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `validate-slo` | Check SLO metric existence | Before deploying SLO configs |
| `verify` | Full contract verification | Before promoting to production |

Use `validate-slo` as a quick check during development. Use `verify` in CI/CD pipelines for comprehensive validation.

## CI/CD Integration

### Pre-Deployment Check

```bash
# Validate before deploying Prometheus rules
nthlayer validate-slo service.yaml --prometheus-url $PROMETHEUS_URL

if [ $? -ne 0 ]; then
  echo "SLO metrics missing - check instrumentation"
  exit 1
fi

# Safe to deploy
kubectl apply -f generated/recording-rules.yaml
```

### GitHub Actions

```yaml
- name: Validate SLO Metrics
  run: |
    nthlayer validate-slo service.yaml \
      --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
      --format json > slo-validation.json

    if [ $(jq '.valid' slo-validation.json) != "true" ]; then
      echo "::error::SLO metrics validation failed"
      exit 1
    fi
```

## Troubleshooting

### Metric Not Found

1. **Check metric name** - Typos in metric names are common
2. **Check labels** - Ensure label selectors match your instrumentation
3. **Check time range** - New metrics may not have data yet
4. **Check scrape config** - Ensure Prometheus is scraping the target

### Label Mismatch

```bash
# List available label values
curl "$PROMETHEUS_URL/api/v1/label/service/values"
```

### Recording Rule Missing

```bash
# Check if recording rule exists
curl "$PROMETHEUS_URL/api/v1/rules" | jq '.data.groups[].rules[] | select(.name == "checkout:requests:rate5m")'
```

## See Also

- [nthlayer verify](./verify.md) - Full contract verification
- [nthlayer apply](./apply.md) - Generate SLO configs
- [SLO Concepts](../concepts/slos.md) - Understanding SLOs
