# Backstage Integration Guide

This guide explains how to integrate NthLayer reliability data into your Backstage service catalog.

## Overview

NthLayer generates static JSON artifacts that Backstage can consume to display reliability data (SLOs, error budgets, deployment gates) on service pages.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ CI/CD Pipeline  │     │  backstage.json  │     │   Backstage     │
│ nthlayer apply  │ ──> │  (static file)   │ ──> │   Frontend      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Prerequisites

1. NthLayer CLI installed (`pip install nthlayer`)
2. Service definitions with SLOs (OpenSRM or legacy format)
3. Backstage instance with catalog configured

## Supported Formats

NthLayer supports two service definition formats:

### OpenSRM Format (Recommended)

```yaml
# payment-api.reliability.yaml
apiVersion: srm/v1
kind: ReliabilitySpec
metadata:
  name: payment-api
  team: payments
  tier: critical
spec:
  slos:
    - name: availability
      target: 99.95
      window: 30d
```

### Legacy Format (Still Supported)

```yaml
# payment-api.yaml
service:
  name: payment-api
  team: payments
  tier: critical
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
```

The generator auto-detects the format—no configuration needed.

## Step 1: Generate Artifacts

Run `nthlayer apply` in your CI/CD pipeline to generate the `backstage.json` artifact:

```bash
# OpenSRM format (recommended)
nthlayer apply payment-api.reliability.yaml

# Legacy format (still supported)
nthlayer apply services/payment-api.yaml

# Or generate only the Backstage artifact
nthlayer generate-backstage payment-api.reliability.yaml
```

This creates:
```
generated/
└── payment-api/
    ├── backstage.json      # ← Backstage reads this
    ├── alerts.yaml
    ├── dashboard.json
    └── sloth/
        └── payment-api.yaml
```

## Step 2: Store Artifacts

Choose where to store the generated `backstage.json`:

### Option A: Commit to Repository (Recommended)

```bash
# In your CI/CD pipeline
nthlayer apply services/payment-api.yaml
git add generated/
git commit -m "Update NthLayer artifacts"
git push
```

### Option B: Artifact Storage (S3, GCS, etc.)

```bash
# Upload to S3
aws s3 cp generated/payment-api/backstage.json \
  s3://my-artifacts/nthlayer/payment-api/backstage.json

# Or GCS
gsutil cp generated/payment-api/backstage.json \
  gs://my-artifacts/nthlayer/payment-api/backstage.json
```

### Option C: Artifact Server

Serve from your CI/CD artifact storage (GitHub Actions artifacts, GitLab artifacts, etc.)

## Step 3: Configure Backstage Catalog

### Option A: Catalog Location (Bulk Discovery)

Add to your `app-config.yaml` to auto-discover all NthLayer artifacts:

```yaml
# app-config.yaml
catalog:
  locations:
    # Discover all backstage.json files in generated directories
    - type: file
      target: ./generated/*/backstage.json
      rules:
        - allow: [Component]

    # Or from a specific URL pattern
    - type: url
      target: https://artifacts.example.com/nthlayer/*/backstage.json
```

### Option B: Entity Annotation (Per-Service)

Annotate individual Component entities in their `catalog-info.yaml`:

```yaml
# catalog-info.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: payment-api
  description: Payment processing service
  annotations:
    # Relative path (from catalog-info.yaml location)
    nthlayer.dev/entity: ./generated/payment-api/backstage.json

    # Or absolute URL
    # nthlayer.dev/entity: https://artifacts.example.com/nthlayer/payment-api/backstage.json
spec:
  type: service
  lifecycle: production
  owner: payments-team
```

## Step 4: Install the Plugin

### Install Dependencies

```bash
# From your Backstage root directory
cd packages/app
yarn add @internal/plugin-nthlayer
```

### Add to Entity Page

Edit `packages/app/src/components/catalog/EntityPage.tsx`:

```tsx
import {
  EntityNthlayerCard,
  isNthlayerAvailable
} from '@internal/plugin-nthlayer';

// Option 1: Add to overview tab (conditional)
const overviewContent = (
  <Grid container spacing={3}>
    {/* ... other cards ... */}

    <EntitySwitch>
      <EntitySwitch.Case if={isNthlayerAvailable}>
        <Grid item xs={12} md={6}>
          <EntityNthlayerCard />
        </Grid>
      </EntitySwitch.Case>
    </EntitySwitch>
  </Grid>
);

// Option 2: Add as dedicated "Reliability" tab
const serviceEntityPage = (
  <EntityLayout>
    <EntityLayout.Route path="/" title="Overview">
      {overviewContent}
    </EntityLayout.Route>

    <EntityLayout.Route
      path="/reliability"
      title="Reliability"
      if={isNthlayerAvailable}
    >
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <EntityNthlayerCard />
        </Grid>
      </Grid>
    </EntityLayout.Route>
  </EntityLayout>
);
```

## Step 5: Verify Integration

1. **Check annotation**: Ensure your entity has the `nthlayer.dev/entity` annotation
2. **Verify JSON accessible**: The JSON URL should be reachable from Backstage
3. **View entity page**: Navigate to the service in Backstage catalog

## CI/CD Integration Examples

### GitHub Actions

```yaml
# .github/workflows/reliability.yml
name: Update Reliability Artifacts

on:
  push:
    paths:
      - '**/*.reliability.yaml'  # OpenSRM format
      - 'services/**/*.yaml'      # Legacy format
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pip install nthlayer

      - name: Generate artifacts
        run: |
          # Process OpenSRM format files
          for service in **/*.reliability.yaml; do
            [ -f "$service" ] && nthlayer apply "$service"
          done
          # Process legacy format files
          for service in services/*.yaml; do
            [ -f "$service" ] && nthlayer apply "$service"
          done

      - name: Commit artifacts
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add generated/
          git diff --staged --quiet || git commit -m "chore: update reliability artifacts"
          git push
```

### GitLab CI

```yaml
# .gitlab-ci.yml
generate-reliability:
  stage: build
  image: python:3.11
  script:
    - pip install nthlayer
    - |
      # Process OpenSRM format files
      find . -name "*.reliability.yaml" -exec nthlayer apply {} \;
      # Process legacy format files
      for service in services/*.yaml; do
        [ -f "$service" ] && nthlayer apply "$service"
      done
  artifacts:
    paths:
      - generated/
    expire_in: 1 week
  only:
    changes:
      - '**/*.reliability.yaml'
      - services/**/*.yaml
```

### Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any

    stages {
        stage('Generate Reliability Artifacts') {
            steps {
                sh 'pip install nthlayer'
                sh '''
                    # Process OpenSRM format files
                    find . -name "*.reliability.yaml" -exec nthlayer apply {} \\;
                    # Process legacy format files
                    for service in services/*.yaml; do
                        [ -f "$service" ] && nthlayer apply "$service"
                    done
                '''
            }
        }

        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: 'generated/**/*'
            }
        }
    }
}
```

## Troubleshooting

### "NthLayer not configured" warning

**Cause**: Entity missing the `nthlayer.dev/entity` annotation

**Fix**: Add annotation to `catalog-info.yaml`:
```yaml
metadata:
  annotations:
    nthlayer.dev/entity: ./generated/my-service/backstage.json
```

### "Failed to load reliability data"

**Cause**: JSON file not accessible from Backstage

**Fix**:
1. Check the URL/path is correct
2. Ensure CORS headers if serving from different domain
3. Verify file exists and is valid JSON

### Card shows "No data available"

**Cause**: JSON file is empty or malformed

**Fix**:
1. Regenerate with `nthlayer apply`
2. Validate JSON: `cat backstage.json | jq .`

### SLOs show "Status unknown"

**Cause**: Static generation doesn't include live metrics

**This is expected** - the JSON is generated at build time without Prometheus access. Live values (`currentValue`, `status`) will be null unless you:
1. Run generation with Prometheus access
2. Implement a backend plugin to fetch live data

## Architecture Decisions

### Why Static JSON?

1. **No runtime dependency**: Works without running NthLayer service
2. **Version controlled**: Artifacts can be reviewed in PRs
3. **Cacheable**: CDN-friendly, fast loading
4. **Offline-capable**: Backstage works even if NthLayer is down

### Why Annotation-Based?

1. **Explicit opt-in**: Only annotated entities show reliability data
2. **Flexible paths**: Each service can have different artifact locations
3. **Standard pattern**: Follows Backstage annotation conventions

## Next Steps

- [NthLayer Service Definition](./service-definition.md) - How to write service YAML
- [SLO Configuration](./slo-configuration.md) - Defining SLOs
- [Deployment Gates](./deployment-gates.md) - Error budget-based deployment controls
