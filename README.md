<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>

  <br><br>

  <img src="demo/vhs/nthlayer-apply.gif" alt="nthlayer apply demo" width="700">
</div>

# NthLayer

### The Missing Layer of Reliability

**Reliability requirements as code.**

[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge)](https://github.com/rsionnach/nthlayer)
[![PyPI](https://img.shields.io/pypi/v/nthlayer?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/nthlayer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE.txt)

NthLayer lets you define what "production-ready" means for a service,
then generates, validates, and enforces those requirements automatically.

**Define once. Generate everything. Block bad deploys.**

---

## The Problem

For every new service, teams are expected to:
- Manually create dashboards
- Hand-craft alerts and recording rules
- Define SLOs and error budgets
- Configure incident escalation
- Decide if a service is "ready" for production

These decisions are usually made **after deployment**, enforced **inconsistently**, or revisited **only during incidents**.

## The Solution

NthLayer moves reliability left in the delivery lifecycle:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ service.yaml → generate → lint → verify → check-deploy → deploy            │
│                   ↓         ↓       ↓           ↓                          │
│               artifacts   valid?  metrics?  budget ok?                     │
│                                                                            │
│ "Is this production-ready?" - answered BEFORE deployment                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

```bash
# In your Tekton/GitHub Actions pipeline:
nthlayer apply service.yaml --lint    # Generate + validate PromQL syntax
nthlayer verify service.yaml          # Verify declared metrics exist
nthlayer check-deploy service.yaml    # Check error budget gate
# Only if all pass: deploy to production
```

Works with: **Tekton**, **GitHub Actions**, **GitLab CI**, **ArgoCD**, **Mimir/Cortex**

---

## 🚦 Shift Left Features

| Command | What It Does | Pipeline Exit Code |
|---------|--------------|-------------------|
| `nthlayer verify` | Validates declared metrics exist in Prometheus | 1 if missing metrics |
| `nthlayer check-deploy` | Checks error budget - blocks if exhausted | 2 if budget exhausted |
| `nthlayer apply --lint` | Validates PromQL syntax with pint | 1 if invalid queries |

### Deployment Gate Example

<div align="center">
  <img src="demo/vhs/check-deploy-demo.gif" alt="nthlayer check-deploy demo" width="700">
</div>

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

## What NthLayer Is

- A **reliability specification** that defines production-readiness
- A **compiler** from service intent to operational reality
- A **CI/CD-native** way to standardize reliability across teams

NthLayer integrates with existing tools (Prometheus, Grafana, PagerDuty) but operates **before** them - deciding what is allowed to reach production.

## What NthLayer Is Not

- Not a service catalog
- Not an observability platform
- Not an incident management system
- Not a runtime control plane

NthLayer **complements** these systems by ensuring services meet reliability expectations before they are deployed.

## Why NthLayer?

| With NthLayer | Without NthLayer |
|---------------|------------------|
| Platform teams encode reliability standards **once** | Standards recreated per service |
| Service teams inherit sane defaults **automatically** | Each team invents their own |
| "Is this production-ready?" = **deterministic check** | "Is this ready?" = negotiated opinion |
| Reliability is **enforced by default** | Reliability is **reactive and inconsistent** |

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
nthlayer portfolio              # Org-wide reliability view
nthlayer portfolio --format json  # Machine-readable for dashboards
nthlayer slo collect service.yaml  # Query current budget from Prometheus
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

### Generation: 20 hours → 5 minutes per service

| Task | Manual Effort | With NthLayer |
|------|---------------|---------------|
| 🎯 Define SLOs & error budgets | 6 hours | Generated from tier |
| 🚨 Research & configure alerts | 4 hours | 400+ battle-tested rules |
| 📊 Build Grafana dashboards | 5 hours | 12-28 panels auto-generated |
| 📟 PagerDuty escalation setup | 2 hours | Tier-based defaults |
| 📋 Write recording rules | 3 hours | 20+ pre-computed metrics |

### Validation: Catch issues before production

| Problem | Without NthLayer | With NthLayer |
|---------|------------------|---------------|
| Missing metrics | Discover after deploy | `nthlayer verify` blocks promotion |
| Invalid PromQL | Prometheus rejects rules | `--lint` catches in CI |
| Policy violations | Manual review | `nthlayer validate-spec` enforces |
| Exhausted budget | Deploy anyway, incident | `check-deploy` blocks risky deploys |

### At Scale

| Scale | Generation Saved | Incidents Prevented* |
|-------|------------------|---------------------|
| 🚀 50 services | 996 hours ($100K) | ~12/year |
| 📈 200 services | 3,983 hours ($400K) | ~48/year |
| 🏢 1,000 services | 19,917 hours ($2M) | ~240/year |

<sub>*Estimated based on 60% reduction in "missing monitoring" incidents. Value at $100/hr engineering cost.</sub>

---

## 🧠 How It Works

### Generation

| Step | What Happens |
|------|--------------|
| 🎯 **Intent Resolution** | Maps "availability SLO" → best matching PromQL query |
| 🔀 **Type Routing** | API services get HTTP metrics, workers get job metrics |
| ⚡ **Tier Defaults** | Critical = 99.95% SLO + 5min escalation, Low = 99.5% + 60min |
| 🏗️ **Technology Templates** | 23 built-in: PostgreSQL, Redis, Kafka, MongoDB, etc. |

### CI/CD Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Generate  │───▶│   Validate  │───▶│   Protect   │───▶│   Deploy    │
│ nthlayer    │    │ --lint      │    │ check-deploy│    │ kubectl     │
│ apply       │    │ verify      │    │             │    │ argocd      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                  │                  │
      ▼                  ▼                  ▼
  artifacts         exit 1 if          exit 2 if
  to git            invalid            budget exhausted
```

Works with: **GitHub Actions**, **GitLab CI**, **ArgoCD**, **Tekton**, **Jenkins**

---

## 🛠️ CLI Commands

### Generate

```bash
nthlayer init                   # Interactive service.yaml creation
nthlayer plan service.yaml      # Preview what will be generated
nthlayer apply service.yaml     # Generate all artifacts
nthlayer apply --push           # Also push dashboard to Grafana
nthlayer apply --push-ruler     # Push alerts to Mimir/Cortex Ruler API
```

### Validate

```bash
nthlayer apply --lint           # Validate PromQL syntax (pint)
nthlayer validate-spec service.yaml  # Check against policies (OPA/Rego)
nthlayer verify service.yaml    # Verify metrics exist in Prometheus
```

### Protect

```bash
nthlayer check-deploy service.yaml  # Check error budget gate (exit 2 = blocked)
nthlayer portfolio              # Org-wide SLO health
nthlayer slo collect service.yaml   # Query current budget from Prometheus
```

---

## 🔮 Coming Soon

| Feature | Description | Status |
|---------|-------------|--------|
| 💰 **Error Budgets** | Track budget consumption, correlate with deploys | ✅ Done |
| 📊 **SLO Portfolio** | Org-wide reliability view across all services | ✅ Done |
| 🚦 **Deployment Gates** | Block deploys when error budget exhausted | ✅ Done |
| ✅ **Contract Verification** | Verify declared metrics exist before promotion | ✅ Done |
| 📝 **Loki Integration** | Generate LogQL alert rules, technology-specific log patterns | 🔨 Next |
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
- [pint](https://github.com/cloudflare/pint) - PromQL linting and validation (Apache 2.0)
- [conftest](https://github.com/open-policy-agent/conftest) / [OPA](https://github.com/open-policy-agent/opa) - Policy validation (Apache 2.0)
- [PagerDuty Python SDK](https://github.com/PagerDuty/pdpyras) - Incident management integration (MIT)

### Architecture Inspiration
- [autograf](https://github.com/FUSAKLA/autograf) - Dynamic Prometheus metric discovery
- [Sloth](https://github.com/slok/sloth) - SLO specification and burn rate calculations
- [OpenSLO](https://github.com/openslo/openslo) - SLO specification standard

### CLI & Documentation
- [Rich](https://github.com/Textualize/rich) - Terminal formatting and styling (MIT)
- [Questionary](https://github.com/tmbo/questionary) - Interactive CLI prompts (MIT)
- [MkDocs Material](https://github.com/squidfunk/mkdocs-material) - Documentation theme (MIT)
- [VHS](https://github.com/charmbracelet/vhs) - Terminal demo recordings (MIT)
- [Nord Theme](https://www.nordtheme.com/) - Color palette inspiration (MIT)

### Tooling
- [Shields.io](https://shields.io/) - Badges
- [Slidev](https://sli.dev/) - Presentation framework
