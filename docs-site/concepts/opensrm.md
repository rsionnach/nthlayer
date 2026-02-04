# OpenSRM Format

The **OpenSRM** (Open Service Reliability Manifest) format is NthLayer's structured schema for declaring service reliability requirements. It replaces the legacy flat YAML format with a richer, namespaced structure that supports contracts, deployment gates, ownership, and cross-service validation.

## What is OpenSRM?

An OpenSRM manifest is a YAML file with:

```yaml
apiVersion: srm/v1
kind: ServiceReliabilityManifest
```

It describes everything NthLayer needs to generate, validate, and protect a service: SLOs, dependencies, contracts, ownership, observability configuration, and deployment gates — all in one file.

## Why OpenSRM?

The legacy `service.yaml` format works well for simple services but lacks structure for:

- **External contracts** — promises your service makes to consumers
- **Deployment gates** — automated deploy blocking based on error budget, SLO compliance, and incident counts
- **Cross-service validation** — checking that dependency expectations are feasible
- **Ownership metadata** — team, escalation, runbooks, PagerDuty integration
- **Observability config** — metric prefixes, log labels, trace service names
- **Templates** — shared base configurations with service-specific overrides

OpenSRM provides all of this in a single, validated schema.

## Schema Overview

```yaml
apiVersion: srm/v1
kind: ServiceReliabilityManifest

metadata:
  name: payment-api              # Service identifier
  team: payments                 # Owning team
  tier: critical                 # critical, standard, or low
  description: Payment processing API
  labels:                        # Arbitrary key-value labels
    domain: commerce
  annotations:                   # Metadata annotations
    owner: "@payments-team"
  template: base-api             # Optional base template

spec:
  type: api                      # Service type

  slos:                          # SLO definitions
    availability:
      target: 99.95
      window: 30d
    latency:
      target: 200
      unit: ms
      percentile: p99
      window: 30d

  contract:                      # External promises to consumers
    availability: 0.999
    latency:
      p99: 500ms

  dependencies:                  # Upstream dependencies
    - name: postgres-primary
      type: database
      critical: true
      database_type: postgresql
      slo:
        availability: 99.99
    - name: redis-cache
      type: cache
      critical: false

  ownership:                     # Team and escalation info
    team: payments
    slack: "#payments-oncall"
    email: payments-oncall@example.com
    pagerduty:
      service_id: P123ABC
    runbook: https://wiki.example.com/runbooks/payment-api

  observability:                 # Metric and tracing config
    metrics_prefix: payment_api
    logs_label: app=payment-api
    traces_service: payment-api

  deployment:                    # Deployment configuration
    environments:
      - production
      - staging
    gates:
      error_budget:
        enabled: true
        threshold: 0.10
      slo_compliance:
        threshold: 0.99
      recent_incidents:
        p1_max: 0
        lookback: 7d
    rollback:
      automatic: true
      criteria:
        error_rate_increase: 5%
        latency_increase: 50%
```

## Service Types

OpenSRM supports 7 service types, each with appropriate default SLOs and metric templates:

| Type | Description | Default SLO Metrics |
|------|-------------|---------------------|
| `api` | HTTP/REST service | Request rate, latency, error rate |
| `worker` | Background job processor | Job throughput, processing time |
| `stream` | Event/message processor | Message throughput, processing latency |
| `ai-gate` | AI judgment service | Reversal rate, calibration, feedback latency |
| `batch` | Batch processing job | Job completion, duration |
| `database` | Database service | Query latency, connection utilization |
| `web` | Web frontend | Page load time, error rate |

## Legacy vs OpenSRM

| Feature | Legacy Format | OpenSRM Format |
|---------|---------------|----------------|
| Format identifier | None (flat YAML) | `apiVersion: srm/v1` |
| SLO definitions | `resources[kind=SLO]` | `spec.slos` map |
| Dependencies | `dependencies: [string]` | `spec.dependencies` with SLO targets |
| External contracts | Not supported | `spec.contract` |
| Deployment gates | Not supported | `spec.deployment.gates` |
| Ownership | `team` field only | `spec.ownership` with full escalation |
| Observability | Not supported | `spec.observability` |
| Templates | Not supported | `metadata.template` with deep merge |
| Cross-service validation | Not supported | `ContractRegistry` + `--registry-dir` |
| Service types | api, worker, stream | api, worker, stream, ai-gate, batch, database, web |

Both formats are fully supported. NthLayer auto-detects the format when loading files.

## Minimal Example

```yaml
apiVersion: srm/v1
kind: ServiceReliabilityManifest
metadata:
  name: my-service
  team: my-team
  tier: standard
spec:
  type: api
  slos:
    availability:
      target: 99.9
      window: 30d
  dependencies:
    - name: postgresql
      type: database
```

## Full Example

See `examples/opensrm/api-critical.reliability.yaml` for a comprehensive example with all fields.

## Migrating from Legacy Format

Use the `nthlayer migrate` command to convert existing service.yaml files:

```bash
# Preview the migration
nthlayer migrate service.yaml --dry-run

# Convert and write to file
nthlayer migrate service.yaml

# Convert to a specific output directory
nthlayer migrate service.yaml --output /path/to/output/
```

The migration preserves all existing configuration and adds the OpenSRM structure. See [nthlayer migrate](../commands/migrate.md) for full details.

## See Also

- [Service YAML Schema](../reference/service-yaml.md) — Full field reference for both formats
- [nthlayer migrate](../commands/migrate.md) — Migration command reference
- [Contracts & Assumptions](contracts.md) — Contract verification and validation
