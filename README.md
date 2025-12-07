<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>

  <br><br>

  <img src="demo/vhs/nthlayer-apply.gif" alt="nthlayer apply demo" width="700">
</div>

# NthLayer

Generate your complete reliability stack from a single service spec.

[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge)](https://github.com/rsionnach/nthlayer)
[![PyPI](https://img.shields.io/pypi/v/nthlayer?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/nthlayer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE.txt)

---

## ⚡ Quick Start

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

## 📥 What You Put In

### 1. Service Spec (`service.yaml`)

```yaml
# Minimal example (5 lines)
name: payment-api
tier: critical
type: api
dependencies:
  - postgresql
```

### 2. Environment Variables (optional)

```bash
# 📟 PagerDuty - auto-create team, escalation policy, service
export PAGERDUTY_API_KEY=...

# 📊 Grafana - auto-push dashboards
export NTHLAYER_GRAFANA_URL=...
export NTHLAYER_GRAFANA_API_KEY=...
export NTHLAYER_GRAFANA_ORG_ID=1              # Default: 1

# 🔍 Prometheus - metric discovery for intent resolution
export NTHLAYER_PROMETHEUS_URL=...
export NTHLAYER_METRICS_USER=...              # If auth required
export NTHLAYER_METRICS_PASSWORD=...
```

---

## 📤 What You Get Out

| Output | File | Deploy To |
|--------|------|-----------|
| 📊 Dashboard | `generated/<service>/dashboard.json` | Grafana |
| 🚨 Alerts | `generated/<service>/alerts.yaml` | Prometheus |
| 🎯 SLOs | `generated/<service>/slos.yaml` | OpenSLO-compatible |
| ⚡ Recording Rules | `generated/<service>/recording-rules.yaml` | Prometheus |
| 📟 PagerDuty | Created via API | Team, escalation policy, service |

---

## 📊 SLO Portfolio

Track reliability across your entire organization:

<div align="center">
  <img src="demo/vhs/portfolio-demo.gif" alt="nthlayer portfolio demo" width="700">
</div>

```bash
$ nthlayer portfolio

======================================================================
  NthLayer Reliability Portfolio
======================================================================

Overall Health: 78% (14/18 SLOs meeting target)

By Tier:
  Critical: 5/6 healthy (83%)
  Standard: 6/8 healthy (75%)
  Low: 3/4 healthy (75%)

Top Budget Burners:
  payment-api/availability: 12.5h burned (156%)
  search-api/latency: 8.2h burned (95%)

Insights:
  ! payment-api needs reliability investment
  * user-api exceeds SLO - consider tier promotion

----------------------------------------------------------------------
Services: 12 | SLOs: 18
```

```bash
nthlayer slo list              # List all SLOs across services
nthlayer slo show payment-api  # Show SLO details for a service
nthlayer slo collect payment-api  # Query Prometheus for current budget
nthlayer portfolio             # Org-wide reliability view
nthlayer portfolio --details   # Full breakdown by service
```

---

## 📝 Full Service Example

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

## 💰 The Value

<div align="center">
  <h3>⏱️ 20 hours → 5 minutes per service</h3>
</div>

### What Gets Automated

| Task | Manual Effort | With NthLayer |
|------|---------------|---------------|
| 🎯 Define SLOs & error budgets | 6 hours | Generated |
| 🚨 Research & configure alerts | 4 hours | 400+ battle-tested rules |
| 📊 Build Grafana dashboards | 5 hours | 12-28 panels auto-generated |
| 📟 PagerDuty escalation setup | 2 hours | Tier-based defaults |
| 📋 Write recording rules | 3 hours | 20+ pre-computed metrics |
| **Total per service** | **20 hours** | **5 minutes** |

<sub>*Hours based on typical SRE team experience for production-grade setup. Actual times vary by team expertise and existing tooling.</sub>

### At Scale

| Scale | Manual Hours | With NthLayer | Hours Saved | Value* |
|-------|--------------|---------------|-------------|--------|
| 🚀 50 services | 1,000 hrs | 4 hrs | 996 hrs | $100K |
| 📈 200 services | 4,000 hrs | 17 hrs | 3,983 hrs | $400K |
| 🏢 1,000 services | 20,000 hrs | 83 hrs | 19,917 hrs | $2M |

<sub>*Value calculated at $100/hr engineering cost. Your mileage may vary.</sub>

---

## 🧠 How It Works

| Step | What Happens |
|------|--------------|
| 🔍 **Metric Discovery** | Queries Prometheus to find what metrics actually exist |
| 🎯 **Intent Resolution** | Maps "availability SLO" → best matching PromQL query |
| 🔀 **Type Routing** | API services get HTTP metrics, workers get job metrics |
| ⚡ **Tier Defaults** | Critical = 5/15/30min escalation, Low = 60min |
| 🏗️ **Technology Templates** | PostgreSQL, Redis, Kubernetes patterns built-in |

---

## 🛠️ CLI Commands

```bash
nthlayer plan service.yaml      # 👀 Preview what will be generated
nthlayer apply service.yaml     # ✨ Generate all artifacts
nthlayer apply --push-grafana   # 📊 Also push dashboard to Grafana
nthlayer apply --lint           # ✅ Validate generated alerts with pint
nthlayer lint alerts.yaml       # 🔍 Lint existing Prometheus rules
```

---

## 🔮 Coming Soon

| Feature | Description | Status |
|---------|-------------|--------|
| 💰 **Error Budgets** | Track budget consumption, correlate with deploys | ✅ Done |
| 📊 **SLO Portfolio** | Org-wide reliability view across all services | ✅ Done |
| 📝 **Loki Integration** | Generate LogQL alert rules, technology-specific log patterns | 🔨 Next |
| 🚦 **Deployment Gates** | Block ArgoCD deploys when budget exhausted | 📋 Planned |
| 🤖 **AI Generation** | Conversational service.yaml creation via MCP | 📋 Planned |

---

## 📦 Installation

```bash
# Recommended
pipx install nthlayer

# Or with pip
pip install nthlayer

# Verify
nthlayer --version
```

---

## 🌐 Live Demo

See NthLayer in action with real Grafana dashboards and generated configs:

[![Live Dashboards](https://img.shields.io/badge/Live-Dashboards-blue?logo=grafana&style=for-the-badge)](https://nthlayer.grafana.net)
[![Interactive Demo](https://img.shields.io/badge/Interactive-Demo-green?style=for-the-badge)](https://rsionnach.github.io/nthlayer/demo/)

---

## 📚 Documentation

**[Full Documentation](https://rsionnach.github.io/nthlayer/)** - Comprehensive guides and reference.

| Quick Links | |
|-------------|---|
| 🚀 [Quick Start](https://rsionnach.github.io/nthlayer/getting-started/quick-start/) | Get running in 5 minutes |
| 🔧 [Setup Wizard](https://rsionnach.github.io/nthlayer/commands/setup/) | Interactive configuration |
| 📊 [SLO Portfolio](https://rsionnach.github.io/nthlayer/commands/portfolio/) | Org-wide reliability view |
| 🔌 [18 Technologies](https://rsionnach.github.io/nthlayer/integrations/technologies/) | PostgreSQL, Redis, Kafka... |
| 📖 [CLI Reference](https://rsionnach.github.io/nthlayer/reference/cli/) | All commands |
| 🤝 [Contributing](CONTRIBUTING.md) | How to contribute |

<details>
<summary>Build docs locally</summary>

```bash
pip install -e ".[docs]"
mkdocs serve  # Opens at http://localhost:8000
```
</details>

---

## 🤝 Contributing

```bash
git clone https://github.com/rsionnach/nthlayer.git
cd nthlayer
make setup    # Install deps, start services
make test     # Run tests (84 should pass)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📄 License

MIT - See [LICENSE.txt](LICENSE.txt)

---

## 🙏 Acknowledgments

### Core Dependencies
- [grafana-foundation-sdk](https://github.com/grafana/grafana-foundation-sdk) - Dashboard generation SDK (Apache 2.0)
- [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts) - 580+ battle-tested alert rules (CC BY 4.0)

### Architecture Inspiration
- [autograf](https://github.com/FUSAKLA/autograf) - Dynamic Prometheus metric discovery
- [Sloth](https://github.com/slok/sloth) - SLO specification and burn rate calculations
- [OpenSLO](https://github.com/openslo/openslo) - SLO specification standard

### Tooling
- [Shields.io](https://shields.io/) - Badges
- [Slidev](https://sli.dev/) - Presentation framework
