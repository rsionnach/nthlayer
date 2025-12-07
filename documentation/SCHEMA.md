# NthLayer YAML Schema Reference

Complete reference for NthLayer service definition files.

---

## File Structure

Every service is defined in a single YAML file with two main sections:

```yaml
service:
  # Service context (required)

resources:
  # Resource definitions (optional if using template)
```

---

## Service Context

The `service` section declares service-level metadata. This context is inherited by all resources.

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string | Service identifier (lowercase-with-hyphens) | `payment-api` |
| `team` | string | Owning team name | `payments` |
| `tier` | string | Service tier: `critical` \| `standard` \| `low` | `critical` |
| `type` | string | Service type: `api` \| `background-job` \| `pipeline` \| `web` \| `database` | `api` |

### Optional Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `template` | string | Template name to inherit resources from | `critical-api` |
| `language` | string | Programming language | `java` |
| `framework` | string | Application framework | `spring-boot` |
| `metadata` | object | Custom metadata | `{version: "1.0"}` |

### Example

```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  template: critical-api  # Optional: use template
  language: java
  framework: spring-boot
```

---

## Template Variables

In any string field within resources, you can use template variables that are automatically substituted:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${service}` | Service name | `payment-api` |
| `${team}` | Team name | `payments` |
| `${tier}` | Service tier | `critical` |
| `${type}` | Service type | `api` |

### Example

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      query: |
        sum(rate(http_requests{service="${service}",team="${team}"}[5m]))
```

After substitution becomes:
```
sum(rate(http_requests{service="payment-api",team="payments"}[5m]))
```

---

## Resources

The `resources` section defines operational resources for the service. Each resource has:

- `kind` - Resource type (SLO, PagerDuty, Dependencies, Observability)
- `name` - Unique resource name within the service
- `spec` - Resource-specific configuration

---

## SLO Resource

Defines Service Level Objectives.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `objective` | number | Yes | Target percentage (0-100) |
| `window` | string | No | Time window (default: `30d`) |
| `indicator` | object | Yes | SLI definition |

### Indicator Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | `availability` or `latency` |
| `query` | string | Yes | Prometheus query |
| `percentile` | number | No | For latency SLOs (e.g., `95`) |
| `threshold_ms` | number | No | For latency SLOs (milliseconds) |

### Example: Availability SLO

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9  # 99.9% availability
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="${service}",code!~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="${service}"}[5m]))
```

### Example: Latency SLO

```yaml
resources:
  - kind: SLO
    name: latency-p95
    spec:
      objective: 99.0  # 99% of requests under threshold
      window: 30d
      indicator:
        type: latency
        percentile: 95
        threshold_ms: 500
        query: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket{service="${service}"}[5m])
          )
```

---

## PagerDuty Resource

Configures PagerDuty integration.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `urgency` | string | Yes | `high` or `low` |
| `auto_create` | boolean | No | Auto-create service if missing (default: `false`) |
| `escalation_policy` | string | No | Escalation policy name |
| `team` | string | No | PagerDuty team name |

### Example

```yaml
resources:
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      auto_create: true
      escalation_policy: payments-critical
      team: payments-team
```

### Usage

```bash
nthlayer setup-pagerduty payment-api.yaml --api-key YOUR_KEY
```

---

## Dependencies Resource

Defines service dependencies for error budget correlation.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `services` | array | Upstream service dependencies |
| `databases` | array | Database dependencies |
| `external_apis` | array | External API dependencies |
| `queues` | array | Message queue dependencies |

### Dependency Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Dependency name |
| `criticality` | string | Yes | `critical` \| `high` \| `medium` \| `low` |
| `type` | string | No | Dependency type (for databases/queues) |

### Example

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

      databases:
        - name: payments-db
          type: postgresql
          criticality: high

      external_apis:
        - name: stripe
          criticality: critical
        - name: analytics
          criticality: low

      queues:
        - name: payment-events
          type: kafka
          criticality: high
```

### Criticality Levels

- **critical** - Service cannot function without this dependency
- **high** - Major degradation if dependency fails
- **medium** - Graceful degradation possible
- **low** - Optional/nice-to-have dependency

---

## Observability Resource

Configures observability endpoints and settings.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `metrics` | object | Metrics configuration |
| `health` | object | Health check configuration |
| `logs` | object | Logging configuration |
| `traces` | object | Tracing configuration |

### Metrics Fields

| Field | Type | Description |
|-------|------|-------------|
| `endpoint` | string | Metrics endpoint path |
| `port` | number | Metrics port |
| `format` | string | Format: `prometheus` \| `statsd` |

### Health Fields

| Field | Type | Description |
|-------|------|-------------|
| `endpoint` | string | Health check endpoint |
| `port` | number | Health check port |

### Logs Fields

| Field | Type | Description |
|-------|------|-------------|
| `format` | string | Log format: `json` \| `text` |
| `level` | string | Log level: `debug` \| `info` \| `warn` \| `error` |

### Example

```yaml
resources:
  - kind: Observability
    name: metadata
    spec:
      metrics:
        endpoint: /metrics
        port: 9090
        format: prometheus

      health:
        endpoint: /health
        port: 8080

      logs:
        format: json
        level: info

      traces:
        enabled: true
        sampling_rate: 0.1
```

---

## Complete Example

A full-featured service definition:

```yaml
# payment-api.yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  language: java
  framework: spring-boot

resources:
  # Availability SLO
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="${service}",code!~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="${service}"}[5m]))

  # Latency SLO
  - kind: SLO
    name: latency-p95
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 95
        threshold_ms: 500
        query: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket{service="${service}"}[5m])
          )

  # PagerDuty Integration
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      auto_create: true
      escalation_policy: payments-critical

  # Service Dependencies
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: high
        - name: fraud-detection
          criticality: high
      databases:
        - name: payments-db
          type: postgresql
          criticality: high
      external_apis:
        - name: stripe
          criticality: critical

  # Observability Config
  - kind: Observability
    name: metadata
    spec:
      metrics:
        endpoint: /actuator/metrics
        port: 8080
      health:
        endpoint: /actuator/health
        port: 8080
      logs:
        format: json
        level: info
```

---

## Using Templates

Templates provide pre-configured resources to reduce boilerplate.

### With Template (Recommended)

```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  template: critical-api  # Inherits 2 SLOs + PagerDuty

# Optional: Override or add resources
resources:
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300  # Override template default
```

### Available Templates

- `critical-api` - 99.9% SLO, high urgency PagerDuty
- `standard-api` - 99.5% SLO, low urgency PagerDuty
- `low-api` - 99.0% SLO, no PagerDuty
- `background-job` - Success rate SLO
- `pipeline` - Data pipeline SLO

See [TEMPLATES.md](TEMPLATES.md) for full template reference.

---

## Validation

Validate your service definition:

```bash
nthlayer validate payment-api.yaml
```

Validation checks:
- ✅ Required fields present
- ✅ Valid tier and type values
- ✅ Template exists (if specified)
- ✅ Resource names are unique
- ✅ SLO objectives in valid range (0-100)
- ✅ Template variables are valid

---

## File Naming Convention

**Convention:** Service file should match service name

✅ **Good:**
- Service name: `payment-api` → File: `payment-api.yaml`
- Service name: `user-service` → File: `user-service.yaml`

❌ **Bad:**
- Service name: `payment-api` → File: `payments.yaml`

This convention is enforced by the validator (can be disabled with `--no-filename-check`).

---

## Best Practices

### 1. Use Templates

Start with a template and override as needed:

```yaml
service:
  name: my-api
  team: my-team
  tier: critical
  template: critical-api  # Start here

# Only override what's different
resources:
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300  # Custom threshold
```

### 2. Use Template Variables

Make queries portable across services:

```yaml
# Good - uses variable
query: |
  rate(http_requests{service="${service}"}[5m])

# Bad - hardcoded
query: |
  rate(http_requests{service="payment-api"}[5m])
```

### 3. Set Appropriate Criticality

Be realistic about dependency criticality:

```yaml
dependencies:
  services:
    - name: auth-service
      criticality: critical  # Can't function without it
    - name: analytics-service
      criticality: low  # Nice to have
```

### 4. Document Custom SLOs

Add comments for custom SLO queries:

```yaml
- kind: SLO
  name: custom-metric
  spec:
    # Measures successful payment completions
    # excluding retryable errors (409, 429)
    query: |
      sum(rate(payments_completed_total{...}))
```

---

## See Also

- [TEMPLATES.md](TEMPLATES.md) - Template reference
- [GETTING_STARTED.md](../GETTING_STARTED.md) - Getting started guide
- [README.md](../README.md) - Project overview
