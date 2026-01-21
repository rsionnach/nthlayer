# nthlayer generate-dashboard

Generate Grafana dashboards from a service specification.

## Synopsis

```bash
nthlayer generate-dashboard <service-file> [options]
```

## Description

The `generate-dashboard` command creates Grafana dashboards tailored to your service's technology stack. Dashboards include SLO panels, health metrics, and technology-specific visualizations.

## Options

| Option | Description |
|--------|-------------|
| `--output, -o PATH` | Output file path (default: `generated/dashboards/{service}.json`) |
| `--env, --environment ENV` | Environment name (dev, staging, prod) |
| `--auto-env` | Auto-detect environment from CI/CD context |
| `--dry-run` | Print dashboard JSON without writing file |
| `--full` | Include all template panels (default: overview only) |
| `--prometheus-url, -p URL` | Prometheus URL for metric discovery |

## Examples

### Basic Generation

```bash
nthlayer generate-dashboard services/payment-api.yaml
```

Generates a Grafana dashboard JSON:

```json
{
  "title": "payment-api - Service Dashboard",
  "uid": "payment-api-dashboard",
  "tags": ["nthlayer", "payment-api", "tier-1"],
  "panels": [
    {
      "title": "Error Budget Remaining",
      "type": "gauge",
      "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
    },
    {
      "title": "Request Rate",
      "type": "timeseries",
      "gridPos": {"h": 8, "w": 12, "x": 6, "y": 0}
    }
  ]
}
```

### Full Dashboard

```bash
nthlayer generate-dashboard services/api.yaml --full
```

Includes all technology-specific panels (28+ panels vs 6-12 in overview mode).

### Preview Mode

```bash
nthlayer generate-dashboard services/api.yaml --dry-run | jq .
```

### With Metric Discovery

```bash
nthlayer generate-dashboard services/api.yaml \
  --prometheus-url http://prometheus:9090
```

When Prometheus URL is provided, the command validates that dashboard metrics exist.

## Dashboard Panels

### Overview Mode (Default)

| Panel | Description |
|-------|-------------|
| Error Budget | Gauge showing remaining error budget |
| SLO Status | Current SLO compliance percentage |
| Request Rate | Requests per second over time |
| Error Rate | 5xx errors as percentage |
| Latency (p50/p95/p99) | Request latency percentiles |
| Availability | Uptime percentage |

### Full Mode (`--full`)

Adds technology-specific panels:

**PostgreSQL:**
- Active connections
- Transaction rate
- Replication lag
- Cache hit ratio

**Redis:**
- Memory usage
- Hit/miss ratio
- Connected clients
- Evictions

**Kubernetes:**
- Pod status
- Resource utilization
- Restart count
- Network I/O

## Technology Templates

| Technology | Panels |
|------------|--------|
| HTTP/API | 8 panels |
| PostgreSQL | 12 panels |
| Redis | 10 panels |
| Kubernetes | 10 panels |

## Output Structure

```
generated/
└── dashboards/
    ├── payment-api.json
    ├── user-service.json
    └── order-service.json
```

## Importing to Grafana

### Via API

```bash
# Generate dashboard
nthlayer generate-dashboard services/api.yaml

# Import to Grafana
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -d @generated/dashboards/payment-api.json \
  http://grafana:3000/api/dashboards/db
```

### Via Grafana UI

1. Navigate to Dashboards > Import
2. Upload the generated JSON file
3. Select your Prometheus data source

## CI/CD Integration

```yaml
jobs:
  generate:
    steps:
      - name: Generate Dashboards
        run: |
          for service in services/*.yaml; do
            nthlayer generate-dashboard "$service" --full
          done

      - name: Upload to Grafana
        run: |
          for dashboard in generated/dashboards/*.json; do
            curl -X POST \
              -H "Authorization: Bearer ${{ secrets.GRAFANA_TOKEN }}" \
              -d @"$dashboard" \
              ${{ vars.GRAFANA_URL }}/api/dashboards/db
          done
```

## See Also

- [nthlayer apply](apply.md) - Generate all resources at once
- [Grafana Integration](../integrations/grafana.md) - Grafana setup
- [Technology Templates](../integrations/technologies.md) - Available templates
- [nthlayer generate-recording-rules](generate-recording-rules.md) - Recording rules for dashboard performance
