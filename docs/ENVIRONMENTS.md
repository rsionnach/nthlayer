# Multi-Environment Configuration Guide

**NthLayer** supports environment-specific configuration overrides, enabling you to maintain different settings for development, staging, production, and custom environments without duplicating service definitions.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Concept Overview](#concept-overview)
3. [Setting Up Environments](#setting-up-environments)
4. [Using the --env Flag](#using-the---env-flag)
5. [Environment Management Commands](#environment-management-commands)
6. [Auto-Detection from CI/CD](#auto-detection-from-cicd)
7. [Environment-Aware Features](#environment-aware-features)
8. [Configuration Merging](#configuration-merging)
9. [File Organization](#file-organization)
10. [Common Patterns](#common-patterns)
11. [CI/CD Integration Examples](#cicd-integration-examples)
12. [Advanced Topics](#advanced-topics)
13. [Best Practices](#best-practices)
14. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Create Base Service Definition

```yaml
# services/payment-api.yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
```

### 2. Create Environment Override

```yaml
# services/environments/dev.yaml
environment: dev
service:
  tier: low  # Relax tier for dev

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0  # Lower SLO for dev
```

### 3. Use Environment-Specific Configuration

```bash
# Generate SLOs for development
nthlayer generate-slo services/payment-api.yaml --env dev

# Generate alerts for production
nthlayer generate-alerts services/payment-api.yaml --env prod
```

---

## Concept Overview

### What Are Environments?

Environments represent different deployment stages or contexts where your services run:

- **Development** (`dev`) - Local development, frequent changes
- **Staging** (`staging`) - Pre-production testing
- **Production** (`prod`) - Live user-facing services
- **Custom** - Any environment name you define

### Why Use Environment-Specific Configs?

**Without environments:**
```
payment-api-dev.yaml       # Duplicate definitions
payment-api-staging.yaml   # Hard to maintain
payment-api-prod.yaml      # Prone to drift
```

**With environments:**
```
payment-api.yaml           # Single source of truth
environments/
  dev.yaml                 # Only the differences
  staging.yaml
  prod.yaml
```

### Benefits

✅ **Single Source of Truth** - Base configuration in one place  
✅ **DRY Principle** - Override only what changes  
✅ **Consistency** - Same structure across all environments  
✅ **Maintainability** - Update base, all environments inherit  
✅ **Safety** - Explicit overrides reduce configuration drift  

---

## Setting Up Environments

### Directory Structure

NthLayer searches for environment files in this order:

```
services/
├── payment-api.yaml                    # Base configuration
├── environments/
│   ├── dev.yaml                        # Shared dev overrides (all services)
│   ├── staging.yaml                    # Shared staging overrides
│   ├── prod.yaml                       # Shared prod overrides
│   ├── payment-api-dev.yaml           # Service-specific dev overrides
│   └── payment-api-prod.yaml          # Service-specific prod overrides
```

**Search Order (most specific wins):**
1. `environments/{service}-{env}.yaml` - Service-specific
2. `environments/{env}.yaml` - Shared
3. Base service file - Fallback

### Creating Environment Files

#### Shared Environment File

Applies to **all services** in this environment:

```yaml
# services/environments/dev.yaml
environment: dev

service:
  tier: low  # All dev services are low priority

# Could add shared resources here too
```

#### Service-Specific Environment File

Overrides for a **specific service** in this environment:

```yaml
# services/environments/payment-api-prod.yaml
environment: prod

service:
  tier: critical  # This service is critical in prod

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99  # Extra 9 for payment API
      
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
          instance: payment-db-prod  # Prod-specific database
```

---

## Using the --env Flag

### Commands Supporting --env

All NthLayer CLI commands support the `--env` / `--environment` flag:

#### 1. Generate SLOs

```bash
# Development environment
nthlayer generate-slo payment-api.yaml --env dev

# Production environment
nthlayer generate-slo payment-api.yaml --env prod
```

**Output:**
```
======================================================================
  NthLayer: Generate SLOs
======================================================================

🌍 Environment: dev

✅ Generated SLOs for payment-api
   SLO count: 2
   Output: generated/sloth/payment-api.yaml
```

#### 2. Generate Alerts

```bash
# Generate alerts for staging
nthlayer generate-alerts payment-api.yaml --env staging \
  --runbook-url https://runbooks.company.com

# Production with PagerDuty
nthlayer generate-alerts payment-api.yaml --env prod \
  --notification-channel pagerduty
```

#### 3. Validate Service

```bash
# Validate dev configuration
nthlayer validate payment-api.yaml --env dev

# Validate production configuration
nthlayer validate payment-api.yaml --env prod --strict
```

#### 4. Setup PagerDuty

```bash
# Setup for staging
nthlayer setup-pagerduty payment-api.yaml --env staging \
  --api-key $PAGERDUTY_API_KEY

# Production setup
nthlayer setup-pagerduty payment-api.yaml --env prod \
  --api-key $PAGERDUTY_API_KEY
```

#### 5. Check Deployment Gate

```bash
# Check if staging deploy is allowed
nthlayer check-deploy payment-api.yaml --env staging

# Check production deploy
nthlayer check-deploy payment-api.yaml --env prod
```

### Short Form vs Long Form

Both forms are supported:

```bash
nthlayer generate-slo payment-api.yaml --env dev
nthlayer generate-slo payment-api.yaml --environment dev
```

---

## Environment Management Commands

NthLayer provides three specialized commands for managing environments.

### 1. List Environments

Discover available environment configurations in your project.

**Syntax:**
```bash
nthlayer list-environments [OPTIONS]
```

**Options:**
- `--directory DIR` - Search for environments in specific directory
- `--service FILE` - Show environments for specific service file

**Examples:**

```bash
# List all shared environments
nthlayer list-environments

# Output:
# 🌍 Available Environments:
#
# Shared environments (apply to all services):
#   ✓ dev (environments/dev.yaml)
#   ✓ staging (environments/staging.yaml)
#   ✓ prod (environments/prod.yaml)

# List environments for specific service
nthlayer list-environments --service payment-api.yaml

# Output includes service-specific files:
# Service-specific environments:
#   ✓ payment-api-dev (environments/payment-api-dev.yaml)
#   ✓ payment-api-prod (environments/payment-api-prod.yaml)
```

**Use Cases:**
- Discover what environments are configured
- Verify environment files exist before deployment
- Document available environments for team

### 2. Compare Environments

Show configuration differences between two environments.

**Syntax:**
```bash
nthlayer diff-envs SERVICE_FILE ENV1 ENV2 [OPTIONS]
```

**Options:**
- `--show-all` - Show all fields (including identical ones)

**Examples:**

```bash
# Compare dev and prod configurations
nthlayer diff-envs payment-api.yaml dev prod

# Output:
# 📊 Configuration Differences: dev vs prod
#
# service.tier:
#   dev:  low
#   prod: critical
#
# resources[0].spec.objective (availability SLO):
#   dev:  95.0%
#   prod: 99.99%

# Show all fields (including identical)
nthlayer diff-envs payment-api.yaml dev staging --show-all

# Output includes both different AND identical fields:
# service.name:
#   dev:     payment-api  (identical)
#   staging: payment-api
#
# service.tier:
#   dev:     low          (DIFFERENT)
#   staging: standard
```

**Use Cases:**
- Verify staging matches production settings
- Document environment differences
- Review changes before promoting to production
- Audit configuration consistency

### 3. Validate Environment

Validate environment file structure and test merge compatibility.

**Syntax:**
```bash
nthlayer validate-env ENVIRONMENT [OPTIONS]
```

**Options:**
- `--service FILE` - Test merge with specific service file
- `--directory DIR` - Look for environment files in directory
- `--strict` - Treat warnings as errors

**Examples:**

```bash
# Validate production environment file
nthlayer validate-env prod

# Output:
# ✅ Environment 'prod' is valid
#
# Structure checks:
#   ✓ Has 'environment' field
#   ✓ Environment name matches file (prod)
#   ✓ Valid YAML structure
#   ✓ All keys are recognized
#
# Content checks:
#   ✓ Service overrides are valid
#   ✓ No invalid SLO objectives

# Validate and test merge with service
nthlayer validate-env dev --service payment-api.yaml

# Validate strictly (warnings = errors)
nthlayer validate-env staging --strict
```

**Use Cases:**
- CI/CD validation of environment files
- Pre-deployment checks
- Catch configuration errors early

---

## Auto-Detection from CI/CD

NthLayer can automatically detect the current environment from CI/CD context.

### Using --auto-env Flag

```bash
# Auto-detect environment and generate SLOs
nthlayer generate-slo payment-api.yaml --auto-env

# Auto-detect and check deployment gate
nthlayer check-deploy payment-api.yaml --auto-env
```

### Detection Sources

NthLayer checks these environment variables (in priority order):

| Variable | Source | Example | Detected As |
|----------|--------|---------|-------------|
| `NTHLAYER_ENV` | Direct | `prod` | `prod` |
| `K8S_NAMESPACE` | Kubernetes | `payments-prod` | `prod` |
| `GITHUB_REF_NAME` | GitHub | `main` | `prod` |
| `CI_COMMIT_BRANCH` | GitLab | `develop` | `dev` |
| `CIRCLE_BRANCH` | CircleCI | `staging` | `staging` |
| `ECS_CLUSTER` | AWS ECS | `my-app-prod` | `prod` |

**12+ sources total** - see full list in advanced section.

### Smart Extraction

```bash
K8S_NAMESPACE=payments-prod     → prod
GITHUB_REF_NAME=main            → prod
GITHUB_REF_NAME=develop         → dev
ECS_CLUSTER=staging-cluster     → staging
```

### Priority Order

1. **Explicit `--env` flag** (highest)
2. **Auto-detected** (if `--auto-env`)  
3. **No environment** (base config)

---

## Environment-Aware Features

NthLayer adjusts behavior based on environment.

### Deployment Gate Thresholds

| Environment | Critical Service | Standard | Low |
|-------------|-----------------|----------|-----|
| **dev**     | Block: 50% | Block: 60% | Warn: 90% |
| **staging** | Block: 20% | Block: 30% | Warn: 60% |
| **prod**    | Block: 10% | Block: 20% | Warn: 50% |

**Example:**
```bash
# Dev allows 30% budget consumed
nthlayer check-deploy api.yaml --env dev
# ✅ Deployment allowed (30% < 50% threshold)

# Prod blocks the same deploy
nthlayer check-deploy api.yaml --env prod
# ❌ Blocked (30% > 10% threshold)
```

### Alert Filtering

| Environment | Alerts Included | Impact |
|-------------|----------------|---------|
| **dev**     | Critical only | ~16 alerts |
| **staging** | Critical + Warning | ~45 alerts |
| **prod**    | All severities | ~85 alerts |

**Reduces dev noise by 80%** while maintaining full prod coverage.

---

## Configuration Merging

### Deep Merge Behavior

Environment overrides use **deep merge** - only specified fields are overridden:

#### Example 1: Partial Override

**Base:**
```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  metadata:
    cost_center: 12345
    owner: alice@company.com
```

**Environment Override:**
```yaml
environment: dev
service:
  tier: low
```

**Result:**
```yaml
service:
  name: payment-api      # Inherited from base
  team: payments         # Inherited from base
  tier: low             # ✅ Overridden
  type: api             # Inherited from base
  metadata:             # Inherited from base
    cost_center: 12345
    owner: alice@company.com
```

#### Example 2: Resource Override

**Base:**
```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        success_rate:
          total_query: "sum(rate(http_requests_total[5m]))"
          error_query: "sum(rate(http_requests_total{status=~'5..'}[5m]))"
```

**Environment Override:**
```yaml
environment: dev
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0  # Only override objective
```

**Result:**
```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0     # ✅ Overridden
      window: 30d         # Inherited
      indicator:          # Inherited
        success_rate:
          total_query: "sum(rate(http_requests_total[5m]))"
          error_query: "sum(rate(http_requests_total{status=~'5..'}[5m]))"
```

### Override Rules

✅ **Merged:** Nested dictionaries  
✅ **Merged:** Service-level fields  
❌ **Replaced:** Lists (resources, dependencies, etc.)  
❌ **Replaced:** Scalar values (strings, numbers, booleans)

---

## File Organization

### Option 1: Centralized Environments

```
services/
├── payment-api.yaml
├── search-api.yaml
├── user-service.yaml
└── environments/
    ├── dev.yaml          # Shared dev config
    ├── staging.yaml      # Shared staging config
    └── prod.yaml         # Shared prod config
```

**Best for:** Organizations with consistent environment policies.

### Option 2: Service-Specific Environments

```
services/
├── payment-api.yaml
├── search-api.yaml
└── environments/
    ├── payment-api-dev.yaml
    ├── payment-api-staging.yaml
    ├── payment-api-prod.yaml
    ├── search-api-dev.yaml
    ├── search-api-staging.yaml
    └── search-api-prod.yaml
```

**Best for:** Services with unique environment requirements.

### Option 3: Hybrid (Recommended)

```
services/
├── payment-api.yaml
├── search-api.yaml
└── environments/
    ├── dev.yaml                    # Shared: All services low tier
    ├── staging.yaml                # Shared: Standard config
    ├── prod.yaml                   # Shared: Base production
    ├── payment-api-prod.yaml      # Override: Payment needs 99.99%
    └── search-api-dev.yaml        # Override: Search needs more resources in dev
```

**Best for:** Most organizations - shared defaults with service-specific overrides.

---

## Common Patterns

### Pattern 1: Relaxed SLOs in Development

**Base (services/payment-api.yaml):**
```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
```

**Dev Override (environments/dev.yaml):**
```yaml
environment: dev
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0  # Lower target for dev
```

### Pattern 2: Different Database Instances

**Base:**
```yaml
resources:
  - kind: Dependencies
    name: databases
    spec:
      databases:
        - type: postgres
          connection: ${DATABASE_URL}
```

**Production Override:**
```yaml
environment: prod
resources:
  - kind: Dependencies
    name: databases
    spec:
      databases:
        - type: postgres
          connection: payment-db.prod.company.com
          read_replicas: 3
```

### Pattern 3: Tier-Based Configuration

**Shared Dev (environments/dev.yaml):**
```yaml
environment: dev
service:
  tier: low  # All services low priority in dev
```

**Critical Service Override (environments/payment-api-dev.yaml):**
```yaml
environment: dev
service:
  tier: standard  # Payment API needs higher tier even in dev
```

### Pattern 4: Environment-Specific Alert Thresholds

**Base:**
```yaml
resources:
  - kind: SLO
    name: latency
    spec:
      objective: 99.0
      threshold_ms: 500
```

**Production Override:**
```yaml
environment: prod
resources:
  - kind: SLO
    name: latency
    spec:
      threshold_ms: 300  # Stricter latency in prod
```

### Pattern 5: PagerDuty Escalation by Environment

**Base:**
```yaml
resources:
  - kind: PagerDuty
    name: primary
    spec:
      escalation_policy: default
      urgency: high
```

**Dev Override:**
```yaml
environment: dev
resources:
  - kind: PagerDuty
    name: primary
    spec:
      escalation_policy: dev-team-only
      urgency: low  # Don't wake anyone in dev
```

---

## CI/CD Integration Examples

### GitHub Actions

**Complete Workflow:**
```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install NthLayer
        run: pip install nthlayer
      
      - name: Validate service configuration
        run: |
          # Auto-detects 'prod' from GITHUB_REF_NAME=main
          nthlayer validate payment-api.yaml --auto-env --strict
      
      - name: Check deployment gate
        run: |
          nthlayer check-deploy payment-api.yaml --auto-env
      
      - name: Generate SLOs
        if: success()
        run: |
          nthlayer generate-slo payment-api.yaml --auto-env
          
      - name: Generate alerts
        run: |
          nthlayer generate-alerts payment-api.yaml --auto-env \
            --runbook-url https://runbooks.company.com
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: slo-configs
          path: generated/
```

**Multi-Environment Workflow:**
```yaml
name: Deploy

on:
  push:
    branches: [develop, staging, main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install NthLayer
        run: pip install nthlayer
      
      - name: Deploy
        run: |
          # Automatically detects environment from branch:
          # develop → dev, staging → staging, main → prod
          nthlayer validate payment-api.yaml --auto-env
          nthlayer check-deploy payment-api.yaml --auto-env
          nthlayer generate-slo payment-api.yaml --auto-env
```

### GitLab CI

**Complete Pipeline:**
```yaml
stages:
  - validate
  - generate
  - deploy

variables:
  NTHLAYER_ENV: prod  # Explicit environment

validate:
  stage: validate
  script:
    - pip install nthlayer
    - nthlayer validate payment-api.yaml --env $NTHLAYER_ENV --strict
  only:
    - main

generate-config:
  stage: generate
  script:
    - pip install nthlayer
    - nthlayer generate-slo payment-api.yaml --env $NTHLAYER_ENV
    - nthlayer generate-alerts payment-api.yaml --env $NTHLAYER_ENV
  artifacts:
    paths:
      - generated/
  only:
    - main

check-gate:
  stage: deploy
  script:
    - pip install nthlayer
    - nthlayer check-deploy payment-api.yaml --env $NTHLAYER_ENV
  only:
    - main
```

**Multi-Environment Pipeline:**
```yaml
.deploy_template:
  script:
    - pip install nthlayer
    - nthlayer validate payment-api.yaml --env $CI_ENVIRONMENT
    - nthlayer check-deploy payment-api.yaml --env $CI_ENVIRONMENT
    - nthlayer generate-slo payment-api.yaml --env $CI_ENVIRONMENT

deploy:dev:
  extends: .deploy_template
  variables:
    CI_ENVIRONMENT: dev
  only:
    - develop

deploy:staging:
  extends: .deploy_template
  variables:
    CI_ENVIRONMENT: staging
  only:
    - staging

deploy:prod:
  extends: .deploy_template
  variables:
    CI_ENVIRONMENT: prod
  only:
    - main
```

### CircleCI

**Complete Config:**
```yaml
version: 2.1

jobs:
  deploy:
    docker:
      - image: python:3.11
    environment:
      NTHLAYER_ENV: prod
    steps:
      - checkout
      
      - run:
          name: Install NthLayer
          command: pip install nthlayer
      
      - run:
          name: Validate configuration
          command: |
            nthlayer validate payment-api.yaml --auto-env --strict
      
      - run:
          name: Check deployment gate
          command: |
            nthlayer check-deploy payment-api.yaml --auto-env
      
      - run:
          name: Generate configs
          command: |
            nthlayer generate-slo payment-api.yaml --auto-env
            nthlayer generate-alerts payment-api.yaml --auto-env
      
      - store_artifacts:
          path: generated/

workflows:
  deploy:
    jobs:
      - deploy:
          filters:
            branches:
              only: main
```

### Jenkins

**Declarative Pipeline:**
```groovy
pipeline {
    agent any
    
    environment {
        NTHLAYER_ENV = "${env.BRANCH_NAME == 'main' ? 'prod' : 'dev'}"
    }
    
    stages {
        stage('Setup') {
            steps {
                sh 'pip install nthlayer'
            }
        }
        
        stage('Validate') {
            steps {
                sh 'nthlayer validate payment-api.yaml --auto-env --strict'
            }
        }
        
        stage('Check Gate') {
            steps {
                sh 'nthlayer check-deploy payment-api.yaml --auto-env'
            }
        }
        
        stage('Generate') {
            steps {
                sh 'nthlayer generate-slo payment-api.yaml --auto-env'
                sh 'nthlayer generate-alerts payment-api.yaml --auto-env'
            }
        }
        
        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'generated/**'
            }
        }
    }
}
```

### ArgoCD Hooks

**Pre-Sync Hook:**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nthlayer-validate
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      containers:
      - name: nthlayer
        image: python:3.11-slim
        command:
        - /bin/sh
        - -c
        - |
          pip install nthlayer
          nthlayer validate /config/payment-api.yaml --auto-env --strict
          nthlayer check-deploy /config/payment-api.yaml --auto-env
        volumeMounts:
        - name: config
          mountPath: /config
      volumes:
      - name: config
        configMap:
          name: service-configs
      restartPolicy: Never
```

### Kubernetes CronJob

**Daily SLO Generation:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: generate-slos
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: nthlayer
            image: python:3.11-slim
            env:
            - name: K8S_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            command:
            - /bin/sh
            - -c
            - |
              pip install nthlayer
              # Auto-detects from K8S_NAMESPACE
              nthlayer generate-slo /config/payment-api.yaml --auto-env
              nthlayer generate-alerts /config/payment-api.yaml --auto-env
            volumeMounts:
            - name: config
              mountPath: /config
          volumes:
          - name: config
            configMap:
              name: service-configs
          restartPolicy: OnFailure
```

### Makefile Integration

**For Local and CI:**
```makefile
# Detect environment
ENV ?= $(shell [ "$$CI" = "true" ] && echo "$(CI_ENV)" || echo "local")

.PHONY: validate
validate:
	nthlayer validate payment-api.yaml --env $(ENV) --strict

.PHONY: check-gate
check-gate:
	nthlayer check-deploy payment-api.yaml --env $(ENV)

.PHONY: generate-slos
generate-slos:
	nthlayer generate-slo payment-api.yaml --env $(ENV)

.PHONY: generate-alerts
generate-alerts:
	nthlayer generate-alerts payment-api.yaml --env $(ENV)

.PHONY: deploy
deploy: validate check-gate generate-slos generate-alerts
	@echo "✅ All checks passed, configs generated"

# CI-specific targets
.PHONY: ci-deploy
ci-deploy:
	nthlayer validate payment-api.yaml --auto-env --strict
	nthlayer check-deploy payment-api.yaml --auto-env
	nthlayer generate-slo payment-api.yaml --auto-env
	nthlayer generate-alerts payment-api.yaml --auto-env
```

---

## Advanced Topics

### Variable Substitution

**✅ Available Now** - Automatically substitute environment context into your configurations.

NthLayer supports three template variables that are substituted at parse time:
- **`${env}`** - Current environment name (dev, staging, prod)
- **`${service}`** - Service name
- **`${team}`** - Team name

**Service Definition:**
```yaml
service:
  name: payment-api
  team: payments
  metadata:
    environment: ${env}
    namespace: ${team}-${env}
    service_id: ${service}-${env}

resources:
  - kind: SLO
    name: availability-${env}
    spec:
      objective: 99.9
      description: "${service} availability in ${env} environment"
```

**Parsed with `--env prod`:**
```yaml
service:
  name: payment-api
  team: payments
  metadata:
    environment: prod              # ${env} → prod
    namespace: payments-prod       # ${team}-${env} → payments-prod
    service_id: payment-api-prod   # ${service}-${env} → payment-api-prod

resources:
  - kind: SLO
    name: availability-prod        # ${env} → prod
    spec:
      objective: 99.9
      description: "payment-api availability in prod environment"  # Fully substituted
```

**How It Works:**
1. Variables work in any string field (names, descriptions, metadata)
2. Substitution happens after environment merging
3. Unknown variables (e.g., `${unknown}`) are left as-is
4. Works recursively in nested structures

**Example Use Cases:**
```yaml
# Dynamic resource naming
resources:
  - kind: SLO
    name: latency-${service}-${env}  # latency-payment-api-prod
  
  - kind: Alert
    name: ${team}-critical-${env}    # payments-critical-prod

# Environment-aware metadata
service:
  metadata:
    cluster: ${service}-cluster-${env}     # payment-api-cluster-prod
    namespace: ${team}-${env}              # payments-prod
    owner: ${team}@company.com             # payments@company.com
    
# Context-rich descriptions
resources:
  - kind: SLO
    spec:
      description: "Managed by ${team} team for ${env} environment"
```

### Conditional Resources

Add resources only in specific environments:

**Base:**
```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
```

**Dev Override (add debugging resources):**
```yaml
environment: dev
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0
      
  - kind: Monitoring
    name: debug
    spec:
      verbose_logging: true
      sample_rate: 100  # Sample all requests in dev
```

### Service-Specific File Priority

**✅ Available Now** - Service-specific environment files take precedence over shared files.

When multiple environment files match, NthLayer uses this priority order:
1. **Service-specific** (e.g., `payment-api-dev.yaml`) - Most specific
2. **Shared** (e.g., `dev.yaml`) - Falls back if no service-specific file
3. **Monorepo** (e.g., `.nthlayer/environments/payment-api-dev.yaml`)

**Example:**
```yaml
# environments/dev.yaml (shared - applies to all services)
environment: dev
service:
  tier: low  # Default: all services low priority in dev

# environments/payment-api-dev.yaml (service-specific - overrides shared)
environment: dev
service:
  tier: standard  # Payment API needs higher tier even in dev
```

**Usage:**
```bash
# Automatically picks payment-api-dev.yaml (service-specific)
nthlayer generate-slo payment-api.yaml --env dev

# Falls back to dev.yaml if no payment-api-dev.yaml exists
nthlayer generate-slo search-api.yaml --env dev
```

**Use Cases:**
- Override shared settings for critical services
- Service-specific SLO objectives
- Custom alert thresholds per service
- Service-specific metadata or configurations

---

### Environment Inheritance

**🚧 Future Feature** - Not yet implemented.

**Planned:** Allow environments to inherit from other environments.

**Example (future):**
```yaml
# environments/base-prod.yaml
environment: prod
service:
  tier: critical

# environments/payment-api-prod.yaml
inherit_from: base-prod  # Planned feature
service:
  # Would inherit tier: critical from base-prod
  metadata:
    extra: payment-specific
```

**Current Workaround:** Use service-specific files (available now) which provide similar functionality.

### Multi-Region Configurations

Use environments for regions:

```bash
# US region
nthlayer generate-slo payment-api.yaml --env us-prod

# EU region
nthlayer generate-slo payment-api.yaml --env eu-prod
```

```yaml
# environments/us-prod.yaml
environment: us-prod
service:
  metadata:
    region: us-east-1
    
resources:
  - kind: Dependencies
    name: databases
    spec:
      databases:
        - type: postgres
          endpoint: payment-db.us-east-1.amazonaws.com
```

---

## Best Practices

### 1. Use Shared Defaults, Override Exceptions

**Good:**
```yaml
# environments/dev.yaml - applies to all services
environment: dev
service:
  tier: low

# environments/payment-api-dev.yaml - only payment needs this
environment: dev
service:
  tier: standard  # Exception for critical service
```

**Avoid:**
```yaml
# payment-api-dev.yaml
# search-api-dev.yaml
# user-service-dev.yaml
# ... repeating same tier: low everywhere
```

### 2. Keep Environment Files Small

**Good:**
```yaml
environment: dev
service:
  tier: low
```

**Avoid:**
```yaml
environment: dev
service:
  name: payment-api        # Don't repeat base config
  team: payments           # These don't change
  type: api
  tier: low               # Only this changes
```

### 3. Document Environment-Specific Behavior

```yaml
# environments/prod.yaml
environment: prod

# Production uses stricter SLOs and higher resource limits
# All prod services are tier: critical or higher
# PagerDuty alerts go to on-call rotation

service:
  tier: critical
```

### 4. Use Consistent Environment Names

**Recommended:**
- `dev` (not `development`, `local`, `dev-env`)
- `staging` (not `stage`, `stg`, `pre-prod`)
- `prod` (not `production`, `live`, `prd`)

### 5. Validate All Environments

```bash
# Validate each environment before deployment
for env in dev staging prod; do
  nthlayer validate payment-api.yaml --env $env --strict
done
```

### 6. Version Control Environment Files

```bash
git add services/environments/
git commit -m "Add production environment overrides for payment-api"
```

### 7. Use Environment-Specific CI/CD Pipelines

```yaml
# .github/workflows/deploy-dev.yml
- name: Generate SLOs for dev
  run: nthlayer generate-slo services/*.yaml --env dev

# .github/workflows/deploy-prod.yml
- name: Generate SLOs for prod
  run: nthlayer generate-slo services/*.yaml --env prod
```

---

## Troubleshooting

### Environment File Not Found

**Symptom:**
```bash
$ nthlayer generate-slo payment-api.yaml --env dev
# Uses base config, no override applied
```

**Solution:**
Check file paths:
```bash
ls services/environments/dev.yaml
ls services/environments/payment-api-dev.yaml
```

Environment files must be in `environments/` subdirectory relative to service file.

### Overrides Not Applied

**Symptom:**
Configuration seems unchanged with `--env` flag.

**Debugging:**
1. Check environment name matches file:
   ```bash
   # File: environments/dev.yaml
   # Must specify: --env dev (not --env development)
   ```

2. Verify environment field in file:
   ```yaml
   environment: dev  # Must match --env value
   ```

3. Check merge behavior - lists replace, dicts merge:
   ```yaml
   # This replaces entire resources list
   resources:
     - kind: SLO
       name: new-slo
   ```

### Wrong Environment Applied

**Symptom:**
Service-specific override ignored, using shared instead.

**Cause:**
Service-specific files must match service name exactly:

**Correct:**
```
services/payment-api.yaml
services/environments/payment-api-dev.yaml  # ✅ Matches
```

**Incorrect:**
```
services/payment-api.yaml
services/environments/paymentapi-dev.yaml   # ❌ No hyphen
```

### ${env} Variable Not Substituted

**Symptom:**
`${env}` appears literally in output.

**Cause:**
Variable substitution happens during parsing. Ensure:

1. Using `--env` flag
2. Variable is in string context:
   ```yaml
   description: "Alerts for ${env}"  # ✅ Works
   count: ${env}                      # ❌ Not a string
   ```

### Validation Fails with Environment

**Symptom:**
```bash
$ nthlayer validate payment-api.yaml --env dev --strict
❌ Validation failed
```

**Solution:**
Check that merged configuration is valid:
```bash
# Test without strict mode first
nthlayer validate payment-api.yaml --env dev

# Fix errors, then enable strict
nthlayer validate payment-api.yaml --env dev --strict
```

### Can't Find Generated Output

**Symptom:**
Generated files not where expected.

**Cause:**
Output directory doesn't include environment name. You may want to separate outputs:

```bash
# Generate to environment-specific directories
nthlayer generate-slo payment-api.yaml --env dev \
  --output generated/dev/

nthlayer generate-slo payment-api.yaml --env prod \
  --output generated/prod/
```

---

## Examples

### Complete Example: Payment API

**Base Service (services/payment-api.yaml):**
```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  metadata:
    cost_center: 12345

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        success_rate:
          total_query: 'sum(rate(http_requests_total{service="payment-api"}[5m]))'
          error_query: 'sum(rate(http_requests_total{service="payment-api",status=~"5.."}[5m]))'
  
  - kind: SLO
    name: latency
    spec:
      objective: 99.0
      window: 30d
      threshold_ms: 500
      
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
        - type: redis
```

**Dev Environment (services/environments/dev.yaml):**
```yaml
environment: dev

service:
  tier: low

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0  # Relaxed
      
  - kind: SLO
    name: latency
    spec:
      objective: 95.0
      threshold_ms: 1000  # More lenient
```

**Production Override (services/environments/payment-api-prod.yaml):**
```yaml
environment: prod

service:
  tier: critical

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99  # Extra nine
      
  - kind: SLO
    name: latency
    spec:
      threshold_ms: 300  # Stricter
      
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
          instance: payment-db-prod.company.com
          connection_pool: 50
        - type: redis
          instance: payment-cache-prod.company.com
          cluster: true
```

**Usage:**
```bash
# Development
nthlayer generate-slo services/payment-api.yaml --env dev
# Result: 95.0% availability, 1000ms latency, tier=low

# Production  
nthlayer generate-slo services/payment-api.yaml --env prod
# Result: 99.99% availability, 300ms latency, tier=critical, prod DBs
```

---

## Summary

### Key Takeaways

1. **`--env` flag** enables environment-specific configuration
2. **Deep merge** means you only override what changes
3. **File organization** matters - shared vs service-specific
4. **All commands** support `--env` flag
5. **Backward compatible** - `--env` is optional

### Quick Reference

| Task | Command |
|------|---------|
| Generate dev SLOs | `nthlayer generate-slo service.yaml --env dev` |
| Generate prod alerts | `nthlayer generate-alerts service.yaml --env prod` |
| Validate staging | `nthlayer validate service.yaml --env staging` |
| Setup PagerDuty | `nthlayer setup-pagerduty service.yaml --env prod` |
| Check deploy gate | `nthlayer check-deploy service.yaml --env prod` |

### Next Steps

1. ✅ Create your first environment file
2. ✅ Test with `--env dev`
3. ✅ Add service-specific overrides as needed
4. ✅ Integrate into CI/CD pipelines
5. ✅ Document your environment strategy for your team

---

## Need Help?

- **Examples:** See `examples/environments/` directory
- **Foundation:** Read `MULTI_ENV_FOUNDATION_COMPLETE.md`
- **Implementation:** See `ENV_FLAG_COMPLETE.md`
- **Issues:** Open a GitHub issue

Happy multi-environment configuration! 🚀
