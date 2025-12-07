# Prometheus Integration

NthLayer uses Prometheus for metric discovery, SLO queries, and alert rules.

## Configuration

### Via Setup Wizard

```bash
nthlayer setup
```

### Via Environment Variables

```bash
export NTHLAYER_PROMETHEUS_URL=http://prometheus:9090

# If authentication required
export NTHLAYER_METRICS_USER=admin
export NTHLAYER_METRICS_PASSWORD=secret
```

### Via Config File

```yaml
# ~/.nthlayer/config.yaml
prometheus:
  default: default
  profiles:
    default:
      url: http://localhost:9090
      type: prometheus
    production:
      url: https://prometheus-prod.example.com
      type: prometheus
      username: admin
      password_secret: prometheus/password
```

## Supported Backends

| Type | Description |
|------|-------------|
| `prometheus` | Standard Prometheus server |
| `mimir` | Grafana Mimir |
| `grafana-cloud` | Grafana Cloud Prometheus |

## What NthLayer Generates

### Alert Rules

```yaml
groups:
  - name: payment-api-alerts
    rules:
      - alert: PaymentApiHighErrorRate
        expr: |
          sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m])) /
          sum(rate(http_requests_total{service="payment-api"}[5m])) > 0.01
        for: 5m
        labels:
          severity: critical
          service: payment-api
        annotations:
          summary: High error rate on payment-api
          description: Error rate is {{ $value | humanizePercentage }}
```

### Recording Rules

```yaml
groups:
  - name: payment-api-recording
    rules:
      - record: service:http_requests:rate5m
        expr: sum(rate(http_requests_total{service="payment-api"}[5m]))
      - record: service:http_errors:rate5m
        expr: sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))
      - record: service:http_latency_p99:5m
        expr: |
          histogram_quantile(0.99,
            sum by (le) (rate(http_request_duration_seconds_bucket{service="payment-api"}[5m]))
          )
```

## SLO Queries

NthLayer queries Prometheus for live SLO status:

```bash
nthlayer slo collect payment-api.yaml
```

Uses queries like:

```promql
# Availability over 30 days
avg_over_time(
  (
    sum(rate(http_requests_total{service="payment-api",status!~"5.."}[5m])) /
    sum(rate(http_requests_total{service="payment-api"}[5m]))
  )[30d:5m]
)
```

## Metric Discovery

NthLayer discovers available metrics to customize dashboards:

```bash
# Discovers metrics matching service label
nthlayer plan payment-api.yaml --discover
```

## Testing Connection

```bash
nthlayer setup --test
```

```
  Prometheus (http://localhost:9090)
    [OK] Connected (Prometheus 2.45.0)
```

## Troubleshooting

### Connection Refused

```
[FAIL] Connection refused - is Prometheus running?
```

- Verify Prometheus is running: `curl http://localhost:9090/-/healthy`
- Check firewall rules
- Verify URL is correct

### Authentication Failed

```
[FAIL] Authentication required
```

- Set `NTHLAYER_METRICS_USER` and `NTHLAYER_METRICS_PASSWORD`
- Or configure in `~/.nthlayer/config.yaml`

### No Metrics Found

- Ensure your application exports metrics with `service` label
- Check metric names match expected patterns
