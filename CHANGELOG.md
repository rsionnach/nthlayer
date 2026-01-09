# Changelog

## v0.1.0a11 (January 9, 2026)

### Security Release + Phase 1 & 2 Features

This release includes critical security fixes and two major feature phases.

#### Security Fixes
- **urllib3** CVE-2025-24810: Decompression-bomb bypass on redirects (2.6.2 → 2.6.3)
- **langgraph-checkpoint** RCE in JsonPlusSerializer (2.1.2 → 3.0.1 via langgraph 1.0)
- **ecdsa** Minerva timing attack: Removed entirely (python-jose → PyJWT migration)

#### Phase 1: Drift Detection
- **`nthlayer drift`** - Analyze SLO reliability trends over time
- Detects degradation, improvement, and oscillation patterns
- Statistical significance with confidence intervals
- Risk scoring based on pattern severity
- Demo mode with `--demo` flag

#### Phase 2: Dependency Intelligence
- **`nthlayer deps`** - Discover service dependencies from Prometheus metrics
- **`nthlayer blast-radius`** - Calculate deployment risk based on downstream dependents
- **Identity resolution module** - Service name normalization across providers
- Supports HTTP, gRPC, database, Redis, and Kafka dependency patterns
- Exit codes for CI/CD gates (0=low, 1=medium, 2=high risk)

#### Code Quality
- Test coverage expanded to 91% (2564 tests)
- Migrated from pip to uv for faster dependency management
- JWT authentication migrated from python-jose to PyJWT

---

## v0.1.0a10 (January 8, 2026)

### PyPI Release
- Version bump for PyPI publication
- No functional changes from a9

---

## v0.1.0a9 (January 7, 2026)

### Test Coverage & Core Improvements

#### Test Coverage
- Expanded test coverage from ~70% to 91%
- Added comprehensive tests for all CLI commands
- Integration tests for end-to-end workflows

#### Core Module
- New `src/nthlayer/core/` module for shared functionality
- Optimized orchestrator for better performance
- Improved configuration loading

#### Documentation
- Updated roadmap with 4-phase technical structure
- Simplified documentation structure

---

## v0.1.0a8 (December 21, 2025)

### Code Quality & CI/CD Improvements

#### Type Safety
- **Mypy errors fixed**: 142 → 0 type errors across all modules
- Full type annotation coverage in core modules

#### CI/CD Enhancements
- **Security scanning**: pip-audit for vulnerability detection
- **Dependabot integration**: Automated dependency updates
- **Pre-commit hooks**: ruff lint, mypy, pytest (pre-push)
- **Self-check validation**: NthLayer validates its own example specs

#### GitHub Actions Updates
- actions/checkout v4 → v6
- actions/cache v4 → v5
- actions/setup-python v5 → v6

#### Documentation
- **Architecture diagrams**: Mermaid diagrams with Iconify icons
- **Tech stack documentation**: Comprehensive module and component docs
- **Technology templates reference**: Exporter requirements and metrics documentation

#### Dependencies Updated
- ruff <0.5.0 → <0.15.0
- structlog 25.x → 26.x
- rich 14.x → 15.x
- mypy 1.11 → 1.20
- aioboto3 13.x → 16.x

#### CLI Fixes
- Questionary prompt styling improvements
- Service type to template mapping fix
- check-deploy latency SLO handling

---

## v0.1.0a7 (December 12, 2025)

### Reliability Shift Left - Major Release

This release establishes NthLayer as the **Reliability Shift Left** platform with comprehensive validation and deployment gates.

#### New Commands
- **`nthlayer verify`** - Contract verification: check declared metrics exist in Prometheus
- **`nthlayer validate-spec`** - OPA/Rego policy validation for service specs
- **`nthlayer validate-metadata`** - Prometheus rule metadata validation (labels, URLs)
- **`nthlayer check-deploy`** - Deployment gates based on error budget status

#### CLI First-Run Experience
- **Styled welcome message** when running `nthlayer` with no arguments
- Shows Quick Start commands, Key Commands, and documentation link
- ASCII banner with Nord colors in interactive terminals

#### Documentation Overhaul
- **Generate/Validate/Protect** structure for docs site
- New pages: CI/CD integration, Mimir support, deployment gates, shift-left concepts
- Nord color palette for docs site (dark/light mode)
- 5 new VHS demo GIFs

#### CI/CD Integration Examples
- GitHub Actions workflow
- GitLab CI template
- ArgoCD deployment gate hook
- Tekton pipeline task

#### Mimir Integration
- `nthlayer apply --push-ruler` supports Mimir/Cortex Ruler API
- Multi-tenant rule management

#### Policy Validation
- OPA/Rego policies for service specs (`policies/service.rego`, `slo.rego`, `dependencies.rego`)
- Conftest integration for CI/CD policy checks

---

## v0.1.0a6 (December 8, 2025)

### Complete CLI Styling with Nord Color Palette

- **New UX Module** (`src/nthlayer/cli/ux.py`) - Hybrid Charm/Rich module with Nord colors
- **ASCII Banner** - Blocky NTHLAYER banner on `--version` and no-command
- **Unicode Symbols** - Clean ✓✗⚠ℹ symbols instead of emojis (universal terminal support)
- **Nord Color Palette** - Frost blue headers, Aurora success/warning/error, Snow Storm muted text
- **Environment-Aware** - Detects CI/CD, respects NO_COLOR/FORCE_COLOR standards
- **Rich Tables** - Colored tables for portfolio and validation output
- **Styled All 19 Commands** - Consistent styling across entire CLI

### Demo GIFs
- Hero GIF with ASCII banner
- All 4 demo GIFs regenerated with new styling

---

## v0.1.0a2 (December 5, 2025)

### Code Quality - DRY Cleanup (~3,860 lines removed)
- **Phase 1**: Removed duplicate dashboard builders (`builder.py` → `builder_sdk.py`) and 6 legacy template files (~2,900 lines)
- **Phase 2**: Extracted secret backends to plugin system with lazy loading (~90 lines net reduction)
- **Phase 3**: Removed deprecated reslayer demo functions (~869 lines)

### New Features
- **SLO Portfolio command** - `nthlayer portfolio` for org-wide reliability view
- **Portfolio health scoring** - Tier-based weighting (tier-1: 3x, tier-2: 2x, tier-3: 1x)
- **Portfolio insights** - Actionable recommendations for SLO improvements

### Roadmap Updates
- Added Loki integration to roadmap (Phase 2.5)
- Added AI/ML service templates to roadmap
- Updated positioning: complementary to PagerDuty (not competitive)

### Improvements
- Modular secrets package with lazy-loaded cloud backends
- Faster startup (cloud backends only imported when needed)
- Cleaner CLI without redundant commands

---

## v0.1.0a1 (December 3, 2025)

Initial alpha release with core functionality.

---

## Phase 4: PagerDuty Integration (December 2025)

### Complete PagerDuty Integration
- **Tier-based escalation policies** - Critical (5/15/30min), High (15/30/60min), Medium (30/60min), Low (60min)
- **Auto-creates resources** - Teams, Schedules (primary/secondary/manager), Escalation Policies, Services
- **Team membership** - API key owner automatically added as team manager
- **Support models** - self, shared, sre, business_hours with routing labels
- **Event Orchestration** - Alert routing for shared/sre support models
- **Alertmanager config** - Auto-generated with PagerDuty receiver, tier-based timing
- **Official SDK** - Uses `pagerduty.RestApiV2Client` (not bespoke HTTP client)
- **Resilient setup** - Continues creating resources even if some fail
- 38+ tests for PagerDuty and Alertmanager modules

### CLI Improvements
- Clean one-line per resource type output
- Verbose mode (`--verbose`) for file list and details
- Warnings grouped at end
- Removed cluttery box drawing

## Phase 3: Observability Suite (December 2025)

### Phase 3D: Polish & Documentation
- Added dashboard customization (--full flag for 28+ panels)
- Created comprehensive observability guide (500 lines)
- Updated README and presentations
- 84/84 tests passing

### Phase 3C: Recording Rules
- Implemented Prometheus recording rules generation
- 20+ pre-computed metrics per service
- CLI command: `generate-recording-rules`
- 10x dashboard performance improvement

### Phase 3B: Technology Templates
- Created 4 technology templates (40 panels total)
- PostgreSQL (12 panels), Redis (10), Kubernetes (10), HTTP/API (8)
- Template registry system
- Dashboards improved from 6 → 12 → 28 panels

### Phase 3A: Dashboard Foundation
- Implemented Grafana dashboard generation
- Dashboard models and builder
- CLI command: `generate-dashboard`
- 6-12 panels per service with SLO, health, and technology metrics

## Weeks 7-8: Multi-Environment Support

- Multi-environment configuration system (dev, staging, prod)
- Environment-specific overrides
- Auto-detection from 12+ CI/CD sources
- Variable substitution (${env}, ${service}, ${team})
- CLI commands: `list-environments`, `diff-envs`, `validate-env`

## Weeks 1-6: Foundation

### Alert Generation
- 400+ battle-tested alert rules from awesome-prometheus-alerts
- Auto-generated alerts for PostgreSQL, Redis, MySQL, MongoDB, Kafka, etc.
- CLI command: `generate-alerts`

### Core Features
- SLO generation from service specifications
- PagerDuty integration with auto-service creation
- Prometheus integration for error budget tracking
- Deployment correlation and gates
- Custom template system
- CLI with 10 commands

## Stats

- **Commands:** 20+ total
- **Tests:** 2564 passing (91% coverage)
- **Documentation:** 30,000+ words
- **Dashboard Panels:** 40 in template library
- **Alert Rules:** 400+
- **Technology Templates:** 18 technologies supported
