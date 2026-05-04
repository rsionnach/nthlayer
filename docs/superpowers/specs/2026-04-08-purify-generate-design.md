# Purify Generate: Remove Runtime Infrastructure

## Context

The observe migration (Phases 0-5) is complete. Code was **copied** to observe — generate's runtime files are untouched. This epic removes every remaining runtime module from generate so it becomes a pure compiler: parse manifests, validate schemas, generate artifacts. Nothing else.

**End state:** Zero SQLAlchemy, zero FastAPI, zero alembic, zero runtime policy evaluation, zero Prometheus queries for live gate enforcement, zero webhook handling.

## Audit: Files to Remove

### 1. Database Layer (`db/`) — 410 lines

| File | What It Does | Consumers |
|------|-------------|-----------|
| `db/__init__.py` | Re-exports repositories, session | api/deps, api/main |
| `db/models.py` | SQLAlchemy ORM: 11 tables (Run, Finding, SLO, ErrorBudget, Deployment, Incident, PolicyEvaluation, PolicyViolation, PolicyOverride, SLOHistory, IdempotencyKey) | slos/storage, slos/cli_helpers, policies/repository, api/routes/teams |
| `db/session.py` | AsyncEngine factory, get_session() dependency | api/deps, api/main, slos/cli_helpers |
| `db/repositories.py` | RunRepository: async CRUD for jobs/findings | api/routes/teams |

**Observe replacement:** `SQLiteAssessmentStore` (different model — assessments, not ORM). Stubs at `nthlayer_observe/db/`.
**What breaks:** Everything that persists to PostgreSQL. All consumers must be removed first.

### 2. FastAPI Server (`api/`) — 670 lines

| File | What It Does | Consumers |
|------|-------------|-----------|
| `api/__init__.py` | Exports `create_app` | tests only |
| `api/main.py` | App factory, CORS, route registration, Mangum Lambda handler | tests only |
| `api/auth.py` | JWT/Cognito RS256 validation, `get_current_user` dependency | tests only |
| `api/deps.py` | Session + job enqueuer dependencies | tests only |
| `api/routes/health.py` | `/health` + `/ready` with DB/Redis checks | tests only |
| `api/routes/teams.py` | `POST /teams/reconcile`, `GET /jobs/{job_id}` | tests only |
| `api/routes/webhooks.py` | `POST /webhooks/deployments/{provider}` — webhook receiver | tests only |
| `api/routes/policies.py` | `POST /policies/{service}/override`, `GET /policies/{service}/audit` | tests only |

**Key finding:** No source code outside `api/` imports from `api/`. Only tests import it. This is the cleanest module to delete.
**Observe replacement:** Stubs at `nthlayer_observe/api/`.

### 3. Deployment Webhooks (`deployments/`) — 301 lines

| File | What It Does | Consumers |
|------|-------------|-----------|
| `deployments/__init__.py` | Exports base, registry, errors | api/routes/webhooks |
| `deployments/base.py` | `BaseDeploymentProvider` ABC, `DeploymentEvent` dataclass | api/routes/webhooks, slos/deployment (TYPE_CHECKING) |
| `deployments/errors.py` | `DeploymentProviderError` | api/routes/webhooks |
| `deployments/registry.py` | Provider registry (dict-based) | api/routes/webhooks |
| `deployments/providers/argocd.py` | ArgoCD webhook parser | tests only |
| `deployments/providers/github.py` | GitHub Actions webhook parser | tests only |
| `deployments/providers/gitlab.py` | GitLab CI/CD webhook parser | tests only |

**Consumers:** Only `api/routes/webhooks.py` and `slos/deployment.py` (TYPE_CHECKING guard).
**Observe replacement:** Stubs at `nthlayer_observe/deployments/`.

### 4. SLO Runtime Files — ~800 lines

| File | What It Does | Consumers | Observe Replacement |
|------|-------------|-----------|---------------------|
| `slos/gates.py` | `DeploymentGate` class — error budget gate enforcement | cli/deploy, generators/backstage, policies/recorder, 7+ test files | `nthlayer_observe/gate/evaluator.py::check_deploy()` |
| `slos/correlator.py` | `DeploymentCorrelator` — 5-factor weighted scoring | slos/gates, cli/deploy, tests | `nthlayer_observe/gate/correlator.py::correlate()` |
| `slos/collector.py` | `SLOCollector` (stateful DB), `SLOMetricCollector` (stateless CLI) | cli/deploy, slos/__init__, tests | `nthlayer_observe/slo/collector.py` |
| `slos/storage.py` | `SLORepository` — async CRUD for SLOs, budgets, deployments, incidents | slos/deployment, slos/correlator, slos/collector, api/routes/webhooks, slos/cli_helpers | `nthlayer_observe/sqlite_store.py::SQLiteAssessmentStore` |
| `slos/deployment.py` | `DeploymentRecorder` — stores deployment events for correlation | api/routes/webhooks, slos/__init__, tests | `nthlayer_observe/gate/evaluator.py` (assessments) |
| `slos/cli_helpers.py` | Async DB session helpers for CLI, SLO persistence | no external consumers | N/A — purely runtime |

**What stays in slos/:** `models.py` (re-export shim), `parser.py`, `calculator.py`, `ceiling.py`, `alerts.py`, `pipeline.py`, `__init__.py` (updated to remove runtime exports).

### 5. Runtime Policy Infrastructure — ~400 lines

| File | What It Does | Consumers | Observe Replacement |
|------|-------------|-----------|---------------------|
| `policies/evaluator.py` | `ConditionEvaluator`, `PolicyContext` — runtime DSL evaluation | slos/gates (lazy import), tests | `nthlayer_observe/gate/policies.py` |
| `policies/conditions.py` | `is_business_hours`, `is_weekday`, `is_freeze_period`, `is_peak_traffic` | policies/evaluator | `nthlayer_observe/gate/conditions.py` |
| `policies/audit.py` | `PolicyEvaluation`, `PolicyViolation`, `PolicyOverride` domain models | policies/recorder, policies/repository, tests | Replaced by Assessment dataclass |
| `policies/recorder.py` | `PolicyAuditRecorder` — fail-open audit trail writer | slos/gates, api/routes/policies, cli/deploy | `AssessmentStore.put()` |
| `policies/repository.py` | `PolicyAuditRepository` — audit query interface | slos/gates, api/routes/policies, cli/deploy | `AssessmentStore.query()` |

**What stays in policies/:** `engine.py` (build-time PolicyEngine), `models.py` (build-time PolicyRule, PolicyReport), `rules.py` (RULE_EVALUATORS registry), `__init__.py` (updated).

### 6. CLI Commands to Remove

| CLI File | Command | Replacement |
|----------|---------|-------------|
| `cli/deploy.py` | `nthlayer check-deploy` | `nthlayer-observe check-deploy` |
| `cli/portfolio.py` | `nthlayer portfolio` | `nthlayer-observe portfolio` |
| `cli/scorecard.py` | `nthlayer scorecard` | `nthlayer-observe scorecard` |

### 7. Generator Cross-Boundary Fix

**`generators/backstage.py`** imports `DeploymentGate` to call `get_threshold_for_tier()` for static threshold lookup. Fix: use `TIER_CONFIGS` from `nthlayer_common.tiers` directly (already extracted in P0). No runtime code needed.

### 8. pyproject.toml Deps to Remove

| Dependency | Reason |
|-----------|--------|
| `fastapi` | Only used by api/ |
| `uvicorn[standard]` | Only used by api/ |
| `mangum` | Only used by api/ (Lambda handler) |
| `sqlalchemy` | Only used by db/ |
| `alembic` | Only used by db/ migrations |
| `psycopg[binary]` | Only used by db/ (PostgreSQL driver) |
| `redis` | Only used by api/routes/health (readiness check) |
| `aws-xray-sdk` | Only used by api/ middleware |
| `PyJWT[crypto]` | Only used by api/auth |
| `jwcrypto` | Only used by api/auth |

**Check before removing:** `circuitbreaker`, `tenacity`, `orjson` — may have other consumers.

## Dependency Chain

```
                    ┌─────────────┐
                    │  cli/deploy │ ← B3
                    └──┬──┬──┬───┘
                       │  │  │
          ┌────────────┘  │  └────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌────────────┐   ┌──────────────┐
    │slos/gates│   │slos/collect│   │slos/correlator│ ← B3
    └──┬──┬────┘   └────────────┘   └──────┬───────┘
       │  │                                │
       │  └───────────┐                    │
       ▼              ▼                    ▼
┌───────────────┐ ┌───────────────┐ ┌────────────┐
│policies/eval  │ │policies/record│ │slos/storage │ ← B2, B3
│policies/conds │ │policies/repo  │ └──────┬─────┘
└───────────────┘ │policies/audit │        │
       ← B2      └───────┬───────┘        │
                          │                │
                          ▼                ▼
                    ┌─────────────────────────┐
                    │         db/             │ ← B5
                    └─────────────────────────┘

    ┌───────────────┐       ┌──────────────────┐
    │api/ (all routes)│ ←B4 │deployments/ (all)│ ← B1
    └───────┬───────┘       └──────┬───────────┘
            │                      │
            └──────────┬───────────┘
                       ▼
              ┌────────────────┐
              │slos/deployment │ ← B1
              └────────┬───────┘
                       ▼
                 ┌──────────┐
                 │slos/store│ ← B3
                 └──────────┘
```

**Removal order (leaf-first):**
1. B1 + B2 (independent leaves, no prerequisites)
2. B3 (depends on B1 + B2)
3. B4 (depends on B1 + B2 + B3)
4. B5 (depends on B3 + B4)
5. B6 (depends on B3 — backstage fix + portfolio/scorecard removal)
6. B7 (depends on all above)

## Bead Breakdown

### B1: Remove Deployment Webhooks

**Delete:**
- `src/nthlayer/deployments/` (entire directory)
- `src/nthlayer/slos/deployment.py`
- `tests/test_deployment_providers.py`
- `tests/test_slo_deployment.py`

**Update:**
- `slos/__init__.py` — remove `Deployment`, `DeploymentRecorder` exports
- `api/routes/webhooks.py` — will be deleted in B4, but if running B1 standalone: remove deployments imports (or just delete the route file and update api/main.py)

**User guidance:** "Webhook handling moves to nthlayer-observe when implemented."

### B2: Remove Runtime Policy Infrastructure

**Delete:**
- `src/nthlayer/policies/evaluator.py`
- `src/nthlayer/policies/conditions.py`
- `src/nthlayer/policies/audit.py`
- `src/nthlayer/policies/recorder.py`
- `src/nthlayer/policies/repository.py`
- `tests/test_policies_evaluator.py`
- `tests/test_policy_audit.py`

**Update:**
- `policies/__init__.py` — remove runtime exports; keep build-time engine/models/rules
- `slos/gates.py` — remove lazy imports of PolicyAuditRecorder, PolicyAuditRepository, ConditionEvaluator, PolicyContext. The `check_deployment_with_audit()` method and `_evaluate_custom_policies()` method will break — that's OK because gates.py is deleted in B3. For B2 to pass tests independently: either (a) make the broken methods raise NotImplementedError, or (b) delete the methods and fix test_gates.py to not call them. Prefer (b).

**What stays:** `policies/engine.py`, `policies/models.py`, `policies/rules.py` (all build-time).

**User guidance:** "Runtime policy audit now in nthlayer-observe gate/."

### B3: Remove check-deploy + SLO Runtime

**Delete:**
- `src/nthlayer/cli/deploy.py`
- `src/nthlayer/slos/gates.py`
- `src/nthlayer/slos/correlator.py`
- `src/nthlayer/slos/collector.py`
- `src/nthlayer/slos/storage.py`
- `src/nthlayer/slos/cli_helpers.py`
- `tests/test_gates.py`
- `tests/test_slo_correlator.py`
- `tests/test_collector.py`
- `tests/test_slo_storage.py`
- `tests/test_cli_deploy.py`
- `tests/test_budget_policy.py`

**Update:**
- `demo.py` — remove check-deploy imports, parser, dispatch, help text
- `slos/__init__.py` — remove runtime exports (DeploymentGate, SLOCollector, SLORepository, DeploymentCorrelator, etc.)
- Smoke tests — remove `check-deploy` tests from `test_analysis_commands.py` and `test_synology.py`

**User guidance:** "Use `nthlayer-observe check-deploy` for deployment gate enforcement."

### B4: Remove API Server

**Delete:**
- `src/nthlayer/api/` (entire directory)
- `tests/test_api_auth.py`
- `tests/test_api_reconcile.py`
- Any remaining API route tests

**Update:**
- `config/settings.py` — remove API-specific settings (cors_origins, api_prefix, cognito config) if no other consumers
- `demo.py` — if there's a `serve` or `api` command, remove it

**User guidance:** "FastAPI server moves to nthlayer-observe."

### B5: Remove Database Layer

**Delete:**
- `src/nthlayer/db/` (entire directory)
- `tests/test_db_models.py`
- `tests/test_db_repositories.py`
- `tests/test_repository.py`
- `tests/test_db_session.py` (if exists)
- `alembic/` directory and `alembic.ini` (if present)

**Update:**
- Any remaining imports of `nthlayer.db` (should be none after B1-B4)

**User guidance:** "Database layer moves to nthlayer-observe."

### B6: Fix Backstage + Remove Portfolio/Scorecard

**Fix:**
- `generators/backstage.py` — replace `from nthlayer.slos.gates import DeploymentGate` with static threshold lookup from `nthlayer_common.tiers.TIER_CONFIGS`. `get_threshold_for_tier(tier)` becomes a local 3-line function using TIER_CONFIGS.

**Delete:**
- `src/nthlayer/cli/portfolio.py`
- `src/nthlayer/cli/scorecard.py`
- `src/nthlayer/portfolio/` (entire directory)
- `src/nthlayer/scorecard/` (entire directory)
- `tests/test_cli_portfolio.py`
- `tests/test_scorecard.py`
- `tests/test_portfolio*.py`

**Update:**
- `demo.py` — remove portfolio, scorecard imports, parsers, dispatch
- `generators/backstage.py` tests — update to not expect DeploymentGate

**User guidance:** "Use `nthlayer-observe portfolio` and `nthlayer-observe scorecard`."

### B7: Purge Runtime Dependencies

**Remove from pyproject.toml:**
- `fastapi`, `uvicorn[standard]`, `mangum`
- `sqlalchemy`, `alembic`, `psycopg[binary]`
- `redis`
- `aws-xray-sdk`, `PyJWT[crypto]`, `jwcrypto`

**Verify before removing:** `circuitbreaker`, `tenacity`, `orjson` — grep for consumers outside deleted modules.

**Update:**
- `pyproject.toml` — remove deps
- `uv.lock` — regenerate
- Verify `pip install -e .` works
- Run full test suite

## Acceptance Criteria (Epic-Level)

1. Generate has zero `import sqlalchemy` in remaining code
2. Generate has zero `import fastapi` in remaining code
3. Generate has zero `from nthlayer.db` imports in remaining code
4. Generate has zero `from nthlayer.api` imports in remaining code
5. Generate has zero `from nthlayer.deployments` imports in remaining code
6. `nthlayer --help` shows only generate/validate/compile commands (no check-deploy, portfolio, scorecard)
7. `pip install -e .` works without sqlalchemy/fastapi/uvicorn/psycopg
8. Full test suite passes
9. `generators/backstage.py` uses `nthlayer_common` only (no DeploymentGate)

## Workflow

Each bead follows the established workflow:
- `/rule-of-five-planning` before implementation
- `/rule-of-five-reviews` (4 passes) before closing
- Feature branch per bead
- Full test suite as gate
