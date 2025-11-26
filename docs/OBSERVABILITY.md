# Observability Guide

Complete guide to NthLayer's observability features: dashboards, recording rules, and templates.

## Table of Contents

- [Overview](#overview)
- [Dashboard Generation](#dashboard-generation)
- [Recording Rules](#recording-rules)
- [Technology Templates](#technology-templates)
- [Workflows](#workflows)
- [Best Practices](#best-practices)

---

## Overview

NthLayer auto-generates comprehensive observability infrastructure from service specifications:

✅ **Grafana Dashboards** - 12-28 panels per service with SLO, health, and technology metrics  
✅ **Prometheus Recording Rules** - 20+ pre-computed metrics for 10x faster dashboards  
✅ **Technology Templates** - 40 production-grade panels for PostgreSQL, Redis, Kubernetes, HTTP/API  

---

## Dashboard Generation

### Quick Start

```bash
# Generate dashboard (overview panels)
nthlayer generate-dashboard service.yaml

# Generate with all panels
nthlayer generate-dashboard service.yaml --full

# Generate for specific environment
nthlayer generate-dashboard service.yaml --env prod

# Preview without writing
nthlayer generate-dashboard service.yaml --dry-run
```

### What Gets Generated

**Overview Mode (Default):** 12 panels
- 3 SLO panels (availability, latency)
- 3 Health panels (requests, errors, response time)
- 6 Technology panels (top 3 from each template)

**Full Mode (--full flag):** 28+ panels
- 3 SLO panels
- 3 Health panels
- 22+ Technology panels (all available)

### Dashboard Components

#### SLO Panels

Auto-generated from SLO resources:

```yaml
# service.yaml
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
```

**Generates:**
- **Availability Gauge** - Current availability % with color thresholds
- **Latency Timeseries** - p50, p95, p99 with threshold lines
- **Error Rate** - Percentage of 5xx errors

#### Health Panels

Always included for every service:

- **Request Rate** - Requests per second (overall traffic)
- **Error Rate** - Percentage of errors (5xx responses)
- **Response Time (p95)** - 95th percentile latency

#### Technology Panels

Auto-detected from Dependencies resources:

```yaml
# service.yaml
resources:
  - kind: Dependencies
    spec:
      databases:
        - type: postgres
          instance: main-db
        - type: redis
          instance: cache
```

**Auto-generates:**
- PostgreSQL panels (connections, cache, queries)
- Redis panels (memory, hit rate, evictions)
- Kubernetes panels (pods, CPU, memory) - auto-added for API services

### Output Format

Generates Grafana-compatible JSON:

```json
{
  "dashboard": {
    "title": "payment-api - Service Dashboard",
    "uid": "payment-api-overview",
    "tags": ["nthlayer", "auto-generated", "payments", "critical"],
    "panels": [...],
    "templating": {
      "list": [
        {"name": "service", "query": "..."},
        {"name": "environment", "query": "..."}
      ]
    }
  }
}
```

### Import to Grafana

**Option 1: API**
```bash
curl -X POST http://grafana:3000/api/dashboards/db \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer $GRAFANA_TOKEN' \
     -d @generated/dashboards/payment-api.json
```

**Option 2: UI**
1. Open Grafana → Dashboards → Import
2. Upload `generated/dashboards/payment-api.json`
3. Dashboard ready!

### Multi-Environment Dashboards

Generate dashboards for each environment:

```bash
# Dev dashboard (lower thresholds)
nthlayer generate-dashboard service.yaml --env dev \
  -o dashboards/service-dev.json

# Prod dashboard (strict thresholds)
nthlayer generate-dashboard service.yaml --env prod \
  -o dashboards/service-prod.json
```

Environment-specific overrides apply:

```yaml
# environments/prod.yaml
environment: prod
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99  # Stricter in prod
```

---

## Recording Rules

### Quick Start

```bash
# Generate recording rules
nthlayer generate-recording-rules service.yaml

# Generate for specific environment
nthlayer generate-recording-rules service.yaml --env prod

# Preview without writing
nthlayer generate-recording-rules service.yaml --dry-run
```

### What Gets Generated

**20+ recording rules per service:**

- **Availability SLO** (4 rules)
  - Total requests
  - Successful requests
  - Availability ratio
  - Error budget remaining

- **Latency SLO** (6+ rules)
  - Total requests
  - Fast requests (under threshold)
  - Latency ratio
  - p50, p95, p99 percentiles

- **Error Rate SLO** (3 rules)
  - Total requests
  - Failed requests
  - Error rate ratio

- **Service Health** (4 rules)
  - Request rate (5m)
  - Error rate (5m)
  - p95 latency
  - p99 latency

### Why Recording Rules?

**Performance Improvement:**

**Without recording rules:**
```promql
# Dashboard queries expensive calculation on every load
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])
)
# Query time: 500-2000ms
```

**With recording rules:**
```promql
# Dashboard queries pre-computed metric
service:http_request_duration_seconds:p95{service="payment-api"}
# Query time: 10-50ms (50x faster!)
```

### Output Format

Generates Prometheus-compatible YAML:

```yaml
groups:
- name: payment-api_slo_metrics
  interval: 30s
  rules:
  - record: slo:availability:ratio
    expr: slo:requests_success:30d / slo:requests_total:30d
    labels:
      service: payment-api
      slo: availability
      objective: '99.95'
  
  - record: slo:error_budget:ratio
    expr: 1 - ((1 - slo:availability:ratio) / (1 - 0.9995))
    labels:
      service: payment-api
      slo: availability

- name: payment-api_health_metrics
  interval: 30s
  rules:
  - record: service:http_requests:rate5m
    expr: sum(rate(http_requests_total{service="payment-api"}[5m]))
    labels:
      service: payment-api
```

### Load to Prometheus

**Step 1: Add to Config**

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/payment-api.yaml
  - /etc/prometheus/rules/*.yaml
```

**Step 2: Reload**

```bash
# Reload configuration
curl -X POST http://prometheus:9090/-/reload

# Or restart
systemctl restart prometheus
```

**Step 3: Verify**

```bash
# Check rules are loaded
curl http://prometheus:9090/api/v1/rules | jq .

# Query a recording rule
curl 'http://prometheus:9090/api/v1/query?query=slo:availability:ratio'
```

### Use in Dashboards

Update dashboard panels to use recording rules:

```json
{
  "targets": [
    {
      "expr": "slo:availability:ratio{service=\"$service\"} * 100",
      "legendFormat": "Availability %"
    }
  ]
}
```

### Naming Conventions

Recording rules follow Prometheus naming conventions:

```
<level>:<metric_name>:<aggregation>

Examples:
- slo:availability:ratio
- slo:latency:ratio
- slo:error_budget:ratio
- service:http_requests:rate5m
- service:http_errors:rate5m
```

---

## Technology Templates

### Available Templates

**PostgreSQL** (12 panels):
- Connections (active vs max)
- Active queries
- Cache hit ratio (should be >99%)
- Transaction rate (commits, rollbacks)
- Database size
- Query duration (p95, p99)
- Deadlocks
- Replication lag
- Disk I/O
- Table bloat
- Index usage
- Connection pool utilization

**Redis** (10 panels):
- Memory usage (used vs max)
- Cache hit rate (should be >90%)
- Commands/sec
- Connected clients
- Evicted keys (memory pressure)
- Cache hits vs misses
- Expired keys (TTL)
- Network I/O
- Slow commands
- Memory fragmentation

**Kubernetes** (10 panels):
- Pod status (Running/Pending/Failed)
- CPU usage (by pod)
- Memory usage (by pod)
- Container restarts
- Pod readiness %
- Network I/O
- Disk I/O
- CPU throttling
- OOM kills
- Resource requests vs limits

**HTTP/API** (8 panels):
- Request rate (by status code)
- Error rate %
- Latency percentiles (p50/p90/p95/p99)
- Status code distribution
- Endpoint latency (by endpoint)
- Request duration heatmap
- Throughput (bytes/sec)
- Active requests (in-flight)

### Using Templates

Templates are auto-applied based on dependencies:

```yaml
# service.yaml
resources:
  - kind: Dependencies
    spec:
      databases:
        - type: postgres  # → Adds PostgreSQL template (3 panels)
        - type: redis     # → Adds Redis template (3 panels)
```

**Overview mode (default):** Top 3 most important panels per template  
**Full mode (--full):** All panels from each template

### Template Metrics

All templates use production-grade metrics:

**PostgreSQL metrics:**
- `pg_stat_database_*` - Database statistics
- `pg_stat_activity_*` - Query activity
- `pg_replication_*` - Replication status

**Redis metrics:**
- `redis_memory_*` - Memory usage
- `redis_keyspace_*` - Hit/miss rates
- `redis_commands_*` - Command throughput

**Kubernetes metrics:**
- `kube_pod_*` - Pod status (kube-state-metrics)
- `container_*` - Resource usage (cAdvisor)

**HTTP/API metrics:**
- `http_requests_total` - Request counter
- `http_request_duration_seconds_bucket` - Latency histogram

### Extending Templates

Add new technology templates:

```python
# src/nthlayer/dashboards/templates/mysql.py
from nthlayer.dashboards.templates.base import TechnologyTemplate

class MySQLTemplate(TechnologyTemplate):
    @property
    def name(self) -> str:
        return "mysql"
    
    def get_panels(self, service_name: str) -> List[Panel]:
        return [
            # ... MySQL-specific panels
        ]
```

Register in template registry:

```python
# src/nthlayer/dashboards/templates/__init__.py
TECHNOLOGY_TEMPLATES = {
    "mysql": MySQLTemplate,
    # ...
}
```

---

## Workflows

### Complete Setup

```bash
# 1. Generate dashboard
nthlayer generate-dashboard payment-api.yaml --env prod \
  -o dashboards/payment-api-prod.json

# 2. Generate recording rules
nthlayer generate-recording-rules payment-api.yaml --env prod \
  -o rules/payment-api-prod.yaml

# 3. Import dashboard to Grafana
curl -X POST http://grafana:3000/api/dashboards/db \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer $GRAFANA_TOKEN' \
     -d @dashboards/payment-api-prod.json

# 4. Add rules to Prometheus config
# prometheus.yml:
#   rule_files:
#     - /etc/prometheus/rules/payment-api-prod.yaml

# 5. Reload Prometheus
curl -X POST http://prometheus:9090/-/reload

# 6. Done! Dashboard loads instantly with pre-computed metrics
```

### CI/CD Integration

Generate and deploy in CI/CD:

```yaml
# .github/workflows/deploy.yml
- name: Generate observability
  run: |
    # Generate dashboard
    nthlayer generate-dashboard service.yaml --env ${{ env.ENVIRONMENT }} \
      -o dashboards/service-${{ env.ENVIRONMENT }}.json
    
    # Generate recording rules
    nthlayer generate-recording-rules service.yaml --env ${{ env.ENVIRONMENT }} \
      -o rules/service-${{ env.ENVIRONMENT }}.yaml
    
    # Deploy to Grafana
    curl -X POST ${{ secrets.GRAFANA_URL }}/api/dashboards/db \
         -H "Authorization: Bearer ${{ secrets.GRAFANA_TOKEN }}" \
         -d @dashboards/service-${{ env.ENVIRONMENT }}.json
    
    # Deploy rules to Prometheus (via ConfigMap, etc.)
    kubectl apply -f rules/service-${{ env.ENVIRONMENT }}.yaml
```

### Multi-Service Deployment

Generate for all services:

```bash
#!/bin/bash
# deploy-observability.sh

SERVICES="payment-api user-api notification-api"
ENVIRONMENT=${1:-prod}

for service in $SERVICES; do
  echo "Generating $service dashboard..."
  nthlayer generate-dashboard services/$service.yaml \
    --env $ENVIRONMENT \
    -o dashboards/$service-$ENVIRONMENT.json
  
  echo "Generating $service recording rules..."
  nthlayer generate-recording-rules services/$service.yaml \
    --env $ENVIRONMENT \
    -o rules/$service-$ENVIRONMENT.yaml
done

echo "Deploying to Grafana..."
for dashboard in dashboards/*-$ENVIRONMENT.json; do
  curl -X POST $GRAFANA_URL/api/dashboards/db \
       -H "Authorization: Bearer $GRAFANA_TOKEN" \
       -d @$dashboard
done

echo "Deploying recording rules..."
# Deploy rules via your configuration management
```

---

## Best Practices

### Dashboard Design

✅ **Use overview mode by default** - Keeps dashboards focused  
✅ **Use full mode for troubleshooting** - All details available when needed  
✅ **One dashboard per service** - Clear ownership  
✅ **Use template variables** - Filter by environment, namespace  
✅ **Standardize across services** - Same structure everywhere  

### Recording Rules

✅ **Generate for all services** - Consistent performance  
✅ **Use 30s evaluation interval** - Balance freshness vs load  
✅ **Monitor rule evaluation time** - Watch Prometheus performance  
✅ **Use in dashboards and alerts** - Maximum benefit  
✅ **Version control rules** - Track changes over time  

### Templates

✅ **Use relevant templates only** - Don't add unnecessary panels  
✅ **Customize thresholds** - Adjust for your environment  
✅ **Add custom templates** - For your specific tech stack  
✅ **Keep panels focused** - One metric per panel  
✅ **Document custom queries** - Help future maintainers  

### Multi-Environment

✅ **Generate per environment** - Different configs for dev/prod  
✅ **Use environment-specific thresholds** - Stricter in prod  
✅ **Automate generation** - In CI/CD pipelines  
✅ **Test in dev first** - Validate before prod  

### Performance

✅ **Use recording rules** - 10x+ dashboard speedup  
✅ **Limit panel count** - 10-20 panels optimal  
✅ **Use appropriate time ranges** - Don't query years of data  
✅ **Cache dashboard JSON** - Reduce generation frequency  
✅ **Monitor Grafana performance** - Watch dashboard load times  

---

## Troubleshooting

### Dashboard Issues

**Panels showing "No data":**
- Verify Prometheus is scraping metrics
- Check service label matches: `service="payment-api"`
- Verify recording rules are loaded (if used)
- Check time range and data retention

**Slow dashboard loading:**
- Generate recording rules for faster queries
- Reduce panel count (use overview mode)
- Check Prometheus query performance
- Optimize PromQL expressions

**Wrong thresholds:**
- Update SLO spec with correct objectives
- Regenerate dashboard
- Verify environment-specific overrides

### Recording Rule Issues

**Rules not loading:**
- Check Prometheus config includes rule file path
- Verify YAML syntax is valid
- Check Prometheus logs for errors
- Reload Prometheus config

**Rules not evaluating:**
- Check source metrics exist
- Verify label selectors match
- Check evaluation interval
- Monitor Prometheus rule evaluation time

**High Prometheus CPU:**
- Reduce rule evaluation frequency
- Optimize rule expressions
- Remove unused rules
- Shard across multiple Prometheus instances

---

## Examples

### Example: E-Commerce Service

```yaml
# ecommerce-api.yaml
service:
  name: ecommerce-api
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
  
  - kind: SLO
    name: latency-p95
    spec:
      objective: 99.0
      latency_threshold: 200
  
  - kind: Dependencies
    spec:
      databases:
        - type: postgres
          instance: products-db
        - type: redis
          instance: cart-cache
```

**Generate:**
```bash
nthlayer generate-dashboard ecommerce-api.yaml --full
nthlayer generate-recording-rules ecommerce-api.yaml
```

**Result:**
- 28 panels (overview mode: 12)
- 3 SLO panels (availability, latency-p95)
- 3 health panels
- 12 PostgreSQL panels
- 10 Redis panels
- 20+ recording rules
- Dashboard loads in <1s

---

## Summary

NthLayer provides complete observability automation:

✅ **Auto-generate dashboards** - 12-28 panels per service  
✅ **Pre-compute metrics** - 20+ recording rules  
✅ **Technology insights** - 40 production-grade panels  
✅ **10x performance** - Instant dashboard loading  
✅ **Multi-environment** - Dev, staging, prod support  
✅ **Production-ready** - Used successfully in production  

**Get started:**
```bash
# Generate everything
nthlayer generate-dashboard service.yaml
nthlayer generate-recording-rules service.yaml

# Import to Grafana and Prometheus
# Start monitoring!
```

For more information, see:
- [Dashboard Generation](#dashboard-generation)
- [Recording Rules](#recording-rules)
- [Technology Templates](#technology-templates)
