# generate-loki-alerts

Generate LogQL alert rules for Grafana Loki based on service dependencies.

## Synopsis

```bash
nthlayer generate-loki-alerts <service-file> [options]
```

## Description

Automatically generates LogQL alert rules for Grafana Loki Ruler based on your service's declared dependencies. This extends NthLayer's "generate from YAML" pattern to logs.

## Options

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output file path (default: `generated/{service}/loki-alerts.yaml`) |
| `--dry-run` | Preview alerts without writing file |

## Examples

### Generate Alerts

```bash
nthlayer generate-loki-alerts services/payment-api.yaml
```

### Preview Without Writing

```bash
nthlayer generate-loki-alerts services/api.yaml --dry-run
```

### Custom Output Path

```bash
nthlayer generate-loki-alerts services/api.yaml -o alerts/loki/api.yaml
```

## Supported Technologies

NthLayer generates LogQL alerts for 15+ technologies:

| Category | Technologies |
|----------|--------------|
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis |
| **Message Queues** | Kafka, RabbitMQ, NATS, Pulsar |
| **Search** | Elasticsearch |
| **Orchestration** | Kubernetes |
| **Load Balancers** | Nginx, HAProxy, Traefik |
| **Service Discovery** | Consul, etcd |

## Alert Types

### Database Alerts
- Fatal/panic errors
- Connection failures
- Replication lag
- Deadlocks
- Slow queries

### Message Queue Alerts
- Under-replicated partitions (Kafka)
- Memory/disk alarms (RabbitMQ)
- Consumer lag
- Broker failures

### Kubernetes Alerts
- OOMKilled containers
- CrashLoopBackOff
- Node not ready
- Probe failures

## Output Format

Alerts are generated in Grafana Loki Ruler YAML format:

```yaml
groups:
  - name: payment-api
    rules:
      - alert: payment-api_postgresql_PostgresqlFatalError
        expr: count_over_time({app="postgresql", service="payment-api"} |= "FATAL" [1m]) > 0
        for: 0m
        labels:
          severity: critical
          service: payment-api
          tier: critical
          technology: postgresql
        annotations:
          summary: "[payment-api/postgresql] PostgreSQL FATAL error detected"
          description: "PostgreSQL logged a FATAL error..."
```

## Integration with Loki

### Deploy to Loki Ruler

```bash
# Generate alerts
nthlayer generate-loki-alerts services/api.yaml

# Deploy to Loki (using mimirtool or Loki API)
mimirtool rules load generated/api/loki-alerts.yaml
```

### With Grafana Cloud

```bash
# Generate
nthlayer generate-loki-alerts services/api.yaml

# Upload via Grafana Cloud API
curl -X POST "https://your-instance.grafana.net/loki/api/v1/rules/nthlayer" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/yaml" \
  --data-binary @generated/api/loki-alerts.yaml
```

## How Dependencies Are Detected

Dependencies are extracted from your `service.yaml`:

```yaml
resources:
  - kind: Dependencies
    name: external
    spec:
      databases:
        - name: payment-db
          type: postgresql
        - name: cache
          type: redis
      services:
        - name: kafka-cluster
          type: kafka
```

## See Also

- [apply Command](./apply.md) - Generate all artifacts including Loki alerts
- [Loki Integration Guide](../integrations/loki.md)
