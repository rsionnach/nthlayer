# NthLayer Service Templates Reference

Pre-configured service templates to accelerate onboarding.

---

## Overview

Templates provide battle-tested configurations for common service types. Instead of writing 80+ lines of YAML, use a template and customize only what's different.

### Benefits

- ✅ **5-minute onboarding** - From zero to SLO in minutes
- ✅ **Best practices built-in** - Proven SLO targets and thresholds
- ✅ **Consistent across services** - Same patterns everywhere
- ✅ **Easy to customize** - Override any resource

### Usage

```yaml
service:
  name: my-api
  team: platform
  tier: critical
  template: critical-api  # 🎨 That's it!
```

Or use the init command:

```bash
nthlayer init my-api --team platform --template critical-api
```

---

## Available Templates

### critical-api

**Use for:** User-facing APIs, payment systems, authentication services

**Characteristics:**
- **SLO Target:** 99.9% availability (3.6 hours downtime/month)
- **Latency:** p95 < 500ms
- **PagerDuty:** High urgency (pages immediately)
- **Use when:** Downtime directly impacts users or revenue

**Resources:**
- ✅ Availability SLO (99.9%)
- ✅ Latency p95 SLO (99.0% under 500ms)
- ✅ PagerDuty integration (high urgency)

**Example:**

```yaml
service:
  name: payment-api
  team: payments
  tier: critical
  template: critical-api
```

**Generated SLOs:**
- `payment-api-availability`: 99.9% availability
- `payment-api-latency-p95`: 99% of requests < 500ms

---

### standard-api

**Use for:** Internal APIs, admin tools, reporting services

**Characteristics:**
- **SLO Target:** 99.5% availability (21.6 hours downtime/month)
- **Latency:** p95 < 1000ms
- **PagerDuty:** Low urgency (ticket only, no page)
- **Use when:** Service is important but has some tolerance for downtime

**Resources:**
- ✅ Availability SLO (99.5%)
- ✅ Latency p95 SLO (95.0% under 1000ms)
- ✅ PagerDuty integration (low urgency)

**Example:**

```yaml
service:
  name: admin-api
  team: platform
  tier: standard
  template: standard-api
```

**When to use vs critical-api:**
- Use `standard-api` for internal-only services
- Use `critical-api` for user-facing services
- Consider error budget: 99.5% = 3.5x more downtime allowed

---

### low-api

**Use for:** Batch APIs, dev/staging services, non-critical endpoints

**Characteristics:**
- **SLO Target:** 99.0% availability (43.2 hours downtime/month)
- **Latency:** p95 < 2000ms (relaxed)
- **PagerDuty:** Not included (add manually if needed)
- **Use when:** Service can tolerate occasional failures

**Resources:**
- ✅ Availability SLO (99.0%)
- ✅ Latency p95 SLO (90.0% under 2000ms)

**Example:**

```yaml
service:
  name: batch-processor
  team: data
  tier: low
  template: low-api
```

**Note:** No PagerDuty by default. Add manually if needed:

```yaml
service:
  name: batch-processor
  tier: low
  template: low-api

resources:
  - kind: PagerDuty
    name: primary
    spec:
      urgency: low
```

---

### background-job

**Use for:** Queue workers, async processors, scheduled jobs

**Characteristics:**
- **SLO Target:** 99.0% success rate
- **Processing Time:** p95 < 60 seconds
- **PagerDuty:** Low urgency
- **Use when:** Service processes async work from queues

**Resources:**
- ✅ Success rate SLO (99.0%)
- ✅ Processing latency SLO (95.0% under 60s)
- ✅ PagerDuty integration (low urgency)

**Example:**

```yaml
service:
  name: email-sender
  team: notifications
  tier: standard
  type: background-job
  template: background-job
```

**SLO Queries:**

```yaml
# Success rate
sum(rate(job_success_total{service="${service}"}[5m]))
/
sum(rate(job_total{service="${service}"}[5m]))

# Processing latency
histogram_quantile(0.95,
  rate(job_duration_seconds_bucket{service="${service}"}[5m])
)
```

**Metrics Required:**
- `job_success_total` - Counter of successful job completions
- `job_total` - Counter of all job attempts
- `job_duration_seconds_bucket` - Histogram of job durations

---

### pipeline

**Use for:** ETL jobs, data pipelines, batch processors

**Characteristics:**
- **SLO Target:** 95.0% success rate (more tolerance than APIs)
- **Freshness:** p95 < 6 hours
- **PagerDuty:** Not included (batch jobs rarely page)
- **Use when:** Data pipeline with relaxed SLOs

**Resources:**
- ✅ Success rate SLO (95.0%)
- ✅ Data freshness SLO (95.0% under 6 hours)

**Example:**

```yaml
service:
  name: user-analytics-etl
  team: data
  tier: standard
  type: pipeline
  template: pipeline
```

**SLO Queries:**

```yaml
# Success rate
sum(rate(pipeline_success_total{service="${service}"}[5m]))
/
sum(rate(pipeline_runs_total{service="${service}"}[5m]))

# Freshness (pipeline duration)
histogram_quantile(0.95,
  rate(pipeline_duration_seconds_bucket{service="${service}"}[5m])
)
```

**Metrics Required:**
- `pipeline_success_total` - Counter of successful pipeline runs
- `pipeline_runs_total` - Counter of all pipeline runs
- `pipeline_duration_seconds_bucket` - Histogram of pipeline durations

---

## Template Comparison

| Template | Tier | Availability | Latency Target | PagerDuty | Best For |
|----------|------|--------------|----------------|-----------|----------|
| **critical-api** | critical | 99.9% | 500ms | High | User-facing APIs |
| **standard-api** | standard | 99.5% | 1000ms | Low | Internal APIs |
| **low-api** | low | 99.0% | 2000ms | None | Batch APIs |
| **background-job** | standard | 99.0% success | 60s | Low | Queue workers |
| **pipeline** | standard | 95.0% success | 6h | None | ETL jobs |

---

## Customizing Templates

Templates are starting points. Override any resource to customize:

### Override Latency Threshold

```yaml
service:
  name: fast-api
  template: critical-api  # Default: 500ms

resources:
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 200  # Stricter than default
```

### Override PagerDuty Settings

```yaml
service:
  name: my-api
  template: standard-api  # Default: low urgency

resources:
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high  # Upgrade to high urgency
      escalation_policy: custom-policy
```

### Add New Resources

```yaml
service:
  name: payment-api
  template: critical-api

resources:
  # Add dependencies (not in template)
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: high
```

### Add Additional SLOs

```yaml
service:
  name: api-gateway
  template: critical-api

resources:
  # Add custom SLO
  - kind: SLO
    name: error-rate
    spec:
      objective: 99.9
      indicator:
        type: availability
        query: |
          sum(rate(http_requests{service="${service}",code!~"4.."}[5m]))
          /
          sum(rate(http_requests{service="${service}"}[5m]))
```

---

## Template Variables

All templates support variable substitution:

| Variable | Substituted With | Example |
|----------|------------------|---------|
| `${service}` | Service name | `payment-api` |
| `${team}` | Team name | `payments` |
| `${tier}` | Service tier | `critical` |
| `${type}` | Service type | `api` |

**Example:**

```yaml
# In template
query: |
  rate(http_requests{service="${service}",team="${team}"}[5m])

# After substitution (service=payment-api, team=payments)
query: |
  rate(http_requests{service="payment-api",team="payments"}[5m])
```

---

## Decision Guide

**Choose your template:**

```
┌─────────────────────────────────────┐
│   What type of service?             │
└─────────────────────────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
  HTTP API      Background Job
    │                 │
    ▼                 ▼
┌─────────┐      background-job
│ Impact? │      or pipeline
└─────────┘
    │
    ├─ User-facing ──▶ critical-api
    ├─ Internal ─────▶ standard-api
    └─ Batch/Dev ────▶ low-api
```

**Examples:**

- **Payment API** → `critical-api` (users can't pay if down)
- **Admin Dashboard API** → `standard-api` (internal only)
- **Email Sender** → `background-job` (async processing)
- **Analytics ETL** → `pipeline` (batch job)
- **Dev Environment API** → `low-api` (dev only)

---

## Creating Custom Templates

Want to create organization-specific templates? (Coming soon)

**Example custom template:**

```yaml
# .nthlayer/templates/mobile-api.yaml
name: mobile-api
description: Mobile API with offline support
tier: critical
type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95  # Higher than critical-api

  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      threshold_ms: 1000  # Mobile can tolerate higher latency
```

**Usage:**

```yaml
service:
  name: ios-api
  template: mobile-api  # Custom template
```

**Note:** Custom templates are not yet supported. Coming in a future release.

---

## Template Metrics Requirements

Each template assumes specific metrics exist:

### API Templates (critical-api, standard-api, low-api)

**Required metrics:**
- `http_requests_total{service, code}` - Counter of HTTP requests
- `http_request_duration_seconds_bucket{service}` - Histogram of request durations

**Example instrumentation (Prometheus):**

```python
from prometheus_client import Counter, Histogram

http_requests = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'code']
)

http_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['service']
)
```

### Background Job Template

**Required metrics:**
- `job_success_total{service}` - Counter of successful jobs
- `job_total{service}` - Counter of all job attempts
- `job_duration_seconds_bucket{service}` - Histogram of job durations

### Pipeline Template

**Required metrics:**
- `pipeline_success_total{service}` - Counter of successful runs
- `pipeline_runs_total{service}` - Counter of all runs
- `pipeline_duration_seconds_bucket{service}` - Histogram of run durations

---

## FAQ

### Can I use multiple templates?

No, only one template per service. But you can:
1. Start with one template
2. Override resources as needed
3. Add new resources

### What if my service doesn't fit any template?

Don't use a template! Just define resources manually:

```yaml
service:
  name: custom-service
  team: platform
  tier: critical
  # No template

resources:
  - kind: SLO
    name: custom-slo
    spec:
      # Your custom SLO
```

### Can I see what's in a template before using it?

Yes! Two ways:

```bash
# 1. List all templates
nthlayer list-templates

# 2. Init with dry-run (coming soon)
nthlayer init --template critical-api --dry-run
```

Or check the template files directly:
```bash
cat src/nthlayer/specs/builtin_templates/critical-api.yaml
```

### Do I need all the metrics a template requires?

Yes. Templates assume metrics exist. If you don't have them:

1. Add instrumentation to your service
2. Or override the SLO with a different query
3. Or don't use a template

### Can I mix template resources with custom ones?

Yes! Template resources are merged with your custom resources:

```yaml
service:
  name: my-api
  template: critical-api  # 2 SLOs + PagerDuty

resources:
  # Add dependencies
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service

# Result: 3 template resources + 1 custom = 4 total
```

---

## See Also

- [SCHEMA.md](SCHEMA.md) - Complete YAML reference
- [GETTING_STARTED.md](../GETTING_STARTED.md) - Getting started guide
- [Built-in Templates](../src/nthlayer/specs/builtin_templates/) - Template source files
