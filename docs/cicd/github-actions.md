# GitHub Actions Reference

Complete reference for the NthLayer GitHub Action.

## Installation

```yaml
- uses: rsionnach/nthlayer@v1
  with:
    command: plan
    service: service.yaml
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `command` | NthLayer command to run | No | `plan` |
| `service` | Path to service.yaml file | **Yes** | - |
| `environment` | Deployment environment | No | `prod` |
| `prometheus-url` | Prometheus server URL | No | - |
| `prometheus-username` | Prometheus basic auth username | No | - |
| `prometheus-password` | Prometheus basic auth password | No | - |
| `grafana-url` | Grafana server URL | No | - |
| `grafana-api-key` | Grafana API key | No | - |
| `fail-on` | Failure threshold | No | `error` |
| `comment` | Post PR comment | No | `true` |
| `upload-sarif` | Upload to GitHub Security | No | `true` |

### Commands

| Command | Description |
|---------|-------------|
| `plan` | Preview what resources would be generated |
| `check-deploy` | Check error budget before deployment |
| `drift` | Detect SLO drift from targets |
| `validate-slo` | Validate SLO definitions are feasible |
| `blast-radius` | Analyze downstream impact of changes |

### Failure Thresholds

| Value | Behavior |
|-------|----------|
| `error` | Fail only on errors |
| `warning` | Fail on warnings or errors |
| `none` | Never fail (informational only) |

## Outputs

| Output | Description |
|--------|-------------|
| `status` | Overall check status (`pass`, `warn`, `fail`) |
| `errors` | Number of errors found |
| `warnings` | Number of warnings found |
| `json-result` | Full JSON output |
| `sarif-file` | Path to SARIF output file |

## Examples

### Basic PR Check

```yaml
name: NthLayer

on:
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      security-events: write

    steps:
      - uses: actions/checkout@v4

      - uses: rsionnach/nthlayer@v1
        with:
          service: service.yaml
```

### Deployment Gate

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: rsionnach/nthlayer@v1
        id: gate
        with:
          command: check-deploy
          service: service.yaml
          prometheus-url: ${{ secrets.PROMETHEUS_URL }}
          fail-on: error

      - name: Deploy
        if: steps.gate.outputs.status == 'pass'
        run: ./deploy.sh
```

### Using Outputs

```yaml
- uses: rsionnach/nthlayer@v1
  id: check
  with:
    service: service.yaml

- name: Handle Results
  run: |
    echo "Status: ${{ steps.check.outputs.status }}"
    echo "Errors: ${{ steps.check.outputs.errors }}"
    echo "Warnings: ${{ steps.check.outputs.warnings }}"
```

### Multiple Services

```yaml
- uses: rsionnach/nthlayer@v1
  with:
    service: services/api.yaml

- uses: rsionnach/nthlayer@v1
  with:
    service: services/worker.yaml
```

### With Secrets

```yaml
- uses: rsionnach/nthlayer@v1
  with:
    command: check-deploy
    service: service.yaml
    prometheus-url: ${{ secrets.PROMETHEUS_URL }}
    prometheus-username: ${{ secrets.PROMETHEUS_USER }}
    prometheus-password: ${{ secrets.PROMETHEUS_PASS }}
    grafana-url: ${{ secrets.GRAFANA_URL }}
    grafana-api-key: ${{ secrets.GRAFANA_API_KEY }}
```

## GitHub Security Integration

When `upload-sarif: true`, NthLayer uploads results to GitHub's Security tab:

1. Go to **Security** → **Code scanning**
2. View NthLayer findings alongside other security tools
3. Track issues over time with alerts

## PR Comments

When `comment: true`, NthLayer posts/updates a comment on PRs:

```markdown
## NthLayer Reliability Check

### payment-api

| Check | Status | Details |
|-------|--------|---------|
| SLO Feasibility | ✅ Pass | Target 99.95% achievable |
| Error Budget | ⚠️ Warning | 23% remaining |
| Drift | ✅ Pass | Within tolerance |
```

The comment is updated on each push, not duplicated.

## Required Permissions

```yaml
permissions:
  contents: read        # Read repository
  pull-requests: write  # Post PR comments
  security-events: write # Upload SARIF
```
