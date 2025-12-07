# nthlayer apply

Generate all reliability configs from a service specification.

## Usage

```bash
nthlayer apply <service.yaml> [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--push` | Push dashboard to Grafana after generation |
| `--output-dir DIR` | Output directory (default: `generated/<service>`) |
| `--dry-run` | Show what would be generated without writing |

## Examples

### Basic Generation

```bash
nthlayer apply payment-api.yaml
```

Output:
```
Generated: generated/payment-api/
├── dashboard.json       # Grafana dashboard
├── alerts.yaml          # Prometheus alert rules
├── slos.yaml            # OpenSLO definitions
└── recording-rules.yaml # Prometheus recording rules
```

### Push to Grafana

```bash
nthlayer apply payment-api.yaml --push
```

Requires `NTHLAYER_GRAFANA_URL` and `NTHLAYER_GRAFANA_API_KEY` to be configured.

### Custom Output Directory

```bash
nthlayer apply payment-api.yaml --output-dir ./configs/payment-api
```

## What Gets Generated

### Dashboard (dashboard.json)

A Grafana dashboard with:

- **SLO Metrics Row**: Availability, latency, error budget
- **Service Health Row**: Request rate, active connections, saturation
- **Dependencies Row**: Panels for each configured dependency (PostgreSQL, Redis, etc.)

### Alerts (alerts.yaml)

Prometheus alert rules including:

- High error rate alerts
- Latency threshold alerts
- Error budget burn rate alerts
- Dependency-specific alerts (e.g., PostgreSQL replication lag)

### SLOs (slos.yaml)

OpenSLO-compatible definitions:

```yaml
apiVersion: openslo/v1
kind: SLO
metadata:
  name: payment-api-availability
spec:
  service: payment-api
  indicator:
    metadata:
      name: availability
    spec:
      ratioMetric:
        good:
          metricSource:
            type: prometheus
            spec:
              query: sum(rate(http_requests_total{service="payment-api",status!~"5.."}[5m]))
        total:
          metricSource:
            type: prometheus
            spec:
              query: sum(rate(http_requests_total{service="payment-api"}[5m]))
  objectives:
    - target: 0.9995
      window: 30d
```

### Recording Rules (recording-rules.yaml)

Pre-aggregated metrics for dashboard performance:

```yaml
groups:
  - name: payment-api-recording
    rules:
      - record: service:http_requests:rate5m
        expr: sum(rate(http_requests_total{service="payment-api"}[5m]))
      - record: service:http_errors:rate5m
        expr: sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))
```

## See Also

- [Service YAML Schema](../reference/service-yaml.md) - Full spec reference
- [CLI Reference](../reference/cli.md) - All commands
