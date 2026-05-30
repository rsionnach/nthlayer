# opensrm-kx5x Implementation Plan — `nthlayer-bench` CI Test Workflow

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub Actions test workflow to `nthlayer-bench` (parity with `nthlayer-workers`'s test.yml) and clear the 4 pre-existing ruff errors so the workflow ships green on first push.

**Architecture:** Byte-mirror of `nthlayer-workers/.github/workflows/test.yml` with `nthlayer-workers` → `nthlayer-bench` substitutions. Same Python 3.11/3.12/3.13 matrix, same sibling-checkout of `nthlayer-common`, same `ruff check + pytest -q` shape. Four small dead-code removals fix the existing lint drift in the same bead so the workflow ships green on first push (mirrors the 1kfs precedent).

**Tech Stack:** GitHub Actions YAML, `astral-sh/setup-uv@v7`, ruff, pytest. No new dependencies.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-30-kx5x-bench-ci-workflow-design.md` (committed at `nthlayer@fef52ba`).

---

## File Structure

**New file:**
- `nthlayer-bench/.github/workflows/test.yml` — CI test workflow (57 lines, mirror of workers').

**Modified files:**
- `nthlayer-bench/src/nthlayer_bench/sre/brief.py` — remove unused `typing.Any` import (line 15).
- `nthlayer-bench/tests/test_app.py` — drop the unused `as pilot` binding at line 236 (the async-context-manager is used for its side effects only; no body reference).
- `nthlayer-bench/tests/test_sre_brief.py` — remove unused `BriefError` import (line ~19).
- `nthlayer-bench/tests/test_widgets_reasoning_capture.py` — remove unused `textual.widgets.Label` import (line 9).

**No new tests.** The new CI workflow IS the test surface; acceptance is its first push to `main` running green.

**Task ordering rationale:** Ruff fixes first (Task 1) — they verify clean before the workflow lands. Workflow file second (Task 2) — atomic, ships green. R5 supervise third (Task 3).

---

## Task 1: Fix 4 pre-existing ruff errors

**Files:**
- Modify: `nthlayer-bench/src/nthlayer_bench/sre/brief.py:15`
- Modify: `nthlayer-bench/tests/test_app.py:236`
- Modify: `nthlayer-bench/tests/test_sre_brief.py:~19`
- Modify: `nthlayer-bench/tests/test_widgets_reasoning_capture.py:9`

- [ ] **Step 1.1: Confirm the 4 errors**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && uv run ruff check src/ tests/
```

Expected output ends with:
```
Found 4 errors.
[*] 3 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```

If the count is different, STOP and report — the spec's drift list is stale and the plan needs review.

- [ ] **Step 1.2: Fix F401 in `src/nthlayer_bench/sre/brief.py`**

Read the file around line 15:

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && sed -n '10,20p' src/nthlayer_bench/sre/brief.py
```

The line will be `from typing import Any` (or similar) where `Any` is no longer referenced anywhere else in the file. Remove just the offending name from the `from typing import ...` line. If `Any` is the only name imported, remove the entire line. If others remain (e.g. `from typing import Any, Optional`), drop only `Any`.

- [ ] **Step 1.3: Fix F841 in `tests/test_app.py:236`**

The current line is:
```python
            async with app.run_test() as pilot:
```

`pilot` is bound but never read in the test body (the test uses `app.client`, `app._client`, `app._on_exit_app`). Drop the `as pilot` binding entirely — the async context manager still runs its `__aenter__`/`__aexit__`:

```python
            async with app.run_test():
```

(Rationale per spec § 3.4: option (b) "side-effect-only" but cleaner than `_pilot` — if it's never referenced, don't bind it.)

- [ ] **Step 1.4: Fix F401 in `tests/test_sre_brief.py`**

Find the offending import:

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && sed -n '15,25p' tests/test_sre_brief.py
```

Expected: a `from nthlayer_bench.sre.brief import (...)` block listing `BriefError` among other names. Drop `BriefError` from the list (keep the others). If `BriefError` is on its own line inside the parenthesised import, just delete that line.

- [ ] **Step 1.5: Fix F401 in `tests/test_widgets_reasoning_capture.py:9`**

Current line 9 is:
```python
from textual.widgets import Input, Label, Static
```

`Label` is unused. Replace with:
```python
from textual.widgets import Input, Static
```

- [ ] **Step 1.6: Verify all 4 fixes cleared**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && uv run ruff check src/ tests/
```

Expected output:
```
All checks passed!
```

- [ ] **Step 1.7: Verify tests still pass**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && uv run pytest -q
```

Expected: 307 passed (matches the pre-fix baseline).

If a test fails — particularly `test_app.py::TestBenchApp::test_app_close_client_on_exit` or similar around line 236 — the `as pilot` drop may have hit a downstream reference. Restore the binding as `_pilot` instead (option (b) in spec § 3.4): `async with app.run_test() as _pilot:`.

- [ ] **Step 1.8: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && git add src/nthlayer_bench/sre/brief.py tests/test_app.py tests/test_sre_brief.py tests/test_widgets_reasoning_capture.py && git commit -m "$(cat <<'EOF'
chore: clear ruff drift (3 F401 + 1 F841) · opensrm-kx5x

Pre-flight cleanup before adding the test CI workflow. Drops unused
typing.Any import, unused BriefError import, unused textual.widgets.Label
import, and the unused `as pilot` binding on app.run_test() (context
manager runs for its side effects, no body reference). 307 tests still
pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `test.yml` workflow

**Files:**
- Create: `nthlayer-bench/.github/workflows/test.yml`

- [ ] **Step 2.1: Verify the workers' workflow file shape**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers && cat .github/workflows/test.yml
```

Confirm the file is 57 lines, references `nthlayer-workers` and `nthlayer-common` paths, declares Py 3.11/3.12/3.13 matrix with `fail-fast: false`, runs `uv sync --extra dev` + `uv run ruff check src/ tests/` + `uv run pytest -q`.

- [ ] **Step 2.2: Create the bench workflow file**

Write the following to `nthlayer-bench/.github/workflows/test.yml`:

```yaml
name: Test

# Security note (per the GitHub Actions injection guide): this workflow
# only references workflow-controlled context (matrix.python-version)
# and never interpolates user-controllable strings (PR titles, commit
# messages, issue bodies, etc.) into `run:` shells. No env-quoting
# precautions needed because no untrusted input flows through.

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      # Don't cancel the rest of the matrix if one Python version fails —
      # operators on different Python versions get full signal.
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      # nthlayer-bench depends on nthlayer-common via a relative-path
      # uv source (`path = "../nthlayer-common"`). Check out both repos
      # as siblings so the path resolves the same way it does locally.
      - name: Checkout nthlayer-bench
        uses: actions/checkout@v6
        with:
          path: nthlayer-bench

      - name: Checkout nthlayer-common (sibling)
        uses: actions/checkout@v6
        with:
          repository: rsionnach/nthlayer-common
          path: nthlayer-common

      - name: Install uv
        uses: astral-sh/setup-uv@v7

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Sync dependencies (with dev extras)
        working-directory: nthlayer-bench
        run: uv sync --extra dev --python ${{ matrix.python-version }}

      - name: Lint (ruff check)
        working-directory: nthlayer-bench
        run: uv run ruff check src/ tests/

      - name: Run tests
        working-directory: nthlayer-bench
        run: uv run pytest -q
```

- [ ] **Step 2.3: Sanity-check the YAML is parseable**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`.

- [ ] **Step 2.4: Diff against workers' workflow to confirm parity**

```
diff /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers/.github/workflows/test.yml /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench/.github/workflows/test.yml
```

Expected: differences only in the path tokens (`nthlayer-workers` → `nthlayer-bench`). No structural changes, no extra steps, no missing steps.

If the diff shows anything other than the path-token substitutions, STOP and reconcile — drift from the canonical shape is the bead's anti-goal.

- [ ] **Step 2.5: Final pre-push verification**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && uv run ruff check src/ tests/ && uv run pytest -q
```

Expected: ruff clean + 307 passed. Same outputs the CI workflow will produce on first push.

- [ ] **Step 2.6: Commit**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-bench && git add .github/workflows/test.yml && git commit -m "$(cat <<'EOF'
ci: add test workflow (parity with nthlayer-workers) · opensrm-kx5x

Push + PR to main, Python 3.11/3.12/3.13 matrix (fail-fast: false),
sibling checkout of nthlayer-common, uv sync + ruff check + pytest -q.
Closes the pre-demo gap where the bench Actions tab showed empty for
the test-on-push surface. Mirror of workers' test.yml; drift here
should be intentional and explained.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: R5 supervise + bead close

**Files:** None modified. Validates the bead is shippable.

- [ ] **Step 3.1: Check git status across affected repos**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem && for d in nthlayer-bench nthlayer; do echo "--- $d ---"; (cd $d && git status --short && git log --oneline -3); done
```

Expected: both repos clean. `nthlayer-bench` HEAD = Task 2 commit (workflow), HEAD~1 = Task 1 commit (ruff fixes). `nthlayer` HEAD = spec commit `fef52ba`, plan commit (next step).

- [ ] **Step 3.2: Invoke /r5-supervise kx5x**

```
/r5-supervise kx5x
```

Expected: 4 sequential R5 passes. Reviewer focus will be lighter than a Python-source bead — this is YAML + dead-code removal:
- Correctness: YAML schema validity, ruff fixes don't change behavior, side-effect-only context manager pattern preserved on `app.run_test()`
- Clarity: workflow comments and security note match workers'
- Edge cases: matrix interactions, what happens if `nthlayer-common`'s `main` is broken (sibling-checkout failure mode), token permissions for `actions/checkout@v6`
- Excellence: parity with workers as a feature (operators can grep one shape across the ecosystem), CI surface as documentation

Expect few findings. R5 supervisor auto-closes on all-passes-clean.

- [ ] **Step 3.3: (If R5 supervisor doesn't auto-close) manually close the bead**

```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd close kx5x --reason "Added test.yml workflow to nthlayer-bench mirroring workers' shape (Py 3.11/3.12/3.13 matrix, sibling nthlayer-common checkout, uv sync + ruff + pytest). Cleared 4 pre-existing ruff errors (3 F401 + 1 F841) so the workflow ships green on first push. 307 tests pass locally + ruff clean. R5 reviewed."
```

Verify:
```
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm && bd show kx5x | head -5
```

Expected: `[● P2 · CLOSED]`.

---

## Self-Review Notes

**Spec coverage map:**
- § 3.1 (byte-mirror of workers' test.yml) → Task 2.2 (file content) + Task 2.4 (diff verification step)
- § 3.2 (ruff drift fixed inline) → Task 1 (all four errors, one commit)
- § 3.3 (no extras) → Task 2.2 produces only the documented steps; no concurrency, cache tuning, codecov, mypy, or per-OS matrix
- § 3.4 (F841 pilot decision deferred) → Task 1.3 picks option (b) (drop `as pilot`); Task 1.7 fallback to `_pilot` if tests reveal the binding is needed

**Placeholder scan:** No "TBD" / "TODO" / "fill in" markers. Every file path is exact. Every command has expected output. The F841 fix has a documented fallback if Step 1.7 fails.

**Type / value consistency:** Workflow filename, matrix versions, and path substitutions match the spec verbatim. Commit message bead ID is consistent (`opensrm-kx5x`). The `nthlayer-bench` ↔ `nthlayer-workers` path substitution is the only difference between workers' and bench's workflow files per § 3.1.
