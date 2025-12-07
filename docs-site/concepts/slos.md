# SLOs & Error Budgets

Service Level Objectives (SLOs) are the foundation of reliability engineering.

## What is an SLO?

An SLO is a target for service reliability, expressed as:

> "99.9% of requests should succeed over a 30-day window"

Components:

- **Objective**: The target (99.9%)
- **Indicator**: What we measure (successful requests)
- **Window**: Time period (30 days)

## Error Budgets

The error budget is the inverse of your SLO:

```
Error Budget = 100% - SLO Objective
```

For a 99.9% SLO over 30 days:

```
Error Budget = 0.1% × 30 days × 24 hours × 60 minutes
             = 43.2 minutes of allowed downtime
```

## How NthLayer Uses SLOs

### 1. Automatic Generation

Define your tier, get sensible defaults:

```yaml
name: payment-api
tier: critical  # Gets 99.95% availability target
type: api
```

### 2. Dashboard Visualization

Generated dashboards show:

- Current SLO compliance
- Error budget remaining
- Burn rate trends

### 3. Portfolio View

See all services at once:

```bash
nthlayer portfolio
```

### 4. Live Queries

Query Prometheus for real-time status:

```bash
nthlayer slo collect payment-api.yaml
```

## SLO Types

### Availability SLO

Percentage of successful requests:

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="$service",status!~"5.."}[5m])) /
          sum(rate(http_requests_total{service="$service"}[5m]))
```

### Latency SLO

Percentage of requests under a threshold:

```yaml
resources:
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      threshold_ms: 200
      indicator:
        type: latency
        percentile: 99
        query: |
          histogram_quantile(0.99,
            sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m]))
          )
```

### Throughput SLO

Minimum requests/operations per second:

```yaml
resources:
  - kind: SLO
    name: throughput
    spec:
      objective: 99.0
      window: 30d
      threshold_rps: 100
      indicator:
        type: throughput
        query: sum(rate(http_requests_total{service="$service"}[5m]))
```

## Tier-Based Defaults

| Tier | Availability | Latency (p99) | Error Budget |
|------|--------------|---------------|--------------|
| **Critical** | 99.95% | 200ms | 21.6 min/month |
| **Standard** | 99.9% | 500ms | 43.2 min/month |
| **Low** | 99.5% | 1000ms | 216 min/month |

## Budget Consumption

NthLayer tracks how much budget has been consumed:

| Status | Budget Consumed | Action |
|--------|-----------------|--------|
| **Healthy** | < 80% | Continue normal development |
| **Warning** | 80-100% | Slow down, focus on stability |
| **Critical** | 100-150% | Freeze changes, investigate |
| **Exhausted** | > 150% | Incident mode, all hands |

## Best Practices

### 1. Start Conservative

Begin with achievable targets and tighten over time:

```yaml
# Start here
tier: standard  # 99.9%

# After proving stability
tier: critical  # 99.95%
```

### 2. Match Business Impact

Tier should reflect business criticality:

- **Critical**: Payment processing, authentication
- **Standard**: Main application features
- **Low**: Internal tools, analytics

### 3. Use Multiple SLOs

Cover different failure modes:

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95

  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      threshold_ms: 200

  - kind: SLO
    name: latency-p50
    spec:
      objective: 99.9
      threshold_ms: 50
```

### 4. Review Regularly

Use the portfolio view for weekly reviews:

```bash
nthlayer portfolio --format json > slo-review-$(date +%Y%m%d).json
```

## Further Reading

- [Google SRE Book - SLOs](https://sre.google/sre-book/service-level-objectives/)
- [The Art of SLOs](https://sre.google/workbook/implementing-slos/)
