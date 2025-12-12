# validate-metadata

Validate Prometheus/Loki rule metadata beyond PromQL syntax.

## Synopsis

```bash
nthlayer validate-metadata <file-or-directory> [options]
```

## Description

Enhanced validation that goes beyond PromQL syntax checking (pint). Validates:

- Required labels (severity, team, service)
- Required annotations (summary, description, runbook_url)
- Label value patterns (regex validation)
- Runbook URL format and accessibility
- Range query vs data retention limits
- Alert `for` duration bounds

## Options

| Option | Description |
|--------|-------------|
| `--strict` | Require runbook_url, team, and service labels |
| `--check-urls` | Actually check if runbook URLs are accessible (makes HTTP requests) |
| `--use-promruval` | Also run promruval if installed |
| `--verbose`, `-v` | Show detailed output with suggestions |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All rules passed |
| 1 | Warnings found (no errors) |
| 2 | Errors found |

## Examples

### Basic Validation

```bash
nthlayer validate-metadata generated/payment-api/alerts.yaml
```

### Strict Mode

Requires runbook_url, team, and service labels:

```bash
nthlayer validate-metadata alerts.yaml --strict
```

### Validate Directory

```bash
nthlayer validate-metadata generated/ --strict --verbose
```

### Check URL Accessibility

Actually makes HTTP requests to verify runbook URLs are accessible:

```bash
nthlayer validate-metadata alerts.yaml --check-urls
```

## Validators

### Built-in Validators

| Validator | Description |
|-----------|-------------|
| `hasRequiredLabels` | Check for required labels |
| `hasRequiredAnnotations` | Check for required annotations |
| `validSeverityLevel` | Validate severity is one of: critical, warning, info, page, ticket |
| `noEmptyLabels` | Labels must have non-empty values |
| `noEmptyAnnotations` | Annotations must have non-empty values |
| `labelMatchesPattern` | Label values match regex patterns |
| `validRunbookUrl` | Runbook URL is well-formed |
| `rangeQueryMaxDuration` | Range queries don't exceed retention |
| `alertForDuration` | Alert `for` duration is reasonable |
| `ruleNamePattern` | Rule names follow naming convention |

### Default Mode

Checks:
- Required: `severity` label
- Required: `summary`, `description` annotations
- Valid severity level
- No empty labels or annotations

### Strict Mode

Additional checks:
- Required: `team`, `service` labels
- Required: `runbook_url` annotation
- Runbook URL format validation
- Range query vs 15d retention
- Alert `for` duration bounds (0s - 1h)

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Validate alert metadata
  run: |
    nthlayer validate-metadata generated/ --strict
```

### Pre-commit Hook

```yaml
repos:
  - repo: local
    hooks:
      - id: validate-metadata
        name: Validate alert metadata
        entry: nthlayer validate-metadata --strict
        language: system
        files: alerts\.yaml$
```

## Programmatic Usage

```python
from nthlayer.validation import (
    MetadataValidator,
    HasRequiredLabels,
    ValidRunbookUrl,
    validate_metadata,
)

# Quick validation
result = validate_metadata("alerts.yaml", strict=True)
if not result.passed:
    for issue in result.issues:
        print(f"{issue.severity.value}: {issue.message}")

# Custom validators
validator = MetadataValidator()
validator.add_validator(HasRequiredLabels(["severity", "team", "tier"]))
validator.add_validator(ValidRunbookUrl(check_accessibility=True))

result = validator.validate_file("alerts.yaml")
```

## See Also

- [lint Command](../validate/linting.md) - PromQL syntax validation with pint
- [apply Command](./apply.md) - Generate artifacts with optional validation
