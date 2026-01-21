# Service YAML Schema

Complete reference for service specification files.

## Full Schema

```yaml
# Required fields
name: string              # Service identifier (lowercase, hyphens)
tier: integer | string    # 1/2/3 or critical/standard/low
type: string              # api, worker, stream

# Optional fields
team: string              # Team name
description: string       # Human-readable description

# Technology dependencies
dependencies:
  - string                # postgresql, redis, kafka, etc.

# Custom resource definitions
resources:
  - kind: string          # SLO, Alert, Dependencies
    name: string          # Resource identifier
    spec: object          # Resource-specific configuration

# Environment-specific overrides
environments:
  production: object      # Override for production
  staging: object         # Override for staging
```

## Field Reference

### name

**Required** | `string`

Service identifier. Must be:

- Lowercase letters, numbers, hyphens only
- Cannot start or end with hyphen
- Unique within your organization

```yaml
name: payment-api        # Valid
name: Payment-API        # Invalid (uppercase)
name: -payment-api       # Invalid (starts with hyphen)
```

### tier

**Required** | `integer` or `string`

Service priority level:

| Value | Meaning | Default SLO |
|-------|---------|-------------|
| `1` / `critical` | Business-critical | 99.95% |
| `2` / `standard` | Important | 99.9% |
| `3` / `low` | Best-effort | 99.5% |

```yaml
tier: 1
# or
tier: critical
```

### type

**Required** | `string`

Service type determines default metrics and SLOs:

| Type | Description |
|------|-------------|
| `api` | HTTP/REST service |
| `worker` | Background job processor |
| `stream` | Event/message processor |

### team

**Optional** | `string`

Team responsible for the service. Used for:

- Dashboard grouping
- Alert routing
- Scorecard aggregation

```yaml
team: payments
```

### dependencies

**Optional** | `list[string]`

Technology dependencies. Each adds dashboard panels and alerts.

```yaml
dependencies:
  - postgresql
  - redis
  - kafka
```

Supported values: See [Technologies](../integrations/technologies.md)

### resources

**Optional** | `list[Resource]`

Custom resource definitions.

#### SLO Resource

```yaml
resources:
  - kind: SLO
    name: availability      # Unique name
    spec:
      objective: 99.95      # Target percentage
      window: 30d           # Time window
      threshold_ms: 200     # For latency SLOs
      indicator:
        type: availability  # availability, latency, throughput
        percentile: 99      # For latency SLOs
        query: |            # PromQL query
          sum(rate(...))
```

#### Alert Resource

```yaml
resources:
  - kind: Alert
    name: high-error-rate
    spec:
      expr: |               # PromQL expression
        sum(rate(http_requests_total{status=~"5.."}[5m])) /
        sum(rate(http_requests_total[5m])) > 0.01
      for: 5m               # Duration before firing
      severity: critical    # critical, warning, info
      labels:
        team: payments
      annotations:
        summary: "High error rate"
        description: "{{ $value | humanizePercentage }}"
```

#### Dependencies Resource

```yaml
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: high
        - name: inventory-service
          criticality: medium
```

### environments

**Optional** | `object`

Environment-specific overrides:

```yaml
environments:
  production:
    tier: critical
    resources:
      - kind: SLO
        name: availability
        spec:
          objective: 99.99

  staging:
    tier: standard
    resources:
      - kind: SLO
        name: availability
        spec:
          objective: 99.5
```

## Complete Example

```yaml
name: payment-api
team: payments
tier: critical
type: api
description: Handles payment processing

dependencies:
  - postgresql
  - redis

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="payment-api",status!~"5.."}[5m])) /
          sum(rate(http_requests_total{service="payment-api"}[5m]))

  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      threshold_ms: 200
      indicator:
        type: latency
        percentile: 99
        query: |
          histogram_quantile(0.99,
            sum by (le) (rate(http_request_duration_seconds_bucket{service="payment-api"}[5m]))
          )

  - kind: Alert
    name: high-error-rate
    spec:
      expr: |
        sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m])) /
        sum(rate(http_requests_total{service="payment-api"}[5m])) > 0.01
      for: 5m
      severity: critical

environments:
  production:
    resources:
      - kind: SLO
        name: availability
        spec:
          objective: 99.99
```

## Validation

```bash
nthlayer validate payment-api.yaml
```
