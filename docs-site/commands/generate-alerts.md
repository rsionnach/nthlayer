# nthlayer generate-alerts

Generate Prometheus alert rules from a service specification.

## Synopsis

```bash
nthlayer generate-alerts <service-file> [options]
```

## Description

The `generate-alerts` command creates Prometheus alerting rules based on your service's technology stack and tier. It leverages 400+ battle-tested alert templates from the [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts) community repository.

## Options

| Option | Description |
|--------|-------------|
| `--output, -o PATH` | Output file path (default: `generated/alerts/{service}.yaml`) |
| `--env, --environment ENV` | Environment name (dev, staging, prod) |
| `--auto-env` | Auto-detect environment from CI/CD context |
| `--dry-run` | Preview alerts without writing file |
| `--runbook-url URL` | Base URL for runbook links |
| `--notification-channel CHANNEL` | Notification channel (slack, etc.) |

## Examples

### Basic Generation

```bash
nthlayer generate-alerts services/payment-api.yaml
```

Generates alerts based on the service's technology stack:

```yaml
# generated/alerts/payment-api.yaml
groups:
  - name: payment-api-alerts
    rules:
      - alert: PaymentAPIHighErrorRate
        expr: |
          sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="payment-api"}[5m])) > 0.01
        for: 5m
        labels:
          severity: critical
          service: payment-api
          tier: "1"
        annotations:
          summary: "High error rate on payment-api"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 1%)"
          runbook_url: "https://runbooks.example.com/payment-api/high-error-rate"

      - alert: PaymentAPIHighLatency
        expr: |
          histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le)) > 0.5
        for: 5m
        labels:
          severity: warning
          service: payment-api
        annotations:
          summary: "High p99 latency on payment-api"
          description: "p99 latency is {{ $value | humanizeDuration }}"
```

### With Runbook URLs

```bash
nthlayer generate-alerts services/api.yaml \
  --runbook-url https://wiki.example.com/runbooks
```

### Preview Mode

```bash
nthlayer generate-alerts services/api.yaml --dry-run
```

## Technology-Specific Alerts

Based on the `technologies` section in your service.yaml, appropriate alerts are generated:

| Technology | Alert Examples |
|------------|---------------|
| PostgreSQL | Connection pool exhaustion, replication lag, slow queries |
| Redis | Memory usage, connection count, evictions |
| Kafka | Consumer lag, partition offline, under-replicated |
| Kubernetes | Pod restarts, OOMKilled, resource limits |
| HTTP/API | Error rate, latency percentiles, availability |

### Example Service with Technologies

```yaml
service:
  name: payment-api
  tier: tier-1
  team: payments-team

technologies:
  - name: postgresql
    role: primary-database
  - name: redis
    role: cache
  - name: kafka
    role: event-bus
```

This generates alerts for the service itself plus technology-specific alerts for PostgreSQL, Redis, and Kafka.

## Tier-Based Severity

Alert severity is adjusted based on service tier:

| Tier | Error Rate Critical | Latency Warning |
|------|---------------------|-----------------|
| Tier 1 (Critical) | > 0.1% | > 200ms |
| Tier 2 (Standard) | > 1% | > 500ms |
| Tier 3 (Low) | > 5% | > 1s |

## CI/CD Integration

```yaml
jobs:
  generate:
    steps:
      - name: Generate Alerts
        run: |
          nthlayer generate-alerts services/api.yaml \
            --runbook-url ${{ vars.RUNBOOK_BASE_URL }} \
            --env prod
```

## Output Structure

```
generated/
└── alerts/
    ├── payment-api.yaml
    ├── user-service.yaml
    └── order-service.yaml
```

## See Also

- [nthlayer apply](apply.md) - Generate all resources at once
- [Technology Templates](../integrations/technologies.md) - Available templates
- [nthlayer generate-loki-alerts](generate-loki-alerts.md) - Log-based alerts
