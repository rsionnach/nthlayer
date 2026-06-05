# nthlayer-bench test-suite audit (Phase 1)

- **Repo:** `nthlayer-bench`
- **HEAD:** `461746803fc9c5900a0f286ad93aed32fde7d968` (branch `main`)
- **Working tree:** clean (`git status --short` empty)
- **Bead:** opensrm-zfyh.4
- **Date:** 2026-06-05

## 1. Test count

Collected via `uv run pytest --collect-only -q`: **307 tests** in 0.39s, zero collection errors. Distribution is layered (`sre/` logic, `widgets/`, `screens/`, `app`, `cli`, plus a top-level `tests/smoke/` package with 5 tests). No `pytest.ini`/`conftest` advertises `xfail` markers in scope; full pass/fail/skip counts require a real run (intentionally skipped per bead scope). `CLAUDE.md` and `AGENTS.md` cite the suite as the lint+pytest gate of CI but do not declare a baseline number; 307 appears to be that baseline.

## 2. Lint state

`uv run ruff check src/ tests/` → **All checks passed!** Zero warnings across all rule codes. CI runs the same command (see `.github/workflows/test.yml` step "Lint (ruff check)").

## 3. Infrastructure rot

Collection succeeds cleanly (no `ImportError`/`ModuleNotFoundError`). Grep for the canonical renamed identifiers (`AutonomyLevel.FULL`, `slo_state`) across `src/` and `tests/` returned zero hits — those renames are already absorbed. No obvious hardcoded fixture paths; `tests/conftest.py` is purely a monkeypatch fixture and uses no on-disk paths.

## 4. Conceptual rot indicators

Surfaced by pattern only; deeper triage is Phase 2's job.

- `test_<function_name>`-style: pervasive — almost every file is organised this way (`test_app.py`, `test_sre_*.py`, `test_widgets_*.py`). Consistent with ecosystem convention; not necessarily rot.
- `test_init` / `test_constructor` / `test_default_*`: 1 hit (`tests/test_sre_case_bench.py::test_default_state_filter_is_pending`). Low signal.
- Test classes with >20 tests in one file: 6 files exceed 20 (`test_sre_post_incident.py` 41, `test_app.py` 32, `test_sre_brief.py` 29, `test_sre_situation_board.py` 28, `test_sre_reasoning_capture.py` 23, `test_sre_case_bench.py` 21). These are file-level counts, not class counts; 10 `TestX` classes exist but none individually exceeds 20.
  - **Borderline judgment call:** `test_sre_case_bench.py` sits exactly on the `>20` threshold (21 qualifies; 20 would not). Flagged here per the bead's "don't silently drop or silently keep" discipline rather than silently included/excluded.
- **Tests mocking own-package internals** — 74 `patch(...)` sites across 10 files; **all 74 target a `"nthlayer_bench.*"` string**. The proportion that resolve to a symbol *defined* in `nthlayer_bench` (vs. own-module rebinding of a third-party class — see sibling audit's PrometheusProvider example) is not derivable by grep alone.
  - **Canonical own-module-bound-to-third-party example in bench:** `patch("nthlayer_bench.app.httpx.AsyncClient", ...)` — the target string looks like own internals, but `httpx.AsyncClient` is a third-party class merely re-exported via `nthlayer_bench.app`. This is the bench analogue of the sibling audit's PrometheusProvider case. The other three unique own-string targets (`widgets.case_brief.build_paging_brief`, `widgets.case_review.build_post_incident_review`, `widgets.situation_board.fetch_situation_board`) are own-module symbols. Full 74-site classification still defers to Phase 2.
  - **Unfamiliar pattern:** disambiguating own-call-shape patches from own-module-attribute-bound-to-third-party requires reading each patch target's import-resolution by hand; defer to Phase 2.

## 5. CI state

Workflow file: `.github/workflows/test.yml` (named `Test`). Last successful run on `main`: 2026-06-01T20:24:11Z, commit "refactor: read version from importlib.metadata, not source literals", 1m0s, conclusion `success`. Matrix runs Python 3.11/3.12/3.13. Runs `ruff check` then `pytest -q`. Additional workflows: `release-please.yml`, `release.yml`, `dependabot-automerge.yml`. No standalone `lint.yml`.

## 6. Documentation state

`README.md` has no "Testing" section and does not reference any testing convention doc. `AGENTS.md` documents the test/lint/run commands (`uv run pytest -q`, `uv run ruff check src/ tests/`) and notes the wheel-install smoke target (`tests/smoke/`). No `CONTRIBUTING.md` exists. `CLAUDE.md` rule #10 codifies "don't assert on rendered text" as a hard discipline rule but cites cross-repo memory (`feedback_test_assertions`), not a `testing.md`.

## Divergences from testing.md

`testing.md` is **absent from both candidate paths** — `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/testing.md` and `nthlayer-bench/docs/contributing/testing.md`. This matches the sibling audit (`opensrm-zfyh.3`). Doc claims below are evaluated against the cross-repo prose summary preserved in that sibling audit and the bead text.

- **§CI workflow filename** —
  - Doc says: every active repo has `.github/workflows/ci.yml`.
  - Repo reality: workflow is `.github/workflows/test.yml` (job name `Test`). No `ci.yml`.
- **§Unit-test layout** —
  - Doc says: `tests/test_module_a.py` at top level.
  - Repo reality: followed. All 19 unit test modules live directly under `tests/`; no per-subpackage nesting.
- **§Fixtures** —
  - Doc says: top-level `tests/conftest.py` and per-package `tests/<package>/conftest.py`.
  - Repo reality: top-level `tests/conftest.py` present (autouse `_quiet_escalation_monitor`). No per-package conftests — but also no per-package test subdirs (other than `tests/smoke/`, which has no `conftest.py`). Convention satisfied vacuously.
- **§Integration tests** —
  - Doc says: `tests/integration/`.
  - Repo reality: directory absent. Closest analogue is `tests/smoke/` (post-wheel-install smoke).
- **§Contract tests** —
  - Doc says: `tests/contracts/`.
  - Repo reality: directory absent.
  - Unfamiliar pattern: bench is HTTP-only against `nthlayer-core` (CLAUDE.md hard rule #1). The absence of an explicit contract directory may be deliberate (no schema-level handshake to pin) or a real gap. Needs human review.
- **§Helper-naming `_test_` prefix** —
  - Doc says: `_test_` prefix for non-test helper functions inside test modules.
  - Repo reality: no helpers named `_test_*` found. Either no such helpers exist (likely — the suite is mostly mock-driven) or the convention is unused. Low signal.
- **§Async** —
  - Doc says: "all worker module tests are async."
  - Repo reality: bench is a TUI, not a worker. Async usage is heavy where Textual demands it: in `test_widgets_*.py` + `test_app.py` together, 73 of 85 test functions are `async` (all 53 widget tests; 20 of 32 app tests). The doc claim is scoped to workers; bench's actual ratio is high but not uniform — 12 sync tests in `test_app.py` are real.
  - **Unfamiliar pattern (cross-tier caveat):** `pyproject.toml` line 31 sets `asyncio_mode = "auto"` (verified via `grep -nE "asyncio_mode" pyproject.toml`). The 73/85 figure counts literal `async def test_` declarations, **not** effective-async behaviour at runtime — under `asyncio_mode = "auto"` pytest-asyncio treats sync `test_*` functions as async at collection. Same caveat as the sibling `nthlayer-workers` audit; declared count and effective behaviour are distinct.

## Validation

- Working tree clean: `cd nthlayer-bench && git status --short` empty post-audit.
- No source files in `nthlayer-bench/` modified.
- Output written to this file only; the audit file is the sole addition to the `nthlayer/` working tree relative to HEAD.
- Audit was generated by re-running, not by inspection of stale CI logs. Reproducer commands: `uv run pytest --collect-only -q`, `uv run ruff check src/ tests/`, `gh run list --workflow=test.yml --limit 3`, plus the targeted greps for `AutonomyLevel.FULL`, `slo_state`, `patch("nthlayer_bench`, and the `test_init*` / `test_default_*` family.
