# nthlayer deps

Discover and display service dependencies from multiple sources.

This command queries various dependency providers (Kubernetes, Backstage, Prometheus) to build a comprehensive view of what services depend on what.

## Usage

```bash
nthlayer deps <service.yaml> [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--prometheus-url, -p URL` | Prometheus server URL |
| `--env ENVIRONMENT` | Environment name (dev, staging, prod) |
| `--provider {prometheus,kubernetes,backstage,all}` | Dependency provider to use (default: all) |
| `--k8s-namespace NAMESPACE` | Kubernetes namespace to search (default: all) |
| `--backstage-url URL` | Backstage catalog URL |
| `--upstream, -u` | Show only upstream dependencies (what this service calls) |
| `--downstream, -d` | Show only downstream dependencies (what calls this service) |
| `--format {table,json}` | Output format (default: table) |
| `--demo` | Show demo output with sample data |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_PROMETHEUS_URL` | Default Prometheus URL |
| `NTHLAYER_BACKSTAGE_URL` | Default Backstage catalog URL |
| `KUBECONFIG` | Kubernetes configuration file |

## Examples

### Basic Dependency Discovery

```bash
nthlayer deps checkout-service.yaml
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Dependencies: checkout-service                                                │
╰──────────────────────────────────────────────────────────────────────────────╯

Upstream Dependencies (what checkout-service calls):
┌─────────────────┬──────────────┬────────────┬───────────┐
│ Service         │ Type         │ Provider   │ Confidence│
├─────────────────┼──────────────┼────────────┼───────────┤
│ payment-api     │ service      │ kubernetes │ 0.95      │
│ user-service    │ service      │ backstage  │ 0.90      │
│ postgres-main   │ datastore    │ kubernetes │ 0.95      │
│ redis-cache     │ datastore    │ prometheus │ 0.85      │
│ stripe          │ external     │ backstage  │ 0.90      │
└─────────────────┴──────────────┴────────────┴───────────┘

Downstream Dependencies (what calls checkout-service):
┌─────────────────┬──────────────┬────────────┬───────────┐
│ Service         │ Type         │ Provider   │ Confidence│
├─────────────────┼──────────────┼────────────┼───────────┤
│ mobile-app      │ service      │ prometheus │ 0.80      │
│ web-frontend    │ service      │ kubernetes │ 0.95      │
└─────────────────┴──────────────┴────────────┴───────────┘

Summary: 5 upstream, 2 downstream dependencies
```

### Filter by Provider

```bash
# Only discover from Kubernetes
nthlayer deps service.yaml --provider kubernetes

# Only discover from Backstage catalog
nthlayer deps service.yaml --provider backstage --backstage-url https://backstage.company.com
```

### JSON Output for CI/CD

```bash
nthlayer deps service.yaml --format json > dependencies.json
```

### Show Demo Data

```bash
nthlayer deps service.yaml --demo
```

## Dependency Providers

### Kubernetes Provider

Discovers dependencies from:
- Service selectors and labels
- ConfigMap references
- Environment variables pointing to other services
- Ingress/egress network policies

**Confidence:** 0.95 (high - explicit configuration)

### Backstage Provider

Discovers dependencies from:
- `spec.dependsOn` in catalog entities
- API relationships
- System membership

**Confidence:** 0.90 (high - curated catalog)

### Prometheus Provider

Discovers dependencies from:
- Metric labels showing service-to-service calls
- Request rate patterns between services

**Confidence:** 0.80-0.85 (medium - inferred from metrics)

## Dependency Types

| Type | Description |
|------|-------------|
| `service` | Another microservice |
| `datastore` | Database, cache, or storage |
| `queue` | Message queue or event bus |
| `external` | External API or third-party service |
| `infrastructure` | Infrastructure component (e.g., Vault, Consul) |

## Confidence Scores

Dependencies are assigned confidence scores (0.0-1.0):

| Range | Meaning |
|-------|---------|
| 0.90-1.0 | High confidence (explicit configuration) |
| 0.75-0.89 | Medium confidence (strong inference) |
| 0.50-0.74 | Low confidence (weak inference) |
| <0.50 | Very low (may be false positive) |

## See Also

- [nthlayer blast-radius](./blast-radius.md) - Calculate deployment impact
- [nthlayer ownership](./ownership.md) - Find service owners
- [Architecture Overview](../architecture.md) - System architecture
