# nthlayer blast-radius

Calculate the deployment blast radius for a service by analyzing its dependency graph.

Understanding blast radius helps teams assess the potential impact of changes before deployment.

## Usage

```bash
nthlayer blast-radius <service.yaml> [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--prometheus-url, -p URL` | Prometheus server URL |
| `--env ENVIRONMENT` | Environment name (dev, staging, prod) |
| `--provider {prometheus,kubernetes,backstage,all}` | Dependency provider to use (default: all) |
| `--k8s-namespace NAMESPACE` | Kubernetes namespace to search (default: all) |
| `--backstage-url URL` | Backstage catalog URL |
| `--depth, -d DEPTH` | Maximum depth for transitive analysis (default: 10) |
| `--format {table,json}` | Output format (default: table) |
| `--demo` | Show demo output with sample data |

## Examples

### Calculate Blast Radius

```bash
nthlayer blast-radius checkout-service.yaml
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Blast Radius Analysis: checkout-service                                       │
╰──────────────────────────────────────────────────────────────────────────────╯

Impact Summary:
  Direct dependents:     3 services
  Transitive dependents: 7 services
  Total blast radius:    10 services

Risk Assessment: MEDIUM

Affected Services by Tier:
┌────────────────────┬──────────┬───────────┬─────────────────────────────────┐
│ Service            │ Tier     │ Distance  │ Impact Path                     │
├────────────────────┼──────────┼───────────┼─────────────────────────────────┤
│ web-frontend       │ critical │ 1         │ checkout → web-frontend         │
│ mobile-app         │ critical │ 1         │ checkout → mobile-app           │
│ order-service      │ standard │ 1         │ checkout → order-service        │
│ notification-svc   │ standard │ 2         │ checkout → order → notification │
│ analytics          │ low      │ 2         │ checkout → order → analytics    │
│ reporting          │ low      │ 3         │ ... → analytics → reporting     │
└────────────────────┴──────────┴───────────┴─────────────────────────────────┘

Recommendations:
  • 2 critical-tier services affected - consider staged rollout
  • Test changes in staging with mobile-app integration
  • Notify platform-team (owns web-frontend)
```

### Limit Analysis Depth

```bash
# Only analyze direct dependencies (depth 1)
nthlayer blast-radius service.yaml --depth 1

# Analyze up to 3 levels deep
nthlayer blast-radius service.yaml --depth 3
```

### JSON Output

```bash
nthlayer blast-radius service.yaml --format json
```

```json
{
  "service": "checkout-service",
  "direct_dependents": 3,
  "transitive_dependents": 7,
  "total_blast_radius": 10,
  "risk_level": "medium",
  "affected_services": [
    {
      "name": "web-frontend",
      "tier": "critical",
      "distance": 1,
      "path": ["checkout-service", "web-frontend"]
    }
  ]
}
```

## Risk Assessment

Risk levels are calculated based on:

| Factor | Weight |
|--------|--------|
| Number of critical-tier dependents | 40% |
| Total blast radius size | 30% |
| Depth of dependency chain | 20% |
| Cross-team impact | 10% |

### Risk Levels

| Level | Description |
|-------|-------------|
| `LOW` | < 3 total dependents, no critical tier |
| `MEDIUM` | 3-10 dependents or 1 critical-tier service |
| `HIGH` | > 10 dependents or multiple critical-tier services |
| `CRITICAL` | Core infrastructure affecting > 50% of services |

## CI/CD Integration

### Deployment Gate

```bash
# Block deployment if blast radius exceeds threshold
BLAST_RADIUS=$(nthlayer blast-radius service.yaml --format json | jq '.total_blast_radius')

if [ "$BLAST_RADIUS" -gt 20 ]; then
  echo "Blast radius too high ($BLAST_RADIUS services) - requires approval"
  exit 1
fi
```

### GitHub Actions

```yaml
- name: Check Blast Radius
  run: |
    nthlayer blast-radius service.yaml --format json > blast-radius.json
    RISK=$(jq -r '.risk_level' blast-radius.json)
    if [ "$RISK" = "critical" ]; then
      echo "::warning::Critical blast radius - manual approval required"
    fi
```

## See Also

- [nthlayer deps](./deps.md) - View service dependencies
- [nthlayer check-deploy](./check-deploy.md) - Deployment gates
- [Deployment Gates Concept](../concepts/deployment-gates.md)
