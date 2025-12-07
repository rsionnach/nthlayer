# Your First Service

Learn how to create a complete service specification.

## Minimal Service

The simplest service spec:

```yaml
name: my-api
tier: standard
type: api
```

This generates default SLOs for a standard API (99.9% availability, 500ms p99 latency).

## Complete Service Example

```yaml
name: payment-api
team: payments
tier: critical        # 1=critical, 2=standard, 3=low
type: api             # api, worker, stream

# Technology dependencies
dependencies:
  - postgresql
  - redis

# Custom SLO overrides
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{service="payment-api",status!~"5.."}[5m])) /
          sum(rate(http_requests_total{service="payment-api"}[5m]))

  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      threshold_ms: 200
      indicator:
        type: latency
        percentile: 99

  # PagerDuty configuration
  - kind: PagerDuty
    name: alerting
    spec:
      urgency: high
      auto_create: true
```

## Service Tiers

| Tier | Availability | Latency (p99) | Escalation |
|------|--------------|---------------|------------|
| **1 (Critical)** | 99.95% | 200ms | 5 min |
| **2 (Standard)** | 99.9% | 500ms | 15 min |
| **3 (Low)** | 99.5% | 1000ms | 30 min |

## Service Types

| Type | Description | Key Metrics |
|------|-------------|-------------|
| **api** | HTTP/REST services | Request rate, latency, error rate |
| **worker** | Background jobs | Job throughput, duration, failure rate |
| **stream** | Event processors | Messages/sec, lag, processing time |

## Dependencies

NthLayer generates monitoring for these technologies:

=== "Databases"
    - `postgresql` - Connections, replication, locks
    - `mysql` - Connections, queries, replication
    - `mongodb` - Connections, operations, replication
    - `redis` - Memory, connections, hit rate
    - `elasticsearch` - Cluster health, indexing, search

=== "Message Queues"
    - `kafka` - Consumer lag, partitions, throughput
    - `rabbitmq` - Queue depth, consumers, rates
    - `nats` - Connections, messages, subscriptions
    - `pulsar` - Throughput, backlog, storage

=== "Proxies"
    - `nginx` - Requests, connections, upstream
    - `haproxy` - Backend health, response time
    - `traefik` - Requests, entrypoints

=== "Infrastructure"
    - `kubernetes` - Pod health, resources
    - `etcd` - Leader, proposals, DB size
    - `consul` - Health checks, services

## Generate and Apply

```bash
# Preview what will be generated
nthlayer plan payment-api.yaml

# Generate all configs
nthlayer apply payment-api.yaml

# Push dashboard to Grafana (if configured)
nthlayer apply payment-api.yaml --push
```

## Next Steps

- [nthlayer apply](../commands/apply.md) - Full apply options
- [Technologies](../integrations/technologies.md) - All 18 templates
- [Service YAML Schema](../reference/service-yaml.md) - Complete schema reference
