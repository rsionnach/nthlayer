# NthLayer Alerts Module

Automatic alert generation from [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts) templates.

## Overview

This module provides **580+ battle-tested alerting rules** for 50+ technologies, automatically applied based on service dependencies.

## Quick Start

```python
from nthlayer.alerts import AlertTemplateLoader

# Load alerts for PostgreSQL
loader = AlertTemplateLoader()
alerts = loader.load_technology("postgres")

print(f"Found {len(alerts)} PostgreSQL alerts")
for alert in alerts[:3]:
    print(f"  - {alert.name} ({alert.severity})")

# Customize for a service
for alert in alerts:
    customized = alert.customize_for_service(
        service_name="search-api",
        team="platform",
        tier=1,
        notification_channel="pagerduty",
        runbook_url="https://runbooks.example.com"
    )
    print(customized.to_prometheus())
```

## Architecture

```
┌──────────────────────────────────────────┐
│        AlertTemplateLoader               │
│  • Loads from templates/ directory       │
│  • Caches results                        │
│  • Fuzzy matching (pg → postgres)        │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│          AlertRule Model                 │
│  • Represents single alert               │
│  • from_dict() - Parse from YAML         │
│  • to_prometheus() - Export              │
│  • customize_for_service() - Add context │
└──────────────────────────────────────────┘
```

## Template Organization

```
templates/
├── databases/
│   ├── postgres.yaml      # 15 PostgreSQL alerts
│   ├── mysql.yaml         # 12 MySQL alerts
│   ├── redis.yaml         # 8 Redis alerts
│   └── mongodb.yaml       # 10 MongoDB alerts
├── proxies/
│   ├── nginx.yaml         # 6 Nginx alerts
│   └── haproxy.yaml       # 8 HAProxy alerts
├── orchestrators/
│   └── kubernetes.yaml    # 25 K8s alerts
└── brokers/
    ├── kafka.yaml         # 18 Kafka alerts
    └── rabbitmq.yaml      # 12 RabbitMQ alerts
```

## Alert Format

Templates follow the awesome-prometheus-alerts format:

```yaml
groups:
  - name: postgres
    rules:
      - alert: PostgresqlDown
        expr: pg_up == 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: Postgresql down (instance {{ $labels.instance }})
          description: Postgresql instance is down
```

## Technology Aliases

The loader supports common aliases:

- `pg`, `postgresql` → `postgres`
- `mongo` → `mongodb`
- `k8s` → `kubernetes`
- `mariadb` → `mysql`

## Next Steps

1. **Populate templates/** - Download from awesome-prometheus-alerts
2. **Add filters.py** - Tier-based filtering
3. **Add customizer.py** - Service-specific customization
4. **Integration** - Add to reconciliation workflow

## Resources

- [awesome-prometheus-alerts GitHub](https://github.com/samber/awesome-prometheus-alerts)
- [Implementation Plan](../../../docs/product/AWESOME_PROMETHEUS_INTEGRATION.md)
- [Prometheus Alerting Docs](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
