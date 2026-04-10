# NthLayer

Reliability at build time, not incident time. Validate production readiness in CI/CD (Generate → Validate → Gate).

## Quick Reference

- **Language:** Python
- **License:** MIT (note: other OpenSRM ecosystem components — nthlayer-measure, nthlayer-correlate, nthlayer-respond — are Apache 2.0)
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
| Ecosystem capability audit (generate migration plan) | `docs/generate-capability-audit.md` |

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
  - `models.py` - Re-export shim → canonical source is `nthlayer_common.dependency_models` (Phase 0 done); exports DependencyType, DependencyDirection, DiscoveredDependency, ResolvedDependency, DependencyGraph, BlastRadiusResult
  - `providers/` - kubernetes, prometheus, consul, etcd, backstage providers
- `deployments/` - DELETED (B1 ✓ done 2026-04-08) — all Python files removed; empty directory shell remains pending full cleanup in B4
- `scorecard/` — DELETED (B6 ✓ done 2026-04-09); entire scorecard package (models.py, calculator.py) moved to nthlayer-observe. The `ScoreBand` enum was inlined into `generators/backstage.py` because backstage entity generation still needs the band → letter-grade mapping for its static output.
- `portfolio/` — DELETED (B6 ✓ done 2026-04-09); entire portfolio package (models.py, aggregator.py) moved to nthlayer-observe.
- `topology/` - Dependency graph topology export for visualization
  - `models.py` - TopologyNode, TopologyEdge, TopologyGraph, SLOContract dataclasses
  - `enrichment.py` - build_topology(): converts DependencyGraph → TopologyGraph with SLO contract enrichment
  - `serializers.py` - Pure serializers: serialize_json(), serialize_mermaid(), serialize_dot()
- `clients/` - Re-export shims → canonical source is `nthlayer_common.clients` (Phase 0 done)
  - `__init__.py` - Exports: BaseHTTPClient, CortexClient, PagerDutyClient, SlackNotifier (re-exports from nthlayer_common.clients.*)
  - `base.py` - Re-export shim → `nthlayer_common.clients.base` (BaseHTTPClient, PermanentHTTPError, RetryableHTTPError, is_retryable_status)
  - `cortex.py` - Re-export shim → `nthlayer_common.clients.cortex` (CortexClient)
  - `pagerduty.py` - Re-export shim → `nthlayer_common.clients.pagerduty` (PagerDutyClient)
  - `slack.py` - Re-export shim → `nthlayer_common.clients.slack`; SlackAPIClient exported as SlackNotifier for backward compat
- `providers/` - Re-export shims → canonical source is `nthlayer_common.providers` for grafana/mimir/pagerduty (Phase 0 done); prometheus already done
  - `grafana.py` - Re-export shim → `nthlayer_common.providers.grafana` (GrafanaProvider, GrafanaProviderError, GrafanaDashboardResource, GrafanaDatasourceResource, GrafanaFolderResource)
  - `mimir.py` - Re-export shim → `nthlayer_common.providers.mimir` (MimirRulerProvider, MimirRulerError, RulerPushResult, DEFAULT_USER_AGENT)
  - `pagerduty.py` - Re-export shim → `nthlayer_common.providers.pagerduty` (PagerDutyProvider, PagerDutyProviderError, PagerDutyTeamMembershipResource)
- `identity/` - Re-export shims → canonical source is `nthlayer_common.identity` (Phase 0 done, including ownership symbols and live ownership providers)
  - `__init__.py` - Re-export shim: all identity + ownership symbols from `nthlayer_common.identity`
  - `models.py` - Re-export shim: ServiceIdentity, IdentityMatch from `nthlayer_common.identity.models`
  - `normalizer.py` - Re-export shim: NormalizationRule, DEFAULT_RULES, normalize_service_name, extract_from_pattern, PROVIDER_PATTERNS, extract_service_name from `nthlayer_common.identity.normalizer`
  - `resolver.py` - Re-export shim: IdentityResolver from `nthlayer_common.identity.resolver`
  - `ownership.py` - Re-export shim → canonical source is `nthlayer_common.identity.ownership`: `OwnershipSource`, `DEFAULT_CONFIDENCE`, `OwnershipSignal`, `OwnershipAttribution`, `OwnershipResolver`, `create_demo_attribution`
  - `ownership_providers/` - Mixed: live providers are re-export shims → `nthlayer_common.identity.ownership_providers`; static providers remain here
    - `__init__.py` - Re-exports all providers including static-only `CODEOWNERSProvider`, `DeclaredOwnershipProvider`
    - `base.py` - Re-export shim → `nthlayer_common.identity.ownership_providers.base` (BaseOwnershipProvider, OwnershipProviderHealth)
    - `backstage.py` - Re-export shim → `nthlayer_common.identity.ownership_providers.backstage`
    - `kubernetes.py` - Re-export shim → `nthlayer_common.identity.ownership_providers.kubernetes`
    - `pagerduty.py` - Re-export shim → `nthlayer_common.identity.ownership_providers.pagerduty`
    - `declared.py` - Static: reads `ownership:` from service manifest (confidence=1.0); remains in nthlayer (generate-only)
    - `codeowners.py` - Static: reads CODEOWNERS file from repo (confidence=0.85); remains in nthlayer (generate-only)
- `specs/` - Service specification models and parsing
  - `helpers.py` - Shared utilities: `TECH_KEYWORDS` constant, `infer_technology_from_name()` function
  - `manifest.py` - ReliabilityManifest unified model (OpenSRM + legacy); `BudgetPolicy`, `BudgetThresholds`, `ErrorBudgetGate` dataclasses for error budget policy DSL
  - `alerting.py` - `AlertingConfig`, `ForDuration` dataclasses; `ForDuration.get_for_severity()` maps severity → `for` duration override
  - `loader.py` - Auto-detect format and load manifests
  - `parser.py` - Legacy format parser, `render_resource_spec()` for variable substitution
  - `opensrm_parser.py` - OpenSRM YAML parser; `_parse_budget_policy()` helper constructs `BudgetPolicy` from gate config
- `slos/` - SLO definition, validation, and recording rule generation (runtime infra deleted B3 ✓ done 2026-04-09)
  - `models.py` - Re-export shim → canonical source is `nthlayer_common.slo_models` (Phase 0 done); exports SLO, ErrorBudget, SLOStatus, TimeWindow, TimeWindowType, Incident for backward compat
  - `parser.py` - OpenSLO YAML parsing
  - `calculator.py` - ErrorBudgetCalculator
  - `ceiling.py` - SLO ceiling validation against upstream SLAs
  - `alerts.py` - Budget alert evaluation: AlertSeverity, AlertType, AlertRule (budget-domain rule with alert_type+threshold, distinct from Prometheus AlertRule in alerts/models.py), AlertEvent, AlertEvaluator
  - `pipeline.py` - AlertPipeline: end-to-end alert orchestration (spec → budget → evaluate); PipelineResult dataclass with worst_severity property; ExplanationEngine and AlertNotifier removed in Phase 1 migration (notifications_sent always 0, explanations always [])
  - `collector.py`, `storage.py`, `gates.py`, `correlator.py`, `deployment.py`, `cli_helpers.py` — DELETED (B3 ✓); moved to nthlayer-observe
- `alerts/` - Alert rule generation from dependencies and SLOs
- `domain/` - Core domain models
  - `models.py` - Re-export shim → canonical source is `nthlayer_common.domain_models` (Phase 0 done); exports RunStatus, TeamSource, Team, Service, Run, Finding for backward compat
- `db/` — DELETED (B5 ✓ done 2026-04-09); entire SQLAlchemy persistence layer (models.py, repositories.py, session.py) + `alembic/` + `alembic.ini` moved to nthlayer-observe. `config/settings.py` also lost its DB settings (`database_url`, `db_pool_size`, `db_max_overflow`, `db_pool_timeout`, `db_pool_recycle`). Note: `cli/slo.py::slo_blame_command` still reads `NTHLAYER_DATABASE_URL` from env for its dead stub output — removal tracked separately (the command is an unreachable stub that references deleted runtime concepts).
- `integrations/` - Third-party service setup clients
  - `pagerduty.py` - PagerDutyClient: service/escalation policy/team creation
- `cloudwatch.py`, `cache.py`, `tracing.py`, `secrets.py`, `queue/`, `workflows/` — DELETED (B7 ✓ done 2026-04-09); all were orphaned runtime scaffolding (aws_xray tracing, redis cache, aioboto3 secrets/queue, cloudwatch metrics collector, langgraph workflows) with no consumers in generate.
- `generators/` - Resource generation from manifests
  - `alerts.py` - Alert rule generation from service dependencies (awesome-prometheus-alerts)
  - `sloth.py` - Sloth SLO specification YAML generation
  - `docs.py` - Service README, ADR scaffold, and API documentation generation; `DocsGenerationResult` dataclass
  - `backstage.py` - Backstage entity JSON generation for service catalog; `BackstageGenerationResult` dataclass; `generate_backstage_entity(service_file, output_dir, prometheus_url, environment)` — auto-detects format via `load_manifest()`, writes `backstage.json`; `generate_backstage_from_manifest(manifest, output_dir)` — takes `ReliabilityManifest` directly; `_build_backstage_entity_from_manifest(manifest)` preferred internal builder; `band_to_grade(band) -> str | None` maps `ScoreBand` → letter (A-F); `gate_result_to_status(result) -> str` maps `GateResult` → "APPROVED"/"WARNING"/"BLOCKED"; static generation: `errorBudget` and `score` sections are `None` (no live data); reads `NTHLAYER_GRAFANA_URL` env var for dashboard links; imports `GateResult` from `nthlayer_common.gate_models`; gate thresholds come from `nthlayer_common.tiers.TIER_CONFIGS` via local `_gate_thresholds_for_tier()` helper (B3 forward-port); `ScoreBand` is defined locally in this module (inlined B6 after `nthlayer.scorecard.models` deletion); tests split across `tests/test_backstage_generator.py` (file-path entry point) and `tests/test_generators_backstage.py` (manifest-level builder, added B6)
- `validation/` - Metadata and resource validation
- `policies/` - Build-time spec validation only (runtime policy infra deleted B2 ✓ done 2026-04-08)
  - `engine.py` - PolicyEngine: loads rules from YAML or dict, evaluates against ReliabilityManifest
  - `models.py` - Build-time models: PolicyRule, PolicyViolation, PolicyReport, RuleType, PolicySeverity
  - `rules.py` - RULE_EVALUATORS registry: required_fields, tier_constraint, dependency_rule evaluators
  - `evaluator.py`, `conditions.py`, `audit.py`, `recorder.py`, `repository.py` — DELETED (B2 ✓); moved to nthlayer-observe
- `api/` — DELETED (B4 ✓ done 2026-04-09); entire FastAPI server (main.py, auth.py, deps.py, routes/health.py, routes/teams.py) moved to nthlayer-observe. `config/settings.py` also lost its API-specific settings (`api_prefix`, `cors_origins`, `cognito_user_pool_id`, `cognito_region`, `cognito_audience`, `jwt_jwks_url`, `jwt_issuer`). Orphaned settings still present in `config/settings.py` pending B7 cleanup: `deployment_webhook_secret_argocd/github/gitlab`, `deployment_providers` (deployments/ deleted B1), `sqs_queue_url`, `job_queue_backend` (queue/ deleted B1, settings not yet removed).
- `cli/deploy.py` — DELETED (B3 ✓ done 2026-04-09); `check-deploy` command moved to nthlayer-observe. Use `nthlayer-observe check-deploy` for runtime deployment gate enforcement.
- `cli/docs.py` - `generate-docs` command: generates README, ADR scaffold, API docs from service manifest
- `cli/formatters/` - Multi-format CLI output system
  - `models.py` - `ReliabilityReport`, `CheckResult`, `OutputFormat`, `CheckStatus` canonical models
  - `sarif.py` - SARIF 2.1.0 formatter (GitHub Code Scanning); defines NTHLAYER001-011 rule taxonomy
  - `json_fmt.py`, `junit.py`, `markdown.py` - Additional output formatters
  - `__init__.py` - `format_report(report, output_format, output_file)` unified entry point
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
7. Deployment webhooks: MOVED to nthlayer-observe (B1 ✓ deleted from generate)
8. Policy evaluation: MOVED to nthlayer-observe (B2 ✓ deleted from generate)
9. Topology export: DependencyGraph → build_topology() → TopologyGraph → serialize_json/mermaid/dot()

### Planned: Agentic Inference (`nthlayer infer`)
- Model analyses a codebase and proposes an OpenSRM manifest for it
- Model provides judgment (what SLOs does this service need?), NthLayer provides transport (validate manifest, generate artifacts)
- ZFC boundary: model=judgment (infer SLO targets), NthLayer=transport (validate + generate)
- ZFC canonical doc: https://github.com/rsionnach/nthlayer-measure/blob/main/ZFC.md

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
- Ecosystem links: [OpenSRM](https://github.com/rsionnach/opensrm), [nthlayer-measure](https://github.com/rsionnach/nthlayer-measure), [nthlayer-correlate](https://github.com/rsionnach/nthlayer-correlate), [nthlayer-respond](https://github.com/rsionnach/nthlayer-respond)
- Full ecosystem composition in `opensrm/ECOSYSTEM.md`: component taxonomy, integration diagram, data flows, deployment tiers, post-incident learning loop
- **nthlayer-measure** (architecture phase, Apache 2.0): quality measurement engine — per-agent quality tracking (rolling windows), degradation detection, self-calibration, cost-per-quality, governance via one-way safety ratchet; proven as Guardian in GasTown
- **nthlayer-correlate** (architecture phase, Apache 2.0): pre-correlation agent — continuously groups signals so correlated view is ready before incident; snapshot schema: id, triggered_by, window, severity, summary, signals, correlations, topology, recommended_actions; states: WATCHING → ALERT → INCIDENT → DEGRADED
- **nthlayer-respond** (architecture phase, Apache 2.0): multi-agent incident response — deterministic orchestrator sequences Triage → (Investigation + Communication) → Remediation; PagerDuty/Slack/email are **downstream notification channels**, not upstream incident sources
- Deployment tiers: Tier 1 (OpenSRM + NthLayer only, zero agents), Tier 2 (+nthlayer-correlate), Tier 3+ (+nthlayer-measure +nthlayer-respond)
- Streaming layer: NATS (small teams), Kafka (enterprise) — sits between event producers and consumers (nthlayer-correlate, nthlayer-measure, nthlayer-respond)
- Alert flow (ecosystem): Alert Source → nthlayer-correlate Snapshot → nthlayer-respond Orchestrator → Agent Pipeline → Notification Channels
- Post-incident learning loop: nthlayer-respond findings → manifest updates + NthLayer rule refinements + nthlayer-measure threshold revisions + nthlayer-correlate correlation improvements

### Ecosystem Migration — COMPLETE (Phases 0–5)
Full audit at `docs/generate-capability-audit.md` (2026-04-06, routing corrected per `NTHLAYER-OBSERVE-SPEC.md`), architectural spec at `NTHLAYER-OBSERVE-SPEC.md`. Migration is complete: generate is now a pure compiler; all runtime infrastructure lives in nthlayer-observe.

**Architecture (post-migration):** generate (specs → artifacts, stateless) → observe (live state → assessments, stateful, no LLM) → measure/correlate/respond/learn (assessments → verdicts, agentic, LLM)

**Key routing rule:** ALL runtime infrastructure moves to nthlayer-observe. No code moves to measure or correlate — they gain a new Assessment input interface instead of receiving moved code.

**Classification summary (296 Python files, 46 CLI commands):**
- **STAYS in generate (~175 files, 59%):** all manifest parsing/models, all generators (sloth, alerts, backstage, docs, loki, alertmanager, pagerduty, dashboards, recording_rules), template system, build-time policy engine, CLI formatters, SLO calculator/ceiling/models/parser, topology models/serializers/enrichment, orchestration engine, simulation engine, all generate/validate CLI commands
- **MOVE to nthlayer-observe (~85 files, 28%):** `slos/collector.py`, `slos/storage.py`, `slos/gates.py` (DeploymentGate/GatePolicy), `slos/correlator.py` (5-factor deterministic scoring — not LLM reasoning), `cli/deploy.py` (check-deploy), `policies/evaluator.py` + `conditions.py` (DONE ✓ B2 deleted), policy audit trail (`policies/audit.py`, `recorder.py`, `repository.py`) (DONE ✓ B2 deleted), `drift/` (DONE ✓ — deleted from generate P5), `discovery/`, `verification/` (DONE ✓ — deleted from generate P5), `dependencies/discovery.py` + all providers, `cli/blast_radius.py` (DONE ✓ — deleted from generate P5), `cli/dependencies.py` (DONE ✓ — deleted from generate P5), live Prometheus enrichment in portfolio/scorecard, entire `api/` FastAPI server, `deployments/` (DONE ✓ B1 Python files deleted), `db/` (ORM + session + repositories)
- **MOVE to nthlayer-respond (~5 files, 2%):** `slos/notifiers.py` (Slack/PD — DONE ✓ deleted), `slos/explanations.py` (DONE ✓ deleted), pipeline notification dispatch (DONE ✓ removed from pipeline.py)
- **MOVE to nthlayer-learn (~1 file):** `scorecard/trends.py` (DONE ✓ — moved; TrendAnalyzer/TrendData removed from scorecard exports)
- **SHARE via nthlayer-common (~20 files, 7%):** `providers/prometheus.py` (DONE — shim), `clients/` (DONE — shims: base, pagerduty, slack, cortex), `providers/registry.py` + `providers/lock.py` (DONE — shims), `providers/base.py` (DONE — shim), `providers/grafana.py` (DONE — shim), `providers/mimir.py` (DONE — shim), `providers/pagerduty.py` (DONE — shim), `identity/` (normalizer, resolver, models — DONE — shims), `identity/ownership.py` (DONE — shim), `identity/ownership_providers/` (base, kubernetes, backstage, pagerduty — DONE — shims; declared/codeowners stay in nthlayer), `dependencies/models.py`, `domain/models.py`, `core/tiers.py` (DONE — shim), `core/errors.py` (DONE — shim), `slos/models.py`, `integrations/pagerduty.py`
- **REMOVE (~10 files):** deprecated `slos/deployment.py` methods (DONE ✓ — record_from_argocd/record_from_github removed), `workflows/team_reconcile.py` (DONE ✓ — workflows/ deleted), `demo.py`, `workers/` (DONE ✓ — workers/ deleted), `queue/`; `drift/` (DONE ✓ P5), `verification/` (DONE ✓ P5)

**Migration order:**
- Phase 0: Extract shared utils to nthlayer-common (tiers ✓, errors ✓, slos/models ✓, deps models ✓, domain models ✓, gate_models ✓, identity ✓, providers/base+lock+registry+prometheus ✓, identity/ownership.py ✓, identity/ownership_providers (base/backstage/kubernetes/pagerduty) ✓, clients/ (base/pagerduty/slack/cortex) ✓, providers/grafana+mimir+pagerduty ✓, integrations/pagerduty)
- Phase 1: Quick wins — move notifiers/explanations → respond; remove deprecated code + workers/queue ✓ (notifiers.py + explanations.py deleted, pipeline stripped of ExplanationEngine + AlertNotifier; workflows/ deleted, workers/ deleted, deprecated deployment.py methods removed, scorecard/trends.py moved to nthlayer-learn)
- Phase 2: Create nthlayer-observe — package structure, Assessment dataclass, SLO collector + storage
- Phase 3: Move drift, verification, discovery, dependencies to observe
- Phase 4: Move gate infrastructure to observe — gates, check-deploy, policies runtime, api, deployments, db
- Phase 5: Cleanup ✓ DONE (2026-04-08) — removed `drift/` (868 lines) and `verification/` (739 lines) from generate; removed CLI commands `drift`, `verify`, `deps`, `blast-radius` (now in nthlayer-observe); removed drift flags from deploy/portfolio; removed scipy/numpy from pyproject.toml. **Scope revision:** `discovery/` and `dependencies/` were NOT removed — both are still load-bearing in generate (dashboards/resolver.py, metrics/discovery.py, cli/topology.py, topology/enrichment.py, slos/correlator.py).

**Observe migration phases (P0–P5) complete.** Code has been copied to observe. Runtime files still present in generate will be deleted in the Purify Generate epic (see below).

### Purify Generate Epic — Next Phase

Spec: `docs/superpowers/specs/2026-04-08-purify-generate-design.md`

P0–P5 copied runtime code to nthlayer-observe. The Purify Generate epic deletes those files from generate so it becomes a true pure compiler: zero SQLAlchemy, zero FastAPI, zero alembic, zero runtime policy evaluation, zero live Prometheus gate enforcement, zero webhook handling.

**7 beads, removal order (leaf-first):**
- B1 (nthlayer-9dm.1) CLOSED ✓ 2026-04-08: Deleted `deployments/` Python files (base.py, registry.py, errors.py, providers/argocd+github+gitlab) + `api/routes/webhooks.py` + tests (test_deployment_providers.py)
- B2 (nthlayer-9dm.2) CLOSED ✓ 2026-04-08: Deleted `policies/evaluator.py`, `conditions.py`, `audit.py`, `recorder.py`, `repository.py` + `api/routes/policies.py` + tests (test_policies_evaluator.py, test_policy_audit.py); removed `check_deployment_with_audit()` from `slos/gates.py`; kept build-time `engine.py`/`models.py`/`rules.py`
- B3 (nthlayer-9dm.3) CLOSED ✓ 2026-04-09: Deleted `cli/deploy.py`, `slos/gates.py`, `slos/correlator.py`, `slos/collector.py`, `slos/storage.py`, `slos/deployment.py`, `slos/cli_helpers.py` + tests (test_cli_deploy.py, test_gates.py, test_slo_correlator.py, test_collector.py, test_slo_storage.py, test_slo_deployment.py, test_slo_cli_helpers.py); removed `check-deploy` from `demo.py`, smoke tests, and `cli/__init__.py`; forward-ported backstage.py gate threshold lookup to use `nthlayer_common.tiers.TIER_CONFIGS` directly. Note: `tests/test_budget_policy.py` was NOT deleted — only the `TestBudgetPolicyCLIWiring` class was removed; the file remains with tests for the build-time `BudgetPolicy` model in `specs/manifest.py` (TestBudgetPolicy, TestErrorBudgetGateWithPolicy, TestBudgetPolicyParsing, TestBudgetPolicyValidation)
- B4 (nthlayer-9dm.4) CLOSED ✓ 2026-04-09: Deleted entire `api/` directory (__init__.py, main.py, auth.py, deps.py, routes/__init__.py, routes/health.py, routes/teams.py) + tests (test_api_auth.py, test_api_reconcile.py); removed API-specific settings from `config/settings.py` (api_prefix, cors_origins, cognito_*, jwt_*).
- B5 (nthlayer-9dm.5) CLOSED ✓ 2026-04-09: Deleted `src/nthlayer/db/` (__init__.py, models.py, session.py, repositories.py) + `alembic/` + `alembic.ini` + tests (test_db_models.py, test_db_repositories.py, test_repository.py, test_db_session.py); removed DB settings from `config/settings.py` (database_url, db_pool_size, db_max_overflow, db_pool_timeout, db_pool_recycle)
- B6 (nthlayer-9dm.6) CLOSED ✓ 2026-04-09: Inlined `ScoreBand` enum into `generators/backstage.py` (the `DeploymentGate` → `TIER_CONFIGS` forward-port was already done in B3); deleted `src/nthlayer/portfolio/` (models.py, aggregator.py, __init__.py), `src/nthlayer/scorecard/` (models.py, calculator.py, __init__.py), `src/nthlayer/cli/portfolio.py`, `src/nthlayer/cli/scorecard.py`, tests (test_cli_portfolio.py, test_portfolio_aggregator.py, test_portfolio_cli.py, test_scorecard.py); removed portfolio/scorecard parser registrations + dispatch from demo.py and cli/__init__.py; dropped obsolete test_portfolio_command_dispatch from test_demo.py.
- B7 (nthlayer-9dm.7) CLOSED ✓ 2026-04-09: Purged all runtime deps from pyproject.toml (fastapi, uvicorn[standard], mangum, sqlalchemy, alembic, psycopg[binary], redis, aws-xray-sdk, PyJWT[crypto], jwcrypto, python-json-logger, orjson, tenacity, circuitbreaker); also deleted orphan modules (cache.py, tracing.py, cloudwatch.py, queue/, secrets.py, workflows/) and their tests + fixtures (mock_server.py, test_mock_server_integration.py); pruned dev extras (types-redis, aiosqlite, greenlet); simplified `[aws]` optional extra to just `boto3` (still required by config/secrets/backends.py for AWSSecretBackend); removed orphan Settings fields (deployment_webhook_secret_*, deployment_providers, sqs_queue_url, job_queue_backend, redis_max_connections). uv.lock regenerated with 91 packages total (down from ~120).

**Acceptance criteria:** zero `import sqlalchemy`/`import fastapi`/`from nthlayer.db`/`from nthlayer.api`/`from nthlayer.deployments` in remaining code; `nthlayer --help` shows only generate/validate/compile commands; `pip install -e .` works without runtime deps; full test suite passes.

**Workflow:** each bead requires `/rule-of-five-planning` before and `/rule-of-five-reviews` (4 passes) before closing.
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

### Deployment Detection Provider Pattern (moved to nthlayer-observe — B1 ✓ done 2026-04-08)
- Pattern deleted from generate; implementation now lives in nthlayer-observe
- See nthlayer-observe CLAUDE.md for the provider ABC, registry, and webhook routing details

### Drift Analysis Integration (moved to nthlayer-observe — P5 ✓ done 2026-04-08)
- `drift/` deleted from generate entirely; `DriftAnalyzer` now lives in nthlayer-observe
- `--drift` flag removed from `portfolio` (deleted B6) and `deploy` (deleted B3) CLI commands
- Use `nthlayer-observe drift --service <name> --prometheus-url <url>` for runtime drift detection

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

### Policy Audit Trail Pattern (moved to nthlayer-observe — B2 ✓ done 2026-04-08)
- Audit domain models, recorder, repository, and REST API deleted from generate
- See nthlayer-observe CLAUDE.md for PolicyEvaluation, PolicyAuditRecorder, PolicyAuditRepository details

### Fail-Open Error Handling for Audit Systems (moved to nthlayer-observe — B2 ✓ done 2026-04-08)
- PolicyAuditRecorder deleted from generate; fail-open pattern applies in nthlayer-observe implementation

### Shared Constants for Module Defaults
- Repeated magic values extracted into module-level constants in `__init__.py` (not scattered across callers)
- Example: default SLO objective `0.999` defined once in `slos/__init__.py`, imported by `cli/slo.py`, `recording_rules/builder.py`, etc.
- Pattern: if a default value appears in 3+ call sites, promote it to a named constant in the owning module's `__init__.py`
- Note: `cli/deploy.py`, `cli/portfolio.py`, `portfolio/aggregator.py`, `slos/collector.py` are deleted — remove from any import example lists

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
  - `test_analysis_commands.py` — `topology export --demo` (JSON/Mermaid formats), `recommend-metrics`; check-deploy tests removed in B3 (now in nthlayer-observe)
  - `test_synology.py` (Tier 2) — `validate-slo` live tests and Grafana dashboard push; `TestCheckDeployLive` removed in B3; verify/drift tests removed in P5 — all now in nthlayer-observe; skipped unless `NTHLAYER_PROMETHEUS_URL` is set; marked `pytest.mark.synology`
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
- JSON format produces nthlayer-correlate-compatible output; Mermaid uses `graph LR` with Nord-themed classDef tier styles and SLO labels on edges; DOT uses Graphviz digraph with Nord palette tier colors and type-based node shapes (cylinder=database, hexagon=worker/batch, parallelogram=queue), critical edges highlighted in red
- Env vars: `NTHLAYER_PROMETHEUS_URL`, `NTHLAYER_METRICS_USER`, `NTHLAYER_METRICS_PASSWORD`
- `build_topology()` (topology/enrichment.py) accepts optional `max_depth` + `root_service` for BFS-limited subgraph export

### Zero Framework Cognition (ZFC) in the Ecosystem
- Canonical doc: `nthlayer-measure/ZFC.md` (applies to entire OpenSRM ecosystem, not just nthlayer-measure)
- Core tenet: "Transport is code. Judgment is model." Originated by Steve Yegge for GasTown.
- Two-question test for any function: (1) "Is there exactly one right answer given the inputs?" → transport, write in code. (2) "Does the right answer depend on context, interpretation, or evaluation?" → judgment, send to model.
- Transport examples: receiving webhook payloads, validating YAML against JSON schema, generating Prometheus rules from declared SLO targets, routing messages, persisting scores
- Judgment examples: deciding if code is correct, scoring quality dimensions, deciding if declining scores are real degradation vs normal variance, correlating quality drops with changes
- Config as guidance: a rejection rate threshold of 0.20 means "operator considers 20% concerning", not "trigger WARN at exactly 0.20" — the model decides the outcome using config as context
- Fail open: if model unavailable, transport continues, judgment pauses ("no quality opinion" not "wrong quality opinion")
- Model-agnostic by design: swap Claude for Gemini/GPT/local model, transport unchanged; judgment quality changes and is itself measurable
- ZFC is NOT "put LLM in every code path" — most ecosystem code is and should remain pure transport
- **NthLayer's ZFC boundary:** code=transport (validate manifest, generate artifacts, enforce gates); model=judgment (infer SLO targets, assess service criticality)
- **nthlayer-measure governance one-way safety ratchet:** nthlayer-measure can always reduce agent autonomy (safe direction) but can NEVER increase it without human approval — automated constraint is always permitted, automated expansion never is
- **nthlayer-measure self-calibration:** every judgment emits `gen_ai.decision.*` OTel event; every human correction emits `gen_ai.override.*`; these feed back into nthlayer-measure's own judgment SLO (false accept rate, precision, recall)

### Alert For Duration Override
- `ForDuration` dataclass (specs/alerting.py) holds severity-based `for` duration overrides: `page` (default "2m") for critical alerts, `ticket` (default "15m") for warning/info
- Added to `AlertingConfig` as `for_duration: ForDuration = field(default_factory=ForDuration)`
- `ForDuration.get_for_severity(severity)` returns `page` for "critical", `ticket` otherwise
- `AlertRule.customize_for_service()` gains optional `for_duration_override: str | None` parameter; applied after rule construction
- Pipeline wiring: `generate_alerts_from_manifest()` passes `alerting_config=manifest.alerting` to `_load_and_customize_alerts()`; the inner loop calls `alerting_config.for_duration.get_for_severity(alert.severity)` and forwards the result as `for_duration_override`
- Manifest YAML key: `spec.alerting.for_duration.page` / `spec.alerting.for_duration.ticket`
- `TIER_DEFAULT_RULES` in specs/alerting.py covers all 4 tiers: `critical`, `high`, `standard`, `low`; "high" sits between critical and standard (budget-warning@0.65, budget-critical@0.85, burn-rate-warning@3.0, budget-exhaustion@6.0)

### Alert Pipeline (slos/pipeline.py)
- `AlertPipeline(prometheus_url, dry_run, notify)` orchestrates end-to-end SLO alert evaluation
- `evaluate_service(manifest, sli_measurements, simulate_burn_pct)` → `PipelineResult`
- Pipeline steps: `resolve_effective_rules()` → build `ErrorBudget` objects → `AlertEvaluator` (ExplanationEngine + AlertNotifier removed in Phase 1 migration — now owned by nthlayer-respond)
- Pipeline is fully synchronous post-Phase 1 — no `asyncio` import; all evaluation is sequential
- `notify` param accepted but always forced to `False`; `notifications_sent` always 0; `explanations` always empty list
- `dry_run=True`: runs full evaluation (budget calc, rule eval) but skips all notifications (no-op post-migration)
- `simulate_burn_pct`: synthesizes budget consumption at given percentage without requiring Prometheus
- `PipelineResult` fields: `budgets_evaluated`, `rules_evaluated`, `alerts_triggered`, `notifications_sent`, `explanations`, `events`, `errors`; `worst_severity` property returns "healthy" | "info" | "warning" | "critical"
- `_build_slo_from_manifest(manifest, slo_def)` converts `SLODefinition` → `SLO`; normalises target: values >1 treated as percentage (99.9 → 0.999)
- `_convert_spec_rule_to_alert_rule(spec_rule, service, slo_id, channels)` maps `SpecAlertRule` → budget-domain `AlertRule` (slos/alerts.py); distinct from Prometheus `AlertRule` (alerts/models.py)
- Note: `slos/alerts.py::AlertRule` is a budget alert rule (has `alert_type`, `threshold`); `alerts/models.py::AlertRule` is a Prometheus alerting rule (has `expr`, `duration`)
- `alerts_explain_command` (cli/alerts.py): both code paths (with and without `--slo-filter`) return "Budget explanations not available in nthlayer-generate"; dead explanation iteration removed post-Phase 1; restoration tracked via bead nthlayer-hmj (nthlayer-observe)

### Error Budget Policy DSL
- `BudgetThresholds(warning=0.20, critical=0.10)` — fraction of remaining budget (e.g. 0.10 = 10% remaining triggers critical)
- `BudgetPolicy(window="30d", thresholds=BudgetThresholds(), on_exhausted=[])` — full policy config in `specs/manifest.py`
- `on_exhausted` valid values: `freeze_deploys` (blocks deployment), `require_approval` (escalates to WARNING, requires explicit override), `notify` (informational)
- `BudgetPolicy.validate()` enforces: valid `on_exhausted` values, `warning >= critical` invariant
- `ErrorBudgetGate.policy: BudgetPolicy | None` — opt-in; absence means existing tier-default behavior
- YAML path: `spec.deployment.gates.error_budget.policy.{window,thresholds,on_exhausted}`
- Parser: `_parse_budget_policy(eb_data)` in `specs/opensrm_parser.py` constructs `BudgetPolicy` from gate config dict
- Conversion to gate layer: `BudgetPolicy → GatePolicy(warning=thresholds.warning*100, blocking=thresholds.critical*100, on_exhausted=...)` — multiply by 100 because `GatePolicy` uses percentage points
- CLI wiring: `_extract_gate_policy()` was in `cli/deploy.py` (DELETED B3); gate enforcement now lives in nthlayer-observe
- Exhaustion enforcement in `DeploymentGate.check_deployment()`: `freeze_deploys` → `BLOCKED`, `require_approval` → `WARNING` — now in nthlayer-observe


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
- **Canonical source:** `nthlayer_common.errors` (migrated from `core/errors.py` in Phase 0). `nthlayer.core.errors` is a backward-compat re-export shim — existing imports continue to work
- Full error taxonomy: `ConfigurationError` (exit 10), `ProviderError` (exit 11), `ValidationError` (exit 12), `BlockedError` (exit 2), `PolicyAuditError` (exit 12), `WarningResult` (exit 1)
- Use `ExitCode` enum for exit codes: `ExitCode.SUCCESS=0`, `WARNING=1`, `BLOCKED=2`, `CONFIG_ERROR=10`, `PROVIDER_ERROR=11`, `VALIDATION_ERROR=12`, `UNKNOWN_ERROR=127`
- CLI command main functions: wrap with `@main_with_error_handling()` decorator from `nthlayer.core.errors` (or `nthlayer_common`) for unified exit code conversion
- `exit_with_error()` stays in `nthlayer.core.errors` (not in nthlayer-common) — it imports `nthlayer.cli.ux` which is generate-only
- `nthlayer.core` (`core/__init__.py`) re-exports only a subset of tier symbols: `Tier`, `TierConfig`, `TIER_NAMES`, `VALID_TIERS`, `get_tier_config`. For the full set (`TIER_CONFIGS`, `normalize_tier`, `is_valid_tier`, `get_tier_thresholds`, `get_slo_targets`), import from `nthlayer.core.tiers` or `nthlayer_common.tiers` directly
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

### Deployment Detection (moved to nthlayer-observe — B1 ✓ done 2026-04-08)
- All deployment webhook provider code deleted from generate; now lives in nthlayer-observe
- `deployments/` directory shell remains with empty `providers/` subdir pending full cleanup in B4

### Policy Audit API (moved to nthlayer-observe — B2 ✓ done 2026-04-08)
- All runtime policy audit code deleted from generate: `policies/audit.py`, `recorder.py`, `repository.py`, `evaluator.py`, `conditions.py`, `api/routes/policies.py`
- `policies/` now contains only build-time engine (engine.py, models.py, rules.py)
- `api/main.py` no longer registers the policies router

### Optional Dependency Groups
- Install with extras for optional integrations: `pip install -e ".[aws]"`, `pip install -e ".[kubernetes]"`
- `[aws]`: boto3, aioboto3 — required for CloudWatch and SQS modules
- `[kubernetes]`: kubernetes client — required for K8s dependency discovery provider
- `[zookeeper]`: kazoo — required for Zookeeper discovery provider
- `[etcd]`: etcd3 — required for etcd discovery provider
- `[service-discovery]`: kazoo + etcd3 bundled — for all service discovery providers at once
- Core `structlog`, `httpx`, `pagerduty`, `grafana-foundation-sdk` are always installed
- Lazy import pattern: the original example (`queue/__init__.py` deferring SQS `JobEnqueuer`) was deleted in B7 with the whole queue package; the pattern itself — use `__getattr__` in `__init__.py` to delay importing optional-extra classes until they are accessed — still applies anywhere generate needs to gate on an extra
- Runtime import deferral: the original motivating example lived in `api/deps.py` (deleted in B4); the pattern itself — import optional-extra classes inside the function body so the module still loads when the extra is missing — still applies anywhere generate consumes optional extras at call time
- TYPE_CHECKING guard prevents circular imports while allowing type hints for optional classes

### Test Organization
- `tests/fixtures/` now holds only YAML demo fixtures; `tests/fixtures/mock_server.py` and the legacy `tests/mock_server.py` were deleted in B7 (fastapi-based mock stack for provider integration tests — the tests only ran against a manually-started server and had been failing for months)
- Integration tests using mock servers live in `tests/integration/` (e.g., `tests/integration/test_mock_server_integration.py`)
- CLI end-to-end smoke tests live in `tests/smoke/` — invoke the real CLI via subprocess; see "CLI Smoke Test Suite" pattern for details
- Shared pytest config (structlog suppression, fixtures) lives in `tests/conftest.py`
- Tests for optional-dependency modules use `pytest.importorskip("package")` at module level to skip when extras are not installed: `aioboto3 = pytest.importorskip("aioboto3", reason="aioboto3 is required for workers tests")`
- Apply `importorskip` to any test module that imports from `[aws]`, `[kubernetes]`, or other optional extras

### Async/Await Usage
- All provider operations are async (health checks, resource creation, discovery)
- Use `asyncio.to_thread()` for sync HTTP operations to avoid blocking event loop
- Parallel operations use `asyncio.gather()` with `return_exceptions=True`
- Provider interfaces define `async def aclose()` for cleanup

### CLI Drift Analysis (moved to nthlayer-observe in P5)
- Drift commands are now in nthlayer-observe: `nthlayer-observe drift --service <name> --prometheus-url <url>`
- `nthlayer portfolio --drift` and `nthlayer check-deploy --include-drift` flags have been removed from generate
- Use `nthlayer-observe drift` for runtime drift detection; generate has no drift module

### Ruff Lint Configuration
- Target: Python 3.11 (`target-version = "py311"`), line length: 100
- Enabled rule sets: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `B` (flake8-bugbear)
- Ignored rules: `B008` (Depends() in function defaults — standard FastAPI pattern), `E402` (module-level import not at top — needed for sys.modules mocking in tests)
- Run via: `make lint` or `ruff check src/ tests/`

### Sloppylint (sloppy) Configuration
- AI-powered code quality checker; run via `/desloppify` workflow
- Ignored paths: `tests/*`, `archive/*`, `scripts/*` (the stale `src/nthlayer/workflows/*` glob was dropped in B7 when workflows/ was physically deleted)
- Disabled checks: `debug_print` (CLI uses print() for user output), `magic_number` (handled by code review), `hallucinated_import` (false positives on relative imports), `wrong_stdlib_import` (false positives on optional deps), `dead_code` (too many false positives on class methods), `duplicate_code` (function structure similarity is not duplication), `overlong_line` (PromQL queries are intentionally long)
- Active severity threshold: `high` — only critical and high issues are reported
- CI threshold: `max-score = 500` (score above this fails the build)
<!-- /AUTO-MANAGED: discovered-conventions -->
