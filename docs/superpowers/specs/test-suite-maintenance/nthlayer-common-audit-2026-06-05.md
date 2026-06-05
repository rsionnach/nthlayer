# nthlayer-common test-suite audit (Phase 1)

- **Repo:** `nthlayer-common`
- **HEAD:** `76b7d1efd489405afd8b6a63a48dd3d6dd620189` (branch `main`)
- **Working tree:** clean (`git status --short` empty pre- and post-audit)
- **Bead:** opensrm-zfyh.1
- **Date:** 2026-06-05

## 1. Test count

- Collection: `uv run pytest --collect-only -q` → **892 tests collected in 0.58s**, zero collection errors. Clean collection.
- On-disk module count: `find tests -name "test_*.py" | wc -l` → **38** (32 top-level + 5 records + 1 smoke).
- Baseline divergence: `nthlayer-common/CLAUDE.md` cites no explicit baseline; the bead text cites "~758 tests". Reality is **892**, a ~+134 drift upward — likely growth, not rot, but baseline citation is stale.
- xfail/skip totals: not enumerated by `--collect-only`; spot-check shows names containing `skip` are tests *of* skip-behaviour, not skipped tests. Full tally deferred to Phase 2.

## 2. Lint state

- **Ruff** (`uv run ruff check src/ tests/`): **0 errors** ("All checks passed!"). Clean — the only sibling-audit clean ruff state so far.
- No custom golden-principle linters (`./scripts/lint/run-all.sh` absent in this repo, as the bead notes — nthlayer-common does not carry the generate-style custom linter suite).

## 3. Infrastructure rot

- No `ModuleNotFoundError` on collection (892/892 collected) — contrast with sibling nthlayer-generate (100 collection errors).
- Renamed-symbol scan: `grep -rE "AutonomyLevel\.FULL|slo_state" tests/ src/` → **0 hits**. No hardcoded fixture paths (no `tests/fixtures/` directory). No infrastructure rot indicators detected in Phase-1 surface scans.

## 4. Conceptual rot indicators

- `test_<function_name>`-style: pervasive across the 38 modules (sampled `test_llm.py`, `test_identity.py`).
- `test_init` / `test_constructor` / `test_default_*`: **3 files** match (`tests/test_verdicts_core.py`, `tests/test_providers.py`, `tests/test_overrides.py`). Lower than sibling generate (35).
- Test files with **>20 tests**: 13 files (top: `test_llm.py` 43, `test_cloudevents.py` 38, `test_identity.py` 38, `test_overrides.py` 37, `test_manifest_parser.py` 36, `test_verdicts_store.py` 35, `tests/records/test_store.py` 29, `test_models.py` 25, `tests/records/test_hashing.py` 24, `test_config.py` 23, `test_prompts.py` 23, `test_verdicts_core.py` 23, `test_outcomes.py` 22). 4 files sit at exactly 20 (`test_governance_bridge.py`, `test_tiers.py`, `test_manifest_models.py`, `tests/records/test_models.py`) — excluded per "20 does not". No files sit at 21 — no borderline-inclusion calls.
- **Tests mocking own-package internals — counts and targets:** `grep -rE "patch\(['\"]nthlayer_common"` → **44 sites across 5 files** (`test_llm.py`, `test_llm_structured.py`, `test_llm_stub.py`, `test_slack.py`, `test_telemetry.py`); quote-agnostic and double-quote-only both 44/5 (no quote-style drift). 7 unique target strings: `nthlayer_common.llm.httpx.post`, `nthlayer_common.llm.time.sleep`, `nthlayer_common.llm_structured._get_anthropic_client`, `nthlayer_common.llm_structured._get_openai_client`, `nthlayer_common.slack.httpx.AsyncClient`, `nthlayer_common.telemetry._otel_available`, `nthlayer_common.telemetry.trace`.
- **Conflation pattern + human-review flag:** third-party-bound-via-own-module canonical examples — `llm.httpx.post`, `slack.httpx.AsyncClient`, `llm.time.sleep` (strings look like own-internals, but `httpx.*` / `time.sleep` are third-party/stdlib); own-module-defined examples — `_get_anthropic_client`, `_get_openai_client`, `_otel_available`. Conflation matches workers/bench/generate pattern (e.g. `nthlayer_generate.discovery.client.httpx.get`). **Unfamiliar pattern: disambiguating own-call-shape from own-module-bound-to-third-party requires per-target import resolution; defer to Phase 2.**

## 5. CI state

- Workflow file: `.github/workflows/ci.yml` (present). Other workflows: `release.yml`, `release-please.yml`, `dependabot-automerge.yml`.
- `gh run list --workflow=ci.yml --branch=main --limit 3`: **all three most-recent runs `success`** — 2026-06-03T20:35:09Z, 2026-06-03T20:22:02Z, 2026-06-03T20:10:21Z. Healthy CI signal. Contrast with sibling generate (3/3 failure).

## 6. Documentation state

- `README.md` has no "Testing" section; `CONTRIBUTING.md` is **absent**. Repo-local `docs/` contains only `architecture.md` + `llm-interface.md` — **no `docs/testing.md`**, no `docs/contributing/testing.md`.
- Canonical reference doc lives at `nthlayer/docs/testing.md` (see Divergences callout for the sibling-audit correction).

## Divergences from testing.md

> **Correction to sibling audits:** `nthlayer/docs/testing.md` exists (17,682 bytes, dated 2026-05-02). The workers, bench, and generate audits each reported testing.md absent — they checked the ecosystem root and `docs/contributing/testing.md` (both correctly absent) but not the nthlayer hub. All §Divergences below are evaluated against `nthlayer/docs/testing.md`.

- **§CI workflow filename** —
  - Doc says: every active repo has `.github/workflows/ci.yml`.
  - Repo reality: `.github/workflows/ci.yml` present, all three latest runs green. Convention satisfied.
- **§Unit-test layout** —
  - Doc says: `tests/test_module_a.py` at top level.
  - Repo reality: followed. 32 modules live directly under `tests/`.
- **§Fixtures** —
  - Doc says: top-level `tests/conftest.py` and per-package `tests/<package>/conftest.py`.
  - Repo reality: **no top-level `tests/conftest.py`**; `tests/records/conftest.py` present (declares shared decision-record builders — verified). Convention partially satisfied; the per-package shape is present (as `CLAUDE.md` notes), but the top-level conftest is missing.
- **§Integration tests** —
  - Doc says: `tests/integration/`.
  - Repo reality: directory absent. nthlayer-common is a pure shared library — no integration surface to host. Likely deliberate; sibling generate (also library-shaped) similarly absent.
- **§Contract tests** —
  - Doc says: `tests/contracts/`.
  - Repo reality: **directory absent**. `CLAUDE.md` mentions "shared contract fixtures live in `nthlayer-common/tests/contracts/fixtures/`" — verified by `ls`: directory does not exist. **Unfamiliar pattern; needs human review** — CLAUDE.md asserts the directory exists; it does not. Either the doc is stale or the fixtures were moved/never added.
- **§Helper-naming `_test_` prefix** —
  - Doc says: `_test_` prefix for non-test helper functions, or `_helpers.py` module convention.
  - Repo reality: `grep -rE "^def _test_" tests/` → **0 hits**; `find tests -name "_helpers.py"` → **0 hits**; `find tests -name "helpers.py"` → **0 hits**. Neither convention used. Shared builders live in `tests/records/conftest.py` instead (`NOW`, `LATER`, model imports).
  - **Unfamiliar pattern:** nthlayer-common uses *conftest-as-builder-module* in place of either prescribed pattern. Differs from sibling bench/workers/generate `_helpers.py`. Needs human review.
- **§Async** —
  - Doc says: "all worker module tests are async."
  - Repo reality: nthlayer-common is a shared library, not a worker. `pyproject.toml` sets `asyncio_mode = "auto"` so the framework is configured for async. **Unfamiliar pattern (cross-tier caveat):** worker-shaped doc claim does not map onto a library tier. Defer.
## Validation

- Working tree clean: `cd nthlayer-common && git status --short` empty post-audit; `uv.lock` was not perturbed by `uv run` this session.
- No source files in `nthlayer-common/` modified.
- Output written to this file only; this audit file is the sole addition to the `nthlayer/` working tree relative to HEAD.
- Reproducer commands: `uv run pytest --collect-only -q`, `uv run ruff check src/ tests/`, `gh run list --workflow=ci.yml --branch=main --limit 3`, plus `grep -rE "patch\(['\"]nthlayer_common" tests/` (44/5), `grep -rlE "def test_(init|default_|constructor)" tests/` (3), per-file `def test_` counts via the bead-pinned for-loop, `find tests -name "conftest.py"`, `find tests -name "_helpers.py"`.
