# Contracts & Assumptions

NthLayer's verification commands (`nthlayer verify`, `nthlayer check-deploy`) depend on specific contracts between your services and your observability stack. This page documents what NthLayer expects and how to ensure your services meet these requirements.

## Metric Naming Conventions

### Required Labels

NthLayer expects metrics to include a `service` label that matches the service name in your `service.yaml`:

```yaml
# service.yaml
name: checkout-api
```

```promql
# Expected metric labels
http_requests_total{service="checkout-api", status="200"}
http_request_duration_seconds_bucket{service="checkout-api", le="0.5"}
```

### Service Label Matching

The `service` label must exactly match the `name` field in your service.yaml:

| service.yaml name | Expected label |
|-------------------|----------------|
| `checkout-api` | `service="checkout-api"` |
| `user-service` | `service="user-service"` |
| `PaymentAPI` | `service="PaymentAPI"` |

**Common mistake**: Using `app` or `application` instead of `service`:
```promql
# ❌ Won't match
http_requests_total{app="checkout-api"}

# ✅ Will match
http_requests_total{service="checkout-api"}
```

### Status/Code Labels

For availability SLOs, NthLayer expects error status indicators:

| Service Type | Success Pattern | Error Pattern |
|--------------|-----------------|---------------|
| API | `status!~"5.."` | `status=~"5.."` |
| Worker | `status!="failed"` | `status="failed"` |
| Stream | `status!="error"` | `status="error"` |

Alternatively, use `code` instead of `status`:
```promql
http_requests_total{service="checkout-api", code="200"}
```

## What "Metric Exists" Means

When `nthlayer verify` checks if a metric exists, it queries Prometheus for any time series matching the metric name and service label within the last 5 minutes.

### Verification Query

```promql
# NthLayer runs approximately this query:
count(http_requests_total{service="checkout-api"}[5m]) > 0
```

### What Passes Verification

✅ **Passes**: At least one time series exists with any value
```
http_requests_total{service="checkout-api", status="200"} 1523
```

✅ **Passes**: Multiple time series exist
```
http_requests_total{service="checkout-api", status="200"} 1523
http_requests_total{service="checkout-api", status="500"} 12
```

### What Fails Verification

❌ **Fails**: No time series in last 5 minutes
- Service not instrumented
- Service not running
- Wrong service label

❌ **Fails**: Metric exists but wrong label
```
# Metric exists but service label doesn't match
http_requests_total{app="checkout-api"} 1523  # Uses 'app' not 'service'
```

## Required Base Metrics

### API Services (type: api)

| Metric | Purpose | Required For |
|--------|---------|--------------|
| `http_requests_total` | Request count | Availability SLO |
| `http_request_duration_seconds_bucket` | Latency histogram | Latency SLO |

### Worker Services (type: worker)

| Metric | Purpose | Required For |
|--------|---------|--------------|
| `job_processed_total` | Job count | Throughput SLO |
| `job_duration_seconds_bucket` | Job duration | Processing time SLO |

### Stream Services (type: stream)

| Metric | Purpose | Required For |
|--------|---------|--------------|
| `messages_processed_total` | Message count | Throughput SLO |
| `message_processing_duration_seconds_bucket` | Processing time | Latency SLO |

## Multi-Cluster & Multi-Tenant Handling

### Federated Prometheus

If you use Prometheus federation, NthLayer queries the federation endpoint. Ensure:

1. Metrics are federated with original labels intact
2. The `service` label is not rewritten during federation
3. Query latency accounts for federation delay

### Multi-Tenant Prometheus (Mimir/Cortex)

Set the tenant header via environment variable:

```bash
export MIMIR_TENANT_ID=your-tenant
nthlayer verify services/checkout-api.yaml
```

Or in your service.yaml:

```yaml
environments:
  production:
    prometheus:
      url: https://mimir.example.com/prometheus
      tenant_id: production
```

### Recording Rules

If your SLO metrics are computed via recording rules:

```yaml
# Recording rule
- record: service:http_requests:rate5m
  expr: sum(rate(http_requests_total[5m])) by (service)
```

NthLayer can verify these, but there's a delay:
- Recording rules evaluate on interval (typically 1-5 minutes)
- New services may not have recorded metrics immediately
- Use `--no-fail` flag during initial rollout

## Verification Modes

### Strict Mode (Default)

```bash
nthlayer verify services/checkout-api.yaml
```

- Exit code 0: All metrics found
- Exit code 1: Optional metrics missing (warning)
- Exit code 2: Required SLO metrics missing (block)

### Lenient Mode

```bash
nthlayer verify services/checkout-api.yaml --no-fail
```

- Always exit code 0
- Prints warnings for missing metrics
- Use during initial adoption or new service rollout

## Troubleshooting Verification Failures

### "Metric not found" for a running service

1. **Check label spelling**:
   ```bash
   # Query Prometheus directly
   curl "$PROMETHEUS_URL/api/v1/query?query=http_requests_total{service='checkout-api'}"
   ```

2. **Check service name matches**:
   ```yaml
   # service.yaml
   name: checkout-api  # Must match exactly
   ```

3. **Check metric exists at all**:
   ```bash
   curl "$PROMETHEUS_URL/api/v1/query?query=http_requests_total"
   ```

### "Metric not found" for a new service

1. **Wait for scrape interval**: Prometheus scrapes every 15-60 seconds
2. **Generate some traffic**: Metrics may not exist until first request
3. **Use --no-fail**: For new services, verify in warning mode first

### Recording rule metrics not found

1. **Wait for recording rule evaluation**: Usually 1-5 minutes
2. **Check recording rule is deployed**: Rules must be loaded by Prometheus
3. **Check recording rule expression**: Ensure it produces output for your service

## Customizing Metric Names

If your metrics use different names, specify them in your service.yaml:

```yaml
name: checkout-api
type: api

slos:
  - name: availability
    metric: custom_requests_total  # Instead of http_requests_total
    success_filter: 'result="success"'  # Instead of status!~"5.."

  - name: latency
    metric: custom_latency_histogram_seconds_bucket
```

## Platform Team Checklist

Before rolling out NthLayer verification to your organization:

- [ ] Standardize on `service` label across all metrics
- [ ] Document which base metrics each service type must emit
- [ ] Configure Prometheus federation/tenant access
- [ ] Test verification against existing services
- [ ] Start with `--no-fail` and graduate to strict mode
