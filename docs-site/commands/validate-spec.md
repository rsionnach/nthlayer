# nthlayer validate-spec

Validate service specifications against organizational policies using OPA/Rego.

## Synopsis

```bash
nthlayer validate-spec <file-or-directory> [options]
```

## Description

The `validate-spec` command checks service YAML files against policy rules. This catches configuration issues before they cause problems:

- Missing required fields
- Invalid tier or type values
- Critical services without proper SLOs
- Aggressive SLO targets that may be unrealistic

## Options

| Option | Description |
|--------|-------------|
| `--policy-dir PATH` | Custom policy directory (default: `policies/`) |
| `--verbose, -v` | Show detailed policy evaluation |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | Warnings found (non-blocking) |
| `2` | Errors found (blocking) |

## Examples

### Validate a Single File

```bash
nthlayer validate-spec services/payment-api.yaml
```

Output:
```
╭──────────────────────────────────────────────────────────────╮
│  Policy Validation: payment-api                              │
╰──────────────────────────────────────────────────────────────╯

  ✓ Required fields present
  ✓ Tier value valid (critical)
  ✓ Type value valid (api)
  ✓ SLO objectives within range
  ✓ Critical tier requirements met

  Result: PASSED (0 errors, 0 warnings)
```

### Validate All Services

```bash
nthlayer validate-spec services/
```

### With Verbose Output

```bash
nthlayer validate-spec services/api.yaml --verbose
```

Output:
```
Evaluating policies from: policies/

Policy: service.rego
  ✓ deny_missing_name: PASSED
  ✓ deny_missing_team: PASSED
  ✓ deny_invalid_tier: PASSED
  ✓ deny_invalid_type: PASSED
  ✓ deny_critical_without_slo: PASSED

Policy: slo.rego
  ✓ deny_invalid_objective: PASSED
  ⚠ warn_aggressive_objective: 99.99% may be unrealistic

Policy: dependencies.rego
  ✓ deny_missing_criticality: PASSED
```

## Built-in Policies

NthLayer includes default policies in `policies/`:

### service.rego

| Rule | Severity | Description |
|------|----------|-------------|
| `deny_missing_name` | Error | Service must have a name |
| `deny_missing_team` | Error | Service must have a team |
| `deny_invalid_tier` | Error | Tier must be critical/standard/low |
| `deny_invalid_type` | Error | Type must be api/worker/stream/web/batch/ml |
| `deny_critical_without_slo` | Error | Critical tier requires SLO |

### slo.rego

| Rule | Severity | Description |
|------|----------|-------------|
| `deny_invalid_objective` | Error | Objective must be 0-100 |
| `warn_aggressive_objective` | Warning | Objectives >99.99% flagged |
| `warn_critical_low_availability` | Warning | Critical tier <99.9% flagged |

### dependencies.rego

| Rule | Severity | Description |
|------|----------|-------------|
| `warn_missing_criticality` | Warning | Dependencies should have criticality |
| `deny_invalid_database_type` | Error | Database type must be known |

## Custom Policies

Add custom Rego policies to your `policies/` directory:

```rego
# policies/custom.rego
package nthlayer.custom

# Deny services without runbook
deny_missing_runbook[msg] {
    input.service.tier == "critical"
    not input.service.runbook_url
    msg := "Critical services must have a runbook_url"
}

# Warn about missing description
warn_missing_description[msg] {
    not input.service.description
    msg := "Service should have a description"
}
```

## Using conftest

If [conftest](https://www.conftest.dev/) is installed, `validate-spec` uses it for evaluation. Otherwise, it falls back to a native Python implementation.

### Install conftest

```bash
# macOS
brew install conftest

# Linux
curl -sL https://github.com/open-policy-agent/conftest/releases/latest/download/conftest_Linux_x86_64.tar.gz | tar xz
sudo mv conftest /usr/local/bin/
```

### Benefits of conftest

- Full OPA/Rego support
- Faster evaluation
- Additional output formats (`--output json`)

## CI/CD Integration

### GitHub Actions

```yaml
- name: Validate Service Specs
  run: nthlayer validate-spec services/
```

### Pre-commit Hook

```yaml
repos:
  - repo: local
    hooks:
      - id: validate-specs
        name: Validate Service Specs
        entry: nthlayer validate-spec
        language: system
        files: services/.*\.yaml$
```

## See Also

- [Validation Overview](../validate/index.md)
- [Contract Verification](./verify.md)
- [conftest Documentation](https://www.conftest.dev/)
