# NthLayer Service Definitions

This directory contains example service definition files.

## File Structure

Each service is defined in a single YAML file with:

1. **Service Context** (declared once):
   - `name` - Service identifier (lowercase-with-hyphens)
   - `team` - Owning team
   - `tier` - critical | standard | low
   - `type` - api | background-job | pipeline | web | database

2. **Resources** (optional):
   - `SLO` - Service Level Objectives
   - `PagerDuty` - PagerDuty integration
   - `Dependencies` - Service dependencies
   - `Observability` - Metrics, logs, traces config

## Examples

### Minimal Service (with template)

```yaml
service:
  name: my-api
  team: my-team
  tier: critical
  type: api
  template: critical-api  # Inherits SLOs, PagerDuty, etc.

# No resources needed - all from template!
```

### Custom Service

```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        query: |
          sum(rate(http_requests{service="{{ .service }}",code!~"5.."}[5m]))
          /
          sum(rate(http_requests{service="{{ .service }}"}[5m]))
```

## Template Variables

In any string field, you can use:
- `{{ .service }}` - Service name
- `{{ .team }}` - Team name
- `{{ .tier }}` - Service tier
- `{{ .type }}` - Service type

These are automatically substituted at generation time.

## Commands

```bash
# Validate service definition
nthlayer validate examples/services/payment-api.yaml

# Generate SLOs
nthlayer generate-slo examples/services/payment-api.yaml

# Setup PagerDuty
nthlayer setup-pagerduty examples/services/payment-api.yaml
```

## Service Examples

- `payment-api.yaml` - Critical API with custom SLOs and dependencies
- `search-api.yaml` - Critical API using template with overrides
- `notification-service.yaml` - Background job service
