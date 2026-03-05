# Architecture

## Core Modules

- `orchestrator.py` — Facade for backward compatibility (delegates to orchestration/)
- `orchestration/` — Phased resource generation orchestration
  - `registry.py` — ResourceHandler protocol and ResourceRegistry
  - `handlers.py` — Concrete handlers (SLO, Alert, Dashboard, PagerDuty, etc.)
  - `engine.py` — ExecutionEngine for running generation loops
  - `plan_builder.py` — Preview generation plans before execution
  - `results.py` — ResultCollector for aggregating generation outcomes
- `dashboards/` — Intent-based dashboard generation with metric resolution
  - `resolver.py` — MetricResolver: translates intents to Prometheus metrics with fallback chains
  - `templates/` — Technology-specific intent templates (postgresql, redis, kafka, etc.)
  - `builder_sdk.py` — Grafana dashboard construction using grafana-foundation-sdk
- `discovery/` — Metric discovery from Prometheus
  - `client.py` — MetricDiscoveryClient: queries Prometheus for available metrics
  - `classifier.py` — Classifies metrics by technology and type
- `dependencies/` — Dependency discovery and graphing
  - `discovery.py` — DependencyDiscovery orchestrator
  - `providers/` — kubernetes, prometheus, consul, etcd, backstage providers
- `deployments/` — Deployment detection via webhooks
  - `base.py` — BaseDeploymentProvider ABC and DeploymentEvent model
  - `registry.py` — Provider registry for webhook routing
  - `providers/` — argocd, github, gitlab webhook parsers
  - `errors.py` — DeploymentProviderError exception
- `providers/` — External service integrations (grafana, prometheus, pagerduty, mimir)
- `identity/` — Service identity resolution across naming conventions
- `specs/` — Service specification models and parsing
  - `helpers.py` — Shared utilities: `TECH_KEYWORDS`, `infer_technology_from_name()`
  - `manifest.py` — ReliabilityManifest unified model (OpenSRM + legacy)
  - `loader.py` — Auto-detect format and load manifests
  - `parser.py` — Legacy format parser, `render_resource_spec()` for variable substitution
- `slos/` — SLO definition, validation, and recording rule generation
  - `models.py` — SLO, ErrorBudget, SLOStatus, Incident dataclasses; default target: 0.999
  - `parser.py` — OpenSLO YAML parsing
  - `collector.py` — SLOCollector: Prometheus queries for live budget data
  - `calculator.py` — ErrorBudgetCalculator
  - `gates.py` — Deployment gate enforcement (error budget thresholds)
  - `deployment.py` — DeploymentRecorder for storing deployment events
  - `correlator.py` — DeploymentCorrelator: weighted scoring for deployment-incident correlation
  - `ceiling.py` — SLO ceiling validation against upstream SLAs
- `alerts/` — Alert rule generation from dependencies and SLOs
- `validation/` — Metadata and resource validation
- `generators/` — Resource generation from manifests
  - `alerts.py` — Alert rule generation from service dependencies (awesome-prometheus-alerts)
  - `sloth.py` — Sloth SLO specification YAML generation
  - `docs.py` — Service README, ADR scaffold, and API documentation generation
  - `backstage.py` — Backstage entity JSON generation for service catalog
- `domain/` — Core domain models
  - `models.py` — Pydantic models: RunStatus, TeamSource, Team, Service, Run, Finding
- `db/` — Database persistence layer
  - `models.py` — SQLAlchemy ORM models (Run, Finding, SLO, ErrorBudget, Deployment, Incident, Policy audit)
  - `repositories.py` — RunRepository: async CRUD for jobs/findings with idempotency
  - `session.py` — SQLAlchemy async engine/session factory
- `drift/` — Reliability drift detection and trend analysis
  - `analyzer.py` — DriftAnalyzer for SLO trend analysis with configurable windows
- `topology/` — Dependency graph topology export for visualization
  - `models.py` — TopologyNode, TopologyEdge, TopologyGraph, SLOContract dataclasses
  - `enrichment.py` — build_topology(): DependencyGraph → TopologyGraph with SLO contract enrichment
  - `serializers.py` — serialize_json(), serialize_mermaid(), serialize_dot()
- `policies/` — Policy DSL and deployment gate enforcement
  - `evaluator.py` — Policy evaluation engine
  - `audit.py` — Audit domain models (PolicyEvaluation, PolicyViolation, PolicyOverride)
  - `recorder.py` — PolicyAuditRecorder for audit events
  - `repository.py` — PolicyAuditRepository for audit queries
- `integrations/` — Third-party service setup clients
  - `pagerduty.py` — PagerDutyClient: service/escalation policy/team creation
- `cloudwatch.py` — AWS CloudWatch MetricsCollector (optional `[aws]` extra)
- `verification/` — Prometheus metric contract verification
  - `verifier.py` — MetricVerifier: checks declared metrics exist in Prometheus
- `api/` — FastAPI API (webhooks, policies, health, teams)
  - `main.py` — App factory; registers routers; optional Mangum/Lambda handler
  - `routes/webhooks.py` — Deployment webhook receiver
  - `routes/policies.py` — Policy audit and override API
  - `routes/health.py` — Liveness/readiness endpoints with DB/Redis checks
- `cli/formatters/` — Multi-format CLI output system
  - `models.py` — ReliabilityReport, CheckResult, OutputFormat, CheckStatus
  - `sarif.py` — SARIF 2.1.0 formatter (GitHub Code Scanning)
  - `json_fmt.py`, `junit.py`, `markdown.py` — Additional formatters
- `scripts/lint/` — Custom linters for golden principles

## Data Flow

1. Service YAML → ServiceOrchestrator (facade) → ResourceDetector (indexes by kind) → OrchestratorContext
2. ExecutionEngine iterates over registered ResourceHandlers (SLO, Alert, Dashboard, etc.)
3. Each handler's generate() method creates resources, returns count
4. Dashboard generation: IntentTemplate.get_panel_specs() → MetricResolver.resolve() → Panel objects
5. Metric resolution: Custom overrides → Discovery → Fallback chain → Guidance
6. Resource creation: Async providers apply changes (Grafana, PagerDuty, etc.)
7. Deployment webhooks: Provider parses webhook → DeploymentEvent → DeploymentRecorder → Database
8. Drift analysis: DriftAnalyzer queries Prometheus for trend analysis → severity assessment
9. Policy evaluation: PolicyEvaluator checks conditions → PolicyAuditRecorder logs → API returns override option
10. Topology export: DependencyGraph → build_topology() → TopologyGraph → serialize_json/mermaid/dot()

## Architectural Invariants

These are hard rules — violations are bugs, not style issues.

1. Dashboard generation must use `IntentBasedTemplate` subclasses and `grafana-foundation-sdk` — no raw JSON dashboard construction
2. Metric resolution must go through the resolver (`dashboards/resolver.py`) — do not hardcode metric names in templates
3. All PromQL must use `service="$service"` label selector (not `cluster` or other labels)
4. `histogram_quantile` must include `sum by (le)` — bare `rate()` inside `histogram_quantile` is always a bug
5. Rate queries must aggregate: `sum(rate(metric{service="$service"}[5m]))`
6. Status label conventions must match service type: API (`status!~"5.."`), Worker (`status!="failed"`), Stream (`status!="error"`)
7. Error handling must use `NthLayerError` subclasses — bare `Exception` or `RuntimeError` raises are not allowed
8. CLI commands must be thin — business logic lives in modules/classes, not in click command functions
9. CLI output must go through `ux.py` helpers — no raw `print()` or `click.echo()` in command handlers
10. External service integrations must use official SDKs (`grafana-foundation-sdk`, `pagerduty`, `boto3`) — no bespoke HTTP clients
11. Exit codes must follow convention: 0=success, 1=warning/error, 2=critical/blocked

## Known Intentional Patterns

Do not flag these during review or audit:

- Demo app intentionally missing metrics (`redis_db_keys` from notification-worker, `elasticsearch_jvm_memory_*` from search-api) to demonstrate guidance panels
- Legacy template patterns that are tracked as known tech debt in Beads
- Empty catch blocks in migration code are intentional (best-effort migration)
- Lenient validation in `nthlayer validate-metadata` is by design (warns, doesn't fail)

## Release Process

- PyPI uses trusted publisher (no token needed)
- Create a GitHub release → triggers `.github/workflows/release.yml` → auto-publishes to PyPI
- Version is defined **only** in `pyproject.toml` (single source of truth via `importlib.metadata`)
- **CHANGELOG.md must be updated** before every release with all changes since the last release
