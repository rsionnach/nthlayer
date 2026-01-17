<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>
  <br><br>
</div>

# NthLayer

**Shift-left reliability for platform teams.**

Define reliability requirements as code. Validate SLOs against dependency chains. Detect drift before incidents. Gate deployments on real data.

[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge)](https://github.com/rsionnach/nthlayer)
[![PyPI](https://img.shields.io/pypi/v/nthlayer?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/nthlayer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE.txt)
[![Alert Rules](https://img.shields.io/badge/Alert_Rules-593+-red?style=for-the-badge&logo=prometheus&logoColor=white)](https://github.com/samber/awesome-prometheus-alerts)

## TL;DR

```bash
pip install nthlayer
```

<div align="center">
  <img src="demo/vhs/check-deploy-demo.gif" alt="nthlayer check-deploy demo" width="700">
</div>

---

## ⚠️ The Problem

Reliability decisions happen too late. Teams set SLOs in isolation, deploy without checking error budgets, and discover missing metrics during incidents. Dashboards are inconsistent. Alerts are copy-pasted. Nobody validates whether a 99.99% target is even achievable given dependencies.

## 💡 The Solution

NthLayer moves reliability left:

```
service.yaml → validate → check-deploy → deploy
                  │            │
                  │            └── Error budget ok? Drift acceptable?
                  │
                  └── SLO feasible? Dependencies support it? Metrics exist?
```

---

## ⚡ Core Features

### Drift Detection

Predict SLO exhaustion before it happens. Don't wait for the budget to hit zero.

```bash
$ nthlayer drift payment-api

payment-api: CRITICAL
  Current: 73.2% budget remaining
  Trend: -2.1%/day (gradual decline)
  Projection: Budget exhausts in 23 days

  Recommendation: Investigate error rate increase before next release
```

### Dependency-Aware SLO Validation

Your SLO ceiling is your weakest dependency chain. NthLayer calculates it.

```bash
$ nthlayer validate-slo payment-api

Target: 99.99% availability
Dependencies:
  → postgresql (99.95%)
  → redis (99.99%)
  → user-service (99.9%)

Serial availability: 99.84%
✗ INFEASIBLE: Target exceeds dependency ceiling by 0.15%

Recommendation: Reduce target to 99.8% or improve user-service SLO
```

### Deployment Gates

Block deploys when error budget is exhausted or drift is critical.

```bash
$ nthlayer check-deploy payment-api

ERROR: Deployment blocked
  - Error budget: -47 minutes (exhausted)
  - Drift severity: critical
  - 3 P1 incidents in last 7 days

Exit code: 2 (BLOCKED)
```

### Blast Radius Analysis

Understand impact before making changes.

```bash
$ nthlayer blast-radius payment-api

Direct dependents (3):
  • checkout-service (critical) - 847K req/day
  • order-service (critical) - 523K req/day
  • refund-worker (standard) - 12K req/day

Transitive impact: 12 services, 2.1M daily requests
Risk: HIGH - affects checkout flow
```

### Metric Recommendations

Enforce OpenTelemetry conventions. Know what's missing before production.

```bash
$ nthlayer recommend-metrics payment-api

Required (SLO-critical):
  ✓ http.server.request.duration    FOUND
  ✗ http.server.active_requests     MISSING

Run with --show-code for instrumentation examples.
```

### Artifact Generation

Generate dashboards, alerts, and SLOs from a single spec.

```bash
$ nthlayer apply service.yaml

Generated:
  → dashboard.json (Grafana)
  → alerts.yaml (Prometheus)
  → recording-rules.yaml (Prometheus)
  → slos.yaml (OpenSLO)
```

---

## 🚀 Quick Start

```bash
# Install
pip install nthlayer

# Create a service spec
nthlayer init

# Validate and generate
nthlayer apply service.yaml

# Check deployment readiness
nthlayer check-deploy payment-api
```

### Minimal `service.yaml`

```yaml
name: payment-api
tier: critical
type: api
team: payments

dependencies:
  - postgresql
  - redis
```

See [full spec reference](https://rsionnach.github.io/nthlayer/reference/service-yaml/) for all options.

---

## 🔄 CI/CD Integration

```yaml
# GitHub Actions
- name: Validate reliability
  run: |
    nthlayer validate-slo ${{ matrix.service }}
    nthlayer check-deploy ${{ matrix.service }}
```

Works with: **GitHub Actions**, **GitLab CI**, **ArgoCD**, **Tekton**, **Jenkins**

---

## 🎯 How It's Different

| Traditional Approach | NthLayer |
|---------------------|----------|
| Set SLOs in isolation | Validate against dependency chains |
| Alert when budget exhausted | Predict exhaustion with drift detection |
| Discover missing metrics in incidents | Enforce before deployment |
| Manual dashboard creation | Generate from spec |
| "Is this ready?" = opinion | "Is this ready?" = deterministic check |

---

## 📚 Documentation

**[Full Documentation](https://rsionnach.github.io/nthlayer/)** - Comprehensive guides and reference.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/rsionnach/nthlayer)

| Guide | Description |
|-------|-------------|
| [Quick Start](https://rsionnach.github.io/nthlayer/getting-started/quick-start/) | Get running in 5 minutes |
| [Drift Detection](https://rsionnach.github.io/nthlayer/features/drift/) | Predict SLO exhaustion |
| [Dependency Discovery](https://rsionnach.github.io/nthlayer/features/dependencies/) | Automatic dependency mapping |
| [CI/CD Integration](https://rsionnach.github.io/nthlayer/guides/cicd/) | Pipeline setup |
| [CLI Reference](https://rsionnach.github.io/nthlayer/reference/cli/) | All commands |

---

## 🗺️ Roadmap

- [x] Artifact generation (dashboards, alerts, SLOs)
- [x] Deployment gates (check-deploy)
- [x] Error budget tracking
- [x] Portfolio view
- [x] Drift detection
- [x] Dependency discovery
- [x] validate-slo
- [x] blast-radius
- [ ] Metric recommendations
- [ ] MCP server integration
- [ ] Backstage plugin

---

## 🤝 Contributing

```bash
# Install uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/rsionnach/nthlayer.git
cd nthlayer
make setup    # Install deps, start services
make test     # Run tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📄 License

MIT - See [LICENSE.txt](LICENSE.txt)

---

## 🙏 Acknowledgments

Built on [grafana-foundation-sdk](https://github.com/grafana/grafana-foundation-sdk), [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts), [pint](https://github.com/cloudflare/pint), and [OpenSLO](https://github.com/openslo/openslo). Inspired by [Sloth](https://github.com/slok/sloth) and [autograf](https://github.com/FUSAKLA/autograf).
