# Commands Overview

NthLayer provides a comprehensive CLI for managing your reliability stack.

## Generation Commands

| Command | Description |
|---------|-------------|
| [`nthlayer apply`](apply.md) | Generate all configs from service spec |
| `nthlayer plan` | Preview what resources would be generated (dry-run) |
| `nthlayer generate-dashboard` | Generate Grafana dashboard |
| `nthlayer generate-alerts` | Generate Prometheus alerts |
| `nthlayer generate-recording-rules` | Generate Prometheus recording rules |
| [`nthlayer generate-loki-alerts`](generate-loki-alerts.md) | Generate Loki LogQL alerts |

## Validation Commands

| Command | Description |
|---------|-------------|
| [`nthlayer verify`](verify.md) | Verify declared metrics exist (contract verification) |
| [`nthlayer validate-spec`](validate-spec.md) | Validate service.yaml against OPA policies |
| [`nthlayer validate-metadata`](validate-metadata.md) | Validate rule metadata (labels, annotations, URLs) |
| [`nthlayer validate-slo`](validate-slo.md) | Validate SLO metrics exist in Prometheus |
| `nthlayer lint` | Lint Prometheus alert rules with pint |

## Dependency Intelligence

| Command | Description |
|---------|-------------|
| [`nthlayer deps`](deps.md) | Show service dependencies |
| [`nthlayer blast-radius`](blast-radius.md) | Calculate deployment blast radius |
| [`nthlayer ownership`](ownership.md) | Show service ownership attribution |
| [`nthlayer identity`](identity.md) | Service identity resolution and management |

## SLO & Error Budget

| Command | Description |
|---------|-------------|
| [`nthlayer slo`](slo.md) | SLO and error budget commands |
| [`nthlayer portfolio`](portfolio.md) | View org-wide SLO health |
| [`nthlayer check-deploy`](check-deploy.md) | Check deployment gate (error budget validation) |
| [`nthlayer drift`](drift.md) | Analyze reliability drift for a service |

## Environment Management

| Command | Description |
|---------|-------------|
| [`nthlayer environments`](environments.md) | List available environments |
| `nthlayer diff-envs` | Compare configurations between environments |
| `nthlayer validate-env` | Validate an environment configuration |

## Setup & Configuration

| Command | Description |
|---------|-------------|
| [`nthlayer setup`](setup.md) | Interactive first-time setup |
| [`nthlayer init`](init.md) | Initialize new NthLayer service |
| [`nthlayer config`](config.md) | Configuration management |
| `nthlayer secrets` | Secrets management |

## Quick Reference

```bash
# Generate configs
nthlayer apply service.yaml

# Validate before deployment
nthlayer verify service.yaml --prometheus-url http://prometheus:9090
nthlayer validate-slo service.yaml

# View dependencies
nthlayer deps service.yaml
nthlayer blast-radius service.yaml

# Check deployment readiness
nthlayer check-deploy service.yaml

# View portfolio health
nthlayer portfolio

# Check SLO status
nthlayer slo show service.yaml
```

## Getting Help

```bash
nthlayer --help
nthlayer <command> --help
```

## See Also

- [CLI Reference](../reference/cli.md) - Complete command reference
- [Getting Started](../getting-started/quick-start.md) - First steps with NthLayer
