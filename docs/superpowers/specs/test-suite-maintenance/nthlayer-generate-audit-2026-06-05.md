# nthlayer-generate test-suite audit (Phase 1)

- **Repo:** `nthlayer-generate`
- **HEAD:** `922d20397a6f8aa4727ec0e0e09021437454bff8` (branch `main`)
- **Working tree:** clean (`git status --short` empty post-audit; transient `uv.lock` touch from `uv run` was reverted with `git checkout -- uv.lock`)
- **Bead:** opensrm-zfyh.5
- **Date:** 2026-06-05

## 1. Test count

- Collection: `uv run pytest --collect-only --continue-on-collection-errors` → **205 tests collected, 100 collection errors in 0.60s**. Over half the test modules fail at import — the suite does not reach a clean collection.
- On-disk module count: **107 top-level + 9 nested = 116 total `test_*.py` files** (nested under `tests/smoke/` + `tests/release-smoke/` + `tests/integration/`). Baseline divergence: README.md and `docs/testing.md` cite "~119 test files"; on-disk reality is 116 — soft drift, three-file gap, baseline stale.
- xfail/skip totals: not enumerable from `--collect-only` while 100 collection errors interrupt; would require a clean collection or full run.

## 2. Lint state

- **Ruff** (`uv run ruff check src/ tests/`): **23 errors**, all `I001` (unsorted/unformatted import blocks), all autofixable. Zero other rule codes triggered (E501 suppressed by config).
- **Custom linter — exception handling** (`./scripts/lint/run-all.sh` → `check-exception-handling`): **14 violations**.
- **Custom linter — orphan TODOs** (`./scripts/lint/run-all.sh` → `check-no-orphan-todos`): **54 violations** (TODOs without bead refs).
- **Custom linter — unstructured logging** (`./scripts/lint/run-all.sh` → `check-no-unstructured-logging`): **592 violations** (bare `print()` calls — largest single category, concentrated in `src/nthlayer_generate/validation/promql.py` and CLI surfaces). Spot-check: 2/3 sampled sites are plausibly intentional CLI output (`demo.py` banner; `validation/promql.py:331` `print(result.summary())`); 1/3 (`specs/environment_detection.py:202` emoji-prefixed status print in a non-CLI module) reads as debug-print leak. Disambiguation deferred to Phase 2.

## 3. Infrastructure rot

Collection is broken at scale: **100 of the failing modules raise `ModuleNotFoundError: No module named 'nthlayer_generate'`** during pytest's test-module import phase, even though `uv run python -c "import nthlayer_generate"` succeeds (resolves to `src/nthlayer_generate/__init__.py`, editable-installed in `.venv`). Candidate causes: pytest import-mode / `sys.path` interaction (no `tests/__init__.py`, default `prepend` mode, two conftests at `tests/conftest.py` + `tests/smoke/conftest.py`). **Unfamiliar pattern:** the disparity (collection-time `ModuleNotFoundError` despite direct interpreter import succeeding) is a recognised-but-unexplained anomaly — none of the three candidate causes above explain why the direct `uv run python -c "import nthlayer_generate"` path works. Defer root-cause investigation to Phase 2 with explicit human-review flag. `tests/release-smoke/test_imports.py` additionally fails at parametrize-time for the same reason. No `AutonomyLevel.FULL` / `slo_state`-style renamed-symbol hits surfaced because collection never gets that far.

## 4. Conceptual rot indicators

Surfaced by pattern only; deeper triage is Phase 2's job.

- `test_<function_name>`-style: pervasive across all 107 top-level modules.
- `test_init` / `test_constructor` / `test_default_*`: **35 files** contain at least one such function (pinned regex `grep -rlE "def test_(init|default_|constructor)" tests/ | wc -l`; e.g. `tests/test_init.py::TestInitCommand::test_init_creates_service_file`). Higher than sibling repos.
- Test files with **>20 tests**: 54 files (top: `test_opensrm.py` 132, `test_discovery_client.py` 73, `test_cli_ux.py` 72, `test_demo.py` 71, `test_config_secrets_init.py` 70, `test_orchestrator.py` 68, `test_sdk_adapter.py` 67). 3 files sit at exactly 20 (`test_validation.py`, `test_recording_rules.py`, `test_loki.py`) and are excluded; 3 sit at 21 (`test_sync_awesome_alerts.py`, `test_domain_models.py`, `test_deps_discovery.py`) and are included per the bead's "21 qualifies, 20 does not" discipline. `test_mimir_provider.py` has 12 tests (verified via `grep -cE "^\s*def test_"`, no parametrize multiplication) and is below threshold.
- **Tests mocking own-package internals** — 457 `patch(['"]nthlayer_generate.*)` sites across 31 files (quote-agnostic; double-quote form alone is 453 / 30). Canonical own-module-bound-to-third-party example: `patch("nthlayer_generate.discovery.client.httpx.get", ...)` (20 occurrences) — string looks like own internals, but `httpx.get` is a third-party function rebound via `discovery.client`. Same pattern as the sibling bench `httpx.AsyncClient` and workers `PrometheusProvider` cases. Top own-package targets spot-checked: `cli.ux.has_gum` verified own-module-defined (`src/nthlayer_generate/cli/ux.py:102`); `config.cli.get_secret_resolver` and `cli.pagerduty.PagerDutyClient` are own-package symbols re-bound into another own-module (defined in `config/secrets/...` and `integrations/pagerduty.py:35` respectively, imported at the patch-target site) — same re-binding shape as the `httpx` case but with own-package sources. Full 457-site classification deferred to Phase 2.
- **Unfamiliar pattern:** disambiguating own-call patches from own-module-attribute-bound-to-third-party requires per-site import-resolution; defer to Phase 2.

## 5. CI state

Workflow file: `.github/workflows/ci.yml` (named `CI`). `gh run list --workflow=ci.yml --limit 3` on `main`: **all three most-recent runs `failure`** — 2026-06-01T20:24:14Z (chore: remove push-demo-metrics), 2026-05-10T19:11:28Z, 2026-05-10T09:54:49Z. **No successful CI run on `main` since at least May 10**. Other workflows: `release-please.yml`, `release.yml`, `deployment-gate.yml`, `docs.yml`, `publish-docker.yml`, `sync-awesome-alerts.yml`, `dependabot-automerge.yml`.

## 6. Documentation state

- `README.md` cites `make test` once (line 331) but has no "Testing" section; `CONTRIBUTING.md` likewise has no testing-doc reference. Neither links the repo-local `docs/testing.md`.
- The reference ecosystem `testing.md` is **absent** at both `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/testing.md` and `nthlayer-generate/docs/contributing/testing.md` (verified by `ls`).
- However, **`nthlayer-generate/docs/testing.md` exists** (41 lines): commands + patterns, asserts "~119 test files" (stale — see §1), lists `tests/fixtures/` and `tests/integration/` (both present), silent on `tests/contracts/`. Separate, narrower doc — not a shim or copy of the missing ecosystem-root `testing.md`; neither references the other. Two distinct documents: one missing (ecosystem-root), one present-but-narrow (repo-local).

## Divergences from testing.md

Reference doc absent (see §6); claims below evaluated against the cross-repo prose summary preserved in the sibling audits and the bead text.

- **§CI workflow filename** —
  - Doc says: every active repo has `.github/workflows/ci.yml`.
  - Repo reality: `.github/workflows/ci.yml` present and used. Convention satisfied — but all three latest runs are red.
- **§Unit-test layout** —
  - Doc says: `tests/test_module_a.py` at top level.
  - Repo reality: followed. 107 modules live directly under `tests/`.
- **§Fixtures** —
  - Doc says: top-level `tests/conftest.py` and per-package `tests/<package>/conftest.py`.
  - Repo reality: `tests/conftest.py` present (structlog setup); `tests/smoke/conftest.py` present. `tests/fixtures/` exists but holds only `demo_data.yaml` — no `conftest.py` there. Convention partially satisfied.
- **§Integration tests** —
  - Doc says: `tests/integration/`.
  - Repo reality: present (1 module, `test_workflows.py`) but fails to collect for the same `ModuleNotFoundError` as the rest of the suite.
- **§Contract tests** —
  - Doc says: `tests/contracts/`.
  - Repo reality: directory absent. nthlayer-generate is a pure compiler with no service-boundary contracts to pin; absence likely deliberate.
  - Unfamiliar pattern: confirm with maintainer that the compiler has no consumer-side contract surface that warrants pinning. Needs human review.
- **§Helper-naming `_test_` prefix** —
  - Doc says: `_test_` prefix for non-test helper functions inside test modules.
  - Repo reality: zero functions match `_test_<name>(`; one helper *module* exists at `tests/smoke/_helpers.py` (different naming convention than testing.md prescribes).
  - **Unfamiliar pattern:** bench / workers / generate use `_helpers.py`-style module naming for shared test helpers; the `_test_<name>` function-prefix convention is unused. Needs human review whether the doc prescription is wrong or whether the repos drifted intentionally.
- **§Async** —
  - Doc says: "all worker module tests are async."
  - Repo reality: generate is a pure deterministic compiler — no workers, no async runtime surface. `pyproject.toml` does set `asyncio_mode = "auto"` (line 84) so the framework is configured for async, but the worker-spec claim does not map onto a compiler tier.
  - **Unfamiliar pattern (cross-tier caveat):** doc convention is worker-shaped; how it should apply to a deterministic compiler is ambiguous. Needs human review; defer to Phase 2.

## Validation

- Working tree clean: `cd nthlayer-generate && git status --short` empty post-audit (`uv.lock` reverted to HEAD via `git checkout -- uv.lock`).
- No source files in `nthlayer-generate/` modified.
- Output written to this file only; this audit file is the sole addition to the `nthlayer/` working tree relative to HEAD.
- Reproducer commands: `uv run pytest --collect-only --continue-on-collection-errors`, `uv run ruff check src/ tests/`, `bash scripts/lint/run-all.sh`, `gh run list --workflow=ci.yml --limit 3`, plus the targeted greps for `patch(['"]nthlayer_generate` (quote-agnostic: 457 sites / 31 files), the `test_(init|default_|constructor)` family (35 files), and per-file `def test_` counts.
