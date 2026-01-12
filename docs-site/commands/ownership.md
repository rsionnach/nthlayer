# nthlayer ownership

Resolve service ownership from multiple sources with confidence-based attribution.

This command queries Backstage, PagerDuty, CODEOWNERS, and Kubernetes labels to determine who owns a service.

## Usage

```bash
nthlayer ownership <service.yaml> [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--env ENVIRONMENT` | Environment name (dev, staging, prod) |
| `--format {table,json}` | Output format (default: table) |
| `--backstage-url URL` | Backstage catalog URL |
| `--pagerduty-token TOKEN` | PagerDuty API token |
| `--k8s-namespace NAMESPACE` | Kubernetes namespace to search |
| `--codeowners-root PATH` | Root directory for CODEOWNERS file |
| `--demo` | Show demo output with sample data |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_BACKSTAGE_URL` | Default Backstage catalog URL |
| `PAGERDUTY_API_KEY` | PagerDuty API token |
| `KUBECONFIG` | Kubernetes configuration file |

## Examples

### Basic Ownership Resolution

```bash
nthlayer ownership checkout-service.yaml
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Ownership: checkout-service                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯

Primary Owner:
  Team:        payments-team
  Confidence:  0.95 (high)
  Source:      backstage

Ownership Sources:
┌─────────────────┬─────────────────┬────────────┬─────────────────────────────┐
│ Source          │ Owner           │ Confidence │ Details                     │
├─────────────────┼─────────────────┼────────────┼─────────────────────────────┤
│ Backstage       │ payments-team   │ 0.95       │ spec.owner in catalog       │
│ PagerDuty       │ payments-team   │ 0.90       │ Escalation policy owner     │
│ CODEOWNERS      │ @acme/payments  │ 0.85       │ /services/checkout/**       │
│ Kubernetes      │ team=payments   │ 0.80       │ Label on deployment         │
│ service.yaml    │ payments-team   │ 1.00       │ service.team field          │
└─────────────────┴─────────────────┴────────────┴─────────────────────────────┘

On-Call Contact:
  Name:     Jane Smith
  Email:    jane.smith@company.com
  Slack:    @jsmith
  Schedule: payments-team-primary

Escalation Path:
  1. payments-team-primary (0-15 min)
  2. payments-team-secondary (15-30 min)
  3. payments-team-manager (30+ min)
```

### JSON Output

```bash
nthlayer ownership service.yaml --format json
```

```json
{
  "service": "checkout-service",
  "primary_owner": {
    "team": "payments-team",
    "confidence": 0.95,
    "source": "backstage"
  },
  "sources": [
    {
      "source": "backstage",
      "owner": "payments-team",
      "confidence": 0.95
    }
  ],
  "on_call": {
    "name": "Jane Smith",
    "email": "jane.smith@company.com"
  }
}
```

### Demo Mode

```bash
nthlayer ownership service.yaml --demo
```

## Ownership Sources

### Backstage Catalog (0.95 confidence)

Reads `spec.owner` from Backstage catalog entities:

```yaml
# catalog-info.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout-service
spec:
  owner: payments-team
```

### PagerDuty (0.90 confidence)

Queries PagerDuty for:
- Service escalation policy owners
- On-call schedules
- Team membership

### CODEOWNERS (0.85 confidence)

Parses GitHub/GitLab CODEOWNERS file:

```
# CODEOWNERS
/services/checkout/** @acme/payments
```

### Kubernetes Labels (0.80 confidence)

Reads labels from Kubernetes resources:

```yaml
metadata:
  labels:
    team: payments
    owner: payments-team
```

### service.yaml (1.00 confidence)

Explicit declaration in the service file:

```yaml
service:
  name: checkout-service
  team: payments-team
```

## Confidence Resolution

When multiple sources provide ownership information:

1. **Unanimous** - All sources agree: highest confidence
2. **Majority** - Most sources agree: weighted average
3. **Conflict** - Sources disagree: lowest confidence, requires resolution

## Use Cases

### Incident Response

```bash
# Find who to page during an incident
nthlayer ownership failing-service.yaml --format json | jq '.on_call'
```

### Dependency Notification

```bash
# Notify owners of affected services before deployment
for dep in $(nthlayer blast-radius service.yaml --format json | jq -r '.affected_services[].name'); do
  owner=$(nthlayer ownership $dep.yaml --format json | jq -r '.primary_owner.team')
  echo "Notifying $owner about $dep"
done
```

### Ownership Audit

```bash
# Find services with unclear ownership
nthlayer ownership service.yaml --format json | jq 'select(.primary_owner.confidence < 0.8)'
```

## See Also

- [nthlayer deps](./deps.md) - View service dependencies
- [nthlayer blast-radius](./blast-radius.md) - Calculate deployment impact
- [nthlayer identity](./identity.md) - Service identity resolution
