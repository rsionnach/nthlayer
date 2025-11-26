# Built-in Service Templates

NthLayer includes 5 pre-configured service templates to accelerate onboarding.

## Available Templates

### critical-api
**Use for:** User-facing APIs, payment systems, authentication services
- **SLO Target:** 99.9% availability
- **Latency:** p95 < 500ms
- **PagerDuty:** High urgency
- **Use when:** Downtime directly impacts users or revenue

### standard-api
**Use for:** Internal APIs, admin tools, reporting services
- **SLO Target:** 99.5% availability
- **Latency:** p95 < 1000ms
- **PagerDuty:** Low urgency
- **Use when:** Service is important but has some tolerance for downtime

### low-api
**Use for:** Batch APIs, dev/staging services, non-critical endpoints
- **SLO Target:** 99.0% availability
- **Latency:** p95 < 2000ms
- **PagerDuty:** Not included (can add manually)
- **Use when:** Service can tolerate occasional failures

### background-job
**Use for:** Queue workers, async processors, scheduled jobs
- **SLO Target:** 99.0% success rate
- **Processing Time:** p95 < 60s
- **PagerDuty:** Low urgency
- **Use when:** Service processes async work

### pipeline
**Use for:** ETL jobs, data pipelines, batch processors
- **SLO Target:** 95.0% success rate
- **Freshness:** p95 < 6 hours
- **PagerDuty:** Not included
- **Use when:** Data pipeline with relaxed SLOs

## Using Templates

```yaml
service:
  name: my-api
  team: platform
  tier: critical
  template: critical-api
```

## Overriding Template Defaults

```yaml
service:
  name: my-api
  team: platform
  tier: critical
  template: critical-api

resources:
  # Override latency threshold
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300  # Stricter than template's 500ms
```

## Template Variables

All templates support these variables:
- `${service}` - Service name
- `${team}` - Team name
- `${tier}` - Service tier

Variables are automatically substituted when the template is applied.
