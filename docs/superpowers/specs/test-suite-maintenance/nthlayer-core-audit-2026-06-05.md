# nthlayer-core test-suite audit (Phase 1)

- **Repo:** `nthlayer-core`
- **HEAD:** `f7fb4cad547fc94529379a525b1983a44434adac` (branch `main`)
- **Working tree:** clean pre- and post-audit; `uv.lock` not perturbed
- **Bead:** opensrm-zfyh.2
- **Date:** 2026-06-05

## 1. Test count

- Collection: `uv run pytest --collect-only -q` → **217 tests collected in 0.26s**, zero collection errors. Clean collection.
- On-disk module count: `find tests -name "test_*.py" | wc -l` → **13** (11 top-level + 2 in `tests/smoke/`).
- No prior numeric baseline in `CLAUDE.md`, `AGENTS.md`, or the bead. 217 stands as baseline. xfail/skip tally deferred to Phase 2.

## 2. Lint state

- **Ruff** (`uv run ruff check src/ tests/`): **0 errors**. Matches sibling common; contrasts with generate (23 I001).
- No custom golden-principle linter suite (`scripts/lint/run-all.sh` absent), consistent with `AGENTS.md`.

## 3. Infrastructure rot

- No `ModuleNotFoundError` on collection (217/217 collected); no collection errors at all — contrast sibling generate (100 errors).
- Renamed-symbol scan: `grep -rE "AutonomyLevel\.FULL|slo_state" tests/ src/` → **0 hits**. No hardcoded fixture paths under `tests/` (no `tests/fixtures/`). No infrastructure rot indicators in Phase-1 surface scans.

## 4. Conceptual rot indicators

- `test_<function_name>`-style: pervasive across all 13 modules (sampled `test_api.py`, `test_store.py`).
- `test_init` / `test_constructor` / `test_default_*`: `grep -rlE "def test_(init|default_|constructor)" tests/ | wc -l` → **0 files**. None present — sharply lower than sibling generate (35) and common (3).
- Test files with **>20 tests** (counted via `^\s*(async )?def test_` to include async, the dominant shape in API tests): **4 files** — `test_api_cases.py` 43, `test_api.py` 35, `test_store.py` 34, `test_store_verdictstore.py` 26. Top: `test_api_cases.py` 43.
- Boundary discipline: **0 files at exactly 20; 0 files at exactly 21**. Nearest below the >20 threshold is `test_retention.py` 16 (then `test_api_heartbeats.py` 15, `test_api_manifests.py` 12). Borderline-inclusion calls absent.
- **Tests mocking own-package internals:** `grep -rE "patch\(['\"]nthlayer_core" tests/ | wc -l` → **0 sites / 0 files** (quote-agnostic). `grep -rlE "Mock|patch\(" tests/` → **1 file**, `tests/test_api.py`, and the sole hit is `await client.patch("/verdicts/...", json=...)` — an httpx HTTP PATCH call, not `unittest.mock.patch`. The suite uses real `Store(tmp_path)` and httpx `AsyncClient` against the Starlette app per `CLAUDE.md` §8 ("Tests use real `Store(tmp_path)`, not a stub"). **No own-package internals are patched anywhere** — qualitatively different from sibling repos (common 44/5, generate 457/31).

## 5. CI state

- **No `ci.yml` workflow exists.** `ls .github/workflows/` → `dependabot-automerge.yml`, `release-please.yml`, `release.yml`. `gh run list --workflow=ci.yml --branch=main --limit 3` → **HTTP 404: workflow ci.yml not found**. `gh run list --branch=main --limit 5` shows only release-please and dependabot runs; no push-triggered pytest job.
- The only test execution in CI is the wheel-smoke gate inside `release.yml` (`pytest -q /smoke` against the built wheel in a `python:3.11-slim` container), which runs only on release. Unit/integration tests on push to main are **not gated by CI**.

## 6. Documentation state

- `README.md` and `AGENTS.md` cite `uv run pytest -q` commands; neither has a "Testing" section.
- `CONTRIBUTING.md` is **absent**. Repo-local `docs/` contains only `architecture.md` — **no `docs/testing.md`**, no `docs/contributing/testing.md`.
- Canonical reference doc lives at `nthlayer/docs/testing.md` (see Divergences callout).

## Divergences from testing.md

> **Correction:** `nthlayer/docs/testing.md` exists (17,682 bytes, 2026-05-02). Workers/bench/generate audits reported it absent — they missed the nthlayer hub. §Divergences below are evaluated against the real doc.

- **§CI workflow filename** —
  - Doc says: every active repo has `.github/workflows/ci.yml` running unit + integration tests on push.
  - Repo reality: `.github/workflows/ci.yml` **absent**. Only release-please, release, and dependabot-automerge workflows exist; the sole pytest invocation is the wheel-smoke gate that runs at release time, not on push.
  - **Unfamiliar pattern; needs human review.** This is a hard divergence — no other audited sibling lacked `ci.yml`. Either core deliberately offloads CI to a different mechanism (not documented) or the workflow was never added.
- **§Unit-test layout** —
  - Doc says: `tests/test_module_a.py` at top level.
  - Repo reality: followed. 11 modules under `tests/` (`test_api*.py`, `test_store*.py`, `test_retention.py`, `test_health.py`).
- **§Fixtures** —
  - Doc says: top-level `tests/conftest.py` and per-package `tests/<package>/conftest.py`.
  - Repo reality: `find tests -name conftest.py` → **0 files**. No `conftest.py` anywhere. Tests inline their own `Store(tmp_path)` setup. Convention not followed; the repo relies on pytest's `tmp_path` builtin instead.
  - **Unfamiliar pattern:** zero conftests, real-store discipline. Differs from every sibling. Likely deliberate (per `CLAUDE.md` §8) but not reconciled in testing.md.
- **§Integration tests** —
  - Doc says: `tests/integration/`.
  - Repo reality: directory absent. Cross-tier integration lives in `nthlayer/test/` (the ecosystem hub) per `nthlayer/CLAUDE.md`. Absence in nthlayer-core is consistent with the three-tier split.
- **§Contract tests** —
  - Doc says: `tests/contracts/`.
  - Repo reality: directory absent. testing.md §Contract calls out "Core's HTTP API as consumed by workers" as the canonical contract surface — yet the producer-side (core) has **no `tests/contracts/`**. The sibling common audit found no contracts dir either, despite `nthlayer-common/CLAUDE.md` claiming `tests/contracts/fixtures/` existed.
  - **Unfamiliar pattern; needs human review.** testing.md explicitly names core's API as the canonical contract example, but neither producer nor consumer hosts a `tests/contracts/` directory. Either contract tests live elsewhere or they are unimplemented.
- **§Helper-naming `_test_` prefix / `_helpers.py`** —
  - Doc says: `_test_` prefix for non-test helpers, or `_helpers.py` module convention.
  - Repo reality: `grep -rE "^def _test_" tests/` → **0 hits**; `find tests -name "_helpers.py"` → **0 hits**. Neither convention used. No shared helpers exist — tests are self-contained.
  - **Unfamiliar pattern:** zero shared helpers AND zero `conftest.py` files — sibling workers/bench/generate/common each use at least one of `_helpers.py` modules or `tests/conftest.py`. Self-contained tests-with-zero-fixture-machinery is a discipline outlier from the sibling cohort; needs human review whether this is intentional (architecture supports it: real `Store(tmp_path)` + real httpx `AsyncClient`) or whether the convention should propagate from siblings.
- **§Async** —
  - Doc says: "all worker module tests are async."
  - Repo reality: nthlayer-core is a Starlette/uvicorn HTTP server (Tier 1), **not a worker**. `pyproject.toml` sets `asyncio_mode = "auto"`; API tests use `async def` against `httpx.AsyncClient` (verified: `test_api.py` has 35 async tests). Convention applies de-facto.
  - **Unfamiliar pattern (cross-tier caveat):** doc claim is worker-shaped; how it maps onto a server tier (where async is intrinsic to the framework, not a worker idiom) needs clarification in testing.md. Defer.
  - **Unfamiliar pattern:** `pyproject.toml` sets `asyncio_mode = "auto"` so pytest treats sync `def test_*` as effective-async at collection. The 122/213 literal-`async def` ratio (cohort-wide `^\s*async def test_` vs `^\s*(async )?def test_`) counts declarations, not effective-async behaviour. Same dual-interpretation caveat as bench, workers, common audits. Needs human review whether the testing.md "all worker module tests are async" claim refers to literal `async def` or to effective-async-under-asyncio_mode=auto — the answer changes how the divergence is classified.

## Validation

- Working tree clean post-audit (`git status --short` empty); `uv.lock` untouched; no `nthlayer-core/` source modified. This audit file is the sole addition to the `nthlayer/` working tree relative to HEAD.
- Reproducer commands: `uv run pytest --collect-only -q` (217), `uv run ruff check src/ tests/` (0), `gh run list --workflow=ci.yml --branch=main --limit 3` (404), `gh run list --branch=main --limit 5`, `grep -rE "patch\(['\"]nthlayer_core" tests/` (0/0), `grep -rlE "def test_(init|default_|constructor)" tests/` (0), per-file `^\s*(async )?def test_` for-loop, `find tests -name "conftest.py"` (0), `find tests -name "_helpers.py"` (0), `grep -rE "AutonomyLevel\.FULL|slo_state" tests/ src/` (0).
