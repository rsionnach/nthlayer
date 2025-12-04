# NthLayer

NthLayer is the "missing layer of reliability" - an automation platform that generates the complete observability and reliability stack from declarative service definitions. The goal is "20 hours of SRE work in 5 minutes" with zero toil.

## Product Vision & Scope

**Core Value Proposition:** "Generate the complete reliability stack from a service spec in 5 minutes"

### The Three Layers

```
                    ┌─────────────────────────────────┐
                    │     Git: services/*.yaml        │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │       NthLayer Platform         │
                    └───┬───────────┬───────────┬─────┘
                        │           │           │
            ┌───────────▼───┐ ┌─────▼─────┐ ┌───▼───────────┐
            │   ResLayer    │ │ GovLayer  │ │ ObserveLayer  │
            │ Error Budgets │ │  Policy   │ │  Monitoring   │
            │    & SLOs     │ │Enforcement│ │  Automation   │
            └───────┬───────┘ └─────┬─────┘ └───────┬───────┘
                    │               │               │
            ┌───────▼───────────────▼───────────────▼───────┐
            │  Prometheus │ Grafana │ PagerDuty │ Datadog   │
            └───────────────────────────────────────────────┘
```

### Usage Modes

| Mode | Description | Catalog Required? |
|------|-------------|-------------------|
| **Standalone** | Git + YAML, no catalog | ❌ No - Start here |
| **With Catalog** | Sync metadata from Backstage/Cortex | Optional |
| **Hybrid** | Catalog + local overrides | Optional |

**Key differentiator:** Catalogs make you adopt their platform first. NthLayer works Day 1.

### What We Generate

| Domain | Output | Status |
|--------|--------|--------|
| **Dashboards** | Grafana dashboards, Datadog dashboards | ✅ Grafana done, 📋 Datadog planned |
| **Alerts** | Prometheus rules, Datadog monitors | ✅ Prometheus done, 📋 Datadog planned |
| **Recording Rules** | Pre-aggregated metrics | ✅ Complete |
| **PagerDuty** | Teams, schedules, escalation policies | ✅ Complete |
| **SLOs** | OpenSLO definitions, error budgets | 🔨 ResLayer Phase 1 |
| **Deployment Gates** | ArgoCD blocking, CI/CD integration | 📋 ResLayer Phase 2 |
| **Policies** | Resource limits, deployment rules | 📋 GovLayer |
| **Runbooks** | Auto-generated troubleshooting guides | 📋 ObserveLayer |

## Roadmap

### Strategic Differentiation
**Compete where PagerDuty/Datadog won't go:**
- Cross-vendor SLO Portfolio (they want lock-in)
- AI-assisted config generation (they do incident response, not setup)

**Don't compete with:**
- Incident pattern learning (PagerDuty Insights)
- Automated incident response (PagerDuty SRE Agent)

### Phase 1: Foundation (✅ DONE)
- service.yaml spec and parser
- Grafana dashboard generation
- Prometheus alert generation
- PagerDuty integration
- pint PromQL linting

### Phase 2: Error Budgets (✅ DONE)
- `nthlayer slo show/list` - View SLOs from service.yaml
- `nthlayer slo collect` - Real-time Prometheus queries (stateless)
- Blame deferred until CI/CD integration

### Phase 2.5: Loki Integration (📋 PLANNED)
**Goal:** Complete observability with logs (same Grafana ecosystem)
- `trellis-loki-epic`: Loki/LogQL integration
- `trellis-loki-alerts`: Generate LogQL alert rules from service.yaml
- `trellis-loki-templates`: Technology-specific log patterns (PostgreSQL, Redis, Kafka)

### Phase 3: SLO Portfolio (🔨 NEXT - Differentiator)
**Goal:** Cross-vendor, org-wide reliability portfolio
- `trellis-portfolio-epic`: SLO Portfolio epic
- `trellis-portfolio-aggregate`: `nthlayer portfolio` command
- `trellis-portfolio-health`: Health scoring by tier
- `trellis-portfolio-insights`: Actionable reliability insights
- `trellis-portfolio-trends`: Local SQLite for historical data
- `trellis-portfolio-web`: Local web dashboard
- `trellis-portfolio-export`: JSON/CSV export for reporting

### Phase 4: AI-Assisted Generation
**Goal:** Conversational service.yaml creation (complements, doesn't compete with PD)
- `trellis-ai-epic`: AI/MCP strategy
- `trellis-mcp-server`: NthLayer as MCP tool for Claude/Cursor
- `trellis-ai-spec-gen`: "Create a tier-1 API with Redis" → YAML
- `trellis-ai-slo`: SLO target recommendations
- `trellis-ai-suggestions`: Best practice recommendations

### Phase 5: Deployment Gates (ResLayer Phase 2)
**Goal:** Deploy blocked when error budget < 10%
- `trellis-tnr`: Policy YAML DSL
- `trellis-a4d`: Condition evaluator
- `trellis-0fl`: ArgoCD blocking
- Requires CI/CD integration: ArgoCD, GitHub Actions, Tekton, GitLab CI

### Phase 6: NthLayer Cloud (Future - Monetization)
- Hosted portfolio dashboard
- Multi-user / team views
- Alerting on portfolio health
- Enterprise features

### Technology Templates (Ongoing)
- `trellis-0cd`: Kafka (consumer lag, partitions, replication)
- `trellis-e8w`: MongoDB (connections, replication, locks)
- `trellis-ai-services`: AI/ML service type (GPU utilization, model latency, inference queue)

## Core Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
make test                    # All tests
pytest tests/test_X.py -v    # Single test file
pytest -k "test_name" -v     # Single test by name

# Linting and type checking
make lint                    # Run ruff linter
make lint-fix                # Auto-fix lint issues
make typecheck               # Run mypy
make format                  # Format code with ruff

# Development environment
make dev-up                  # Start Postgres + Redis in Docker
make dev-down                # Stop Docker services
make migrate                 # Run database migrations

# Demo commands
python -m nthlayer.demo --help           # CLI help
python regenerate_hybrid_dashboards.py   # Regenerate all dashboards
python scripts/validate_dashboard_metrics.py  # Validate metric coverage
```

## Project Layout

```
src/nthlayer/
├── cli/           → CLI commands (plan, apply, status)
├── dashboards/    → Dashboard generation (hybrid model, intent templates)
│   ├── builder_sdk.py      → Main SDK-based dashboard builder
│   ├── resolver.py         → Metric resolution (intent → discovered metrics)
│   ├── intents.py          → Intent definitions with candidate metrics
│   └── templates/          → Technology-specific templates
│       ├── base_intent.py          → Base class for intent templates
│       ├── http_intent.py          → API service health panels
│       ├── worker_intent.py        → Worker service panels
│       ├── stream_intent.py        → Stream processing panels
│       ├── postgresql_intent.py    → PostgreSQL dependency panels
│       ├── redis_intent.py         → Redis dependency panels
│       └── elasticsearch_intent.py → Elasticsearch dependency panels
├── discovery/     → Live Prometheus metric discovery
├── slos/          → SLO definitions and error budget tracking
├── alerts/        → Alert rule generation
├── specs/         → Service specification models (ServiceContext, Resource)
├── recording_rules/ → Prometheus recording rule generation
├── orchestrator.py  → Unified plan/apply workflow
└── demo.py        → CLI entrypoint (60KB, comprehensive demo)

tests/             → pytest test suite (28+ test files)
demo/fly-app/      → Live demo app deployed to Fly.io
generated/         → Output directory for generated dashboards
docs/              → GitHub Pages demo site
scripts/           → Utility scripts (validation, migration)
.beads/            → Issue tracking (beads format)
```

## Development Patterns & Constraints

### Dashboard Generation (Hybrid Model)
- **Intent-based templates**: Define what metrics SHOULD exist, resolve to what DOES exist
- **Service types**: `api`, `worker`, `stream` - each has different health metrics
- **Row organization**: Dashboards organized into "SLO Metrics" → "Service Health" → "Dependencies"
- **Guidance panels**: Show "No Data - Check metric instrumentation" for missing metrics

### Status Label Conventions (CRITICAL)
| Service Type | Success Pattern | Error Pattern |
|--------------|-----------------|---------------|
| API          | `status!~"5.."` | `status=~"5.."` |
| Worker       | `status!="failed"` | `status="failed"` |
| Stream       | `status!="error"` | `status="error"` |

### PromQL Query Patterns
- Always use `service="$service"` label selector (NOT `cluster` or other labels)
- histogram_quantile MUST include `sum by (le)`:
  ```promql
  histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m])))
  ```
- Rate queries should aggregate: `sum(rate(metric{service="$service"}[5m]))`

### Coding Style
- Python 3.9+ with type hints
- Pydantic models for data validation
- Use `structlog` for logging
- Prefer composition over inheritance
- Tests first when fixing bugs

### External Service SDKs (CRITICAL)
Always use official SDKs/clients for external service integrations. Do not create bespoke HTTP clients when official libraries exist.

| Service | Official SDK | Package |
|---------|--------------|---------|
| **PagerDuty** | `pagerduty` | `pagerduty>=6.0.0` |
| **Grafana** | `grafana-foundation-sdk` | `grafana-foundation-sdk>=0.0.11` |
| **AWS** | `boto3` / `aioboto3` | `boto3>=1.34.0` |
| **Slack** | `slack_sdk` | (add when needed) |

When integrating a new external service:
1. Research if an official SDK exists
2. If yes, add to `pyproject.toml` and use it
3. If no official SDK, check for well-maintained community libraries
4. Only create custom HTTP clients as a last resort

### Technology Templates
When adding a new database/cache template:
1. Create `src/nthlayer/dashboards/templates/{tech}_intent.py`
2. Extend `BaseIntentTemplate`
3. Add intent definitions to `src/nthlayer/dashboards/intents.py`
4. Register in `src/nthlayer/dashboards/templates/__init__.py`
5. Add test cases to `tests/test_hybrid_dashboard_builder.py`

## Git Workflow

1. Branch from `safeharbor` (current development branch)
2. Run `make lint && make typecheck && make test` before committing
3. Commit messages: `<type>: <description>` (e.g., `fix: Add sum by (le) to histogram queries`)
4. Update `.beads/issues.jsonl` when completing tasks

## Testing Requirements

Before completing any task:
1. Run `make test` - all tests must pass
2. Run `make lint` - no linting errors
3. Run `make typecheck` - no type errors
4. For dashboard changes: run `python scripts/validate_dashboard_metrics.py`

### Test Patterns
```python
# Use pytest fixtures for common setup
# Mock external services (Grafana, Prometheus) with respx
# Test intent resolution with known metric sets
# Validate PromQL query syntax in tests
```

## External Services

| Service | Purpose | Config |
|---------|---------|--------|
| Grafana Cloud | Dashboard hosting | `NTHLAYER_GRAFANA_URL`, `NTHLAYER_GRAFANA_API_KEY` |
| Fly.io | Demo app hosting | `https://nthlayer-demo.fly.dev` |
| Prometheus | Metric discovery | Via Grafana Cloud or direct |

## Current Focus Areas

Check `.beads/issues.jsonl` for the latest priorities. Key epics:

| Epic | Description | Key Issues |
|------|-------------|------------|
| **Error Budget Foundation** | SLO tracking, burn rates, budget alerts | `trellis-3h6` |
| **Deployment Policies & Gates** | Block deploys when error budget exhausted | `trellis-3e6` |
| **Intelligent Alerts** | Smart alerting with explanations | `trellis-tt3` |
| **Observability Expansion** | APM, tracing, log aggregation | `trellis-7pw` |
| **Compliance & Governance** | SOC2, GDPR, audit logging | `trellis-gmi` |

### Technology Templates to Add
- `trellis-0cd`: Kafka
- `trellis-e8w`: MongoDB
- `trellis-ys8`: RabbitMQ
- `trellis-uum`: Elasticsearch (✅ done)

## Gotchas

1. **Row panels in Grafana**: For expanded rows, panels must be at root level (not nested in row). Use `dash.with_row(row)` then `dash.with_panel(panel)`.

2. **Metric resolution cache**: Clear `resolver._resolution_cache` between services when regenerating multiple dashboards.

3. **Intent candidates**: When metrics aren't resolving, check `intents.py` for missing candidate metric names.

4. **Grafana SDK quirk**: `Row().with_panel()` sets `collapsed=True` automatically. Don't nest panels if you want expanded rows.

5. **Demo app metrics**: Intentionally missing metrics (`redis_db_keys` from notification-worker, `elasticsearch_jvm_memory_*` from search-api) to demonstrate guidance panels.

## Evidence Required for PRs

- All tests pass (`make test`)
- Lint clean (`make lint`)
- Type check passes (`make typecheck`)
- For dashboard changes: validation script shows 100% coverage or explains gaps
- Beads issue updated if applicable
