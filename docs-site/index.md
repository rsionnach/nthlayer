# NthLayer

**Reliability at build time, not incident time.**

Shift reliability left into your CI/CD pipeline. Validate before deploy, not after incidents.

---

## The Reliability Pipeline

```
   service.yaml
        │
        ▼
┌───────────┐     ┌───────────┐     ┌───────────┐
│  Generate │ ──▶ │  Validate │ ──▶ │  Protect  │ ──▶ Deploy
└───────────┘     └───────────┘     └───────────┘
   apply            verify           check-deploy
   init             validate-spec    portfolio
                    --lint
```

| Stage | What Happens | Exit Code |
|-------|--------------|-----------|
| **Generate** | Create dashboards, alerts, SLOs from YAML | - |
| **Validate** | Verify specs, lint PromQL, check contracts | 1 if invalid |
| **Protect** | Block deploys when error budget exhausted | 2 if blocked |

## The Problem

Teams deploy code without reliability validation:

- Alerts created **after** the first incident
- Dashboards built **after** users complain
- SLOs defined **after** budget is exhausted
- No gates to prevent risky deploys

## The Solution

NthLayer shifts reliability left - from incident response to CI/CD:

```yaml title="service.yaml"
name: payment-api
tier: critical
type: api
dependencies:
  - postgresql
  - redis
```

```bash
# Generate → Validate → Protect → Deploy
nthlayer apply service.yaml --lint
nthlayer verify service.yaml --prometheus-url $PROM_URL
nthlayer check-deploy service.yaml --prometheus-url $PROM_URL
kubectl apply -f generated/
```

## What Gets Generated

| Output | Description |
|--------|-------------|
| **Dashboards** | Grafana dashboards with technology-aware panels |
| **Alerts** | Prometheus alert rules with best-practice thresholds |
| **SLOs** | OpenSLO-compatible definitions with error budgets |
| **Recording Rules** | Pre-aggregated metrics for performance |
| **PagerDuty** | Teams, schedules, and escalation policies |

## Key Features

### Deployment Gates

Block deploys when error budget is exhausted:

![check-deploy demo](assets/check-deploy-demo.gif)

```bash
nthlayer check-deploy service.yaml --prometheus-url $PROM_URL
# Exit code: 0=approved, 1=warning, 2=blocked
```

### SLO Portfolio

Track reliability across your entire organization:

![portfolio demo](assets/portfolio-demo.gif)

```bash
nthlayer portfolio --path services/
```

### Contract Verification

Verify declared metrics exist before deploy:

![verify demo](assets/verify-demo.gif)

```bash
nthlayer verify service.yaml --prometheus-url $PROM_URL
```

### 23 Technology Templates

Pre-built monitoring for:

- **Databases:** PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
- **Message Queues:** Kafka, RabbitMQ, NATS, Pulsar
- **Proxies:** Nginx, HAProxy, Traefik
- **Infrastructure:** Kubernetes, etcd, Consul

## CI/CD Integration

```yaml title=".github/workflows/deploy.yml"
jobs:
  deploy:
    steps:
      - name: Validate Specs
        run: nthlayer validate-spec services/

      - name: Generate & Lint
        run: nthlayer apply services/*.yaml --lint

      - name: Verify Metrics
        run: nthlayer verify services/*.yaml --prometheus-url $PROM_URL

      - name: Check Deploy Gate
        run: nthlayer check-deploy services/*.yaml --prometheus-url $PROM_URL

      - name: Deploy
        if: success()
        run: kubectl apply -f generated/
```

Integrates with GitHub Actions, GitLab CI, ArgoCD, Tekton, and Jenkins.

## Get Started

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Installation**

    ---

    Install NthLayer with pip in 30 seconds

    [:octicons-arrow-right-24: Install](getting-started/installation.md)

-   :material-rocket-launch:{ .lg .middle } **Quick Start**

    ---

    Generate your first dashboard in 5 minutes

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-shield-check:{ .lg .middle } **Validate**

    ---

    Catch issues before they reach production

    [:octicons-arrow-right-24: Validation](validate/index.md)

-   :material-gate:{ .lg .middle } **Protect**

    ---

    Block risky deploys with error budget gates

    [:octicons-arrow-right-24: Protection](protect/index.md)

</div>

## The Google SRE Connection

NthLayer automates concepts from the [Google SRE Book](https://sre.google/sre-book/):

| SRE Concept | Manual Process | NthLayer Automation |
|-------------|----------------|---------------------|
| Production Readiness Review | Multi-week checklist | `nthlayer verify` in CI |
| Error Budget Policy | Spreadsheet tracking | `nthlayer check-deploy` gates |
| Release Engineering | Manual runbooks | Generated artifacts + GitOps |
| Monitoring Standards | Wiki pages | `service.yaml` spec |
