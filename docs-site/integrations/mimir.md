# Mimir/Cortex Integration

Push alert rules directly to Grafana Mimir or Cortex via the Ruler API.

## Overview

NthLayer can push generated alert rules directly to Mimir or Cortex, eliminating the need for manual file deployment. This is ideal for GitOps workflows where you want to:

1. Generate alerts from `service.yaml`
2. Push directly to Mimir/Cortex Ruler API
3. Rules become active immediately

## Setup

### Environment Variables

```bash
# Required: Mimir Ruler API URL
export MIMIR_RULER_URL=https://your-mimir:8080

# Optional: Multi-tenant setups
export MIMIR_TENANT_ID=your-tenant

# Optional: Authentication
export MIMIR_API_KEY=your-api-key          # Bearer token
# OR
export MIMIR_USERNAME=your-username        # Basic auth
export MIMIR_PASSWORD=your-password
```

## Usage

### Push Alerts to Mimir

```bash
nthlayer apply service.yaml --push-ruler
```

Output:
```
Applied 4 resources in 0.3s → generated/payment-api/

Pushing alerts to Mimir Ruler...
  URL: https://mimir:8080
  Tenant: my-tenant
  ✓ Pushed 2 rule group(s) to namespace 'payment-api'
```

### Combined with Grafana Push

```bash
# Push dashboards to Grafana AND alerts to Mimir
nthlayer apply service.yaml --push --push-ruler
```

## API Details

NthLayer uses the Mimir Ruler API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/rules/{namespace}` | POST | Create/update rule groups |
| `/api/v1/rules/{namespace}` | DELETE | Delete all rules in namespace |
| `/api/v1/rules/{namespace}/{groupName}` | DELETE | Delete specific group |
| `/api/v1/rules` | GET | List all rules |

The namespace is set to the service name from `service.yaml`.

## Tekton Pipeline Example

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: nthlayer-apply
spec:
  params:
    - name: service-file
      type: string
  steps:
    - name: generate-and-push
      image: python:3.11-slim
      env:
        - name: MIMIR_RULER_URL
          valueFrom:
            secretKeyRef:
              name: mimir-credentials
              key: url
        - name: MIMIR_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: mimir-credentials
              key: tenant-id
        - name: MIMIR_API_KEY
          valueFrom:
            secretKeyRef:
              name: mimir-credentials
              key: api-key
      script: |
        pip install nthlayer
        nthlayer apply $(params.service-file) --push-ruler --lint
```

## GitHub Actions Example

```yaml
jobs:
  deploy-alerts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pip install nthlayer

      - name: Generate and Push Alerts
        env:
          MIMIR_RULER_URL: ${{ secrets.MIMIR_RULER_URL }}
          MIMIR_TENANT_ID: ${{ secrets.MIMIR_TENANT_ID }}
          MIMIR_API_KEY: ${{ secrets.MIMIR_API_KEY }}
        run: |
          nthlayer apply service.yaml --push-ruler --lint
```

## Multi-Tenant Setup

For Mimir multi-tenant deployments, set the `MIMIR_TENANT_ID`:

```bash
export MIMIR_TENANT_ID=team-payments
nthlayer apply payment-api.yaml --push-ruler
```

This sets the `X-Scope-OrgID` header on all API requests.

## Cortex Compatibility

The Ruler API is compatible with both Grafana Mimir and Cortex. The same configuration works for either:

```bash
# Mimir
export MIMIR_RULER_URL=https://mimir.example.com:8080

# Cortex
export MIMIR_RULER_URL=https://cortex.example.com:9009
```

## Troubleshooting

### Connection Refused

```
✗ Mimir error: Failed to connect to Mimir at https://mimir:8080/api/v1/rules/payment-api
```

- Verify `MIMIR_RULER_URL` is correct
- Check network connectivity
- Ensure Ruler component is enabled in Mimir

### Authentication Failed

```
✗ Failed to push rules: 401 Unauthorized
```

- Verify `MIMIR_API_KEY` or `MIMIR_USERNAME`/`MIMIR_PASSWORD`
- Check tenant ID is correct for multi-tenant setups

### Invalid YAML

```
✗ Failed to push rules: 400 Bad Request - invalid rule syntax
```

- Run `nthlayer apply service.yaml --lint` first to validate
- Check PromQL queries are valid

## See Also

- [Prometheus Integration](./prometheus.md) - Query metrics for verification
- [Grafana Integration](./grafana.md) - Push dashboards
- [CLI Reference](../reference/cli.md) - Full command options
