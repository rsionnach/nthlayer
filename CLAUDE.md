# NthLayer

Reliability at build time, not incident time. Validate production readiness in CI/CD (Generate → Validate → Gate).

## Quick Reference

- **Language:** Python
- **License:** MIT (note: other OpenSRM ecosystem components — Arbiter, SitRep, Mayday — are Apache 2.0)
- **Build:** `pip install -e .`
- **Test:** `make test` | `make smoke` (CLI smoke, ~40s offline) | `make smoke-full` (includes Synology)
- **Lint:** `make lint` and `./scripts/lint/run-all.sh` (custom golden-principle linters)
- **Typecheck:** `make typecheck`
- **Format:** `make format`

## Documentation Map

| What | Where |
|------|-------|
| Architecture & package layout | `docs/architecture.md` |
| Coding conventions | `docs/conventions.md` |
| Golden principles (mechanical rules) | `docs/golden-principles.md` |
| Testing patterns | `docs/testing.md` |
| Quality grades by package | `docs/quality.md` |
| Active specs | `specs/` |
| Execution plans (spec implementations) | `plans/` |
| Technical debt backlog | `plans/tech-debt.md` |
| Design & promotion plans | `docs/plans/` |

Read the specific doc relevant to your task. Do NOT try to load all docs at once.

**MkDocs Documentation Site:**
- Configuration: `mkdocs.yml`
- Source docs: `docs-site/`
- Build output: `site/` (gitignored)
- Deploy: GitHub Actions workflow (`.github/workflows/docs.yml`) builds and deploys to GitHub Pages at rsionnach.github.io/nthlayer/
  - Triggers: push to `main` with changes to `docs-site/`, `mkdocs.yml`, or workflow file itself
  - Build step: `mkdocs build --strict` with MkDocs Material theme and minify plugin
  - Deploy step: `actions/deploy-pages` to GitHub Pages environment

## Key Architectural Rules

These are enforced by linters and structural tests. See `docs/golden-principles.md` for the full list with rationale.

1. Validate inputs at the boundary, not inline
2. Use shared utilities — do not hand-roll helpers that already exist
3. Structured logging only — no bare `print()` outside CLI entrypoints
4. Handle exceptions with context at module boundaries
5. Use template system for all generated output — no raw string construction
6. Every `TODO` must reference a Beads issue ID

## Task Tracking (Beads)

```bash
bd ready              # Show tasks ready to work on
bd update <id> --status in_progress
bd close <id> --reason "What was done"
bd create --title "..." --description "..." --priority 1 --type feature
```

See `docs/conventions.md` for full Beads workflow.

## Branching Strategy

- **`develop`** is the integration branch — all work goes here via feature branches and PRs
- **`main`** is the release branch — only updated by merging `develop` at release time
- **Never commit directly to `main`**
- Feature branches: `feat/<slug>`, merged to `develop` via PR

## Workflow

- **Task tracking:** Beads (`bd ready`, `bd list`, `bd close`)
- **Issue creation:** `./scripts/create-audit-issue.sh` for dual Beads + GitHub Issues
- **Code review:** Automated on every PR via GitHub Action
- **Codebase audit:** `/audit-codebase`
- **GC sweep:** `/gc-sweep` (entropy cleanup)
- **Doc gardening:** `/doc-garden`
- **Spec to tasks:** `/spec-to-beads <spec-file>`
- **Code quality sweep:** `/desloppify` (scan → fix → resolve loop for technical debt, dead code, code smells)
- **Autonomous loop:** `.claude/ralph-loop.sh [max-iterations]` runs Ralph loop; prompt at `.claude/ralph-prompt.md`; signal completion with `RALPH_COMPLETE`
- **Release:** Update CHANGELOG.md, merge `develop` → `main`, create GitHub release → auto-publishes to PyPI

## Commit Messages

Format: `<type>: <description> (<bead-id>)`

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `lint`

When fixing a GitHub Issue: `fix: <description> (<bead-id>, closes #<number>)`

<!-- AUTO-MANAGED: architecture -->
## Architecture

### Core Modules
- `orchestrator.py` - Facade for backward compatibility (delegates to orchestration/)
- `orchestration/` - Phased resource generation orchestration
  - `registry.py` - ResourceHandler protocol and ResourceRegistry
  - `handlers.py` - Concrete handlers (SLO, Alert, Dashboard, PagerDuty, etc.)
  - `engine.py` - ExecutionEngine for running generation loops
  - `plan_builder.py` - Preview generation plans before execution
  - `results.py` - ResultCollector for aggregating generation outcomes
- `dashboards/` - Intent-based dashboard generation with metric resolution
  - `resolver.py` - MetricResolver: translates intents to Prometheus metrics with fallback chains
  - `templates/` - Technology-specific intent templates (postgresql, redis, kafka, etc.)
  - `builder_sdk.py` - Grafana dashboard construction using grafana-foundation-sdk
- `discovery/` - Metric discovery from Prometheus
  - `client.py` - MetricDiscoveryClient: queries Prometheus for available metrics
  - `classifier.py` - Classifies metrics by technology and type
- `dependencies/` - Dependency discovery and graphing
  - `discovery.py` - DependencyDiscovery orchestrator
  - `providers/` - kubernetes, prometheus, consul, etcd, backstage providers
- `deployments/` - Deployment detection via webhooks
  - `base.py` - BaseDeploymentProvider ABC and DeploymentEvent model
  - `registry.py` - Provider registry for webhook routing
  - `providers/` - argocd, github, gitlab webhook parsers
  - `errors.py` - DeploymentProviderError exception
- `drift/` - Reliability drift detection and trend analysis
  - `analyzer.py` - DriftAnalyzer for SLO trend analysis with configurable windows
- `topology/` - Dependency graph topology export for visualization
  - `models.py` - TopologyNode, TopologyEdge, TopologyGraph, SLOContract dataclasses
  - `enrichment.py` - build_topology(): converts DependencyGraph → TopologyGraph with SLO contract enrichment
  - `serializers.py` - Pure serializers: serialize_json(), serialize_mermaid(), serialize_dot()
- `providers/` - External service integrations (grafana, prometheus, pagerduty, mimir)
- `identity/` - Service identity resolution across naming conventions
- `specs/` - Service specification models and parsing
  - `helpers.py` - Shared utilities: `TECH_KEYWORDS` constant, `infer_technology_from_name()` function
  - `manifest.py` - ReliabilityManifest unified model (OpenSRM + legacy); `BudgetPolicy`, `BudgetThresholds`, `ErrorBudgetGate` dataclasses for error budget policy DSL
  - `alerting.py` - `AlertingConfig`, `ForDuration` dataclasses; `ForDuration.get_for_severity()` maps severity → `for` duration override
  - `loader.py` - Auto-detect format and load manifests
  - `parser.py` - Legacy format parser, `render_resource_spec()` for variable substitution
  - `opensrm_parser.py` - OpenSRM YAML parser; `_parse_budget_policy()` helper constructs `BudgetPolicy` from gate config
- `slos/` - SLO definition, validation, and recording rule generation
  - `models.py` - SLO, ErrorBudget, SLOStatus, Incident dataclasses; default target: 0.999
  - `parser.py` - OpenSLO YAML parsing
  - `collector.py` - SLOCollector: Prometheus queries for live budget data
  - `calculator.py` - ErrorBudgetCalculator
  - `gates.py` - Deployment gate enforcement (error budget thresholds); `GatePolicy.on_exhausted` list drives exhaustion behaviors (freeze_deploys, require_approval, notify) enforced in `DeploymentGate.check_deployment()`
  - `deployment.py` - DeploymentRecorder for storing deployment events
  - `correlator.py` - DeploymentCorrelator: 5-factor weighted scoring (burn_rate 0.35, proximity 0.25, magnitude 0.15, dependency 0.15, history 0.10)
  - `ceiling.py` - SLO ceiling validation against upstream SLAs
- `alerts/` - Alert rule generation from dependencies and SLOs
- `domain/` - Core domain models
  - `models.py` - Pydantic models: RunStatus, TeamSource, Team, Service, Run, Finding
- `db/` - Database persistence layer
  - `models.py` - SQLAlchemy ORM models (Run, Finding, SLO, ErrorBudget, Deployment, Incident, Policy audit)
  - `repositories.py` - RunRepository: async CRUD for jobs/findings with idempotency
  - `session.py` - SQLAlchemy async engine/session factory
- `integrations/` - Third-party service setup clients
  - `pagerduty.py` - PagerDutyClient: service/escalation policy/team creation
- `cloudwatch.py` - AWS CloudWatch MetricsCollector (optional `[aws]` extra)
- `generators/` - Resource generation from manifests
  - `alerts.py` - Alert rule generation from service dependencies (awesome-prometheus-alerts)
  - `sloth.py` - Sloth SLO specification YAML generation
  - `docs.py` - Service README, ADR scaffold, and API documentation generation; `DocsGenerationResult` dataclass
  - `backstage.py` - Backstage entity JSON generation for service catalog
- `validation/` - Metadata and resource validation
- `policies/` - Policy DSL, build-time spec validation, and deployment gate enforcement
  - `engine.py` - PolicyEngine: loads rules from YAML or dict, evaluates against ReliabilityManifest
  - `models.py` - Build-time models: PolicyRule, PolicyViolation, PolicyReport, RuleType, PolicySeverity
  - `rules.py` - RULE_EVALUATORS registry: required_fields, tier_constraint, dependency_rule evaluators
  - `evaluator.py` - Runtime policy evaluation engine (deployment gates)
  - `audit.py` - Runtime audit domain models (PolicyEvaluation, PolicyViolation, PolicyOverride)
  - `recorder.py` - PolicyAuditRecorder for audit events
  - `repository.py` - PolicyAuditRepository for audit queries
- `api/` - FastAPI API (webhooks, policies, health, teams)
  - `main.py` - App factory; registers teams, webhooks, policies, health routers; optional Mangum/Lambda handler
  - `routes/webhooks.py` - Deployment webhook receiver
  - `routes/policies.py` - Policy audit and override API
  - `routes/health.py` - Liveness (`/health`) and readiness (`/ready`) endpoints with DB/Redis checks
- `cli/deploy.py` - `check-deploy` command; `_extract_gate_policy()` resolves `GatePolicy` from `DeploymentGate` resource first, then falls back to manifest `BudgetPolicy` conversion
- `cli/docs.py` - `generate-docs` command: generates README, ADR scaffold, API docs from service manifest
- `cli/formatters/` - Multi-format CLI output system
  - `models.py` - `ReliabilityReport`, `CheckResult`, `OutputFormat`, `CheckStatus` canonical models
  - `sarif.py` - SARIF 2.1.0 formatter (GitHub Code Scanning); defines NTHLAYER001-011 rule taxonomy
  - `json_fmt.py`, `junit.py`, `markdown.py` - Additional output formatters
  - `__init__.py` - `format_report(report, output_format, output_file)` unified entry point
- `verification/` - Prometheus metric contract verification
  - `verifier.py` - `MetricVerifier`: checks declared metrics exist in Prometheus
- `scripts/lint/` - Custom linters for golden principles
  - `check-exception-handling.sh` - Enforce exception handling with context
  - `check-no-orphan-todos.sh` - Enforce TODO tracking via Beads
  - `check-no-unstructured-logging.sh` - Enforce structured logging
  - `run-all.sh` - Orchestrator for all lint rules
- `docs/` - Standalone documentation files (reference material for agents)
  - `architecture.md` - Architecture details, invariants, release process
  - `conventions.md` - Coding conventions, Beads workflow, exit codes
  - `golden-principles.md` - Mechanical enforcement rules with promotion ladder
  - `testing.md` - Test patterns, commands, coverage by area
  - `quality.md` - Package quality grades (A-F scale), improvement priorities
  - `plans/` - Design and promotion plans (DAG-based implementation docs)
- `docs-site/` - MkDocs documentation site source
- `plans/` - Execution plan tracking for spec implementations
  - `README.md` - Plan lifecycle and format documentation
  - `tech-debt.md` - Technical debt inventory with AUTO-MANAGED section

### Data Flow
1. Service YAML → ServiceOrchestrator (facade) → ResourceDetector (indexes by kind) → OrchestratorContext
2. ExecutionEngine iterates over registered ResourceHandlers (SLO, Alert, Dashboard, etc.)
3. Each handler's generate() method creates resources, returns count
4. Dashboard generation: IntentTemplate.get_panel_specs() → MetricResolver.resolve() → Panel objects
5. Metric resolution: Custom overrides → Discovery → Fallback chain → Guidance
6. Resource creation: Async providers apply changes (Grafana, PagerDuty, etc.)
7. Deployment webhooks: Provider parses webhook → DeploymentEvent → DeploymentRecorder → Database
8. Drift analysis: DriftAnalyzer queries Prometheus for trend analysis → severity assessment (CRITICAL/WARN/OK)
9. Policy evaluation: PolicyEvaluator checks conditions → PolicyAuditRecorder logs result → API returns override option if blocked
10. Topology export: DependencyGraph → build_topology() → TopologyGraph → serialize_json/mermaid/dot()

### Planned: Agentic Inference (`nthlayer infer`)
- Model analyses a codebase and proposes an OpenSRM manifest for it
- Model provides judgment (what SLOs does this service need?), NthLayer provides transport (validate manifest, generate artifacts)
- ZFC boundary: model=judgment (infer SLO targets), NthLayer=transport (validate + generate)
- ZFC canonical doc: https://github.com/rsionnach/arbiter/blob/main/ZFC.md

### Planned: MCP Server and Backstage Plugin
- MCP server integration: planned (roadmap)
- Backstage plugin: planned (roadmap)

### Manifest Format Support
- Supports `opensrm/v1` (OpenSRM format with `apiVersion: opensrm/v1`) and legacy `srm/v1` format
- Auto-detected via `specs/loader.py`; `ReliabilityManifest` unified model handles both

### Acknowledgments
Built on: grafana-foundation-sdk, awesome-prometheus-alerts, pint, OpenSLO. Inspired by: Sloth, autograf.

### OpenSRM Ecosystem (README section)
- NthLayer is the **Tool** layer: deterministic, invocable, no reasoning — one of three execution models (Data Sources / Tools / Agents)
- Execution model test: "Does this component need to reason about ambiguous inputs?" Yes → Agent; same output every time → Tool; queryable state → Data Source
- Data and tool layers (OpenSRM manifests + NthLayer) work with zero agents; agent layer is additive, not foundational
- Ecosystem links: [OpenSRM](https://github.com/rsionnach/opensrm), [Arbiter](https://github.com/rsionnach/arbiter), [SitRep](https://github.com/rsionnach/sitrep), [Mayday](https://github.com/rsionnach/mayday)
- Full ecosystem composition in `opensrm/ECOSYSTEM.md`: component taxonomy, integration diagram, data flows, deployment tiers, post-incident learning loop
- **Arbiter** (architecture phase, Apache 2.0): quality measurement engine — per-agent quality tracking (rolling windows), degradation detection, self-calibration, cost-per-quality, governance via one-way safety ratchet; proven as Guardian in GasTown
- **SitRep** (architecture phase, Apache 2.0): pre-correlation agent — continuously groups signals so correlated view is ready before incident; snapshot schema: id, triggered_by, window, severity, summary, signals, correlations, topology, recommended_actions; states: WATCHING → ALERT → INCIDENT → DEGRADED
- **Mayday** (architecture phase, Apache 2.0): multi-agent incident response — deterministic orchestrator sequences Triage → (Investigation + Communication) → Remediation; PagerDuty/Slack/email are **downstream notification channels**, not upstream incident sources
- Deployment tiers: Tier 1 (OpenSRM + NthLayer only, zero agents), Tier 2 (+SitRep), Tier 3+ (+Arbiter +Mayday)
- Streaming layer: NATS (small teams), Kafka (enterprise) — sits between event producers and consumers (SitRep, Arbiter, Mayday)
- Alert flow (ecosystem): Alert Source → SitRep Snapshot → Mayday Orchestrator → Agent Pipeline → Notification Channels
- Post-incident learning loop: Mayday findings → manifest updates + NthLayer rule refinements + Arbiter threshold revisions + SitRep correlation improvements
<!-- /AUTO-MANAGED: architecture -->

<!-- AUTO-MANAGED: learned-patterns -->
## Learned Patterns

### Intent-Based Dashboard Generation
- Templates extend `IntentBasedTemplate` (from `dashboards/templates/base_intent.py`)
- Define panels using abstract "intents" instead of hardcoded metric names
- `get_panel_specs()` returns `List[PanelSpec]` with intent references
- `MetricResolver` translates intents to actual Prometheus metrics at generation time
- Resolution waterfall: custom overrides → primary discovery → fallback chain → guidance panels
- Example: `postgresql.connections` intent resolves to `pg_stat_database_numbackends` or fallback

### Metric Discovery and Resolution
- `MetricDiscoveryClient` (discovery/client.py) queries Prometheus for available metrics
- `MetricResolver` (dashboards/resolver.py) resolves intents with fallback chains
- `discover_for_service(service_name)` populates discovered metrics cache
- `resolve(intent_name)` returns `ResolutionResult` with status (resolved/fallback/unresolved)
- Unresolved intents generate guidance panels with exporter installation instructions
- Supports custom metric overrides from service YAML

### Async Provider Pattern
- All providers implement async interface: `async def health_check()`, `async def apply()`
- Use `asyncio.to_thread()` for sync HTTP clients (httpx.Client) to avoid blocking
- Dependency providers implement `async def discover(service)` and `async def discover_downstream(service)`
- DependencyDiscovery orchestrator runs providers in parallel with `asyncio.gather()`
- Provider errors raise `ProviderError` subclasses, never bare `Exception` or `RuntimeError`

### Phased Resource Orchestration
- `ResourceHandler` protocol defines `plan()` and `generate()` interface
- `ResourceRegistry` maintains handlers for each resource type (slos, alerts, dashboards, etc.)
- `OrchestratorContext` carries shared state (service YAML, output dir, env, ResourceDetector)
- `ExecutionEngine` iterates over handlers, calls generate(), collects results
- Each handler returns count of resources created
- `ResultCollector` aggregates outcomes and errors across all handlers
- Handlers are modular - new resource types register without changing orchestration core
- `ServiceOrchestrator` (orchestrator.py) is now a facade for backward compatibility

### Deployment Detection Provider Pattern
- Provider-agnostic webhook handling via `BaseDeploymentProvider` ABC
- Each provider implements `verify_webhook()` (signature validation) and `parse_webhook()` (payload parsing)
- Providers return `DeploymentEvent` intermediate model (service, commit_sha, environment, author, etc.)
- `DeploymentProviderRegistry` maps provider names to implementations
- Webhook route dispatches based on `/webhooks/deployments/{provider_name}` path parameter
- `DeploymentRecorder.record_event()` stores events to database for correlation analysis
- Self-registering providers: import triggers `register_deployment_provider()` at module load
- Supported providers: ArgoCD (app.sync.succeeded), GitHub Actions (workflow_run.completed), GitLab (Pipeline Hook)

### Drift Analysis Integration
- `DriftAnalyzer` (drift/analyzer.py) detects reliability trend degradation
- Integrated into `portfolio` and `deploy` CLI commands via `--drift` flag
- Configurable analysis windows (default from tier-specific config)
- Results include severity (CRITICAL/WARN/OK) and trend direction
- Tier-based thresholds determine when drift blocks deployments
- Exit code escalation: drift severity can upgrade warning (1) to critical (2)
- Portfolio aggregation: drift results included in JSON/CSV/Markdown output

### Golden Principles Enforcement
- Mechanical rules enforced via custom lint scripts in `scripts/lint/`
- Promotion ladder: Documentation → Convention Check → Lint → Structural Test
- Three enforced principles: structured logging, exception handling, TODO tracking
- `run-all.sh` orchestrator executes all check-*.sh scripts
- Called from CI and Claude Code hooks
- Failures block commits with remediation instructions
- `check-exception-handling.sh` detects bare `except` blocks without `# intentionally ignored: <reason>` comment

### Documentation Site (MkDocs)
- Material theme with dark/light mode toggle, Nord color scheme
- Navigation: Getting Started → Generate → Validate → Protect → Dependencies → Integrations → Concepts → Reference
- Mermaid diagram support for architecture visualization
- Markdown extensions: syntax highlighting, tabbed content, admonitions, emoji
- Plugins: search, minify
- Deployed to GitHub Pages at rsionnach.github.io/nthlayer/
- Source docs in `docs-site/`, built output in `site/` (gitignored)
- Assets: Custom CSS (stylesheets/nord.css), Mermaid config (javascripts/mermaid-config.js)

### Execution Plan Tracking
- Plans in `plans/` track spec implementation lifecycle
- Format: `YYYY-MM-DD-<slug>.md` with metadata, requirements checklist, decision log, deviation log
- Created by `/spec-to-beads`, updated during implementation
- Plan lifecycle: active plans in `plans/active/`, completed plans move to `plans/completed/`
- Decision log tracks architectural choices that diverge from or clarify specs
- Deviation log defends against spec drift
- Technical debt tracked in `plans/tech-debt.md` with AUTO-MANAGED section for audit agents
- Design, promotion, and feature implementation plans (DAG-based, task-by-task) stored in `docs/plans/` (e.g., `docs/plans/2026-03-06-c-to-b-promotion-design.md`, `docs/plans/2026-03-10-alert-for-budget-policy.md`)

### Quality Grading System
- Package quality grades (A-F) based on test coverage, docs, error handling, API stability
- Grade criteria: A (>80% coverage), B (>60%), C (>40%), D (<40%), F (untested)
- Tracked in `docs/quality.md` with AUTO-MANAGED sections for grades and history
- As of 2026-03-06: no F-grade or D-grade packages remain; domain/ reached A-grade (100% tested, fully documented)
- Core promotions completed 2026-03-06: domain/ C→A, core/ C→B, db/ C→B, identity/ C→B, policies/ reached B-grade (55 tests: models 10, rules 30, engine 15)
- Packages with D or lower grades should have active Beads issues for improvement
- Run `/audit-codebase` to identify specific gaps

### Policy Audit Trail Pattern
- Immutable audit records for all policy evaluations, violations, and overrides
- Domain models: `PolicyEvaluation` (gate checks), `PolicyViolation` (blocked/warning), `PolicyOverride` (manual approvals)
- Repository pattern: `PolicyAuditRepository` for queries, `PolicyAuditRecorder` for writes
- REST API exposes audit history at `GET /policies/{service}/audit`
- Override creation at `POST /policies/{service}/override` with approval metadata (who, why, when expires)
- Enables compliance tracking and post-mortem analysis of deployment gate decisions

### Fail-Open Error Handling for Audit Systems
- All DB operations in audit recorders wrapped in try/except blocks
- Audit errors logged via structlog with `exc_info=True` but never block deployments
- Methods return `None` on DB error to signal failure gracefully
- Critical principle: "audit failures are logged, not fatal" — deployments continue even if audit trail breaks
- Prevents cascading failures where observability systems block deployment gates
- Applied in `PolicyAuditRecorder` for gate evaluations and overrides

### Shared Constants for Module Defaults
- Repeated magic values extracted into module-level constants in `__init__.py` (not scattered across callers)
- Example: default SLO objective `0.999` defined once in `slos/__init__.py`, imported by `collector.py`, `cli/slo.py`, `cli/deploy.py`, `cli/portfolio.py`, `portfolio/aggregator.py`, `recording_rules/builder.py`
- Pattern: if a default value appears in 3+ call sites, promote it to a named constant in the owning module's `__init__.py`

### CLI Formatter System
- All CLI command output flows through `cli/formatters/` — never construct ad-hoc output strings
- `ReliabilityReport(service, command, checks, summary, metadata)` is the canonical report model; all formatters consume it
- `CheckResult(name, status, message, details, rule_id, location, line)` represents individual check outcomes
- `format_report(report, output_format, output_file)` dispatches to the correct formatter; supports TABLE, JSON, SARIF, JUNIT, MARKDOWN
- SARIF output (GitHub Code Scanning) maps check failures to rule IDs NTHLAYER001–NTHLAYER011:
  - NTHLAYER001: SLOInfeasible, NTHLAYER002: DriftCritical, NTHLAYER003: MetricMissing
  - NTHLAYER004: BudgetExhausted, NTHLAYER005: HighBlastRadius, NTHLAYER006: TierMismatch
  - NTHLAYER007: OwnershipMissing, NTHLAYER008: RunbookMissing
  - NTHLAYER009: PolicyRequiredField, NTHLAYER010: PolicyTierConstraint, NTHLAYER011: PolicyDependencyRule
- Set `rule_id` on `CheckResult` to emit structured SARIF annotations; omit for generic findings

### CLI Smoke Test Suite
- Location: `tests/smoke/` — end-to-end subprocess tests that invoke the real `nthlayer` CLI
- Runner: `tests/smoke/_helpers.run_nthlayer(*args)` executes `uv run nthlayer <args>` and returns `CLIResult(exit_code, stdout, stderr, command)`
- Manifest fixtures: `CHECKOUT_SERVICE` (`examples/services/checkout-service.yaml`), `PAYMENT_API_OPENSRM` (`examples/uat/payment-api.reliability.yaml`)
- All tests tagged `pytest.mark.smoke`; `conftest.py` provides `output_dir` fixture (tmp_path)
- Test categories:
  - `test_validate_commands.py` — `validate-spec`, `validate`, `validate-metadata`, `validate-slo --demo`
  - `test_generate_commands.py` — all `generate-*` commands with `--dry-run`
  - `test_apply_plan.py` — `plan` and `apply --output-dir`; validates dashboard JSON structure and alerts YAML (must have `groups` key)
  - `test_analysis_commands.py` — `check-deploy --demo` (exit 0/1), `check-deploy --demo-blocked` (exit 2), `topology export --demo`, `recommend-metrics`
  - `test_synology.py` (Tier 2) — `verify` and `drift`; skipped unless `NTHLAYER_PROMETHEUS_URL` is set; marked `pytest.mark.synology`
- Makefile targets: `make smoke` (offline, `-x` fail-fast), `make smoke-full` (sets `NTHLAYER_PROMETHEUS_URL`/`NTHLAYER_GRAFANA_URL` for Synology)
- Pre-push hook: `smoke-test` in `.pre-commit-config.yaml` runs `uv run pytest tests/smoke/ -x -q --tb=short` automatically before every `git push`

### Service Documentation Generation
- `generators/docs.py`: `generate_service_docs(service_file, output_dir, environment, include_adr, include_api)` produces Markdown docs from a `ReliabilityManifest`
- Generated artifacts: `README.md` (ownership, architecture, SLOs, dependencies, deployment sections), ADR scaffold (`adr/` subdirectory), API documentation stub
- `DocsGenerationResult` dataclass: `success`, `service`, `files_generated`, `output_dir`, `error`
- CLI: `nthlayer generate-docs <manifest> [--output DIR] [--env ENV] [--include-adr] [--include-api] [--dry-run]`
- Default output dir: `generated/{service_name}/` (derived from manifest filename stem)
- Input format auto-detected via `specs/loader.py` (supports OpenSRM and legacy formats)

### Topology Export CLI Pattern
- CLI command: `nthlayer topology export <manifest> [--format json|mermaid|dot] [--output FILE] [--depth N] [--demo]`
- `--demo` flag runs export with built-in sample data (no manifest required)
- JSON format produces Sitrep-compatible output; Mermaid uses `graph LR` with Nord-themed classDef tier styles and SLO labels on edges; DOT uses Graphviz digraph with Nord palette tier colors and type-based node shapes (cylinder=database, hexagon=worker/batch, parallelogram=queue), critical edges highlighted in red
- Env vars: `NTHLAYER_PROMETHEUS_URL`, `NTHLAYER_METRICS_USER`, `NTHLAYER_METRICS_PASSWORD`
- `build_topology()` (topology/enrichment.py) accepts optional `max_depth` + `root_service` for BFS-limited subgraph export

### Zero Framework Cognition (ZFC) in the Ecosystem
- Canonical doc: `arbiter/ZFC.md` (applies to entire OpenSRM ecosystem, not just Arbiter)
- Core tenet: "Transport is code. Judgment is model." Originated by Steve Yegge for GasTown.
- Two-question test for any function: (1) "Is there exactly one right answer given the inputs?" → transport, write in code. (2) "Does the right answer depend on context, interpretation, or evaluation?" → judgment, send to model.
- Transport examples: receiving webhook payloads, validating YAML against JSON schema, generating Prometheus rules from declared SLO targets, routing messages, persisting scores
- Judgment examples: deciding if code is correct, scoring quality dimensions, deciding if declining scores are real degradation vs normal variance, correlating quality drops with changes
- Config as guidance: a rejection rate threshold of 0.20 means "operator considers 20% concerning", not "trigger WARN at exactly 0.20" — the model decides the outcome using config as context
- Fail open: if model unavailable, transport continues, judgment pauses ("no quality opinion" not "wrong quality opinion")
- Model-agnostic by design: swap Claude for Gemini/GPT/local model, transport unchanged; judgment quality changes and is itself measurable
- ZFC is NOT "put LLM in every code path" — most ecosystem code is and should remain pure transport
- **NthLayer's ZFC boundary:** code=transport (validate manifest, generate artifacts, enforce gates); model=judgment (infer SLO targets, assess service criticality)
- **Arbiter governance one-way safety ratchet:** Arbiter can always reduce agent autonomy (safe direction) but can NEVER increase it without human approval — automated constraint is always permitted, automated expansion never is
- **Arbiter self-calibration:** every judgment emits `gen_ai.decision.*` OTel event; every human correction emits `gen_ai.override.*`; these feed back into Arbiter's own judgment SLO (false accept rate, precision, recall)

### Alert For Duration Override
- `ForDuration` dataclass (specs/alerting.py) holds severity-based `for` duration overrides: `page` (default "2m") for critical alerts, `ticket` (default "15m") for warning/info
- Added to `AlertingConfig` as `for_duration: ForDuration = field(default_factory=ForDuration)`
- `ForDuration.get_for_severity(severity)` returns `page` for "critical", `ticket` otherwise
- `AlertRule.customize_for_service()` gains optional `for_duration_override: str | None` parameter; applied after rule construction
- Pipeline wiring: `generate_alerts_from_manifest()` passes `alerting_config=manifest.alerting` to `_load_and_customize_alerts()`; the inner loop calls `alerting_config.for_duration.get_for_severity(alert.severity)` and forwards the result as `for_duration_override`
- Manifest YAML key: `spec.alerting.for_duration.page` / `spec.alerting.for_duration.ticket`

### Error Budget Policy DSL
- `BudgetThresholds(warning=0.20, critical=0.10)` — fraction of remaining budget (e.g. 0.10 = 10% remaining triggers critical)
- `BudgetPolicy(window="30d", thresholds=BudgetThresholds(), on_exhausted=[])` — full policy config in `specs/manifest.py`
- `on_exhausted` valid values: `freeze_deploys` (blocks deployment), `require_approval` (escalates to WARNING, requires explicit override), `notify` (informational)
- `BudgetPolicy.validate()` enforces: valid `on_exhausted` values, `warning >= critical` invariant
- `ErrorBudgetGate.policy: BudgetPolicy | None` — opt-in; absence means existing tier-default behavior
- YAML path: `spec.deployment.gates.error_budget.policy.{window,thresholds,on_exhausted}`
- Parser: `_parse_budget_policy(eb_data)` in `specs/opensrm_parser.py` constructs `BudgetPolicy` from gate config dict
- Conversion to gate layer: `BudgetPolicy → GatePolicy(warning=thresholds.warning*100, blocking=thresholds.critical*100, on_exhausted=...)` — multiply by 100 because `GatePolicy` uses percentage points
- CLI wiring: `_extract_gate_policy()` (cli/deploy.py) tries `DeploymentGate` resource first, then falls back to manifest `BudgetPolicy` conversion
- Exhaustion enforcement in `DeploymentGate.check_deployment()`: when `budget_remaining_pct <= 0` and `on_exhausted` is set, `freeze_deploys` → `BLOCKED`, `require_approval` → `WARNING`

### Build-Time Policy Engine
- `PolicyEngine` (policies/engine.py) validates spec correctness at CI/build time — distinct from runtime `PolicyAuditRecorder`/`Repository` (policies/audit.py)
- Two load paths: `PolicyEngine.from_yaml(path)` for central policy YAML, `PolicyEngine.from_dict(data)` for per-service `PolicyRules` resources
- `engine.add_rules(rules)` merges central + per-service rules before evaluation
- `engine.evaluate(manifest)` returns `PolicyReport` with violations, rules_evaluated count, and `passed` property (True if no error-severity violations)
- Rule types (RuleType enum in policies/models.py): `required_fields`, `tier_constraint`, `dependency_rule`
- `RULE_EVALUATORS` registry (policies/rules.py) maps `RuleType` → evaluator function; extend by adding new entries
- `required_fields` evaluator uses dot-path resolution (e.g., `"ownership.runbook"`) against `ReliabilityManifest` attributes
- `tier_constraint` evaluator checks `min_slos`, `require_deployment_gates`, `require_ownership` for a given tier or "all"
- `dependency_rule` evaluator checks `require_critical_deps_have_slo` and `max_critical_deps` limits
- `PolicySeverity`: `error` blocks (`passed=False`), `warning` surfaces but does not block
- CLI integration: `nthlayer validate <manifest> --policies <policies.yaml>` runs structural validation then policy evaluation; exit 0 = all pass, exit 1 = errors found
- `PolicyHandler` registered in `orchestration/handlers.py` handles `PolicyRules` resource kind embedded in service YAMLs; evaluated during `apply`/`plan` runs
<!-- /AUTO-MANAGED: learned-patterns -->

<!-- AUTO-MANAGED: discovered-conventions -->
## Discovered Conventions

### Error Handling
- Always raise `ProviderError` or `NthLayerError` subclasses for application errors
- Never use bare `Exception` or `RuntimeError` in application code
- Provider modules define their own error subclasses: `GrafanaProviderError(ProviderError)`
- Import errors from `nthlayer.core.errors`
- Full error taxonomy in `core/errors.py`: `ConfigurationError` (exit 10), `ProviderError` (exit 11), `ValidationError` (exit 12), `BlockedError` (exit 2), `PolicyAuditError` (exit 12), `WarningResult` (exit 1)
- Use `ExitCode` enum for exit codes: `ExitCode.SUCCESS=0`, `WARNING=1`, `BLOCKED=2`, `CONFIG_ERROR=10`, `PROVIDER_ERROR=11`, `VALIDATION_ERROR=12`, `UNKNOWN_ERROR=127`
- CLI command main functions: wrap with `@main_with_error_handling()` decorator from `nthlayer.core.errors` for unified exit code conversion
- Silently swallowed exceptions (bare `except` or `except Exception: pass`) must have explicit `# intentionally ignored: <reason>` comment
- Golden Principle #4: Re-raise exceptions with context using `raise XError("doing X") from err` at layer boundaries
- Lint enforcement: `check-exception-handling.sh` detects bare except blocks without intentional-ignore comments

### Logging
- Use `structlog` for all logging - no bare `print()` outside CLI entrypoints
- Import logger: `logger = structlog.get_logger()`
- Field naming: `err` or `error` (not `e`, `exc`), `component` (not `module`), `duration_ms` (not `elapsed`)
- Stdlib `logging` module is forbidden in application modules — use structlog exclusively
- Lint enforcement: `check-no-unstructured-logging.sh` detects print() in non-CLI modules
- CLI entrypoints (orchestration/engine.py) may use print() for user-facing output
- Tests use `tests/conftest.py` structlog test config to suppress log noise during test runs

### Dashboard Template Architecture
- Templates live in `src/nthlayer/dashboards/templates/`
- Technology-specific templates: `{technology}_intent.py` (e.g., `postgresql_intent.py`, `redis_intent.py`)
- All intent templates extend `IntentBasedTemplate` base class
- Base class implements `get_panels()` which calls template's `get_panel_specs()`
- Never construct raw JSON dashboards - always use `grafana-foundation-sdk` and intent templates

### Dependency Discovery
- Provider implementations in `src/nthlayer/dependencies/providers/`
- Each provider extends `BaseDepProvider` with async `discover()` and `discover_downstream()`
- Providers: kubernetes, prometheus, consul, etcd, zookeeper, backstage
- `DependencyDiscovery` (dependencies/discovery.py) orchestrates multiple providers
- Uses `IdentityResolver` to normalize service names across providers

### Deployment Detection
- Deployment providers in `src/nthlayer/deployments/providers/`
- Each provider extends `BaseDeploymentProvider` with `verify_webhook()` and `parse_webhook()`
- Providers: argocd, github, gitlab
- `DeploymentProviderRegistry` (deployments/registry.py) manages provider registration
- Webhook signature verification via HMAC SHA256 (X-Hub-Signature-256, X-Argo-Signature headers)
- FastAPI webhook endpoint: `POST /webhooks/deployments/{provider_name}`
- Response codes: 201 (recorded), 204 (skipped), 401 (invalid signature), 404 (unknown provider)

### Policy Audit API
- Policy evaluation, violation, and override tracking via REST API
- Endpoints: `POST /policies/{service}/override`, `GET /policies/{service}/audit?hours=24`
- Audit trail `hours` query param controls time window (default=24, range 1-720)
- Domain models in `policies/audit.py`: PolicyEvaluation, PolicyViolation, PolicyOverride
- `PolicyAuditRecorder` (policies/recorder.py) records audit events
- `PolicyAuditRepository` (policies/repository.py) queries audit history
- Integrated with deployment gates for manual override workflows
- Audit trail endpoint returns evaluations, violations, and overrides in single response
- policies router registered in `api/main.py` under `settings.api_prefix` with tag "policies"

### Optional Dependency Groups
- Install with extras for optional integrations: `pip install -e ".[aws]"`, `pip install -e ".[workflows]"`
- `[aws]`: boto3, aioboto3 — required for CloudWatch and SQS modules
- `[workflows]`: langgraph, langchain — required for `workflows/` LangGraph orchestration
- `[kubernetes]`: kubernetes client — required for K8s dependency discovery provider
- `[zookeeper]`: kazoo — required for Zookeeper discovery provider
- `[etcd]`: etcd3 — required for etcd discovery provider
- `[service-discovery]`: kazoo + etcd3 bundled — for all service discovery providers at once
- Core `structlog`, `httpx`, `pagerduty`, `grafana-foundation-sdk` are always installed
- Lazy import pattern: Optional imports use `__getattr__` in `__init__.py` (e.g., `queue/__init__.py` for SQS JobEnqueuer) to delay import until used, avoiding hard dependency on missing extras
- Runtime import deferral: `api/deps.py` imports `SQS JobEnqueuer` inside the function body at call time (not at module load) — use this pattern in FastAPI dependency functions to avoid failing on startup when optional extras are absent
- TYPE_CHECKING guard prevents circular imports while allowing type hints for optional classes

### Test Organization
- Shared mock servers live in `tests/fixtures/` (e.g., `tests/fixtures/mock_server.py`) — this is the canonical location; `tests/mock_server.py` is a legacy duplicate, do not add new files there
- Integration tests using mock servers live in `tests/integration/` (e.g., `tests/integration/test_mock_server_integration.py`)
- CLI end-to-end smoke tests live in `tests/smoke/` — invoke the real CLI via subprocess; see "CLI Smoke Test Suite" pattern for details
- Shared pytest config (structlog suppression, fixtures) lives in `tests/conftest.py`
- Tests for optional-dependency modules use `pytest.importorskip("package")` at module level to skip when extras are not installed: `aioboto3 = pytest.importorskip("aioboto3", reason="aioboto3 is required for workers tests")`
- Apply `importorskip` to any test module that imports from `[aws]`, `[workflows]`, or other optional extras

### Async/Await Usage
- All provider operations are async (health checks, resource creation, discovery)
- Use `asyncio.to_thread()` for sync HTTP operations to avoid blocking event loop
- Parallel operations use `asyncio.gather()` with `return_exceptions=True`
- Provider interfaces define `async def aclose()` for cleanup

### CLI Drift Analysis
- `nthlayer portfolio --drift` includes trend analysis for all services
- `nthlayer check-deploy --include-drift` checks deployment gate with drift detection
- Drift window configurable via `--drift-window` (e.g., "30d")
- Results displayed in table/JSON/CSV/markdown formats
- Exit code escalation: CRITICAL drift → exit 2, WARN → exit 1
<!-- /AUTO-MANAGED: discovered-conventions -->
