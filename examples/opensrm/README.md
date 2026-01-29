# OpenSRM Examples

This directory contains example Service Reliability Manifest files in the OpenSRM format.

## File Extension

OpenSRM manifests use the `.reliability.yaml` extension by default:
- `payment-api.reliability.yaml`
- `fraud-detector.reliability.yaml`

## Examples

| File | Service Type | Description |
|------|--------------|-------------|
| `api-basic.reliability.yaml` | `api` | Minimal API service configuration |
| `api-critical.reliability.yaml` | `api` | Full-featured critical API with all options |
| `ai-gate.reliability.yaml` | `ai-gate` | AI decision service with judgment SLOs |
| `worker.reliability.yaml` | `worker` | Background job processor |
| `stream.reliability.yaml` | `stream` | Event stream processor |
| `batch.reliability.yaml` | `batch` | Scheduled batch job |

## Service Types

OpenSRM defines 6 service types:

| Type | Description | Key SLOs |
|------|-------------|----------|
| `api` | Request/response services | Availability, latency, error rate |
| `worker` | Background processors | Throughput, error rate |
| `stream` | Event processors | Throughput, lag, error rate |
| `ai-gate` | AI decision services | Standard SLOs + judgment SLOs |
| `batch` | Scheduled jobs | Completion rate, duration |
| `database` | Managed databases | Availability, latency |

## Validating Examples

```bash
# Validate a single file
nthlayer validate examples/opensrm/api-basic.reliability.yaml

# Validate all examples
for f in examples/opensrm/*.reliability.yaml; do
  nthlayer validate "$f"
done
```

## Migrating from Legacy Format

If you have existing NthLayer service.yaml files, use the migration command:

```bash
nthlayer migrate services/payment-api.yaml

# Preview without writing
nthlayer migrate services/payment-api.yaml --dry-run
```

## Learn More

- [OpenSRM Specification](https://github.com/rsionnach/opensrm)
- [NthLayer Documentation](https://rsionnach.github.io/nthlayer/)
