# Service Specifications

A service spec is a YAML file that describes your service and its reliability requirements.

## Structure

```yaml
# Basic metadata
name: payment-api
team: payments
tier: critical      # 1, 2, 3 or critical, standard, low
type: api           # api, worker, stream

# Dependencies (optional)
dependencies:
  - postgresql
  - redis

# Custom resources (optional)
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      ...
```

## Required Fields

| Field | Description |
|-------|-------------|
| `name` | Service identifier (lowercase, hyphens allowed) |
| `tier` | Priority level: `1`/`critical`, `2`/`standard`, `3`/`low` |
| `type` | Service type: `api`, `worker`, `stream` |

## Optional Fields

| Field | Description |
|-------|-------------|
| `team` | Team responsible for the service |
| `description` | Human-readable description |
| `dependencies` | List of technology dependencies |
| `resources` | Custom SLO, alert, or PagerDuty configs |

## Service Types

### API (`type: api`)

HTTP/REST services with request/response patterns.

**Default Metrics:**

- `http_requests_total` - Request count by status
- `http_request_duration_seconds` - Latency histogram

**Default SLOs:**

- Availability: % of non-5xx responses
- Latency: p99 response time

### Worker (`type: worker`)

Background job processors.

**Default Metrics:**

- `job_processed_total` - Jobs completed
- `job_duration_seconds` - Processing time
- `job_failed_total` - Failed jobs

**Default SLOs:**

- Throughput: Jobs processed per minute
- Success rate: % of successful jobs

### Stream (`type: stream`)

Event/message processors.

**Default Metrics:**

- `messages_processed_total` - Messages handled
- `consumer_lag` - Messages behind
- `processing_duration_seconds` - Processing time

**Default SLOs:**

- Throughput: Messages per second
- Lag: Consumer lag in messages

## Dependencies

List technologies your service depends on:

```yaml
dependencies:
  - postgresql
  - redis
  - kafka
```

Each dependency adds:

- Dashboard panels with technology-specific metrics
- Alerts for common failure modes
- Recording rules for aggregation

See [Technologies](../integrations/technologies.md) for all 18 supported technologies.

## Custom Resources

Override defaults or add custom configurations:

### Custom SLO

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99        # Override default
      window: 7d              # Custom window
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="payment-api",status!~"5.."}[5m])) /
          sum(rate(http_requests_total{service="payment-api"}[5m]))
```

### Custom Alert

```yaml
resources:
  - kind: Alert
    name: high-latency
    spec:
      expr: |
        histogram_quantile(0.99,
          sum by (le) (rate(http_request_duration_seconds_bucket{service="payment-api"}[5m]))
        ) > 0.5
      for: 5m
      severity: warning
      annotations:
        summary: "High latency on payment-api"
```

### PagerDuty

```yaml
resources:
  - kind: PagerDuty
    name: alerting
    spec:
      urgency: high
      auto_create: true
```

## Environment Overrides

Different settings per environment:

```yaml
# payment-api.yaml
name: payment-api
tier: critical
type: api

environments:
  production:
    resources:
      - kind: SLO
        name: availability
        spec:
          objective: 99.99

  staging:
    resources:
      - kind: SLO
        name: availability
        spec:
          objective: 99.9
```

## Validation

Validate your spec before applying:

```bash
nthlayer validate payment-api.yaml
```

```
✓ payment-api.yaml is valid
  - 2 SLOs defined
  - 2 dependencies (postgresql, redis)
  - PagerDuty integration enabled
```

## Examples

See the [examples/services](https://github.com/rsionnach/nthlayer/tree/main/examples/services) directory for complete examples.
