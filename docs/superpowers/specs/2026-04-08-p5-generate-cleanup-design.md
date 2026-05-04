# P5 Generate Cleanup — Design Spec

## Context

Phases 0–4 of the nthlayer-observe migration are complete. Code was **copied** to observe (not moved) — generate's files are untouched. P5 removes the duplicate runtime modules from generate that now live in observe, making generate leaner.

**Scope change from original plan:** After auditing internal consumers, `discovery/` and `dependencies/` cannot be removed — they're still load-bearing in generate (dashboards, topology, metric recommendations). P5 is scoped to `drift/` and `verification/` only, plus CLI commands that moved to observe.

## Pre-conditions

- nthlayer-observe: 286 tests passing, 9 CLI commands, all boundaries verified
- nthlayer-generate: all tests passing
- No cross-package imports in either direction

## What Gets Removed

### Modules (1,607 lines)

| Module | Files | Lines | Reason |
|--------|-------|-------|--------|
| `src/nthlayer/drift/` | `__init__.py`, `analyzer.py`, `models.py`, `patterns.py` | 868 | Fully duplicated in observe; only used by removable CLI + optional drift features |
| `src/nthlayer/verification/` | `__init__.py`, `models.py`, `extractor.py`, `verifier.py`, `exporter_guidance.py` | 739 | Fully duplicated in observe; zero non-CLI consumers |

### CLI Files (4 files)

| File | Command | Reason |
|------|---------|--------|
| `src/nthlayer/cli/drift.py` | `nthlayer drift` | Now `nthlayer-observe drift` |
| `src/nthlayer/cli/verify.py` | `nthlayer verify` | Now `nthlayer-observe verify` |
| `src/nthlayer/cli/deps.py` | `nthlayer deps` | Now `nthlayer-observe dependencies` |
| `src/nthlayer/cli/blast_radius.py` | `nthlayer blast-radius` | Now `nthlayer-observe blast-radius` |

### Tests

| Test File | Reason |
|-----------|--------|
| `tests/test_drift.py` | Backing module removed; observe has equivalent |
| `tests/test_verification.py` | Backing module removed; observe has equivalent |
| `tests/test_cli_blast_radius.py` | CLI file removed |
| `tests/test_cli_dependencies.py` | CLI file removed |

## What Gets Updated

### `src/nthlayer/demo.py` (main CLI router)

- Remove imports: `handle_drift_command`, `register_drift_parser`, `handle_verify_command`, `register_verify_parser`, `handle_deps_command`, `register_deps_parser`, `handle_blast_radius_command`, `register_blast_radius_parser`
- Remove parser registrations: `register_verify_parser(subparsers)`, `register_drift_parser(subparsers)`, `register_deps_parser(subparsers)`, `register_blast_radius_parser(subparsers)`
- Remove command dispatch blocks for `verify`, `drift`, `deps`, `blast-radius`
- Remove `--include-drift` and `--drift-window` args from deploy parser (lines ~676–683)
- Remove `include_drift`/`drift_window` from `deploy_check_command()` call (lines ~1131–1133)
- Remove "nthlayer verify" from help text (line ~922)

### `src/nthlayer/cli/deploy.py`

- Remove `from nthlayer.drift import DriftAnalyzer, DriftResult, DriftSeverity, get_drift_defaults` (line 16)
- Remove `include_drift`/`drift_window` parameters from `deploy_check_command()` signature
- Remove `_check_drift()` function (lines ~395–440)
- Remove `_display_drift_summary()` function (lines ~542–567)
- Remove drift severity escalation logic in `_format_result()` (drift_result parameter, CRITICAL/WARN checks)

### `src/nthlayer/cli/portfolio.py`

- Remove `from nthlayer.drift import DriftAnalyzer, DriftResult, DriftSeverity, get_drift_defaults` (line 30)
- Remove `_collect_drift_data()` function and all drift-related parameters
- Remove drift table display code

### `pyproject.toml`

- Remove `scipy` from dependencies (only used by drift/)
- Remove `numpy` from dependencies (only used by drift/)
- Remove or empty `drift-ml` optional dependency group

## What Stays (No Changes)

| Module | Reason |
|--------|--------|
| `discovery/` | Used by `dashboards/resolver.py` (metric validation), `metrics/discovery.py` (recommendations) |
| `dependencies/` (providers + discovery.py) | Used by `cli/topology.py`, `topology/enrichment.py`, `slos/correlator.py` |
| `slos/gates.py` | Used by `cli/deploy.py`, `generators/backstage.py` |
| `slos/correlator.py` | Used by `gates.py`, `cli/deploy.py` |
| `policies/` | Used by gates, API, deploy CLI |
| `api/` | Full FastAPI infrastructure — webhooks, policies, teams |
| `db/` | Persistence layer — deeply embedded |
| `deployments/` | Webhook processing, tied to API |
| `slos/collector.py` | Used by `cli/deploy.py`, storage, correlator |
| `cli/topology.py` | Topology export — untouched |
| `dashboards/resolver.py` | Metric resolution — untouched |

## Execution Order

1. Create feature branch `p5-generate-cleanup`
2. Delete `drift/` directory and `verification/` directory
3. Delete 4 CLI files (drift, verify, deps, blast_radius)
4. Delete 4 test files
5. Update `demo.py` — remove imports, parser registrations, dispatch blocks, drift args
6. Update `cli/deploy.py` — strip all drift logic
7. Update `cli/portfolio.py` — strip all drift logic
8. Update `pyproject.toml` — remove scipy, numpy
9. Run `uv run pytest tests/ -v --tb=short -x` — fix any remaining broken imports
10. Run `uv run ruff check src/ tests/` — verify no lint errors

## Verification

1. `uv run pytest tests/ -v --tb=short -x` — all remaining tests pass
2. `uv run ruff check src/ tests/ --ignore E501` — no broken imports or lint errors
3. `uv pip install -e .` works without scipy/numpy
4. `nthlayer --help` — drift, verify, deps, blast-radius commands absent
5. `nthlayer check-deploy --help` — no `--include-drift` or `--drift-window` flags
6. `nthlayer topology --help` — still works (dependencies/ untouched)
7. `nthlayer generate --help` — still works (core compiler untouched)

## Acceptance Criteria

1. `drift/` and `verification/` directories deleted from generate
2. 4 CLI commands removed (drift, verify, deps, blast-radius)
3. Deploy and portfolio commands work without drift features
4. Generate test suite passes (minus removed test files)
5. `pip install -e .` works with reduced dependencies (no scipy/numpy)
6. No broken imports in remaining generate code
