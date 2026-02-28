# NthLayer

Reliability at build time, not incident time. Validate production readiness in CI/CD (Generate → Validate → Gate).

## Quick Reference

- **Language:** Python
- **Build:** `pip install -e .`
- **Test:** `make test`
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
- `slos/` - SLO definition, validation, and recording rule generation
  - `models.py` - SLO, ErrorBudget, SLOStatus, Incident dataclasses; default target: 0.999
  - `parser.py` - OpenSLO YAML parsing
  - `collector.py` - SLOCollector: Prometheus queries for live budget data
  - `calculator.py` - ErrorBudgetCalculator
  - `gates.py` - Deployment gate enforcement (error budget thresholds)
  - `deployment.py` - DeploymentRecorder for storing deployment events
  - `correlator.py` - DeploymentCorrelator for error budget correlation
  - `ceiling.py` - SLO ceiling validation against upstream SLAs
- `alerts/` - Alert rule generation from dependencies and SLOs
- `validation/` - Metadata and resource validation
- `policies/` - Policy DSL and deployment gate enforcement
  - `evaluator.py` - Policy evaluation engine
  - `audit.py` - Audit domain models (PolicyEvaluation, PolicyViolation, PolicyOverride)
  - `recorder.py` - PolicyAuditRecorder for audit events
  - `repository.py` - PolicyAuditRepository for audit queries
- `api/` - FastAPI API (webhooks, policies, health, teams)
  - `main.py` - App factory; registers teams, webhooks, policies, health routers; optional Mangum/Lambda handler
  - `routes/webhooks.py` - Deployment webhook receiver
  - `routes/policies.py` - Policy audit and override API
  - `routes/health.py` - Liveness (`/health`) and readiness (`/ready`) endpoints with DB/Redis checks
- `cli/formatters/` - Multi-format CLI output system
  - `models.py` - `ReliabilityReport`, `CheckResult`, `OutputFormat`, `CheckStatus` canonical models
  - `sarif.py` - SARIF 2.1.0 formatter (GitHub Code Scanning); defines NTHLAYER001-008 rule taxonomy
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
- Plan status: active → completed → moved to archive
- Decision log tracks architectural choices that diverge from or clarify specs
- Deviation log defends against spec drift
- Technical debt tracked in `plans/tech-debt.md` with AUTO-MANAGED section for audit agents

### Quality Grading System
- Package quality grades (A-F) based on test coverage, docs, error handling, API stability
- Grade criteria: A (>80% coverage), B (>60%), C (>40%), D (<40%), F (untested)
- Tracked in `docs/quality.md` with AUTO-MANAGED sections for grades and history
- Packages with D/F grades should have active Beads issues for improvement
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
- SARIF output (GitHub Code Scanning) maps check failures to rule IDs NTHLAYER001–NTHLAYER008:
  - NTHLAYER001: SLOInfeasible, NTHLAYER002: DriftCritical, NTHLAYER003: MetricMissing
  - NTHLAYER004: BudgetExhausted, NTHLAYER005: HighBlastRadius, NTHLAYER006: TierMismatch
  - NTHLAYER007: OwnershipMissing, NTHLAYER008: RunbookMissing
- Set `rule_id` on `CheckResult` to emit structured SARIF annotations; omit for generic findings

### Topology Export CLI Pattern
- CLI command: `nthlayer topology export <manifest> [--format json|mermaid|dot] [--output FILE] [--depth N] [--demo]`
- `--demo` flag runs export with built-in sample data (no manifest required)
- JSON format produces Sitrep-compatible output; Mermaid uses `graph LR` with Nord-themed classDef tier styles and SLO labels on edges; DOT uses Graphviz digraph with Nord palette tier colors and type-based node shapes (cylinder=database, hexagon=worker/batch, parallelogram=queue), critical edges highlighted in red
- Env vars: `NTHLAYER_PROMETHEUS_URL`, `NTHLAYER_METRICS_USER`, `NTHLAYER_METRICS_PASSWORD`
- `build_topology()` (topology/enrichment.py) accepts optional `max_depth` + `root_service` for BFS-limited subgraph export
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
