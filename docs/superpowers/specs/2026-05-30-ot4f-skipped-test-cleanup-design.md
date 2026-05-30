# Delete Skipped Legacy-Measure Tests Design (opensrm-ot4f)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-30. Bead: `opensrm-ot4f`. Rescoped after pre-flight audit revealed the production-module deletion is bigger than the bead description implied; production cleanup is filed as follow-up `opensrm-t5yr`. This bead now covers the tight subset: deleting the four skipped test surfaces only.

**Foundation:**
- `opensrm-mnyj` (closed) — skipped 17 tests across `nthlayer-workers/tests/measure/` that target legacy pre-P3-C.2 modules (`ErrorBudgetGovernance`, FastAPI per-module server, 3-level autonomy enum, legacy `GovernanceAction` shape). The skips were documented with `opensrm-mnyj` references.
- `opensrm-t5yr` (open, P3) — follow-up bead for production-side cleanup (ErrorBudgetGovernance class, api/server.py + 3 sibling api modules, 4 legacy CLI subcommands in cli.py). Larger scope; gets its own brainstorm+plan+R5 cycle.

---

## 1. Problem statement

`opensrm-mnyj` left 17 skipped tests in the suite with `opensrm-mnyj` references for deletion. The skips clutter test output (`18 skipped` line in every pytest run for nthlayer-workers, plus dead-code surface in greps and IDE navigation). With the supersession documented and the live test surface (P3-C.2 deterministic governance in `measure/worker.py`) covered by `test_measure_worker.py::TestReduceAutonomy`, the skipped surfaces serve no purpose and should be removed.

Pre-flight audit also surfaced live production importers of `ErrorBudgetGovernance` (4 CLI subcommands) and `api/server.py` (none beyond the file's own internal imports). The production-module deletion has wider blast radius than the bead description implied — filed separately as `opensrm-t5yr` to keep this bead tight.

---

## 2. Existing surface

- `tests/measure/test_governance.py` — module-level `pytest.mark.skip` with `opensrm-mnyj` reason. 11 tests inside, all targeting the legacy `ErrorBudgetGovernance` class. Whole file is dead.
- `tests/measure/test_api_server.py` — module-level `pytest.mark.skip` AND `pytest.importorskip("fastapi")`. Targets the legacy `measure/api/server.py` FastAPI handler. Whole file is dead.
- `tests/measure/test_types.py` — TWO individual function-level skips:
  - `test_autonomy_level_values()` (lines 62-71): asserts on pre-P3-C.2 3-level enum (`FULL`/`SUPERVISED`/`SUSPENDED`)
  - `test_governance_action_construction()` (lines 133-148): references pre-P3-C.2 `AutonomyLevel.SUPERVISED` + legacy `GovernanceAction` shape
  - Other tests in the same file are LIVE — file stays, only these two functions get removed.
- `tests/measure/test_cli.py` — ONE individual function-level skip:
  - `test_governance_restore_requires_approver()` (lines 197-225): tests legacy `cmd_governance_restore` which passes pre-P3-C.2 enum value `"full"` (current taxonomy uses `"fully_autonomous"`)
  - Other tests in the same file are LIVE — file stays, only this one function gets removed.
- Imports in `test_types.py` and `test_cli.py` that exist solely to satisfy the deleted functions: `AutonomyLevel.SUPERVISED` reference, `GovernanceAction` import, possibly `patch("nthlayer_workers.measure.governance.engine.ErrorBudgetGovernance", ...)`. Audit and clean up after function removal.

---

## 3. Locked decisions

### 3.1 Delete two whole files, prune two test functions, audit imports

- Delete `tests/measure/test_governance.py` outright.
- Delete `tests/measure/test_api_server.py` outright.
- In `tests/measure/test_types.py`: remove `test_autonomy_level_values` (lines 62-71) and `test_governance_action_construction` (lines 133-148) including their preceding `@pytest.mark.skip(...)` decorators and surrounding blank lines.
- In `tests/measure/test_cli.py`: remove `test_governance_restore_requires_approver` (lines 197-225) including its preceding `@pytest.mark.skip(...)` decorator and surrounding blank lines.
- After each function-level removal: scan the file's imports for names now unused; remove or trim those imports too. Ruff F401 will catch any miss in Step 5 verification.

Rationale: matches the bead's literal description, minimum-viable-cleanup, no production-side churn (those are `opensrm-t5yr`'s scope).

### 3.2 Production modules stay (deferred to opensrm-t5yr)

Per § 1: `src/nthlayer_workers/measure/governance/engine.py` (the `ErrorBudgetGovernance` class + the `GovernanceEngine` Protocol), `src/nthlayer_workers/measure/api/server.py` (+ likely-orphaned `queue.py`, `normalise.py`, `response.py`), and the 4 dead CLI subcommands in `cli.py` (`cmd_serve`, `cmd_api_serve`, `cmd_governance_show`, `cmd_governance_restore`) STAY in place for this bead. `opensrm-t5yr` (filed 2026-05-30, P3) tracks the production-side cleanup with the full audit findings.

This means after the bead lands:
- Production code is unchanged
- `bd close ot4f` is correct per the bead's literal description ("delete legacy measure modules and their skipped tests" — the latter half is done; the former half is acknowledged but explicitly out of scope)
- The test suite size drops by 14 tests (11 from test_governance.py + 1 from test_api_server.py module + 2 from test_types.py + 1 from test_cli.py = 15 skipped tests removed; the bead's "17 skipped" figure overcounted by 2)
- `pytest -q` skip count goes from `18 skipped` down to `3 skipped` (15 removed + 3 remaining: any other legacy skips outside the ot4f set)

### 3.3 Verification: pytest + ruff lint + import-graph integrity

After deletions: `uv run pytest -q` must pass (same passing count as before; skip count drops by 15 — the deleted tests are subtracted). `uv run ruff check src/ tests/` must remain clean (any imports we missed in § 3.1's audit step would surface as F401). The smoke test `tests/smoke/test_imports.py` walks every module under `nthlayer_workers` via pkgutil and asserts every `__all__` symbol resolves — confirms no import-graph regression from any imports we trimmed.

### 3.4 One commit, not four

Single atomic commit for the bead. Per project Git Hygiene rule, deleting multiple test files in separate commits would fragment the history without aiding bisect (the tests are all dead-code removal; reverting one is reverting them all). Commit message attributes the deletion to opensrm-ot4f and notes the follow-up bead ID for the production-side work.

---

## 4. Out of scope

- **All production-module deletions** — `engine.py`, `api/server.py`, `api/queue.py`, `api/normalise.py`, `api/response.py`, `api/__init__.py`, the 4 CLI subcommands in `cli.py`, the argparse plumbing for those subcommands, the `governance.yaml` prompt file. All filed in `opensrm-t5yr`.
- **Other skipped tests in the suite** that are NOT in the ot4f set (e.g. if other beads documented their own skips for separate reasons). Out of scope; bead-specific.
- **The `governance.yaml` prompt file** — referenced only by `ErrorBudgetGovernance`, deletion bundled with `opensrm-t5yr`.
- **Touching `cmd_governance_show`'s live test** (`test_cli.py::test_governance_show`, line 184) — this test exercises a live legacy CLI subcommand that still works against the still-alive `ErrorBudgetGovernance`. Stays until `opensrm-t5yr` deletes both the subcommand and the test.

---

## 5. Test surface

No new tests. The bead's test surface IS the deletion. Acceptance:
- `pytest --collect-only tests/measure/test_governance.py` returns "no tests collected" (file gone) — exit non-zero is expected behaviour.
- `pytest --collect-only tests/measure/test_api_server.py` same.
- `pytest -q tests/measure/test_types.py` skip count == 0 (was 2).
- `pytest -q tests/measure/test_cli.py` skip count == 0 (was 1).
- `pytest -q` full suite: passing count unchanged from baseline (1890); skip count drops from 18 to 3.
- `ruff check src/ tests/` exit 0 (no F401 from any unused imports left behind).

---

## 6. Implementation plan

Five edits (one commit):

1. Delete `tests/measure/test_governance.py`.
2. Delete `tests/measure/test_api_server.py`.
3. Edit `tests/measure/test_types.py`: remove lines 62-71 (`test_autonomy_level_values` + its skip decorator) and lines 133-148 (`test_governance_action_construction` + its skip decorator). Audit imports of `AutonomyLevel.SUPERVISED` / `GovernanceAction` — if no live test uses them, remove from import block.
4. Edit `tests/measure/test_cli.py`: remove lines 197-225 (`test_governance_restore_requires_approver` + its skip decorator). Audit imports of `cmd_governance_restore` / patch-target for `ErrorBudgetGovernance` — remove if unused.
5. Verify: `pytest -q` passes, skip count down by 15; `ruff check src/ tests/` clean.

Commit. Close bead with reference to `opensrm-t5yr` follow-up.

---

## 7. Effort

- 4 file edits (2 deletes + 2 prune-and-import-clean)
- 1 commit
- No R5 supervise — deletion-only, no logic, no new code. Per Output Token Management: R5 ceremony on dead-code removal exceeds bead value.
- 0.25 session total
