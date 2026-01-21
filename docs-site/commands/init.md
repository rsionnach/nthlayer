# nthlayer init

Interactively create a new service specification file.

## Synopsis

```bash
nthlayer init [options]
```

## Description

The `init` command guides you through creating a `service.yaml` file with interactive prompts. It auto-generates appropriate resources based on your selections.

## Options

| Option | Description |
|--------|-------------|
| `--output, -o PATH` | Output file path (default: `service.yaml`) |
| `--template NAME` | Use a pre-built template |
| `--no-interactive` | Use defaults without prompts |

## Interactive Mode

```bash
nthlayer init
```

The wizard prompts for:

1. **Service name** - e.g., `payment-api`
2. **Team** - e.g., `platform`
3. **Tier** - critical, standard, or low
4. **Type** - api, worker, stream, web, batch, or ml
5. **Dependencies** - databases, caches, queues

### Example Session

```
╭──────────────────────────────────────────────────────────────╮
│  NthLayer Service Generator                                  │
╰──────────────────────────────────────────────────────────────╯

Service name: payment-api
Team: payments

Select service tier:
  ❯ critical  - 99.95% availability, 5min escalation
    standard  - 99.9% availability, 15min escalation
    low       - 99.5% availability, business hours

Select service type:
  ❯ api       - HTTP/REST API service
    worker    - Background job processor
    stream    - Event/stream processor
    web       - Web application
    batch     - Batch processing job
    ml        - ML inference service

Select dependencies (space to toggle):
  ◉ postgresql
  ◉ redis
  ○ kafka
  ○ mongodb
  ○ elasticsearch
  ○ rabbitmq

✓ Created services/payment-api.yaml
```

## Generated Output

Based on your selections, `init` generates appropriate resources:

### Critical Tier API

```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  # Availability SLO (99.95% for critical)
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability

  # Latency SLO (auto-added for API type)
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      threshold_ms: 200
      indicator:
        type: latency
        percentile: 99

  # Dependencies
  - kind: Dependencies
    name: deps
    spec:
      databases:
        - type: postgresql
          criticality: high
      caches:
        - type: redis
          criticality: high
```

### Standard Tier Worker

```yaml
service:
  name: email-worker
  team: notifications
  tier: standard
  type: worker

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
```

## Resource Auto-Generation

| Selection | Generated Resources |
|-----------|---------------------|
| Tier: critical | Higher SLO targets |
| Tier: standard | Standard SLO targets |
| Tier: low | Lower SLO targets |
| Type: api | Latency SLO |
| Type: worker | Job completion SLO |
| Type: stream | Throughput SLO |
| Dependencies | Dependencies resource |

## Templates

Use pre-built templates for common patterns:

```bash
# List available templates
nthlayer init --list-templates

# Use a template
nthlayer init --template api-with-postgres
```

### Available Templates

| Template | Description |
|----------|-------------|
| `api-basic` | Simple API with availability SLO |
| `api-with-postgres` | API with PostgreSQL dependency |
| `worker-basic` | Background worker |
| `stream-kafka` | Kafka stream processor |

## Non-Interactive Mode

Generate with defaults:

```bash
nthlayer init --no-interactive \
  --name my-service \
  --team platform \
  --tier standard \
  --type api
```

## See Also

- [nthlayer apply](./apply.md) - Generate configs from service spec
- [Service YAML Schema](../reference/service-yaml.md) - Full specification
- [Quick Start](../getting-started/quick-start.md) - Getting started guide
