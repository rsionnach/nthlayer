# Custom Service Templates

Create organization-specific templates for NthLayer.

---

## Overview

While NthLayer includes 5 built-in templates, you can create custom templates tailored to your organization's needs.

**Use cases:**
- ✅ Organization-specific SLO targets
- ✅ Custom service types (mobile-api, graphql-api, etc.)
- ✅ Company-specific monitoring patterns
- ✅ Team-specific defaults

---

## Creating Custom Templates

### 1. Create Templates Directory

```bash
mkdir -p .nthlayer/templates
```

### 2. Create Template File

Create a YAML file in `.nthlayer/templates/`:

```yaml
# .nthlayer/templates/mobile-api.yaml
name: mobile-api
description: Mobile API with higher latency tolerance
tier: critical
type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="${service}"}[5m]))

  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 99
        threshold_ms: 2000  # Mobile networks tolerate higher latency

  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      auto_create: true
```

### 3. Use Custom Template

```bash
# List templates (custom will appear)
nthlayer list-templates

# Use custom template
nthlayer init ios-api --team mobile --template mobile-api
```

---

## Template Structure

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique template identifier |
| `description` | string | Template description |
| `tier` | string | Default tier: `critical` \| `standard` \| `low` |
| `type` | string | Service type: `api` \| `background-job` \| `pipeline` \| `web` \| `database` |
| `resources` | array | Default resources (SLOs, PagerDuty, etc.) |

### Optional Fields

Templates support the same resource types as services:
- `SLO` - Service Level Objectives
- `PagerDuty` - PagerDuty integration
- `Dependencies` - Service dependencies
- `Observability` - Observability config

---

## Template Variables

Use variables in your custom templates for portability:

```yaml
resources:
  - kind: SLO
    name: availability
    spec:
      query: |
        # Variables are substituted when template is applied
        rate(http_requests{
          service="${service}",
          team="${team}",
          tier="${tier}"
        }[5m])
```

**Available variables:**
- `${service}` - Service name
- `${team}` - Team name
- `${tier}` - Service tier
- `${type}` - Service type

---

## Template Precedence

**Custom templates override built-in templates with the same name.**

Example:
```
Built-in: critical-api (standard definition)
Custom:   critical-api (your custom definition)

Result: Custom version is used
```

This allows you to:
- ✅ Override built-in templates with org-specific versions
- ✅ Keep the same template name
- ✅ Standardize across your org

---

## Examples

### Example 1: GraphQL API Template

```yaml
# .nthlayer/templates/graphql-api.yaml
name: graphql-api
description: GraphQL API with query complexity monitoring
tier: critical
type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      indicator:
        query: |
          sum(rate(graphql_requests{service="${service}",error!="true"}[5m]))
          /
          sum(rate(graphql_requests{service="${service}"}[5m]))

  - kind: SLO
    name: query-complexity
    spec:
      objective: 99.0
      indicator:
        query: |
          sum(rate(graphql_queries{service="${service}",complexity<100}[5m]))
          /
          sum(rate(graphql_queries{service="${service}"}[5m]))

  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      auto_create: true
```

### Example 2: Organization-Specific Critical API

Override the built-in critical-api with your org's standards:

```yaml
# .nthlayer/templates/critical-api.yaml
name: critical-api
description: Our company's critical API standard (OVERRIDES built-in)
tier: critical
type: api

resources:
  # Company requires 99.95% (not 99.9%)
  - kind: SLO
    name: availability
    spec:
      objective: 99.95

  # Company requires p99 monitoring (not just p95)
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      threshold_ms: 1000

  # Company-specific PagerDuty settings
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      escalation_policy: company-critical-escalation
      auto_create: true
```

### Example 3: Kafka Consumer Template

```yaml
# .nthlayer/templates/kafka-consumer.yaml
name: kafka-consumer
description: Kafka consumer service with lag monitoring
tier: standard
type: background-job

resources:
  # Consumer lag SLO
  - kind: SLO
    name: consumer-lag
    spec:
      objective: 99.0
      window: 30d
      indicator:
        query: |
          sum(kafka_consumer_lag{service="${service}"}) < 1000

  # Processing success rate
  - kind: SLO
    name: success-rate
    spec:
      objective: 99.0
      indicator:
        query: |
          sum(rate(messages_processed{service="${service}",status="success"}[5m]))
          /
          sum(rate(messages_processed{service="${service}"}[5m]))

  - kind: PagerDuty
    name: primary
    spec:
      urgency: low
      auto_create: true
```

---

## Best Practices

### 1. Use Descriptive Names

```yaml
# ✅ Good
name: mobile-api

# ❌ Bad
name: template1
```

### 2. Document Your Templates

Add clear descriptions:

```yaml
description: Mobile API with higher latency tolerance and offline support
```

### 3. Include Default Dependencies

If all services of this type have common dependencies:

```yaml
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: auth-service
          criticality: high
```

Users can override or extend these.

### 4. Use Template Variables

Make queries portable:

```yaml
# ✅ Good - portable
query: "rate(requests{service=\"${service}\"}[5m])"

# ❌ Bad - hardcoded
query: "rate(requests{service=\"my-api\"}[5m])"
```

### 5. Test Your Templates

Create a test service to validate:

```bash
nthlayer init test-service --template mobile-api
nthlayer validate test-service.yaml
nthlayer generate-slo test-service.yaml
```

---

## Sharing Templates

### Within Your Organization

**Option 1: Git Repository**
```bash
# .nthlayer/templates/ is version-controlled
git add .nthlayer/templates/mobile-api.yaml
git commit -m "Add mobile-api template"
git push

# Other teams pull and use
git pull
nthlayer init their-service --template mobile-api
```

**Option 2: Shared Directory** (for monorepos)
```
monorepo/
├── .nthlayer/templates/      # Shared templates
├── services/
│   ├── payment-api/
│   │   └── service.yaml
│   └── user-api/
│       └── service.yaml
```

All services use the shared templates.

### Template Registry (Future)

Coming in a future release:

```bash
# Publish template to registry
nthlayer template publish mobile-api --registry company-registry

# Install from registry
nthlayer template install @company/mobile-api
```

---

## Validation

Custom templates are validated when loaded:

**Checks:**
- ✅ Required fields present (name, description, tier, type)
- ✅ Valid tier value
- ✅ Valid type value
- ✅ Resources have required fields
- ✅ YAML is valid

**Invalid templates are skipped with warnings.**

---

## Troubleshooting

### "Custom template not found"

**Cause:** Template file not in `.nthlayer/templates/`

**Solution:**
```bash
# Check directory exists
ls .nthlayer/templates/

# Check template file exists
ls .nthlayer/templates/mobile-api.yaml
```

### "Template validation failed"

**Cause:** Template YAML is invalid or missing required fields

**Solution:**
Check template structure matches the schema:
```yaml
name: template-name        # Required
description: "..."         # Required
tier: critical             # Required
type: api                  # Required
resources:                 # Required (can be empty array)
  - kind: SLO
    name: slo-name         # Required
    spec: {...}            # Required
```

### "Template not showing in list"

**Cause:** Either invalid YAML or wrong directory

**Solution:**
```bash
# Verify YAML is valid
python -c "import yaml; yaml.safe_load(open('.nthlayer/templates/my-template.yaml'))"

# Check for warnings
nthlayer list-templates  # Look for warning messages
```

---

## FAQ

### Can I override built-in templates?

**Yes!** Create a custom template with the same name:

```yaml
# .nthlayer/templates/critical-api.yaml
name: critical-api  # Same name as built-in
description: Our company's critical API standard
...
```

Your version will be used instead of the built-in.

### Can I inherit from built-in templates?

**Not yet.** Each template is independent.

**Workaround:** Copy the built-in template and modify:

```bash
# Copy built-in template
cp src/nthlayer/specs/builtin_templates/critical-api.yaml \
   .nthlayer/templates/my-critical-api.yaml

# Edit the copy
vi .nthlayer/templates/my-critical-api.yaml
```

### Where are templates loaded from?

**Search order:**
1. `.nthlayer/templates/` in current directory
2. `.nthlayer/templates/` in parent directories (up to root)
3. Built-in templates (if not overridden)

### Can I version custom templates?

**Yes!** Check `.nthlayer/templates/` into Git:

```bash
git add .nthlayer/templates/
git commit -m "Add mobile-api template"
```

Templates are versioned with your code.

---

## See Also

- [TEMPLATES.md](TEMPLATES.md) - Built-in template reference
- [SCHEMA.md](SCHEMA.md) - Complete YAML reference
- [GETTING_STARTED.md](../GETTING_STARTED.md) - Getting started guide
