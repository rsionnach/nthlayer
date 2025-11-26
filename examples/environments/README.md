# Environment Configuration Examples

This directory contains example environment configuration files demonstrating multi-environment support in NthLayer.

## Overview

These examples show how to use the `--env` flag with NthLayer CLI commands to maintain different configurations for development, staging, and production environments.

## Files in This Directory

- `dev.yaml` - Shared development environment configuration
- `staging.yaml` - Shared staging environment configuration
- `prod.yaml` - Shared production environment configuration
- `payment-api-dev.yaml` - Service-specific dev overrides for payment-api
- `payment-api-prod.yaml` - Service-specific prod overrides for payment-api
- `search-api-prod.yaml` - Service-specific prod overrides for search-api

## Usage

Place environment files in an `environments/` subdirectory next to your service YAML files:

```
services/
├── payment-api.yaml
├── search-api.yaml
└── environments/
    ├── dev.yaml
    ├── staging.yaml
    └── prod.yaml
```

Then use the `--env` flag with any NthLayer command:

```bash
# Generate SLOs for development
nthlayer generate-slo services/payment-api.yaml --env dev

# Generate alerts for production
nthlayer generate-alerts services/payment-api.yaml --env prod

# Validate staging configuration
nthlayer validate services/payment-api.yaml --env staging
```

## See Also

- **Full Documentation:** `docs/ENVIRONMENTS.md`
- **Example Services:** `examples/services/`
- **Implementation Details:** `ENV_FLAG_COMPLETE.md`
