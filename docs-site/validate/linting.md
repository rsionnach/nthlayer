# PromQL Linting

Validate PromQL query syntax and best practices before they reach Prometheus.

## Overview

NthLayer integrates with [pint](https://cloudflare.github.io/pint/) to validate generated Prometheus rules. This catches:

- **Syntax errors** - Invalid PromQL that Prometheus would reject
- **Missing metrics** - References to metrics that don't exist
- **Best practice violations** - Queries that work but could be improved

## Usage

### Lint During Apply

```bash
nthlayer apply services/api.yaml --lint
```

Output:
```
Applied 4 resources in 0.3s → generated/api/

Validating alerts with pint...
  ✓ 12 rules validated

  ⚠ [promql/series] Line 45: metric "http_errors_total" not found
```

### Lint Existing Files

```bash
# Lint a specific file
pint lint generated/api/alerts.yaml

# Lint all generated rules
pint lint generated/*/alerts.yaml
```

## What Gets Checked

### Syntax Validation

```yaml
# Invalid - missing closing brace
- alert: HighLatency
  expr: histogram_quantile(0.99, sum(rate(http_duration_bucket[5m]))
```

```
ERROR: promql/syntax - unexpected end of input
```

### Series Existence

```yaml
# Warning - metric may not exist
- alert: HighErrors
  expr: rate(custom_errors_total[5m]) > 0.1
```

```
WARNING: promql/series - metric "custom_errors_total" not found
```

### Best Practices

```yaml
# Warning - histogram_quantile without sum by (le)
- alert: SlowRequests
  expr: histogram_quantile(0.99, rate(http_duration_bucket[5m])) > 1
```

```
WARNING: promql/aggregate - histogram_quantile should use sum by (le)
```

## Configuration

### pint Configuration

Create `.pint.hcl` in your repo root:

```hcl
prometheus "default" {
  uri     = "http://prometheus:9090"
  timeout = "30s"
}

rule {
  # Require runbook_url on all alerts
  annotation "runbook_url" {
    severity = "warning"
    required = true
  }
}

rule {
  # Require severity label
  label "severity" {
    severity = "warning"
    required = true
  }
}
```

### NthLayer Integration

NthLayer automatically:

1. Detects if `pint` is installed
2. Runs validation when `--lint` flag is provided
3. Reports results with severity levels
4. Returns appropriate exit codes

## Installing pint

```bash
# macOS
brew install cloudflare/tap/pint

# Linux
curl -sL https://github.com/cloudflare/pint/releases/latest/download/pint-linux-amd64.tar.gz | tar xz

# Verify installation
pint version
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Install pint
  run: |
    curl -sL https://github.com/cloudflare/pint/releases/latest/download/pint-linux-amd64.tar.gz | tar xz
    sudo mv pint /usr/local/bin/

- name: Generate and Lint
  run: nthlayer apply services/*.yaml --lint
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: nthlayer-lint
        name: NthLayer PromQL Lint
        entry: nthlayer apply --lint
        language: system
        files: services/.*\.yaml$
```

## Common Issues

### "pint not found"

```
⚠ pint not installed, skipping PromQL validation
  Install: brew install cloudflare/tap/pint
```

Install pint or skip linting with `--no-lint`.

### "Prometheus connection failed"

pint needs Prometheus access to verify metric existence:

```bash
# Provide Prometheus URL
export PROMETHEUS_URL=http://prometheus:9090
nthlayer apply services/api.yaml --lint
```

Or disable series checks in `.pint.hcl`:

```hcl
checks {
  disabled = ["promql/series"]
}
```

## See Also

- [pint Documentation](https://cloudflare.github.io/pint/)
- [nthlayer apply](../commands/apply.md)
- [Contract Verification](../commands/verify.md)
