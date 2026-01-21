# Validate

**Catch reliability issues before deploy, not after incidents.**

NthLayer's validation layer ensures your reliability configuration is correct *before* it reaches production. This is the core of "Shift Left" - moving validation earlier in your pipeline.

## The Three Validation Layers

| Layer | Command | What It Checks | When to Use |
|-------|---------|----------------|-------------|
| **Syntax** | `nthlayer apply --lint` | PromQL query validity | Every commit |
| **Policy** | `nthlayer validate-spec` | Service spec compliance | Every commit |
| **Contract** | `nthlayer verify` | Metrics exist in Prometheus | Before promotion |

## Validation Flow

```
service.yaml
     │
     ▼
┌─────────────────┐
│  Policy Check   │  nthlayer validate-spec
│  (OPA/Rego)     │  "Is the spec well-formed?"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PromQL Lint    │  nthlayer apply --lint
│  (pint)         │  "Are queries valid?"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Contract       │  nthlayer verify
│  Verification   │  "Do metrics exist?"
└────────┬────────┘
         │
         ▼
    Deploy ✓
```

## Quick Start

### 1. Validate Service Spec (No Prometheus Required)

```bash
# Check policy compliance
nthlayer validate-spec services/payment-api.yaml

# Output:
# ✓ Required fields present (name, team, tier, type)
# ✓ Tier value valid (critical)
# ✓ SLO objectives within range
```

### 2. Lint Generated PromQL

```bash
# Generate and lint in one step
nthlayer apply services/payment-api.yaml --lint

# Output:
# Applied 4 resources → generated/payment-api/
# Validating with pint...
# ✓ 12 rules validated
```

### 3. Verify Metrics Exist (Requires Prometheus)

```bash
# Verify against staging Prometheus
nthlayer verify services/payment-api.yaml \
  --prometheus-url http://prometheus:9090

# Output:
# ✓ http_requests_total
# ✓ http_request_duration_seconds_bucket
# Contract verification passed
```

## CI/CD Integration

Add all three checks to your pipeline:

```yaml
# GitHub Actions
jobs:
  validate:
    steps:
      - name: Policy Check
        run: nthlayer validate-spec services/*.yaml

      - name: Generate & Lint
        run: nthlayer apply services/*.yaml --lint

      - name: Verify Contracts
        run: |
          nthlayer verify services/*.yaml \
            --prometheus-url ${{ secrets.STAGING_PROMETHEUS }}
```

## Exit Codes

All validation commands use consistent exit codes:

| Code | Meaning | Pipeline Action |
|------|---------|-----------------|
| `0` | All checks passed | Continue |
| `1` | Warnings (non-blocking) | Continue with caution |
| `2` | Errors (blocking) | Fail pipeline |

## Next Steps

- [Contract Verification](../commands/verify.md) - Verify metrics exist
- [Policy Validation](../commands/validate-spec.md) - OPA/Rego policy checks
- [PromQL Linting](./linting.md) - Syntax and best practices
