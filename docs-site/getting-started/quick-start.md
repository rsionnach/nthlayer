# Quick Start

Generate your complete reliability stack in 5 minutes.

## 1. Install NthLayer

```bash
pipx install nthlayer
```

## 2. Run Interactive Setup

```bash
nthlayer setup
```

This guides you through configuring:

- **Prometheus** - For metric discovery and SLO queries
- **Grafana** - For dashboard deployment (optional)
- **PagerDuty** - For alerting integration (optional)

Example output:
```
================================================================================
  Welcome to NthLayer!
================================================================================

Quick Setup
----------------------------------------
1. Prometheus Configuration
   Prometheus URL [http://localhost:9090]:

2. Grafana Configuration (optional)
   Configure Grafana? [Y/n]: y
   Grafana URL [http://localhost:3000]:
   API Key: ****

Testing Connections
----------------------------------------
  Prometheus (http://localhost:9090)
    [OK] Connected (Prometheus 2.45.0)

  Grafana (http://localhost:3000)
    [OK] Connected - Org: Main Org

Configuration saved to: ~/.nthlayer/config.yaml
```

## 3. Create a Service Spec

Create `payment-api.yaml`:

```yaml
name: payment-api
tier: critical
type: api
team: payments

dependencies:
  - postgresql
  - redis
```

## 4. Generate Configs

```bash
nthlayer apply payment-api.yaml
```

Output:
```
Generated: generated/payment-api/
├── dashboard.json       # Import to Grafana
├── alerts.yaml          # Add to Prometheus
├── slos.yaml            # OpenSLO format
└── recording-rules.yaml # Prometheus rules
```

## 5. View Your SLO Portfolio

```bash
nthlayer portfolio
```

```
================================================================================
  NthLayer SLO Portfolio
================================================================================

Organization Health: 100% (1/1 services meeting SLOs)

By Tier:
  Critical:  100%  ████████████████████  1/1 services
```

## Next Steps

- [Your First Service](first-service.md) - Detailed service spec guide
- [Commands](../commands/index.md) - Full CLI reference
- [Technologies](../integrations/technologies.md) - 18 supported technologies
