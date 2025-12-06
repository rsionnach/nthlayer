# Grafana Integration

NthLayer generates and optionally pushes dashboards to Grafana.

## Configuration

### Via Setup Wizard

```bash
nthlayer setup
```

### Via Environment Variables

```bash
export NTHLAYER_GRAFANA_URL=http://grafana:3000
export NTHLAYER_GRAFANA_API_KEY=glsa_xxxxxxxxxxxx
export NTHLAYER_GRAFANA_ORG_ID=1  # Optional, default: 1
```

### Via Config File

```yaml
# ~/.nthlayer/config.yaml
grafana:
  default: default
  profiles:
    default:
      url: http://localhost:3000
      type: grafana
      org_id: 1
      api_key_secret: grafana/api_key
```

## Supported Backends

| Type | Description |
|------|-------------|
| `grafana` | Self-hosted Grafana |
| `grafana-cloud` | Grafana Cloud |

## Creating an API Key

1. Go to **Administration > Service accounts**
2. Create a new service account
3. Add a token with **Editor** role
4. Copy the token (starts with `glsa_`)

## Dashboard Generation

### Generate Only (Default)

```bash
nthlayer apply payment-api.yaml
```

Creates `generated/payment-api/dashboard.json` - import manually to Grafana.

### Auto-Push to Grafana

```bash
nthlayer apply payment-api.yaml --push
```

Pushes directly to Grafana API.

## Dashboard Structure

Generated dashboards include:

### SLO Metrics Row

- **Availability** - Current vs target
- **Error Budget** - Remaining budget gauge
- **Latency P99** - Current latency vs threshold

### Service Health Row

- **Request Rate** - Requests per second
- **Error Rate** - 5xx errors percentage
- **Active Connections** - Current connections
- **Saturation** - Resource utilization

### Dependencies Row

One row per dependency with technology-specific panels:

- **PostgreSQL**: Connections, replication lag, locks
- **Redis**: Memory usage, hit rate, connections
- **Kafka**: Consumer lag, partition status

## Dashboard Variables

Dashboards include variables for filtering:

| Variable | Description |
|----------|-------------|
| `$service` | Service name |
| `$environment` | Environment (dev/staging/prod) |

## Manual Import

If not using `--push`:

1. Go to **Dashboards > Import**
2. Upload `generated/<service>/dashboard.json`
3. Select Prometheus data source
4. Click **Import**

## Testing Connection

```bash
nthlayer setup --test
```

```
  Grafana (http://localhost:3000)
    [OK] Connected - Org: Main Org
```

## Troubleshooting

### Invalid API Key

```
[FAIL] Invalid API key
```

- Verify token starts with `glsa_`
- Check token has Editor role
- Ensure token isn't expired

### Dashboard Already Exists

Dashboards are upserted by UID. Existing dashboards with the same UID are updated.

### Wrong Organization

Set `NTHLAYER_GRAFANA_ORG_ID` if using multiple orgs:

```bash
export NTHLAYER_GRAFANA_ORG_ID=2
```
