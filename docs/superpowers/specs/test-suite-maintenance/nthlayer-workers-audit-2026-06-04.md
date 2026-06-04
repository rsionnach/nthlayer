# nthlayer-workers test suite audit — Phase 1

- Bead: `opensrm-zfyh.3`
- Repo HEAD: `63a3e3f74a69f248ed1d0f9ec91992ad6831bdea` (clean working tree)
- Date: 2026-06-04
- Reference doc note: `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/testing.md` and `nthlayer/docs/contributing/testing.md` both **absent on disk** — divergences below verified against repo reality, not doc text.

## 1. Test count

- `uv run pytest --collect-only -q` → **1884 tests collected**, 0 collection errors.
- 113 `test_*.py` files across `tests/{observe,measure,correlate,respond,learn}/` plus `tests/test_runner.py`, `tests/test_cli_gate.py`, and `tests/release-smoke/`.
- Baseline per `CLAUDE.md` / `AGENTS.md`: "1873 passed, 1 skipped". Current collection (+11) is consistent with normal accretion; no full run executed (per task budget).
- xfail/skip totals: not enumerated (would require full run); collection found none flagged at collect time.

## 2. Lint state

- `uv run ruff check src/ tests/` → **`All checks passed!`** Zero warnings to categorise.

## 3. Known issues — infrastructure rot

- `pytest --collect-only` produced **no ImportError / ModuleNotFoundError** lines (1884 tests collected cleanly).
- `AutonomyLevel.FULL` and bare `slo_state` identifiers: **0 hits** in `tests/` (already migrated to `FULLY_AUTONOMOUS` / `slo_status`).
- `FileNotFoundError` references appear only in 2 test files (`tests/learn/test_cli_recommendations.py`, `tests/learn/test_gh.py`) and are intentional (testing error paths), not stale-fixture rot.
- No other infra-rot signals surfaced.

## 4. Conceptual rot indicators

Candidates surfaced by pattern — not judgments; each entry needs human review.

- **`test_init*` / `test_constructor` / `test_default_*` pattern** — 17 hits, by package:
  - observe (4): `test_discovery.py::test_initialization`, `::test_initialization_with_auth`, `::test_initialization_with_bearer`, `test_verification.py::test_initialization`
  - respond (6): `test_agent_base.py::test_init_requires_client_or_verdict_store`, `test_escalation.py::test_initial_state_is_active`, `test_config.py::test_default_config`, `test_sre_delegation.py::test_default_max_duration`, `test_sre_suppression.py::test_default_multiplier_is_3`, `test_webhook.py::test_default_allowlist_is_empty_fail_closed`
  - correlate (4): `test_state.py::test_initial_state_is_watching`, `::test_default_config`, `test_types.py::test_default_fields`, `test_summary.py::test_default_omissions`
  - learn (2): `test_recommendations.py::test_default_requires_human_review_true`, `::test_default_generated_by`
  - measure (1): `test_verdict_integration.py::test_default_approve_threshold_value`
- Test files with >20 tests (high redundancy risk): `tests/learn/test_recommendations.py` (62), `tests/respond/test_respond_worker.py` (50), `tests/learn/test_cli_recommendations.py` (45), `tests/measure/test_measure_worker.py` (44), `tests/observe/test_decision_records.py` (39), `tests/correlate/test_trace_tempo.py` (39), `tests/respond/test_remediation.py` (37), `tests/learn/test_learn_worker.py` (35), `tests/observe/test_drift.py` (34), `tests/learn/test_yaml.py` (34).
- `patch("nthlayer_workers...")` sites: **101 occurrences** across 13 files.
  - Unfamiliar pattern: the regex conflates two cases — (a) own-module rebinding of a third-party class (e.g. `tests/observe/test_slo_collector.py` patches `nthlayer_workers.observe.slo.collector.PrometheusProvider`, where the bound name resolves to the third-party Prometheus-client class — the `nthlayer_workers...` prefix is just the import path where it's bound) and (b) genuinely patching own-package call shape. Disambiguation requires reading each patch target's import resolution by hand; flag for human review by the summary bead, not for Phase-1 judgment. PrometheusProvider is the canonical "looks-like-mocking-own-internals-but-isn't" example.
- Duplicate-named tests across files (potential copy-paste): `test_restore_state_accepts_none` (7 copies), `test_satisfies_protocol` (5), `test_manifest_fetch_fails_no_crash` (5), `test_system_prompt_includes_slo` (4).

## 5. CI state

- Workflow: `.github/workflows/test.yml` (named "Test"; not `ci.yml`) — runs `ruff check` + `pytest -q` on push and PR to `main`, matrix Python 3.11/3.12/3.13.
- Last run (`gh run list --workflow=test.yml --limit 3`): **success on 2026-06-03** (`r5(excellence): catalogue measure/config.py validation invariants`). Two prior runs failed (2026-06-01, 2026-05-10).
- Also present: `release-please.yml`, `release.yml`, `dependabot-automerge.yml`.

## 6. Documentation state

- `README.md` mentions deploy-gate CLI but does **not** document testing conventions and does **not** link to a `testing.md`.
- `AGENTS.md` documents testing commands (`uv run pytest -q`, baseline `1873 passed, 1 skipped`, ruff invocation, release-smoke gate at `tests/release-smoke/`) but does not link to an ecosystem-level `testing.md`.
- No `CONTRIBUTING.md` at repo root.

## Divergences from `testing.md`

- **Reference doc missing.** `testing.md` not present at ecosystem root nor at `nthlayer/docs/contributing/testing.md`. All divergences below grounded in repo state only.
- §CI claim (`ci.yml`): divergent — actual file is `.github/workflows/test.yml` (per `opensrm-1kfs`). Last successful run 2026-06-03.
- §Unit-tests layout (`tests/test_module_*.py` flat): divergent — repo nests by subpackage (`tests/observe/`, `tests/measure/`, `tests/correlate/`, `tests/respond/`, `tests/learn/`). Only `tests/test_runner.py` and `tests/test_cli_gate.py` live flat at top level.
- §Fixtures (`tests/conftest.py` + per-package conftests): partial divergence — **no top-level `tests/conftest.py`**; per-package conftests exist only at `tests/respond/conftest.py`, `tests/measure/conftest.py`, `tests/correlate/conftest.py` (none for `observe/` or `learn/`).
- §Integration tests (`tests/integration/`): divergent — directory **does not exist**. Integration-shaped tests live inline (e.g. `tests/measure/test_tiering_integration.py`, `tests/respond/test_respond_worker_integration.py`).
- §Contract tests (`tests/contracts/`): divergent — directory **does not exist**. Contract tests live inline (e.g. `tests/correlate/test_contract_module.py`).
- §Naming (`_test_` prefix for non-test helpers): no `_test_`-prefixed helper functions found in `tests/`.
- **§Async claim** —
  - Doc says: "all worker module tests are async".
  - Repo reality: files with `@pytest.mark.asyncio` or `async def test_` / total test files — `observe 0/22`, `measure 9/20`, `correlate 3/24`, `respond 13/33`, `learn 0/10`. Note: `pyproject.toml` sets `asyncio_mode = "auto"`, so pytest treats every sync `test_*` as async at collection time — the ratio above counts `async def` declarations, not effective async behaviour.
  - Unfamiliar pattern: the doc's "all async" claim may be interpreted as either "all `async def`" or "all effective-async under asyncio_mode=auto"; flag for human review by the summary bead.
- Extra dirs not described in testing.md conventions: `tests/release-smoke/` (read-only wheel-install smoke), `tests/scenarios/synthetic/`, and `tests/correlate/scenarios/` (sibling of the per-package test files; verified present on disk, contains a `synthetic/` subdir). Unfamiliar pattern (out of doc scope); all three need human review for purpose.

## Validation

- Working tree clean: `git status --short` empty post-audit.
- No source files in `nthlayer-workers/` modified.
- Output written to this file only.
