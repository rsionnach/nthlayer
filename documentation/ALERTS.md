# Alert Generation Guide

**Auto-generate production-ready alerts from awesome-prometheus-alerts**

---

## Overview

NthLayer automatically generates 400+ battle-tested alert rules based on your service dependencies. No more spending hours researching and configuring alerts!

### Key Features

- ✅ **46 Technologies Supported** - Databases, brokers, proxies, orchestrators, and more
- ✅ **400+ Alert Rules** - Battle-tested by thousands of engineers
- ✅ **Automatic Detection** - Reads dependencies from your service YAML
- ✅ **Tier-Based Filtering** - Critical services get comprehensive alerts, low-tier get essentials
- ✅ **Service Customization** - Adds your service labels, team info, runbook URLs
- ✅ **Prometheus-Ready** - Output ready to deploy immediately

---

## Quick Start

### 1. Add Dependencies to Your Service

```yaml
# payment-api.yaml
service:
  name: payment-api
  team: payments
  tier: critical

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          type: postgres
        - name: redis-cache
          type: redis
```

### 2. Generate Alerts

```bash
nthlayer generate-alerts payment-api.yaml
```

### 3. Result

```
📊 Loading alerts for dependencies: postgres, redis
   ✓ postgres: 15 alerts
   ✓ redis: 12 alerts

✅ Generated 27 total alerts
   Written to: generated/alerts/payment-api.yaml
```

---

## Supported Technologies (46)

### Databases (14)
- **postgres** - 15 alerts (down, replication, vacuum, connections, etc.)
- **mysql** - 14 alerts (down, replication, slow queries, connections, etc.)
- **redis** - 12 alerts (down, memory, replication, evictions, etc.)
- **mongodb** - 7 alerts (down, replication, cursors, etc.)
- **elasticsearch** - 19 alerts (cluster health, shards, JVM, etc.)
- **cassandra** - 18 alerts (down, compaction, read/write latency, etc.)
- **couchdb** - 18 alerts
- **clickhouse** - 20 alerts
- **sqlserver** - 2 alerts
- **etcd** - 13 alerts
- **consul** - 3 alerts
- **minio** - 3 alerts
- **zookeeper** - (available)

### Message Brokers (5)
- **kafka** - 2 alerts (consumer lag, offline partitions)
- **rabbitmq** - 10 alerts (down, memory, disk, connections, etc.)
- **nats** - 19 alerts
- **pulsar** - 10 alerts

### Proxies/Load Balancers (5)
- **nginx** - 3 alerts (down, high connections, etc.)
- **haproxy** - 16 alerts (down, backend errors, response time, etc.)
- **traefik** - 3 alerts
- **apache** - 3 alerts
- **caddy** - 3 alerts

### Orchestrators (4)
- **kubernetes** - 36 alerts (pod/node health, resources, etc.)
- **nomad** - 4 alerts
- **istio** - 10 alerts
- **linkerd** - 1 alert

### Storage (3)
- **minio** - 3 alerts (disk usage, availability, etc.)
- **ceph** - 13 alerts (cluster health, OSDs, etc.)
- **zfs** - 1 alert

### Infrastructure (5)
- **consul** - 3 alerts (leader election, raft, etc.)
- **etcd** - 13 alerts (leader election, disk, etc.)
- **vault** - 4 alerts (sealed, HA, etc.)
- **coredns** - 1 alert
- **zookeeper** - (available)

### Observability (5)
- **prometheus** - 28 alerts (self-monitoring, TSDB, targets, etc.)
- **loki** - 4 alerts
- **thanos** - 2 alerts
- **cortex** - 6 alerts
- **promtail** - 2 alerts

### CI/CD (3)
- **jenkins** - 8 alerts (executors, jobs, disk, etc.)
- **argocd** - 2 alerts
- **fluxcd** - 4 alerts

### Runtimes (3)
- **jvm** - 1 alert (memory, GC, etc.)
- **php-fpm** - 1 alert
- **sidekiq** - 2 alerts

### Systems/Security (4)
- **host** - 35 alerts (CPU, memory, disk, network, etc.)
- **docker** - 9 alerts (containers, images, etc.)
- **windows** - 5 alerts
- **blackbox** - 9 alerts (endpoint monitoring)

---

## Tier-Based Filtering

Alerts are automatically filtered based on your service tier:

### Critical Tier
```yaml
tier: critical
```
**Gets:** All alerts (comprehensive monitoring)

Example: 15 postgres alerts (down, replication, vacuum, slow queries, etc.)

### Standard Tier
```yaml
tier: standard
```
**Gets:** Critical + Warning alerts (balanced)

Example: 10 postgres alerts (down, replication, critical issues only)

### Low Tier
```yaml
tier: low
```
**Gets:** Only critical alerts (minimal noise)

Example: 5 postgres alerts (down, critical replication issues only)

---

## Customization

### Add Runbook URLs

```bash
nthlayer generate-alerts payment-api.yaml \
  --runbook-url https://runbooks.company.com
```

**Result:**
```yaml
annotations:
  runbook: https://runbooks.company.com/payment-api/PostgresqlDown
```

### Add Notification Channel

```bash
nthlayer generate-alerts payment-api.yaml \
  --notification-channel pagerduty-critical
```

**Result:**
```yaml
annotations:
  channel: pagerduty-critical
```

### Custom Output Path

```bash
nthlayer generate-alerts payment-api.yaml \
  --output custom/path/alerts.yaml
```

### Dry Run (Preview)

```bash
nthlayer generate-alerts payment-api.yaml --dry-run
```

Shows what would be generated without writing files.

---

## Generated Alert Format

```yaml
# Alert rules generated by NthLayer
# Templates sourced from awesome-prometheus-alerts
# https://github.com/samber/awesome-prometheus-alerts
# Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

groups:
- name: payment-api-postgres
  rules:
  - alert: PostgresqlDown
    expr: pg_up == 0
    for: 0m
    labels:
      severity: critical
      service: payment-api      # Your service
      team: payments            # Your team
      tier: critical            # Your tier
    annotations:
      summary: Postgresql down (instance {{ $labels.instance }})
      description: Postgresql instance is down
      runbook: https://runbooks.company.com/payment-api/PostgresqlDown
```

---

## Example Use Cases

### Microservices Stack

```yaml
dependencies:
  databases:
    - type: postgres
    - type: redis
    - type: mongodb
  infrastructure:
    - type: consul
    - type: vault
  orchestrators:
    - type: kubernetes
```

**Result:** 80+ alerts covering your entire stack!

### Data Platform

```yaml
dependencies:
  databases:
    - type: elasticsearch
    - type: clickhouse
  brokers:
    - type: kafka
    - type: pulsar
  storage:
    - type: minio
```

**Result:** 60+ alerts for data infrastructure!

### Web Application

```yaml
dependencies:
  databases:
    - type: mysql
    - type: redis
  proxies:
    - type: nginx
  runtimes:
    - type: php-fpm
```

**Result:** 30+ alerts for classic web stack!

---

## Best Practices

### 1. Start with Dependencies

Always declare your dependencies explicitly:

```yaml
resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          type: postgres      # ← Explicit type
```

### 2. Use Appropriate Tier

Choose tier based on service criticality:
- **critical** - User-facing, revenue-impacting
- **standard** - Important but not critical
- **low** - Dev, testing, non-essential

### 3. Add Runbook URLs

Always include runbooks for faster incident response:

```bash
nthlayer generate-alerts service.yaml \
  --runbook-url https://runbooks.company.com
```

### 4. Review Generated Alerts

Always review before deploying:

```bash
# Preview first
nthlayer generate-alerts service.yaml --dry-run

# Generate
nthlayer generate-alerts service.yaml

# Review
cat generated/alerts/service.yaml
```

### 5. Test in Staging First

Deploy to staging environment before production:

```bash
kubectl apply -f generated/alerts/service.yaml --namespace staging
```

---

## Deployment

### Kubernetes

```bash
kubectl apply -f generated/alerts/payment-api.yaml
```

### Prometheus Config

Add to Prometheus configuration:

```yaml
rule_files:
  - /etc/prometheus/alerts/payment-api.yaml
```

### Verify

Check Prometheus UI:
- Navigate to Alerts
- Search for your service name
- Verify alerts are loaded

---

## Troubleshooting

### No Alerts Generated

**Problem:** No dependencies found

**Solution:** Add Dependencies resource to your service YAML:

```yaml
resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
```

### Wrong Technology

**Problem:** Technology not detected

**Solution:** Specify explicit `type`:

```yaml
databases:
  - name: postgres-main
    type: postgres    # ← Explicit
```

### Too Many Alerts

**Problem:** Overwhelmed by alerts

**Solution:** Use a lower tier:

```yaml
tier: standard  # or low
```

---

## Attribution

Alert templates sourced from **awesome-prometheus-alerts**:
- Repository: https://github.com/samber/awesome-prometheus-alerts
- License: CC BY 4.0
- 580+ production-tested rules from thousands of engineers

NthLayer customizes these templates with your service context but preserves the original alert logic.

---

## FAQ

### Q: Can I modify generated alerts?

**A:** Yes! Generated alerts are standard Prometheus YAML. Edit as needed.

### Q: Do I need to use all generated alerts?

**A:** No. Review and remove alerts that don't apply to your setup.

### Q: Can I add custom alerts?

**A:** Yes! Add your own alert rules to the generated file.

### Q: How often should I regenerate?

**A:** Regenerate when:
- Dependencies change
- Service tier changes
- You want updated templates

### Q: Are alerts tested?

**A:** Yes! Templates are from awesome-prometheus-alerts, used by thousands of engineers in production.

### Q: What if a technology isn't supported?

**A:** Open an issue! We're adding more technologies regularly. Currently 46 supported, 63 available in awesome-prometheus-alerts.

---

## See Also

- [Service Templates](TEMPLATES.md)
- [Dependencies Guide](SCHEMA.md#dependencies)
- [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts)
- [Prometheus Alerting](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
