# nthlayer slo

Query and manage SLOs for individual services.

## Commands

```bash
nthlayer slo show <service.yaml>     # Show SLO definitions
nthlayer slo list <service.yaml>     # List SLOs briefly
nthlayer slo collect <service.yaml>  # Query live metrics from Prometheus
```

## nthlayer slo show

Display detailed SLO information:

```bash
nthlayer slo show payment-api.yaml
```

```
================================================================================
  SLOs for payment-api
================================================================================

availability
  Type: availability
  Objective: 99.95%
  Window: 30 days
  Error Budget: 21.6 minutes/month

latency-p99
  Type: latency
  Objective: 99.0% of requests < 200ms
  Window: 30 days
  Percentile: p99
```

## nthlayer slo list

Brief listing:

```bash
nthlayer slo list payment-api.yaml
```

```
payment-api SLOs:
  - availability: 99.95% (30d)
  - latency-p99: 99.0% < 200ms (30d)
```

## nthlayer slo collect

Query live metrics from Prometheus:

```bash
nthlayer slo collect payment-api.yaml
```

```
================================================================================
  Live SLO Status: payment-api
================================================================================

availability
  Current: 99.92%
  Target: 99.95%
  Status: WARNING (approaching budget)
  Budget Consumed: 87.5%
  Budget Remaining: 2.7 hours

latency-p99
  Current: 185ms
  Target: 200ms
  Status: HEALTHY
  Budget Consumed: 45.2%
  Budget Remaining: 11.8 hours
```

### Options

| Option | Description |
|--------|-------------|
| `--prometheus-url URL` | Prometheus server URL |
| `--window DURATION` | Query window (default: 30d) |

### Environment Variables

```bash
export NTHLAYER_PROMETHEUS_URL=http://prometheus:9090
```

## Understanding SLO Status

| Status | Meaning |
|--------|---------|
| **HEALTHY** | < 80% budget consumed |
| **WARNING** | 80-100% budget consumed |
| **CRITICAL** | 100-150% budget consumed |
| **EXHAUSTED** | > 150% budget consumed |

## Error Budget Calculation

For a 99.95% availability SLO over 30 days:

```
Error Budget = (1 - 0.9995) × 30 days × 24 hours × 60 minutes
             = 0.0005 × 43,200 minutes
             = 21.6 minutes
```

## See Also

- [nthlayer portfolio](portfolio.md) - Org-wide SLO view
- [SLOs & Error Budgets](../concepts/slos.md) - Concepts
