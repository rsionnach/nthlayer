# NthLayer

Reliability at build time, not incident time. Validate production readiness in CI/CD (Generate → Validate → Gate).

## Quick Reference

- **Language:** Python
- **Build:** `pip install -e .`
- **Test:** `make test`
- **Lint:** `make lint` / `./scripts/lint/run-all.sh`
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
| Execution plans | `plans/active/` |
| Completed plans | `plans/completed/` |
| Technical debt backlog | `plans/tech-debt.md` |

Read the specific doc relevant to your task. Do NOT try to load all docs at once.

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

## Workflow

- **Task tracking:** Beads (`bd ready`, `bd list`, `bd close`)
- **Issue creation:** `./scripts/create-audit-issue.sh` for dual Beads + GitHub Issues
- **Code review:** Automated on every PR via GitHub Action
- **Codebase audit:** `/audit-codebase`
- **GC sweep:** `/gc-sweep` (entropy cleanup)
- **Doc gardening:** `/doc-garden`
- **Spec to tasks:** `/spec-to-beads <spec-file>`
- **Release:** Update CHANGELOG.md, create GitHub release → auto-publishes to PyPI

## Commit Messages

Format: `<type>: <description> (<bead-id>)`

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `lint`

When fixing a GitHub Issue: `fix: <description> (<bead-id>, closes #<number>)`

<!-- AUTO-MANAGED: architecture -->
## Architecture

### Core Modules
- `orchestrator.py` - Service orchestration: coordinates SLO, alert, dashboard generation from service YAML
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
- `providers/` - External service integrations (grafana, prometheus, pagerduty, mimir)
- `identity/` - Service identity resolution across naming conventions
- `slos/` - SLO definition, validation, and recording rule generation
  - `deployment.py` - DeploymentRecorder for storing deployment events
- `alerts/` - Alert rule generation from dependencies and SLOs
- `validation/` - Metadata and resource validation
- `api/` - FastAPI webhook endpoints
  - `routes/webhooks.py` - Deployment webhook receiver

### Data Flow
1. Service YAML → ServiceOrchestrator → ResourceDetector (indexes by kind)
2. ResourceDetector determines what to generate (SLOs, alerts, dashboards, etc.)
3. Dashboard generation: IntentTemplate.get_panel_specs() → MetricResolver.resolve() → Panel objects
4. Metric resolution: Custom overrides → Discovery → Fallback chain → Guidance
5. Resource creation: Async providers apply changes (Grafana, PagerDuty, etc.)
6. Deployment webhooks: Provider parses webhook → DeploymentEvent → DeploymentRecorder → Database
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

### Service Orchestration
- `ServiceOrchestrator` (orchestrator.py) coordinates resource generation from service YAML
- `ResourceDetector` builds single-pass index of resources by kind (SLO, Dependencies, etc.)
- Auto-generates recording rules and Backstage entities when SLOs exist
- Auto-generates alerts and dashboards when dependencies exist
- `plan()` returns preview, `apply()` executes generation

### Deployment Detection Provider Pattern
- Provider-agnostic webhook handling via `BaseDeploymentProvider` ABC
- Each provider implements `verify_webhook()` (signature validation) and `parse_webhook()` (payload parsing)
- Providers return `DeploymentEvent` intermediate model (service, commit_sha, environment, author, etc.)
- `DeploymentProviderRegistry` maps provider names to implementations
- Webhook route dispatches based on `/webhooks/deployments/{provider_name}` path parameter
- `DeploymentRecorder.record_event()` stores events to database for correlation analysis
- Self-registering providers: import triggers `register_deployment_provider()` at module load
- Supported providers: ArgoCD (app.sync.succeeded), GitHub Actions (workflow_run.completed), GitLab (Pipeline Hook)
<!-- /AUTO-MANAGED: learned-patterns -->

<!-- AUTO-MANAGED: discovered-conventions -->
## Discovered Conventions

### Error Handling
- Always raise `ProviderError` or `NthLayerError` subclasses for application errors
- Never use bare `Exception` or `RuntimeError` in application code
- Provider modules define their own error subclasses: `GrafanaProviderError(ProviderError)`
- Import errors from `nthlayer.core.errors`

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

### Async/Await Usage
- All provider operations are async (health checks, resource creation, discovery)
- Use `asyncio.to_thread()` for sync HTTP operations to avoid blocking event loop
- Parallel operations use `asyncio.gather()` with `return_exceptions=True`
- Provider interfaces define `async def aclose()` for cleanup
<!-- /AUTO-MANAGED: discovered-conventions -->
