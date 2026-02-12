# Architecture

## Core Modules

- `orchestrator.py` — Service orchestration: coordinates SLO, alert, dashboard generation from service YAML
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
- `slos/` — SLO definition, validation, and recording rule generation
  - `deployment.py` — DeploymentRecorder for storing deployment events
- `alerts/` — Alert rule generation from dependencies and SLOs
- `validation/` — Metadata and resource validation
- `api/` — FastAPI webhook endpoints
  - `routes/webhooks.py` — Deployment webhook receiver

## Data Flow

1. Service YAML → `ServiceOrchestrator` → `ResourceDetector` (indexes by kind)
2. `ResourceDetector` determines what to generate (SLOs, alerts, dashboards, etc.)
3. Dashboard generation: `IntentTemplate.get_panel_specs()` → `MetricResolver.resolve()` → Panel objects
4. Metric resolution: Custom overrides → Discovery → Fallback chain → Guidance
5. Resource creation: Async providers apply changes (Grafana, PagerDuty, etc.)
6. Deployment webhooks: Provider parses webhook → `DeploymentEvent` → `DeploymentRecorder` → Database

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
