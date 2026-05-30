# nthlayer-bench CI Test Workflow Design (opensrm-kx5x)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-30. Bead: `opensrm-kx5x`. Parent pattern: `opensrm-1kfs` (closed) — the same workflow shape was added to `nthlayer-workers` and cleared its lint drift in one bead.

**Foundation:**
- `nthlayer-workers/.github/workflows/test.yml` — canonical reference: push + PR triggers on `main`, Python 3.11/3.12/3.13 matrix (`fail-fast: false`), sibling checkout of `nthlayer-common`, `uv sync --extra dev`, `ruff check src/ tests/`, `pytest -q`.
- `nthlayer-bench/.github/workflows/` — already ships `release-please.yml`, `release.yml`, `dependabot-automerge.yml`. Missing: `test.yml`. Pre-demo external-visibility concern: viewers see an empty Actions tab for the test-on-push surface.
- `nthlayer-bench/pyproject.toml` — already declares `ruff>=0.8` in dev deps and `[tool.ruff]` config (`target-version = "py311"`, `line-length = 100`). The bead's original note ("either add the dev dep or skip the ruff step initially") is stale — ruff is configured.
- `nthlayer-bench/pyproject.toml` — declares `nthlayer-common = { path = "../nthlayer-common", editable = true }`. Same sibling-checkout pattern as workers.

---

## 1. Problem statement

`nthlayer-bench` ships release-please + smoke gate + dependabot but has no CI test workflow. Push and PR to `main` run zero tests, zero lint. Pre-demo external visibility (Actions tab) shows an empty test surface. Workers solved the same gap via `opensrm-1kfs` in a single bead — copy that shape to bench.

Concurrent pre-flight observation: `uv run ruff check src/ tests/` on bench's current `main` reports 4 errors. Without addressing them first, the workflow's first push would be red. Per design § 3.2, fix in the same bead.

---

## 2. Existing surface

- Workers `test.yml`: 57 lines, security note (workflow uses only workflow-controlled context, no user-controllable strings interpolated into `run:`), one `test` job, sibling-checkout step pulling `rsionnach/nthlayer-common` to `../nthlayer-common`, then `uv sync` + `ruff check` + `pytest -q`.
- Bench's `pyproject.toml` ruff config: `target-version = "py311"`, `line-length = 100`. No per-file ignores beyond standard. Ruleset is whatever ruff's default + project overrides.
- Bench's current ruff state (verified by `uv run ruff check src/ tests/`):
  - `src/nthlayer_bench/sre/brief.py:15`: `F401 typing.Any imported but unused`
  - `tests/test_app.py:236`: `F841 Local variable pilot is assigned to but never used`
  - `tests/test_sre_brief.py:19`: `F401 nthlayer_bench.sre.brief.BriefError imported but unused`
  - `tests/test_widgets_reasoning_capture.py:9`: `F401 textual.widgets.Label imported but unused`
- Bench's test count: 307 (per `pytest --collect-only`), up from the 272 noted in the kx5x bead description (drift since 2026-05-02).

---

## 3. Locked decisions

### 3.1 Workflow shape: byte-mirror of workers' test.yml

`nthlayer-bench/.github/workflows/test.yml` is the exact same shape as workers' test.yml with `nthlayer-workers` → `nthlayer-bench` substitutions. Preserves:
- Security note prose (still applies — bench's workflow also references only workflow-controlled context)
- `fail-fast: false` matrix policy (full signal across Py versions)
- Sibling checkout of `nthlayer-common`
- `uv sync --extra dev --python ${{ matrix.python-version }}`
- `ruff check src/ tests/` step
- `pytest -q` step

No bench-specific additions (e.g. textual snapshot tests, TUI smoke). The bench test suite is pure pytest; the existing 307 tests run under `pytest -q` without special infrastructure.

Rationale: parity beats novelty. Diverging from the workers shape would create a per-repo maintenance burden for future ecosystem-wide CI changes.

### 3.2 Ruff drift fixed in the same bead

All 4 ruff errors fixed inline. None require behavioral change — they're dead-code removal:
- 3× `F401` (unused imports): remove the offending import line. Auto-fixable via `ruff --fix` but applied as explicit edits in the bead so each removal is visible in `git diff`.
- 1× `F841` (unused local `pilot` in test_app.py:236): inspect the test to decide whether to remove the assignment or use `_` prefix. If `pilot` is unused because the test relies on side-effects of its construction, prefix with `_` to express intent. If it's actually dead code, remove the line.

After fixes: `uv run ruff check src/ tests/` clean; `uv run pytest -q` continues at 307 passed.

Rationale: workflow ships green on first push. Filing drift as a separate follow-up bead introduces a flaky-CI window between this bead landing and the cleanup; the 1kfs precedent fixed drift inline.

### 3.3 No workflow runtime config beyond workers'

No `concurrency:` group, no `cache:` for pip/uv beyond what `setup-uv@v7` provides by default, no Codecov upload, no per-OS matrix. All deferred — if needed, they get their own beads. YAGNI.

### 3.4 Inspect F841 (`pilot`) decision deferred to implementation

The `pilot` variable in `test_app.py:236` could be:
- (a) Genuinely dead: `pilot = await app.run_test()` then never used — remove the line
- (b) Side-effect-only: pilot context manager exit is what the test relies on — prefix with `_pilot` to express intent
- (c) Refactor candidate: the test was simplified at some point and the variable became vestigial — remove

The implementation step inspects the test and picks. All three resolutions are mechanical; the decision is not load-bearing for the bead's scope.

---

## 4. Out of scope

- Bench-specific CI extensions (textual snapshot regression, TUI smoke gate) — own bead if ever wanted
- Cross-repo integration coverage involving bench (already lives in `nthlayer/test/integration-three-tier.sh`)
- Cache tuning beyond `setup-uv@v7` defaults
- Per-OS matrix (linux only, matching workers)
- Codecov / coverage badges
- Mypy step (workers doesn't have one either; if added later, add to both for parity)
- Filing a separate bead for the ruff drift (per § 3.2 it's in scope here)

---

## 5. Test surface

No new unit tests. The bead's test surface IS the new CI workflow — its successful first run on push to `main` is the acceptance signal. Pre-push verification:

```
cd nthlayer-bench && uv run ruff check src/ tests/    # → exit 0
cd nthlayer-bench && uv run pytest -q                  # → 307 passed
```

Both must pass locally before the workflow gets pushed.

---

## 6. Implementation plan

Four code edits + one new file:

1. `nthlayer-bench/src/nthlayer_bench/sre/brief.py` — remove unused `typing.Any` import (line 15).
2. `nthlayer-bench/tests/test_sre_brief.py` — remove unused `BriefError` import (line ~19).
3. `nthlayer-bench/tests/test_widgets_reasoning_capture.py` — remove unused `textual.widgets.Label` import (line 9).
4. `nthlayer-bench/tests/test_app.py` — inspect `pilot` at line 236, apply the appropriate one of § 3.3's three resolutions.
5. `nthlayer-bench/.github/workflows/test.yml` (new file) — byte-mirror of workers' `test.yml`.

After each edit, verify `ruff check src/ tests/` reports one less error. After all four ruff fixes, run `pytest -q` to confirm 307 passed. Then add the workflow file.

Commit policy: one commit for the ruff fixes (atomic dead-code cleanup), one commit for the new workflow file. Both authored under bead `opensrm-kx5x`.

---

## 7. Effort

- 4 ruff fixes: ~5 LOC removed across 4 files (auto-fixable for 3 of them)
- 1 new workflow file: ~57 LOC (mirror)
- 2 commits
- R5 supervise (lighter pass — YAML + small Python edits, reviewers focus on workflow security note correctness and ruff-fix non-regression)
- 0.5 session total
