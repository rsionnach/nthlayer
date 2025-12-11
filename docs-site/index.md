# NthLayer

**Reliability at build time, not incident time.**

Shift reliability left into your CI/CD pipeline. Validate before deploy, not after incidents.

---

## The Problem

Teams deploy code without reliability validation:

- Alerts created **after** the first incident
- Dashboards built **after** users complain
- SLOs defined **after** budget is exhausted
- No gates to prevent risky deploys

## The Solution

NthLayer shifts reliability left:

```
service.yaml → generate → lint → verify → check-deploy → deploy
                  ↓         ↓       ↓           ↓
              artifacts   valid?  metrics?  budget ok?
```

| Command | What It Does | Exit Code |
|---------|--------------|-----------|
| `nthlayer verify` | Validates declared metrics exist | 1 if missing |
| `nthlayer check-deploy` | Checks error budget gate | 2 if exhausted |
| `nthlayer apply --lint` | Validates PromQL syntax | 1 if invalid |

## What Gets Generated

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
