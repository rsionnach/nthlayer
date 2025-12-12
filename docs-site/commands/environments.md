# Environment Management

NthLayer supports multi-environment deployments with environment-specific configurations.

## Overview

Environments allow you to customize service configurations for different deployment targets (dev, staging, production) while keeping a single source of truth in your service.yaml.

## Commands

### list-environments

Discover available environment configurations.

```bash
# List environments in current directory
nthlayer list-environments

# List environments for a specific service
nthlayer list-environments --service services/payment-api.yaml

# Search a specific directory
nthlayer list-environments --directory ./config
```

**Example output:**

```
NthLayer: List Environments

Directory: /home/user/project

✓ Found 3 environment(s):

📦 development
   Shared: development.yaml

📦 staging
   Shared: staging.yaml
   Service-specific: 2 file(s)
      • payment-api: payment-api-staging.yaml
      • user-service: user-service-staging.yaml

📦 production
   Shared: production.yaml
   Service-specific: 1 file(s)
      • payment-api: payment-api-production.yaml

Usage:
   nthlayer generate-slo service.yaml --env development
   nthlayer validate service.yaml --env development
```

### diff-envs

Compare configurations between two environments to see what changes between them.

```bash
nthlayer diff-envs services/payment-api.yaml staging production
```

**Example output:**

```
NthLayer: Environment Diff

Service: payment-api
Comparing: staging → production

┌─────────────────┬─────────────┬─────────────┐
│ Field           │ staging     │ production  │
├─────────────────┼─────────────┼─────────────┤
│ replicas        │ 2           │ 5           │
│ resources.cpu   │ 500m        │ 2000m       │
│ resources.memory│ 512Mi       │ 2Gi         │
│ slo.availability│ 99.5%       │ 99.95%      │
└─────────────────┴─────────────┴─────────────┘

3 differences found
```

**Options:**

| Option | Description |
|--------|-------------|
| `--show-all` | Show all fields, not just differences |

### validate-env

Validate an environment configuration for correctness.

```bash
# Basic validation
nthlayer validate-env production

# Validate against a specific service
nthlayer validate-env production --service services/payment-api.yaml

# Strict mode (warnings become errors)
nthlayer validate-env production --strict
```

**What gets validated:**

- Environment file syntax (valid YAML)
- Required fields present
- Value types match expected schema
- Variable references resolve correctly
- No conflicts with service defaults

**Example output:**

```
NthLayer: Validate Environment

Environment: production
Directory: ./environments

✓ Found environment file: production.yaml

Validating...
  ✓ Valid YAML syntax
  ✓ Required fields present
  ✓ Value types correct
  ⚠ Warning: 'debug_mode' is set to true in production

Validation passed with 1 warning(s)
```

## Environment File Structure

### Shared Environment File

`environments/production.yaml`:

```yaml
environment: production

# Override service defaults
defaults:
  replicas: 3
  resources:
    cpu: "1000m"
    memory: "1Gi"

# Environment-specific SLO targets
slo:
  availability: 99.95
  latency_p99_ms: 200

# Prometheus endpoint for this environment
prometheus:
  url: https://prometheus.prod.example.com

# Grafana for this environment
grafana:
  url: https://grafana.prod.example.com
  folder: Production
```

### Service-Specific Environment File

`environments/payment-api-production.yaml`:

```yaml
environment: production
service: payment-api

# Service-specific overrides for production
replicas: 5
resources:
  cpu: "2000m"
  memory: "2Gi"

# Stricter SLO for payment service
slo:
  availability: 99.99
  latency_p99_ms: 100
```

## Using Environments

### With Generate Commands

```bash
# Generate with environment-specific config
nthlayer apply services/payment-api.yaml --env production

# Preview what would be generated
nthlayer plan services/payment-api.yaml --env production
```

### With Validation Commands

```bash
# Verify metrics exist in production Prometheus
nthlayer verify services/payment-api.yaml --env production

# Check deployment gate against production SLOs
nthlayer check-deploy services/payment-api.yaml --env production
```

### With SLO Commands

```bash
# Collect SLO metrics from production
nthlayer slo collect services/payment-api.yaml --env production
```

## Best Practices

### 1. Use Shared Defaults

Put common configuration in shared environment files, override only what's different per-service.

### 2. Validate Before Deploy

```bash
# In CI/CD pipeline
nthlayer validate-env $ENVIRONMENT --strict
nthlayer validate services/*.yaml --env $ENVIRONMENT
```

### 3. Compare Before Promotion

```bash
# Before promoting staging to production
nthlayer diff-envs services/payment-api.yaml staging production
```

### 4. Keep Environments Consistent

Use the same environment names across all services for predictable behavior.

## Directory Structure

Recommended layout:

```
project/
├── services/
│   ├── payment-api.yaml
│   ├── user-service.yaml
│   └── notification-worker.yaml
├── environments/
│   ├── development.yaml           # Shared dev config
│   ├── staging.yaml               # Shared staging config
│   ├── production.yaml            # Shared production config
│   ├── payment-api-production.yaml    # Service-specific override
│   └── user-service-staging.yaml      # Service-specific override
└── generated/
    ├── development/
    ├── staging/
    └── production/
```
