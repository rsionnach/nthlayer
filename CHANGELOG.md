# Changelog

## v0.1.0a16 (February 4, 2026)

### Intelligent Alerts Pipeline

- **`nthlayer alerts` command family** — evaluate, show, explain, test subcommands for alert management
- **AlertPipeline** — full pipeline evaluation against live or simulated budget data with notification support
- **AlertEvaluator** — rule resolution engine combining explicit and auto-generated alert rules per tier
- **ExplanationEngine** — context-aware budget explanations with technology-specific investigation actions
- **Alert simulation** — `nthlayer alerts test --simulate-burn 80` to preview what would fire at a given burn level
- **Multiple output formats** — table, JSON, YAML, and Markdown output for CI/CD integration
- Exit codes for CI/CD: 0=healthy, 1=warnings, 2=critical

### OpenSRM Phase 4: Contract & Dependency Validation

- **Contract registry** (`ContractRegistry`) — file-based registry that scans directories for manifest contracts, enabling cross-service validation (spec 11.3 Optional)
- **Dependency expectation validation** — warns when a dependency's expected availability exceeds the provider's published contract (spec 11.3 Recommended)
- **Transitive feasibility check** — warns when a service's contract availability is mathematically infeasible given its critical dependency chain (serial chain model, spec 11.3 Optional)
- **Template resolution** — OpenSRM templates are now resolved and deep-merged before parsing, with service-wins override semantics (spec 8.3)
- **Circular template detection** — templates that reference other templates are detected and warned about (spec 8.3.4 no-chaining rule, spec 11.2 Recommended)
- **Contract validation wired into validator** — `validate_service_file()` now runs `validate_contracts()` for OpenSRM files and accepts an optional `ContractRegistry` for cross-service checks
- **CLI `--registry-dir` flag** — `nthlayer validate --registry-dir <dir>` enables dependency and transitive feasibility validation against a directory of manifests
- **`metadata.template` passed through** in OpenSRM parser (previously parsed but not stored on manifest)

All new validation produces warnings (not errors) per spec Recommended/Optional priority.

#### Bug Fixes

- Fix policy evaluator parentheses regex matching function-call arguments

#### Dependencies

- Update rich from <14.0.0 to <15.0.0
- Update cachetools requirement
- Update mangum requirement
- Update python-json-logger requirement
- Update langchain from <0.4.0 to <1.3.0
- Resolve yanked numpy 2.4.0 in lockfile

#### CI

- Bump actions/checkout from 4 to 6
- Bump github/codeql-action from 3 to 4
- Bump peter-evans/create-pull-request from 5 to 8

---

## v0.1.0a15 (January 30, 2026)

### OpenSRM: Service Reliability Manifest Format

- **New format: `apiVersion: srm/v1`** - Declarative service reliability manifests
  - Unified `ReliabilityManifest` internal model that both OpenSRM and legacy NthLayer formats normalize to
  - OpenSRM YAML parser with validation for all spec sections
  - Format auto-detection loader — existing legacy files continue to work
  - Support for 7 service types: api, worker, stream, ai-gate, batch, database, web
  - AI gate services with judgment SLOs (reversal rate, calibration, feedback latency)
  - Deployment gates: error budget, SLO compliance, recent incidents
  - External contracts with internal SLO margin validation
  - Example manifests for all service types in `examples/opensrm/`

- **Generator migration to ReliabilityManifest** - All generators now accept both formats
  - `generate_alerts_from_manifest()` — alert generation from manifest
  - `generate_sloth_from_manifest()` — Sloth SLO spec generation from manifest
  - `ManifestDashboardBuilder` — Grafana dashboard generation from manifest
  - `generate_loki_alerts_from_manifest()` — Loki alert generation from manifest
  - `recommend_metrics_from_manifest()` — metric recommendations from manifest
  - Recording rules manifest builder adapter
  - Shared `extract_dependency_technologies()` helper consolidating duplicated logic
  - `ReliabilityManifest.as_service_context()` factory for backward compatibility

- **CLI migration to `load_as_legacy()` bridge** - All CLI commands now work with OpenSRM files
  - `load_as_legacy()` bridge function auto-detects format and routes to correct parser
  - OpenSRM files: `load_manifest()` → `as_service_context()` + `as_resources()`
  - Legacy files: direct `parse_service_file()` fallback for full compatibility
  - `ReliabilityManifest.as_resources()` converts SLOs, dependencies, and PagerDuty to Resource objects
  - All 17 CLI commands migrated (`validate`, `plan`, `generate-dashboard`, `generate-alerts`, etc.)
  - All generators, orchestrator, and portfolio aggregator migrated
  - `parse_service_file()` remains available for direct import (non-breaking)

- **`nthlayer migrate`** - CLI command to convert legacy format to OpenSRM

#### Bug Fixes

- Fix `recommend_metrics` returning `slo_ready=True` when no metric template found
- Add logging to sloth generator exception handlers (previously silent)
- Warn on invalid dependency criticality values in OpenSRM parser and legacy loader
- Fix dependency dashboard panels using application service name instead of exporter service name in PromQL queries (e.g. `service="postgresql"` instead of `service="payment-api"`)
- Fix intent resolution producing empty guidance panels when no MetricResolver configured; now uses first candidate metric name as fallback
- Fix gauge panels missing min/max; only set explicit max for percent/percentunit units
- Fix queue dependencies silently dropped in dashboard builder — Kafka, RabbitMQ, etc. now generate panels
- Fix validator rejecting legacy type aliases (`background-job`, `pipeline`)
- Add Redpanda as template alias for Kafka (wire-compatible)
- Fix `ServiceContext` type annotation in sloth `convert_to_sloth_slo`
- Remove unused `Contract` import from loader
- Fix f-strings without placeholders in OpenSRM parser
- Fix mypy type errors in sloth indicator dict and alerts routing argument

### Reliability Scorecard Calculator

- **`nthlayer scorecard`** - Per-service reliability scores (0-100)
  - Weighted score components: SLO Compliance (40%), Incident Score (30%), Deploy Success Rate (20%), Error Budget Remaining (10%)
  - Score bands: EXCELLENT (90+), GOOD (75-89), FAIR (50-74), POOR (25-49), CRITICAL (0-24)
  - Team aggregation with tier weighting (tier-1: 3x, tier-2: 2x, tier-3: 1x)
  - Output formats: table, json, csv
  - `--by-team` flag for team-level view
  - Exit codes for CI/CD: 0=excellent/good, 1=fair, 2=poor/critical
  - 36 tests with 100% coverage on core module

#### Dependencies

- Update httpx from <0.28.0 to <0.29.0
- Update pytest from <9.0.0 to <10.0.0
- Update respx from <0.22.0 to <0.23.0
- Update pytest-asyncio requirement

---

## v0.1.0a14 (January 18, 2026)

### CI/CD Proliferation, SLO Ceiling Validation & Metrics Recommendation Engine

This release adds three major features for production reliability enforcement.

#### New CLI Commands

- **`nthlayer recommend-metrics`** - Metrics recommendation based on service type
  - 7 service type templates: api, grpc, worker, queue-consumer, database-client, gateway, cache
  - Runtime-specific metrics: Python, JVM, Go, Node.js
  - Prometheus metric discovery with 50+ alias mappings
  - Integration with official `opentelemetry-semantic-conventions` package
  - `--check` flag to validate against live Prometheus
  - `--show-code` flag for instrumentation snippets

- **`nthlayer validate-slo-ceiling`** - SLO ceiling validation
  - Validates SLO targets don't exceed what dependencies can support
  - Calculates maximum achievable availability based on dependency SLAs
  - Warns when SLO targets are unrealistic given dependency constraints

#### CI/CD Integration

- **Output formatters** for CI/CD pipelines
  - GitHub Actions annotations (`--format github`)
  - GitLab CI reports (`--format gitlab`)
  - JSON output (`--format json`)
  - Quiet mode (`-q`) to suppress non-essential output

- **GitHub Action** workflow for automated validation
  - Ready-to-use action at `.github/actions/nthlayer-validate`

#### Internal

- Renamed `metrics.py` to `cloudwatch.py` to avoid module naming conflict
- Added `opentelemetry-semantic-conventions` as dependency
- 96% test coverage on the metrics module

---

## v0.1.0a13 (January 14, 2026)

### Alert Template Sync & Bug Fixes

This release adds automated alert template synchronization from the awesome-prometheus-alerts community repository, plus several bug fixes.

#### New Features

- **Alert Template Sync** - Automated synchronization from [awesome-prometheus-alerts](https://github.com/samber/awesome-prometheus-alerts)
  - `scripts/sync_awesome_alerts.py` - Sync script with auto-fix for common template bugs
  - New `AlertValidator` class for template validation and repair
  - Fixes label references, syntax issues, and common template errors
  - GitHub Action workflow for scheduled sync (`.github/workflows/sync-awesome-alerts.yml`)

#### Bug Fixes

- **Dashboard generation** - Fix `$service` variable replacement (now uses actual service name)
- **CLI** - Add `--prometheus-url` option to dashboard commands
- **Recording rules** - Align metric name with drift analyzer expectations
- **CLI version** - Use `importlib.metadata` for single source of truth

#### Internal

- Migrated issue tracking to proper `bd` CLI workflow
- Updated CLAUDE.md with beads usage documentation

---

## v0.1.0a12 (January 12, 2026)

### Phase 2 Complete: Dependency Intelligence & Service Discovery

This release completes Phase 2 (Dependency Intelligence) and Phase 2.5 (Service Discovery Providers), adding comprehensive service dependency analysis, ownership resolution, and multi-provider discovery.

#### New CLI Commands

- **`nthlayer identity`** - Service identity resolution and normalization
  - `identity resolve <name>` - Resolve service to canonical name
  - `identity list` - List known service identities
  - `identity normalize <name>` - Show normalization steps
  - `identity add-mapping` - Add custom identity mappings

- **`nthlayer ownership`** - Multi-source ownership attribution
  - Queries Backstage, PagerDuty, CODEOWNERS, Kubernetes labels
  - Confidence-based resolution when sources disagree
  - Shows on-call contact and escalation path

- **`nthlayer validate-slo`** - SLO metric existence validation
  - Validates SLO metrics exist in Prometheus before deployment
  - Checks recording rule dependencies
  - Label consistency validation

#### Enhanced Commands

- **`nthlayer deps`** - Now supports multiple providers
  - Backstage catalog integration
  - Kubernetes service discovery
  - Prometheus metric-based inference
  - DOT graph output format

- **`nthlayer blast-radius`** - Improved impact analysis
  - Multi-provider dependency traversal
  - Configurable depth analysis
  - Risk scoring with exit codes

#### New Dependency Providers (Phase 2.5)

- **Backstage** - Catalog API integration for service relationships
- **Kubernetes** - Service/Deployment label-based discovery
- **Consul** - Service catalog, health checks, Connect intentions
- **Zookeeper** - Curator-style service discovery
- **etcd** - Key-value prefix-based discovery

#### New Ownership Providers

- **Backstage** - `spec.owner` from catalog entities
- **PagerDuty** - Escalation policy owners, on-call schedules
- **Kubernetes** - `team`/`owner` labels on resources
- **CODEOWNERS** - GitHub/GitLab code ownership files
- **Declared** - Explicit `service.team` in service.yaml

#### Developer Experience

- **Pre-push hooks** - Tests run automatically before `git push`
- `make pre-commit-install` now installs both commit and push hooks
- `make setup` includes hook installation for new developers

#### Documentation

- New command documentation: deps, blast-radius, ownership, identity, validate-slo
- Updated CLI reference with all Phase 2 commands
- Dependencies section added to docs navigation

#### Stats Update

- **Tests:** 2821 passing
- **New CLI commands:** 4 (identity, ownership, validate-slo + subcommands)
- **Dependency providers:** 5 (Backstage, Kubernetes, Consul, Zookeeper, etcd)
- **Ownership providers:** 5 (Backstage, PagerDuty, Kubernetes, CODEOWNERS, declared)

---

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

## Pre-release

### Phase 4: PagerDuty Integration (December 2025)

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

### Phase 3: Observability Suite (December 2025)

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

### Weeks 7-8: Multi-Environment Support

- Multi-environment configuration system (dev, staging, prod)
- Environment-specific overrides
- Auto-detection from 12+ CI/CD sources
- Variable substitution (${env}, ${service}, ${team})
- CLI commands: `list-environments`, `diff-envs`, `validate-env`

### Weeks 1-6: Foundation

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

- **Commands:** 30+ total
- **Tests:** 3,364 passing
- **Documentation:** 30,000+ words
- **Dashboard Panels:** 50+ in template library
- **Alert Rules:** 580+
- **Technology Templates:** 21 technologies supported
