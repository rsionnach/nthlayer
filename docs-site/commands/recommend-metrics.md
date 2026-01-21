# nthlayer recommend-metrics

Generate metric recommendations based on service type and runtime, following OpenTelemetry Semantic Conventions.

## Synopsis

```bash
nthlayer recommend-metrics <service-file> [options]
```

## Description

The `recommend-metrics` command analyzes your service specification and recommends metrics based on:

- **Service type** (api, grpc, worker, queue-consumer, database-client, gateway, cache)
- **Runtime** (Python, JVM, Go, Node.js)
- **OpenTelemetry Semantic Conventions** for standardized metric names

This helps teams instrument services consistently and ensures critical metrics are captured for SLO monitoring.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All required metrics found (with `--check`) or recommendations generated |
| 1 | Some required metrics missing (with `--check`) |

## Options

| Option | Description |
|--------|-------------|
| `--prometheus-url, -p URL` | Prometheus URL for metric discovery |
| `--format FORMAT` | Output format: `table` (default), `json`, `yaml` |
| `--level LEVEL` | Metrics to show: `required`, `recommended`, `all` (default) |
| `--check` | Validate metrics exist in live Prometheus |
| `--show-code` | Show instrumentation code snippets |
| `--env, -e ENV` | Environment for variable substitution |
| `--selector-label LABEL` | Prometheus label for service selection (default: `service`) |

## Examples

### Basic Recommendations

```bash
nthlayer recommend-metrics services/payment-api.yaml
```

Output:
```
Metric Recommendations: payment-api (api)

Required Metrics (4):
  http_server_request_duration_seconds    histogram   Request latency
  http_server_requests_total              counter     Total requests
  http_server_active_requests             gauge       Active requests
  http_server_request_body_size_bytes     histogram   Request body size

Recommended Metrics (3):
  http_server_response_body_size_bytes    histogram   Response body size
  process_cpu_seconds_total               counter     CPU usage
  process_resident_memory_bytes           gauge       Memory usage

Runtime Metrics (Python):
  python_gc_collections_total             counter     GC collections
  python_gc_objects_collected_total       counter     Objects collected
```

### Check Against Live Prometheus

```bash
nthlayer recommend-metrics services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --check
```

Output:
```
Metric Validation: payment-api

Required Metrics:
  http_server_request_duration_seconds    Found
  http_server_requests_total              Found
  http_server_active_requests             MISSING
  http_server_request_body_size_bytes     Found (alias: http_request_size_bytes)

Status: 3/4 required metrics found

Recommendation: Add instrumentation for http_server_active_requests.
Use --show-code for implementation examples.
```

### Show Instrumentation Code

```bash
nthlayer recommend-metrics services/api.yaml --show-code
```

Output includes language-specific instrumentation snippets:

```python
# Python (prometheus_client)
from prometheus_client import Counter, Histogram, Gauge

REQUEST_LATENCY = Histogram(
    'http_server_request_duration_seconds',
    'Request latency in seconds',
    ['method', 'path', 'status']
)

REQUEST_COUNT = Counter(
    'http_server_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status']
)
```

### JSON Output

```bash
nthlayer recommend-metrics services/api.yaml --format json
```

```json
{
  "service": "payment-api",
  "service_type": "api",
  "runtime": "python",
  "metrics": {
    "required": [
      {
        "name": "http_server_request_duration_seconds",
        "type": "histogram",
        "description": "Request latency",
        "otel_convention": "http.server.request.duration"
      }
    ],
    "recommended": [...],
    "runtime": [...]
  }
}
```

## Service Type Templates

| Type | Description | Key Metrics |
|------|-------------|-------------|
| `api` | HTTP/REST APIs | Request duration, count, errors |
| `grpc` | gRPC services | RPC duration, count, codes |
| `worker` | Background workers | Job duration, count, queue depth |
| `queue-consumer` | Message consumers | Message latency, throughput, lag |
| `database-client` | Database clients | Query duration, connections, errors |
| `gateway` | API gateways | Upstream latency, routing metrics |
| `cache` | Cache services | Hit ratio, latency, evictions |

## Metric Aliases

The command recognizes 50+ common metric name variations:

| Semantic Convention | Common Aliases |
|--------------------|----------------|
| `http_server_request_duration_seconds` | `http_request_duration_seconds`, `request_latency_seconds` |
| `http_server_requests_total` | `http_requests_total`, `requests_total` |
| `process_cpu_seconds_total` | `cpu_seconds_total`, `node_cpu_seconds_total` |

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  validate-metrics:
    steps:
      - name: Check Required Metrics
        run: |
          nthlayer recommend-metrics services/api.yaml \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --check \
            --level required
```

### Pre-deploy Validation

```bash
# Fail if required metrics are missing
nthlayer recommend-metrics services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --check \
  --level required

if [ $? -ne 0 ]; then
  echo "Missing required metrics - deploy blocked"
  exit 1
fi
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_PROMETHEUS_URL` | Default Prometheus URL |

## See Also

- [nthlayer verify](verify.md) - Contract verification
- [Technology Templates](../integrations/technologies.md) - Template reference
- [Service Specs](../concepts/service-specs.md) - Service YAML schema
