<!-- GIF placeholder: nthlayer apply → files generated → dashboard -->
<!-- TODO: Add CLI demo GIF here -->

<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>
</div>

# NthLayer

Generate your complete reliability stack from a single service spec.

[![Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=flat-square)](https://github.com/rsionnach/nthlayer)
[![PyPI](https://img.shields.io/pypi/v/nthlayer?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/nthlayer/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE.txt)

---

## Quick Start

```bash
pipx install nthlayer

nthlayer apply service.yaml

# Output: generated/payment-api/
#   ├── dashboard.json       → Grafana
#   ├── alerts.yaml          → Prometheus
#   ├── slos.yaml            → OpenSLO
#   └── recording-rules.yaml → Prometheus
```

---

## What You Put In

### 1. Service Spec (`service.yaml`)

```yaml
# Minimal example (5 lines)
name: payment-api
tier: critical
type: api
dependencies:
  - postgresql
```

### 2. API Keys (optional, enables auto-push)

```bash
export PAGERDUTY_API_KEY=...         # Creates team, escalation, service
export NTHLAYER_GRAFANA_URL=...      # Auto-push dashboards
export NTHLAYER_GRAFANA_API_KEY=...
```

---

## What You Get Out

| Output | File | Deploy To |
|--------|------|-----------|
| Dashboard | `generated/<service>/dashboard.json` | Grafana |
| Alerts | `generated/<service>/alerts.yaml` | Prometheus |
| SLOs | `generated/<service>/slos.yaml` | OpenSLO-compatible |
| Recording Rules | `generated/<service>/recording-rules.yaml` | Prometheus |
| PagerDuty | Created via API | Team, escalation policy, service |

---

## Full Service Example

```yaml
name: payment-api
tier: critical              # critical | standard | low
type: api                   # api | worker | stream
team: payments

slos:
  availability: 99.95       # Generates Prometheus alerts
  latency_p99_ms: 200       # Generates histogram queries

dependencies:
  - postgresql              # Adds PostgreSQL panels
  - redis                   # Adds Redis panels
  - kubernetes              # Adds K8s pod metrics

pagerduty:
  enabled: true
  support_model: self       # self | shared | sre | business_hours
```

---

## Time Saved

| Task | Manual | NthLayer |
|------|--------|----------|
| PromQL for SLOs | 2-4 hrs | Generated |
| Grafana dashboard | 4-8 hrs | Generated |
| PagerDuty setup | 1-2 hrs | Generated |
| Alert rules | 2-4 hrs | Generated |
| **Total** | **10-20 hrs** | **5 min** |

---

## How It Works

1. **Metric Discovery** - Queries Prometheus to find what metrics actually exist
2. **Intent Resolution** - Maps "availability SLO" → best matching PromQL query
3. **Type Routing** - API services get HTTP metrics, workers get job metrics
4. **Tier Defaults** - Critical = 5/15/30min escalation, Low = 60min
5. **Technology Templates** - PostgreSQL, Redis, Kubernetes patterns built-in

---

## CLI Commands

```bash
nthlayer plan service.yaml      # Preview what will be generated
nthlayer apply service.yaml     # Generate all artifacts
nthlayer apply --push-grafana   # Also push dashboard to Grafana
nthlayer apply --lint           # Validate generated alerts with pint
nthlayer lint alerts.yaml       # Lint existing Prometheus rules
```

---

## Coming Soon

| Feature | Description | Status |
|---------|-------------|--------|
| **Error Budgets** | Track budget consumption, correlate with deploys | In Progress |
| **Deployment Gates** | Block ArgoCD deploys when budget exhausted | Planned |
| **Runbook Generation** | Auto-generate troubleshooting docs from service metadata | Planned |

---

## Installation

```bash
# Recommended
pipx install nthlayer

# Or with pip
pip install nthlayer

# Verify
nthlayer --version
```

---

## Live Demo

See NthLayer in action with real Grafana dashboards and generated configs:

[![Live Dashboards](https://img.shields.io/badge/Live-Dashboards-blue?logo=grafana&style=for-the-badge)](https://nthlayer.grafana.net)
[![Demo Site](https://img.shields.io/badge/Demo-Site-green?style=for-the-badge)](https://rsionnach.github.io/nthlayer)

---

## Documentation

| Guide | Description |
|-------|-------------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | 10-minute setup guide |
| [docs/TEMPLATES.md](docs/TEMPLATES.md) | Service template reference |
| [docs/ALERTS.md](docs/ALERTS.md) | Auto-generated alerts docs |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guide |

---

## Contributing

```bash
git clone https://github.com/rsionnach/nthlayer.git
cd nthlayer
make setup    # Install deps, start services
make test     # Run tests (84 should pass)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

MIT - See [LICENSE.txt](LICENSE.txt)

---

## Acknowledgments

- [grafana-foundation-sdk](https://github.com/grafana/grafana-foundation-sdk) - Dashboard generation
- [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts) - Alert templates
- [OpenSLO](https://github.com/openslo/openslo) - SLO specification standard
