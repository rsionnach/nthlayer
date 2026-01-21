# nthlayer identity

Service identity resolution and management for consistent naming across systems.

Services often have different names across systems (Kubernetes, Prometheus, Backstage, etc.). This command helps resolve and normalize service identities.

## Usage

```bash
nthlayer identity <subcommand> [options]
```

## Subcommands

### resolve

Resolve a service name to its canonical identity.

```bash
nthlayer identity resolve <service-name>
```

### list

List all known service identities.

```bash
nthlayer identity list
```

### normalize

Show how a service name gets normalized.

```bash
nthlayer identity normalize <service-name>
```

### add-mapping

Add an explicit identity mapping.

```bash
nthlayer identity add-mapping <alias> <canonical-name>
```

## Examples

### Resolve Service Identity

```bash
nthlayer identity resolve checkout-svc
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Identity Resolution: checkout-svc                                             │
╰──────────────────────────────────────────────────────────────────────────────╯

Canonical Name: checkout-service

Known Aliases:
  • checkout-svc (kubernetes deployment)
  • checkout_service (prometheus metrics)
  • CheckoutService (backstage)

Resolution Path:
  Input: checkout-svc
  Normalized: checkout-svc
  Matched: checkout-service (similarity: 0.92)
  Canonical: checkout-service
```

### List All Identities

```bash
nthlayer identity list
```

Output:
```
Known Service Identities:
┌─────────────────────┬────────────────────────────────────────────────────────┐
│ Canonical Name      │ Aliases                                                │
├─────────────────────┼────────────────────────────────────────────────────────┤
│ checkout-service    │ checkout-svc, checkout_service, CheckoutService        │
│ payment-api         │ payment-service, payments-api, PaymentAPI              │
│ user-service        │ user-svc, users, UserService                           │
│ order-service       │ orders, order-api, OrderService                        │
└─────────────────────┴────────────────────────────────────────────────────────┘
```

### Show Normalization

```bash
nthlayer identity normalize "Payment-API_v2"
```

Output:
```
Normalization Steps:
  1. Input:      "Payment-API_v2"
  2. Lowercase:  "payment-api_v2"
  3. Normalize:  "payment-api-v2"
  4. Strip:      "payment-api"
  5. Canonical:  "payment-api"
```

### Add Custom Mapping

```bash
nthlayer identity add-mapping "legacy-checkout" "checkout-service"
```

Output:
```
Added mapping: legacy-checkout → checkout-service
```

## Normalization Rules

Service names are normalized using these rules:

| Rule | Example |
|------|---------|
| Lowercase | `PaymentAPI` → `paymentapi` |
| Replace underscores | `payment_api` → `payment-api` |
| Strip version suffixes | `service-v2` → `service` |
| Strip environment suffixes | `service-prod` → `service` |
| Strip common suffixes | `payment-service` → `payment` (optional) |

## Identity Sources

Identities are discovered from:

1. **service.yaml** - Explicit `service.name` declaration
2. **Backstage** - Catalog entity names
3. **Kubernetes** - Deployment/Service names
4. **Prometheus** - Metric label values

## Configuration

### Custom Mappings File

Create `.nthlayer/identity-mappings.yaml`:

```yaml
mappings:
  # Explicit aliases
  legacy-checkout: checkout-service
  old-payment-system: payment-api

  # Regex patterns
  patterns:
    - match: "^(.+)-prod$"
      canonical: "$1"
    - match: "^(.+)_service$"
      canonical: "$1-service"
```

### Environment-Specific Names

```yaml
# service.yaml
service:
  name: checkout-service
  identity:
    kubernetes: checkout-svc
    prometheus: checkout_service
    backstage: CheckoutService
```

## Use Cases

### Cross-System Correlation

```bash
# Find all references to a service across systems
canonical=$(nthlayer identity resolve "$ALERT_SERVICE" | grep "Canonical" | awk '{print $3}')
echo "Looking for $canonical in all systems..."
```

### Metric Queries

```bash
# Get the Prometheus-style name for queries
prom_name=$(nthlayer identity normalize "$SERVICE" --style prometheus)
curl "$PROMETHEUS_URL/api/v1/query?query=up{service=\"$prom_name\"}"
```

### Service Discovery

```bash
# Resolve service name from Kubernetes event
k8s_name=$(kubectl get events -o json | jq -r '.items[0].involvedObject.name')
canonical=$(nthlayer identity resolve "$k8s_name")
```

## See Also

- [nthlayer ownership](./ownership.md) - Find service owners
- [nthlayer deps](./deps.md) - View service dependencies
- [Service YAML Schema](../reference/service-yaml.md)
