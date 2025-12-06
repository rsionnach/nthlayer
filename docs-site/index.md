# NthLayer

**Generate your complete reliability stack from a single service spec.**

20 hours of SRE work in 5 minutes. Zero toil.

---

## What is NthLayer?

NthLayer is an automation platform that generates your complete observability and reliability infrastructure from declarative service definitions. Define your service once, get:

| Output | Description |
|--------|-------------|
| **Dashboards** | Grafana dashboards with technology-aware panels |
| **Alerts** | Prometheus alert rules with best-practice thresholds |
| **SLOs** | OpenSLO-compatible definitions with error budgets |
| **Recording Rules** | Pre-aggregated metrics for performance |
| **PagerDuty** | Teams, schedules, and escalation policies |

## Quick Example

```yaml title="service.yaml"
name: payment-api
tier: critical
type: api
dependencies:
  - postgresql
  - redis
```

```bash
nthlayer apply service.yaml
```

**Output:**
```
generated/payment-api/
├── dashboard.json       # Grafana dashboard
├── alerts.yaml          # Prometheus rules
├── slos.yaml            # OpenSLO definitions
└── recording-rules.yaml # Pre-aggregated metrics
```

## Key Features

### SLO Portfolio

Track reliability across your entire organization:

```
================================================================================
  NthLayer SLO Portfolio
================================================================================

Organization Health: 78% (14/18 services meeting SLOs)

By Tier:
  Critical:  ████████░░  83% (5/6 services)
  Standard:  ███████░░░  75% (6/8 services)
  Low:       ███████░░░  75% (3/4 services)

Services Needing Attention:
  payment-api    availability  156% budget burned  EXHAUSTED
  search-api     latency       95% budget burned   WARNING
```

### 18 Technology Templates

Pre-built monitoring for:

- **Databases:** PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
- **Message Queues:** Kafka, RabbitMQ, NATS, Pulsar
- **Proxies:** Nginx, HAProxy, Traefik
- **Infrastructure:** Kubernetes, etcd, Consul

### Interactive Setup

```bash
nthlayer setup
```

Guided configuration for Prometheus, Grafana, and PagerDuty with connection testing.

## Get Started

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Installation**

    ---

    Install NthLayer with pip or pipx

    [:octicons-arrow-right-24: Install](getting-started/installation.md)

-   :material-rocket-launch:{ .lg .middle } **Quick Start**

    ---

    Generate your first dashboard in 5 minutes

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-file-document:{ .lg .middle } **Commands**

    ---

    Full CLI reference

    [:octicons-arrow-right-24: Commands](commands/index.md)

-   :material-connection:{ .lg .middle } **Integrations**

    ---

    Connect to Prometheus, Grafana, PagerDuty

    [:octicons-arrow-right-24: Integrations](integrations/prometheus.md)

</div>
