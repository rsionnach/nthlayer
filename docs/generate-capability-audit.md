# nthlayer-generate Capability Audit

**Date:** 2026-04-06
**Updated:** 2026-04-06 (corrected routing per `NTHLAYER-OBSERVE-SPEC.md`)
**Scope:** Complete inventory of `nthlayer/src/nthlayer/` — 296 Python source files, 46 CLI commands
**Purpose:** Classify every capability as STAYS, MOVE, SHARE, or REMOVE to restore generate as a pure, deterministic, stateless compiler. Runtime infrastructure moves to nthlayer-observe; only agentic (LLM-dependent) code goes to measure/correlate/respond/learn.

## Classification Test

For each capability:
- **"Does it need an LLM?"** — If yes, agentic component (measure/correlate/respond/learn).
- **"Does it query live infrastructure?"** — If yes, nthlayer-observe.
- **"Is it deterministic given the same manifest?"** — If yes, stays in generate.
- **"Does it do something to the world?"** — Respond.

---

## 1. Classification Table

### A. STAYS in generate (Pure Compilation / Deterministic)

| Capability | Current Location | Justification |
|---|---|---|
| Manifest parsing (legacy) | `specs/parser.py` | Pure text-to-data. Same YAML always produces same parse tree. |
| Manifest parsing (OpenSRM) | `specs/opensrm_parser.py` | Deterministic format conversion. |
| Manifest loading + auto-detect | `specs/loader.py` | Auto-detect + delegate. No runtime state. |
| Manifest model (ReliabilityManifest, SLODefinition, Ownership, Dependency, BudgetPolicy, DeploymentGates) | `specs/manifest.py` | Data model. BudgetPolicy parsing is compile-time; enforcement is gate. |
| Resource models | `specs/models.py` | Pure data structures. |
| Schema validation | `specs/validator.py` | Deterministic structural validation. |
| Alerting config model | `specs/alerting.py` | Static config model (AlertingConfig, ForDuration). |
| Contract definitions | `specs/contracts.py` | Data models. |
| Spec helpers | `specs/helpers.py` | Utility functions (infer_technology_from_name). |
| SLO YAML generation (Sloth) | `generators/sloth.py` | Manifest in, Sloth YAML out. |
| Prometheus alert rule generation | `generators/alerts.py` | Manifest in, alert YAML out. Uses awesome-prometheus-alerts templates. |
| Backstage entity generation | `generators/backstage.py` | Manifest in, Backstage JSON out. |
| Documentation generation | `generators/docs.py` | Manifest in, Markdown out. |
| Loki alert rule generation | `loki/generator.py`, `loki/models.py`, `loki/templates.py` | Manifest in, Loki rules out. |
| AlertManager config generation | `alertmanager/config.py` | Manifest in, alertmanager YAML out. |
| PagerDuty resource generation | `pagerduty/` (all files) | Generates PD config from manifest. Deterministic. |
| Grafana dashboard generation | `dashboards/` (all 18+ files) | Intent-based generation. Same manifest always produces same dashboard JSON. |
| Recording rule generation | `recording_rules/` (all files) | Manifest in, recording rules out. |
| Template system | `specs/template.py`, `specs/template_loader.py`, `specs/custom_templates.py`, `specs/builtin_templates/` | Pure template expansion. |
| Service init/scaffolding | `cli/init.py` | Creates initial manifest structure. Deterministic. |
| Environment management | `specs/environments.py`, `specs/environment_merger.py`, `specs/environment_detection.py`, `specs/environment_alerts.py`, `specs/environment_gates.py` | Environment-aware config merging. Stateless. |
| Variable substitution | `specs/variable_substitution.py` | Pure string replacement. |
| Build-time policy engine | `policies/engine.py`, `policies/rules.py`, `policies/models.py` | Validates manifests against policy rules at build time. Same input, same violations. |
| CLI formatters | `cli/formatters/` (json_fmt.py, sarif.py, junit.py, markdown.py, models.py) | Pure output formatting (JSON, SARIF, JUnit, Markdown). |
| Tier definitions | `core/tiers.py` | Static tier configuration. Also extract to common. |
| Error handling | `core/errors.py` | Error taxonomy, ExitCode enum. Also extract to common. |
| Metric recommendations (static) | `metrics/recommender.py` | Recommends metrics based on service type. No runtime query. |
| Metric templates | `metrics/templates/` (8 service type templates) | Static metric definitions per service type. |
| Metric standards | `metrics/standards/` (aliases.py, otel_semconv.py) | Static alias mappings and OTel conventions. |
| Metric models | `metrics/models.py` | Data structures only. |
| SLO calculator | `slos/calculator.py` | Pure math. Given SLO + measurements, deterministic budget output. |
| SLO ceiling validation | `slos/ceiling.py` | Manifest-only math. Validates SLO targets against upstream SLA ceilings. |
| SLO models | `slos/models.py` | Data structures (SLO, ErrorBudget, SLOStatus, TimeWindow, Incident). |
| SLO parser | `slos/parser.py` | OpenSLO YAML parsing. Deterministic. |
| Alert rule models + evaluator | `slos/alerts.py` | AlertEvaluator is pure function: given budget + rules, emit events. |
| Alert spec models | `alerts/loader.py`, `alerts/models.py`, `alerts/validator.py` | Alert rule loading and validation from specs. |
| Topology models | `topology/models.py` | Data structures (TopologyNode, TopologyEdge, TopologyGraph). |
| Topology serializers | `topology/serializers.py` | Pure format conversion (JSON, Mermaid, DOT). |
| Topology enrichment | `topology/enrichment.py` | Converts DependencyGraph to TopologyGraph. Given same graph + manifests, deterministic. |
| Orchestration engine | `orchestration/` (engine.py, handlers.py, registry.py, plan_builder.py, results.py) | Resource generation orchestration. |
| Orchestrator facade | `orchestrator.py` | Backward-compat facade for plan/apply. |
| Simulation engine | `simulate/` (engine.py, graph.py, models.py, output.py, what_if.py) | Monte Carlo simulation. Pure computation given same seed + inputs. |
| Validate commands | `cli/validate.py`, `cli/validate_metadata.py`, `cli/validate_slo.py`, `cli/validate_spec.py` | Static validation. |
| Generate commands | `cli/generate.py`, `cli/generate_alerts.py`, `cli/generate_loki.py` | Artifact generation CLI. |
| Apply command | `cli/apply.py` | Applies generated artifacts. |
| Plan command | `cli/plan.py` | Previews what would be generated. |
| Lint command | `cli/lint.py` | Static analysis via pint. |
| Migrate command | `cli/migrate.py` | Format migration tool. |
| Templates command | `cli/templates.py` | Template management. |
| Recording rules command | `cli/recording_rules.py` | Generation CLI. |
| Dashboard commands | `cli/dashboard.py`, `cli/dashboard_validate.py` | Dashboard generation + validation CLI. |
| Backstage command | `cli/backstage.py` | Generation CLI. |
| Docs command | `cli/docs.py` | Documentation generation CLI. |
| PagerDuty command | `cli/pagerduty.py` | PD config generation CLI. |
| Setup command | `cli/setup.py` | Initial setup wizard. |
| Environments commands | `cli/environments.py` | list-environments, diff-envs, validate-env CLI. |
| Simulate command | `cli/simulate.py` | Simulation CLI. |
| Alerts command | `cli/alerts.py` | Alert rule management CLI. |
| SLO command (generation portions) | `cli/slo.py` | SLO generation is pure. Live-query portions should be extracted. |
| SLO CLI helpers | `slos/cli_helpers.py` | Shared CLI utilities. |
| SLO dependencies | `slos/dependencies.py` | Static dependency tracking. |
| PromQL validation | `validation/promql.py`, `validation/promruval.py` | Static syntax validation. |
| Metadata validation | `validation/metadata.py` | Static metadata checks. |
| Config module | `config/` (all files) | Application config loading. |
| Cache | `cache.py` | In-memory cache utilities. |
| User config | `user_config.py` | User preference loading. |
| Logging | `logging.py` | Structured logging setup. |
| Tracing | `tracing.py` | OpenTelemetry tracing setup. |
| Secrets | `secrets.py` | Secret resolution. |
| CloudWatch | `cloudwatch.py` | Optional AWS metrics collector for build-time reporting. |
| UX helpers | `cli/ux.py` | Console output helpers. |
| Grafana provider | `providers/grafana.py` | Dashboard push (generate concern). |
| Provider base/CLI | `providers/base.py`, `providers/cli.py`, `providers/__main__.py` | Provider infrastructure for generate's artifact push. |

### B. MOVE to observe — Gate (Deploy-Time Decisions Using Runtime State)

Deployment gates are deterministic runtime decisions (threshold checks, freeze periods, budget math), not agentic judgment. All gate infrastructure moves to `nthlayer-observe/gate/`. See `NTHLAYER-OBSERVE-SPEC.md` for the architectural rationale.

| Capability | Current Location | Destination | Justification |
|---|---|---|---|
| Deployment gate class | `slos/gates.py` (DeploymentGate, GatePolicy, GateResult, DeploymentGateCheck) | `observe/gate/evaluator.py` | Makes go/no-go deployment decisions based on error budget state. Deterministic given same inputs — not agentic. |
| check-deploy command | `cli/deploy.py` | `observe/cli.py` as `nthlayer-observe check-deploy` | The main gate CLI. Queries Prometheus, evaluates thresholds, produces gate decisions. |
| Gate policy evaluation | `policies/evaluator.py` (ConditionEvaluator, PolicyContext) | `observe/gate/policies.py` | Runtime condition evaluation for deployment gates (business_hours, budget thresholds). |
| Gate policy conditions | `policies/conditions.py` | `observe/gate/policies.py` | Runtime helper functions (is_business_hours, is_freeze_period). |
| Policy audit trail | `policies/audit.py`, `policies/recorder.py`, `policies/repository.py` | `observe/gate/audit.py` | Runtime audit logging for deployment gate decisions. |
| FastAPI server | `api/main.py`, `api/auth.py`, `api/deps.py` | `observe/api/` | A long-running web server is not a compiler concern. Observe owns all runtime HTTP. |
| Deployment webhook routes | `api/routes/webhooks.py` | `observe/api/routes/` | Receives deployment events for correlation/gating. Runtime. |
| Policy override API | `api/routes/policies.py` | `observe/api/routes/` | Runtime policy override management. |
| Health routes | `api/routes/health.py` | `observe/api/routes/` | Liveness/readiness for the API server. |
| Teams routes | `api/routes/teams.py` | `observe/api/routes/` | Team management via API. Runtime. |
| Deployment providers | `deployments/` (base.py, errors.py, registry.py, providers/argocd.py, providers/github.py, providers/gitlab.py) | `observe/deployments/` | Webhook payload parsing for deployment detection. Runtime concern. |
| Deployment event recording | `slos/deployment.py` (DeploymentRecorder.record_event) | `observe/gate/` | Stores deployment events to database for gate correlation. |
| SLO storage/repository | `slos/storage.py` | `observe/slo/storage.py` | Used by collector, correlator, and gate. Not a generate concern. |
| Database ORM models | `db/models.py` | `observe/db/` | ORM models for runtime state (SLOs, deployments, incidents, policy audits). |
| Database session | `db/session.py` | `observe/db/` | Database session management for runtime state. |
| Database repositories | `db/repositories.py` | `observe/db/` | CRUD operations for runtime state. |
| Alembic migrations | `alembic/` | `observe/db/` | Database migration scripts for runtime state. |
| Worker handler | `workers/handler.py` | REMOVE | Long-running job processor. No consumers post-migration. |
| Queue module | `queue/memory.py`, `queue/models.py`, `queue/sqs.py` | REMOVE | Job queueing infrastructure. No consumers post-migration. |

### C. MOVE to observe — Observation (Reads Telemetry / Observes SLO State)

These capabilities are deterministic observations — same Prometheus query, same result. They do NOT belong in the agentic measure component. nthlayer-measure's Prometheus adapter exists for its LLM evaluation pipeline, not to own all observation. Post-migration, measure reads assessments from observe instead of querying Prometheus directly.

| Capability | Current Location | Destination | Justification |
|---|---|---|---|
| SLO metric collection from Prometheus | `slos/collector.py` (SLOCollector, SLOMetricCollector) | `observe/slo/collector.py` | Queries Prometheus for live SLI data. Deterministic observation, not agentic evaluation. |
| Drift detection | `drift/analyzer.py`, `drift/models.py`, `drift/patterns.py` | `observe/drift/` | Queries Prometheus for budget history and calculates trends. Deterministic math. |
| Drift command | `cli/drift.py` | `observe/cli.py` as `nthlayer-observe drift` | CLI for drift analysis. |
| Metric discovery from Prometheus | `discovery/client.py`, `discovery/classifier.py`, `discovery/models.py` | `observe/discovery/` | Queries live Prometheus for available metrics. Observation, not judgment. |
| Metric verification against Prometheus | `verification/verifier.py`, `verification/models.py`, `verification/extractor.py`, `verification/exporter_guidance.py` | `observe/verification/` | Checks declared metrics exist in live Prometheus. Observation. |
| Verify command | `cli/verify.py` | `observe/cli.py` as `nthlayer-observe verify` | CLI for metric verification. |
| Metric discovery (from metrics module) | `metrics/discovery.py` | `observe/discovery/` | Queries live system for metric information. |
| Portfolio aggregation (live portions) | `portfolio/aggregator.py` (live Prometheus enrichment) | `observe/portfolio/` | Queries Prometheus to enrich service health data. Static portfolio scan stays. |
| Portfolio command (live portions) | `cli/portfolio.py` (live metric enrichment, drift integration) | `observe/cli.py` | Static scan stays; live enrichment moves. |
| Scorecard (live portions) | `scorecard/calculator.py` (prometheus_url, incident_source, deployment_source inputs) | `observe/portfolio/scorecard.py` | Pure score math stays; live data inputs move. |
| Scorecard command | `cli/scorecard.py` | `observe/cli.py` | Same split as calculator. |
| Recommend-metrics command (live portions) | `cli/recommend_metrics.py` (Prometheus discovery) | `observe/cli.py` | Static recommendations stay; live metric discovery moves. |

### D. MOVE to observe — Infrastructure Discovery (Live State, Not Reasoning)

Live dependency discovery (querying K8s, Consul, Prometheus for service graphs) is observation. The 5-factor weighted deployment correlator is a deterministic heuristic, not LLM reasoning. nthlayer-correlate's LLM-powered causal reasoning consumes these as inputs and adds its own judgment layer.

| Capability | Current Location | Destination | Justification |
|---|---|---|---|
| Deployment correlator | `slos/correlator.py` (DeploymentCorrelator) | `observe/gate/correlator.py` | 5-factor weighted scoring is a deterministic heuristic. Same inputs, same score. Not LLM reasoning — nthlayer-correlate adds the judgment layer on top. |
| Live dependency discovery | `dependencies/discovery.py`, `dependencies/providers/` (kubernetes.py, prometheus.py, consul.py, etcd.py, zookeeper.py, backstage.py) | `observe/dependencies/` | Queries live systems for dependency relationships. Infrastructure observation, not causal reasoning. |
| Blast radius calculation | `cli/blast_radius.py` | `observe/cli.py` as `nthlayer-observe blast-radius` | Calculates downstream impact from live dependency graph. Deterministic graph traversal. |
| Dependencies command | `cli/dependencies.py`, `cli/deps.py` | `observe/cli.py` as `nthlayer-observe dependencies` | CLI for live dependency discovery. |
| Topology export command (live portions) | `cli/topology.py` (with `--prometheus-url`) | `observe/cli.py` | Static topology export from manifest stays in generate; live discovery moves. |

### E. MOVE to respond (Actions / Notifications)

| Capability | Current Location | Justification |
|---|---|---|
| Slack notifier | `slos/notifiers.py` (SlackNotifier) | Sends messages to Slack. This does something to the world. nthlayer-respond already has `notifications.py`. |
| PagerDuty notifier | `slos/notifiers.py` (PagerDutyNotifier) | Triggers PagerDuty pages. nthlayer-respond already has notification capabilities. |
| Alert notifier orchestrator | `slos/notifiers.py` (AlertNotifier) | Routes alerts to notification channels. |
| Explanation engine | `slos/explanations.py` | Generates human-readable alert context for responders. nthlayer-respond's communication agent needs this. |
| Alert pipeline (notification dispatch) | `slos/pipeline.py` (_dispatch_notifications portion) | The evaluate_service() core is pure and stays; the notification dispatch moves. |

### F. MOVE to learn (Feedback / Historical)

| Capability | Current Location | Justification |
|---|---|---|
| Scorecard trends | `scorecard/trends.py` | Historical trend tracking of reliability scores. Feedback loop. |

### G. SHARE via nthlayer-common (Used by Multiple Components)

| Capability | Current Location | Justification |
|---|---|---|
| Prometheus HTTP client | `providers/prometheus.py`, `clients/prometheus.py` | Prometheus query wrapper used by measure, correlate, gate, and generate. |
| HTTP client base | `clients/base.py` | Generic HTTP client used across components. |
| PagerDuty client | `clients/pagerduty.py`, `providers/pagerduty.py` | Shared PD interaction. |
| Slack client | `clients/slack.py` | Shared Slack client (nthlayer-common already has SlackNotifier). |
| Cortex/Mimir client | `clients/cortex.py`, `providers/mimir.py` | Shared telemetry backend. |
| Provider registry/lock | `providers/registry.py`, `providers/lock.py` | Provider infrastructure used by multiple components. |
| Identity module | `identity/normalizer.py`, `identity/resolver.py`, `identity/models.py` | Service name normalization needed by correlate, measure, and generate. |
| Ownership providers (live) | `identity/ownership_providers/kubernetes.py`, `identity/ownership_providers/backstage.py`, `identity/ownership_providers/pagerduty.py` | Live system queries for ownership resolution. (Declared/codeowners stay in generate.) |
| Dependency models | `dependencies/models.py` | DependencyGraph, DependencyEdge used by correlate and generate's topology. |
| Domain models | `domain/models.py` | Pydantic models (Run, Finding, Team, Service). |
| PagerDuty integration client | `integrations/pagerduty.py` | PD service/team creation used at runtime. |

### H. REMOVE (Deprecated / Superseded)

| Capability | Current Location | Justification |
|---|---|---|
| Deprecated deployment methods | `slos/deployment.py` (record_from_argocd, record_from_github) | Explicitly deprecated. Provider-based record_event() supersedes. |
| LangGraph team workflow | `workflows/team_reconcile.py` | LLM workflow for team reconciliation. Not compilation. No current consumers. |
| Demo entry point | `demo.py` | Legacy demo code. |

---

## 2. Migration Risk Assessment

### High Risk (Complex interdependencies, multiple consumers)

1. **`slos/collector.py` to observe** — Imported by `cli/deploy.py` (gate), `portfolio/aggregator.py`, and `scorecard/calculator.py`. Moving requires untangling SLOMetricCollector from the gate check flow. The async SLOCollector class drags `slos/storage.py` and `db/` along. Mitigated by the fact that all three consumers also move to observe.

2. **`slos/gates.py` + `cli/deploy.py` to observe** — The check-deploy command is the most user-facing capability today. DeploymentGate imports from `policies/evaluator.py`, `policies/recorder.py`, `slos/correlator.py`, and `slos/collector.py`. Highest fan-out migration — but all dependencies also move to observe, which simplifies the cut significantly vs. the original multi-destination plan.

3. **`api/` (entire FastAPI server) to observe** — The webhook receiver, policy override endpoint, and health checks form a coherent runtime application. Moving requires extracting the full server along with `db/`, `deployments/`, and `policies/` runtime modules. Architecturally the clearest move — a compiler should not host a long-running web server.

4. **`db/` (database layer) to observe + common** — SQLAlchemy models, session management, and repositories underpin collector, correlator, gates, deployment recording, and policy audit. All consumers move to observe, so the db layer moves as a unit. Shared data structures (SLO, ErrorBudget) go to common.

5. **`dependencies/` (live discovery) to observe** — DependencyDiscovery orchestrator and 6 providers query K8s, Prometheus, Consul, etcd, Zookeeper, and Backstage. Topology enrichment in generate consumes the dependency graph, so a clean interface must be maintained (generate imports models from common, observe owns live discovery).

### Quick Wins (Low interdependency, clear boundaries)

1. **`slos/notifiers.py` to respond** — Slack and PagerDuty notifiers have exactly one consumer: `slos/pipeline.py`'s `_dispatch_notifications()`. Remove the call, move the module. nthlayer-respond already has `notifications.py`.

2. **`slos/explanations.py` to respond** — ExplanationEngine consumed by pipeline.py and notifiers.py. Moving it alongside notifiers is clean.

3. **`drift/` to observe** — Self-contained module. Only consumers are `cli/deploy.py` (optional flag) and `cli/portfolio.py`. Both also move to observe.

4. **`verification/` to observe** — Self-contained Prometheus metric verifier. Only consumer is `cli/verify.py`. Clean cut.

5. **`discovery/` to observe** — Self-contained Prometheus metric discovery client. Only consumer is dashboard MetricResolver, which can accept pre-discovered metrics.

6. **`slos/correlator.py` to observe** — Only consumed by `cli/deploy.py` (optional `--include-correlation` flag). Deterministic 5-factor heuristic — not LLM reasoning. Moves alongside the gate infrastructure it serves.

7. **Deprecated methods in `slos/deployment.py`** — Already deprecated with warnings. Trivial removal.

8. **`workflows/team_reconcile.py`** — No current consumers. Remove.

9. **`demo.py`** — Legacy. Remove.

10. **`workers/handler.py`**, **`queue/`** — No consumers post-migration. Remove.

### Shared Utilities (Extract to nthlayer-common)

1. **`core/tiers.py`** — TIER_CONFIGS used by gates, pipeline, drift analysis. Shared across generate, observe, measure.
2. **`core/errors.py`** — ExitCode, error taxonomy. Used everywhere.
3. **`identity/`** — Service name normalization needed across ecosystem.
4. **`providers/prometheus.py`** — Prometheus query wrapper. Primary consumer: observe. Also used by measure and correlate directly (for now).
5. **`dependencies/models.py`** — DependencyGraph, ServiceIdentity. Used by topology (generate), discovery (observe), correlator (observe).
6. **`clients/`** — HTTP client wrappers. Used by providers, notifiers.
7. **`slos/models.py`** — SLO, ErrorBudget data structures shared across observe, measure, generate.

---

## 3. Recommended Migration Order

See `NTHLAYER-OBSERVE-SPEC.md` for the full architectural rationale and `Assessment` dataclass definition.

### Phase 0: Extract Shared Utilities to nthlayer-common

Extract first so all subsequent moves can import from common:
- `core/tiers.py`
- `core/errors.py`
- `slos/models.py` (data structures only)
- `dependencies/models.py`
- `identity/` (normalizer, resolver, models)
- `providers/prometheus.py` + `clients/prometheus.py`
- `clients/base.py`

### Phase 1: Quick Wins

Low-risk moves with clear boundaries:
- `slos/notifiers.py` -> nthlayer-respond
- `slos/explanations.py` -> nthlayer-respond
- Remove deprecated methods from `slos/deployment.py`
- Remove `demo.py`, `workflows/team_reconcile.py`
- Remove `workers/handler.py`, `queue/` (no consumers post-migration)

### Phase 2: Create nthlayer-observe with SLO Collection

Create the new component and move the first real capability:
- Create `nthlayer-observe` package structure (see `NTHLAYER-OBSERVE-SPEC.md` Phase 0)
- Create `Assessment` dataclass + assessment store
- `slos/collector.py` -> `observe/slo/collector.py`
- `slos/storage.py` -> `observe/slo/storage.py`
- Create CLI: `nthlayer-observe collect --specs-dir ./specs/ --prometheus-url http://localhost:9090`
- Wire assessment output so nthlayer-measure can consume it

### Phase 3: Move Drift, Verification, Discovery to Observe

Self-contained observation modules:
- `drift/` -> `observe/drift/`
- `verification/` -> `observe/verification/`
- `discovery/` -> `observe/discovery/`
- `dependencies/discovery.py` + `dependencies/providers/` -> `observe/dependencies/`
- `cli/blast_radius.py` -> observe CLI
- `cli/dependencies.py` -> observe CLI
- Create CLI commands: `nthlayer-observe verify`, `nthlayer-observe discover`, `nthlayer-observe drift`, `nthlayer-observe blast-radius`, `nthlayer-observe dependencies`

### Phase 4: Move Gate Infrastructure to Observe

The largest move — all gate infrastructure into observe:
- `slos/gates.py` -> `observe/gate/evaluator.py`
- `cli/deploy.py` -> `observe/cli.py` as `nthlayer-observe check-deploy`
- `policies/evaluator.py`, `policies/conditions.py` -> `observe/gate/policies.py`
- `policies/audit.py`, `policies/recorder.py`, `policies/repository.py` -> `observe/gate/audit.py`
- `slos/correlator.py` -> `observe/gate/correlator.py`
- `api/` (entire FastAPI server) -> `observe/api/`
- `deployments/` -> `observe/deployments/`
- `db/` -> `observe/db/` (runtime models and session)
- `slos/deployment.py` -> `observe/gate/`

### Phase 5: Cleanup Generate + Update Agentic Consumers

- Remove all moved source files from generate
- Update all import paths
- Remove runtime dependencies from generate's `pyproject.toml` (FastAPI, SQLAlchemy, etc.)
- Update nthlayer-measure to consume assessments from observe (new input path)
- Update nthlayer-correlate to consume dependency assessments from observe
- Run full test suite (4,419 tests)
- Update CLAUDE.md documentation (add nthlayer-observe to ecosystem)
- Verify: generate has no Prometheus imports, observe has no LLM imports

---

## 4. Summary Statistics

| Classification | File Count (approx) | % of Codebase |
|---|---|---|
| STAYS in generate | ~175 | 59% |
| MOVE to observe | ~85 | 28% |
| MOVE to respond | ~5 | 2% |
| MOVE to learn | ~1 | <1% |
| SHARE via common | ~20 | 7% |
| REMOVE | ~10 | 3% |

**The core finding:** nthlayer-generate is 59% compiler and 41% runtime system. The migration restores it to a pure compiler by moving all runtime infrastructure to nthlayer-observe — a deterministic, non-agentic component that reads live state and produces structured assessments. The agentic components (measure, correlate, respond, learn) remain thin LLM reasoning layers that consume assessments as input. No code moves to measure or correlate — they gain a new input interface (assessments) instead.
