<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=flat-square)](https://github.com/rsionnach/nthlayer)
[![PyPI](https://img.shields.io/pypi/v/nthlayer?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/nthlayer/)
[![Tests][tests-shield]][tests-url]
[![Python][python-shield]][python-url]
[![License][license-shield]][license-url]
[![Contributors][contributors-shield]][contributors-url]

> **Early Access** - NthLayer is in active development. We're looking for early adopters to try it and share feedback! [Join the discussion](https://github.com/rsionnach/nthlayer/discussions) or [report issues](https://github.com/rsionnach/nthlayer/issues).

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer Logo" width="400">
  </a>

<h3 align="center">NthLayer</h3>

  <p align="center">
    <strong>The Missing Layer of Reliability</strong>
    <br />
    One YAML file. Complete reliability stack. Zero toil.
    <br />
    <em>Auto-generate dashboards, SLOs, alerts, runbooks, and deployment gates from a single service definition.</em>
    <br />
    <br />
    <a href="https://github.com/rsionnach/nthlayer"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="#usage">View Demo</a>
    ·
    <a href="https://github.com/rsionnach/nthlayer/issues/new?labels=bug">Report Bug</a>
    ·
    <a href="https://github.com/rsionnach/nthlayer/issues/new?labels=enhancement">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#-live-demo">🌐 Live Demo</a></li>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#the-problem">The Problem</a></li>
        <li><a href="#the-solution">The Solution</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#key-features">Key Features</a></li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#documentation">Documentation</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

---

## 🌐 Live Demo

**See what NthLayer generates — real dashboards, real metrics, real configs:**

[![Live Dashboards](https://img.shields.io/badge/Live-Dashboards-blue?logo=grafana&style=for-the-badge)](https://nthlayer.grafana.net/d/payment-api-overview/payment-api-service-dashboard)
[![Demo Site](https://img.shields.io/badge/Demo-Site-green?style=for-the-badge)](https://rsionnach.github.io/nthlayer)

**What's in the demo:**
- [**Live Grafana Dashboards**](https://nthlayer.grafana.net) - 6 auto-generated dashboards with real metrics from our demo app
- [**Generated Configs**](./generated/payment-api/) - Real dashboard JSON, SLO definitions, alert rules, and recording rules
- [**Demo Site**](https://rsionnach.github.io/nthlayer) - Overview of NthLayer capabilities with links to live examples

---

<!-- ABOUT THE PROJECT -->
## About The Project

**NthLayer** eliminates operational toil by auto-generating SLOs, alerts, dashboards, and deployment gates from simple service definitions.

Define once. Generate everywhere. Zero toil.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### The Problem

Every new service requires **20+ hours** of manual operational setup:

- **6 hours:** Define SLOs and calculate error budgets
- **4 hours:** Research and configure alert rules for dependencies (PostgreSQL, Redis, Kafka, etc.)
- **5 hours:** Build Grafana dashboards with technology-specific panels
- **5 hours:** Set up deployment gates, runbooks, and PagerDuty escalation

**Cost:** 20 hours × 200 services = **4,000 hours of annual toil**

### The Solution

Write one YAML file. NthLayer generates everything automatically with a **unified workflow**:

```bash
# 1. Initialize from template
$ nthlayer init payment-api --team payments --template critical-api

# 2. Preview what will be generated (like terraform plan)
$ nthlayer plan payment-api.yaml
✅ SLOs (3)
✅ Alerts (28) - PostgreSQL, Redis, Kubernetes
✅ Dashboard (1) - 12 panels
✅ Recording Rules (21) - 10x faster dashboards
✅ PagerDuty Service (1)

# 3. Generate everything at once (like terraform apply)
$ nthlayer apply payment-api.yaml
✅ [1/5] SLOs          → 3 created
✅ [2/5] Alerts        → 28 created
✅ [3/5] Dashboard     → 1 created
✅ [4/5] Recording     → 21 created
✅ [5/5] PagerDuty     → 1 created

Successfully applied 54 resources in 1.2s

# 4. Check deployment readiness
$ nthlayer check-deploy payment-api.yaml
✅ Deployment approved (15% error budget consumed)

# Or use environment-specific configs
$ nthlayer apply payment-api.yaml --env prod
```

**Time saved:** 20 hours → 5 minutes ⚡
**Commands:** 7 → 2 (like Terraform!) 🚀

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

[![Python][python-badge]][python-url]
[![Pydantic][pydantic-badge]][pydantic-url]
[![FastAPI][fastapi-badge]][fastapi-url]
[![SQLAlchemy][sqlalchemy-badge]][sqlalchemy-url]
[![Alembic][alembic-badge]][alembic-url]
[![PostgreSQL][postgresql-badge]][postgresql-url]
[![Redis][redis-badge]][redis-url]
[![Prometheus][prometheus-badge]][prometheus-url]
[![Grafana][grafana-badge]][grafana-url]
[![Docker][docker-badge]][docker-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- KEY FEATURES -->
## Key Features

### Unified Workflow (NEW!)
- ✅ **`nthlayer plan`** - Preview all resources (like `terraform plan`)
- ✅ **`nthlayer apply`** - Generate everything at once (like `terraform apply`)
- ✅ **Auto-Detection** - Automatically detects what resources to generate
- ✅ **One Command** - Replace 5-7 commands with a single unified workflow
- ✅ **Declarative** - Define once, get everything (SLOs, alerts, dashboards, rules)

### Core Capabilities
- ✅ **5 Built-in Templates** - critical-api, standard-api, low-api, background-job, pipeline
- ✅ **SLO Generation** - Generates Sloth specifications from service definitions
- ✅ **Auto-Generated Alerts** - 400+ battle-tested rules from awesome-prometheus-alerts
- ✅ **Multi-Environment Support** - Dev/staging/prod configs with `--env` flag
- ✅ **PagerDuty Integration** - Auto-creates services with escalation policies
- ✅ **Prometheus Integration** - Real-time error budget tracking
- ✅ **Deployment Gates** - Error budget-based deployment validation
- ✅ **Template Variables** - Portable queries with `${service}`, `${team}`, etc.

### Observability Suite
- ✅ **Hybrid Dashboard Model** - Intent-based templates + live metric discovery for zero "No Data" panels
- ✅ **Dashboard Generation** - Auto-generate Grafana dashboards (12-28 panels per service)
- ✅ **Technology Templates** - 40+ production-grade panels for PostgreSQL, Redis, Elasticsearch, MongoDB, HTTP/API
- ✅ **118 Auto-Generated Alerts** - Production-ready Prometheus alerts with smart routing
- ✅ **Recording Rules** - 20+ pre-computed metrics for 10x faster dashboards
- ✅ **4 Deployment Methods** - Kubernetes, Mimir/Cortex, GitOps, or traditional Prometheus

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Get NthLayer running locally in 5 minutes. No external accounts required for development.

### Prerequisites

You only need:
* **Docker** - For PostgreSQL and Redis
* **Python 3.9+** - For the NthLayer CLI
* **Make** - For convenient shortcuts (optional)

### Installation

**Option 1: pip install (recommended)**
```bash
pip install nthlayer
```

**Option 2: From source (for development)**

1. Clone the repo
   ```bash
   git clone https://github.com/rsionnach/nthlayer.git
   cd nthlayer
   ```

2. Run setup (installs dependencies, starts services, runs migrations)
   ```bash
   make setup
   ```

3. Verify installation
   ```bash
   make test
   # All 84 tests should pass ✅
   ```

4. Try the demo
   ```bash
   make demo-reconcile
   # Shows step-by-step what NthLayer does
   ```

**That's it!** You're ready to use NthLayer.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

### Unified Workflow (Recommended)

**Preview what will be generated:**
```bash
nthlayer plan payment-api.yaml

# Output:
# ✅ SLOs (3)
# ✅ Alerts (28)
# ✅ Dashboard (1)
# ✅ Recording Rules (21)
# ✅ PagerDuty Service (1)
```

**Generate all resources at once:**
```bash
nthlayer apply payment-api.yaml

# Output:
# ✅ [1/5] SLOs          → 3 created
# ✅ [2/5] Alerts        → 28 created
# ✅ [3/5] Dashboard     → 1 created
# ✅ [4/5] Recording     → 21 created
# ✅ [5/5] PagerDuty     → 1 created
```

**With environment-specific configs:**
```bash
# Production: Stricter thresholds, all alerts
nthlayer apply payment-api.yaml --env prod

# Development: Relaxed thresholds, critical alerts only
nthlayer apply payment-api.yaml --env dev
```

**Advanced options:**
```bash
# Skip specific resources
nthlayer apply payment-api.yaml --skip pagerduty

# Only generate specific resources
nthlayer apply payment-api.yaml --only slos dashboard

# Verbose output
nthlayer apply payment-api.yaml --verbose

# Dry-run (preview without writing files)
nthlayer apply payment-api.yaml --dry-run
```

### Individual Commands (Advanced)

For granular control, individual commands are still available:

```bash
# Generate specific resource types
nthlayer generate-slo payment-api.yaml
nthlayer generate-alerts payment-api.yaml
nthlayer generate-dashboard payment-api.yaml --full
nthlayer generate-recording-rules payment-api.yaml

# Check deployment readiness
nthlayer check-deploy payment-api.yaml
```

### Development Workflow

```bash
# Start services
make dev-up

# Run tests
make test

# Start mock API server
make mock-server

# Demo workflows
make demo-reconcile

# Stop services
make dev-down
```

_For more examples and detailed usage, please refer to the [Getting Started Guide](GETTING_STARTED.md) and [Documentation](#documentation)_

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- DOCUMENTATION -->
## Documentation

### User Guides
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - 10-minute quick start guide
- **[docs/OBSERVABILITY.md](docs/OBSERVABILITY.md)** - Dashboard & recording rules guide
- **[docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md)** - Multi-environment configuration
- **[docs/ALERTS.md](docs/ALERTS.md)** - Auto-generated alerts documentation
- **[docs/TEMPLATES.md](docs/TEMPLATES.md)** - Service template reference
- **[docs/CUSTOM_TEMPLATES.md](docs/CUSTOM_TEMPLATES.md)** - Custom template guide

### Developer Docs
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Complete developer guide
- **[docs/DIAGRAMS.md](docs/DIAGRAMS.md)** - Visual architecture diagrams
- **[Makefile](Makefile)** - Run `make help` to see all commands
- **[nthlayer_architecture.md](nthlayer_architecture.md)** - System architecture

### Reference
- **[CHANGELOG.md](CHANGELOG.md)** - Feature changelog
- **[ATTRIBUTION.md](ATTRIBUTION.md)** - Third-party attributions
- **[LICENSING_COMPLIANCE.md](LICENSING_COMPLIANCE.md)** - License compliance
- **[archive/dev-notes/](archive/dev-notes/)** - Development history

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

### Recently Completed ✅
- [x] Multi-environment support (dev/staging/prod)
- [x] Auto-generated alerts (400+ rules)
- [x] Dashboard generation (12-28 panels)
- [x] Technology templates (PostgreSQL, Redis, K8s, HTTP/API)
- [x] Recording rules (20+ metrics)
- [x] Template variables and portability

### Coming Soon
- [ ] MySQL, MongoDB, Elasticsearch templates
- [ ] Custom panel selection for dashboards
- [ ] Multi-service aggregate dashboards
- [ ] Datadog integration
- [ ] Slack notifications

See the [open issues](https://github.com/rsionnach/nthlayer/issues) for a full list of proposed features and known issues.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community amazing. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".

1. Read [GETTING_STARTED.md](GETTING_STARTED.md) to understand the codebase
2. Fork the Project
3. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
4. Write tests with `respx` mocks
5. Run tests and linting (`make test lint format`)
6. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
7. Push to the Branch (`git push origin feature/AmazingFeature`)
8. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

NthLayer builds on the shoulders of giants:

### Core Dependencies
* **[grafana-foundation-sdk](https://github.com/grafana/grafana-foundation-sdk)** - Grafana dashboard generation SDK (Apache 2.0). Powers our Hybrid Model for intent-based dashboard generation with type-safe panel building.
* **[awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts)** - 580+ battle-tested alert rules (CC BY 4.0). Our alert templates for PostgreSQL, Redis, Elasticsearch, and 40+ technologies.

### Architecture Inspiration
* **[Sloth](https://github.com/slok/sloth)** - SLO specification format and burn rate calculations
* **[OpenSLO](https://github.com/openslo/openslo)** - SLO specification standard

### Tooling
* **[Best-README-Template](https://github.com/othneildrew/Best-README-Template)** - This README structure
* **[Shields.io](https://shields.io/)** - Badges used in this README
* **[Slidev](https://sli.dev/)** - Presentation framework for our decks

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## Quick Links

**Getting Started:**
```bash
# Setup and test
make setup && make test

# Try the unified workflow
nthlayer plan examples/services/payment-api.yaml
nthlayer apply examples/services/payment-api.yaml
```

**Need Help?**
- 📖 [Quick Start Guide](GETTING_STARTED.md)
- 💬 [Open an Issue](https://github.com/rsionnach/nthlayer/issues)
- 🎯 [View Roadmap](#roadmap)

**Happy coding!** 🚀

<!-- MARKDOWN LINKS & IMAGES -->
[tests-shield]: https://img.shields.io/github/actions/workflow/status/rsionnach/nthlayer/ci.yml?style=for-the-badge&logo=github&label=tests
[tests-url]: https://github.com/rsionnach/nthlayer/actions/workflows/ci.yml
[python-shield]: https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge&logo=python
[python-url]: https://python.org
[license-shield]: https://img.shields.io/badge/license-MIT-green?style=for-the-badge
[license-url]: LICENSE.txt
[contributors-shield]: https://img.shields.io/github/contributors/rsionnach/nthlayer.svg?style=for-the-badge
[contributors-url]: https://github.com/rsionnach/nthlayer/graphs/contributors

<!-- Tech Stack Badges -->
[python-badge]: https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://python.org
[pydantic-badge]: https://img.shields.io/badge/Pydantic-2.7+-E92063?style=for-the-badge&logo=pydantic&logoColor=white
[pydantic-url]: https://docs.pydantic.dev
[fastapi-badge]: https://img.shields.io/badge/FastAPI-0.111+-009688?style=for-the-badge&logo=fastapi&logoColor=white
[fastapi-url]: https://fastapi.tiangolo.com
[sqlalchemy-badge]: https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white
[sqlalchemy-url]: https://sqlalchemy.org
[alembic-badge]: https://img.shields.io/badge/Alembic-1.13+-6BA81E?style=for-the-badge&logo=sqlalchemy&logoColor=white
[alembic-url]: https://alembic.sqlalchemy.org
[postgresql-badge]: https://img.shields.io/badge/PostgreSQL-14+-316192?style=for-the-badge&logo=postgresql&logoColor=white
[postgresql-url]: https://postgresql.org
[redis-badge]: https://img.shields.io/badge/Redis-7+-DC382D?style=for-the-badge&logo=redis&logoColor=white
[redis-url]: https://redis.io
[prometheus-badge]: https://img.shields.io/badge/Prometheus-Alerts-E6522C?style=for-the-badge&logo=prometheus&logoColor=white
[prometheus-url]: https://prometheus.io
[grafana-badge]: https://img.shields.io/badge/Grafana-Dashboards-F46800?style=for-the-badge&logo=grafana&logoColor=white
[grafana-url]: https://grafana.com
[docker-badge]: https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white
[docker-url]: https://docker.com
