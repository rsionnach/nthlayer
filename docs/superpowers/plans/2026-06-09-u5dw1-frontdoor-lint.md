# u5dw.1 Front-door Python helper lint coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire ruff lint coverage for the front-door's 5 Python helpers via a new root `pyproject.toml` and a new `python-lint` CI job, unblocking `opensrm-314j`.

**Architecture:** Single-repo change in `nthlayer/`. Add `pyproject.toml` at repo root holding only `[tool.ruff]` (ecosystem floor, pinned ruff version via the CI invocation). Add `python-lint` job to `.github/workflows/ci.yml` parallel to the existing `shell-syntax` job. Update header comment and `docs/integration-testing.md`. No mypy, no venv setup, no Python `[project]` block.

**Tech Stack:** ruff 0.15.15 (pinned via `uvx ruff@0.15.15`); `astral-sh/setup-uv@v6` GitHub Action; ecosystem ruff floor (`py311`, `line-length=100`, `select = ["E4","E7","E9","F","I","UP","SIM","B"]`) mirrored from `nthlayer-common/pyproject.toml`.

**Spec:** `docs/superpowers/specs/2026-06-09-u5dw1-frontdoor-lint-design.md` (commit `42fcbad`).

---

### Task 1: Capture baseline ruff findings before any config lands

**Files:** None (read-only investigation).

This task exists so subsequent tasks know exactly what autofix produces, and what manual `# noqa: E501` suppressions (if any) are needed. The spec mandates: "Findings that autofix get committed in the same change as the config. Findings that don't autofix … E501 banners suppressed inline."

- [ ] **Step 1: Snapshot the current state of the 5 helper files**

Run:
```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
git status
```
Expected: `working tree clean` on branch `main`. If not clean, stop and reconcile before proceeding.

- [ ] **Step 2: Run ruff against the helpers WITHOUT any config (defaults only)**

This gives the universe of findings before we narrow to the ecosystem floor.

Run:
```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
uvx ruff@0.15.15 check test/ demo/ --output-format=concise
```
Expected: some number of findings (likely a handful — these helpers are mature). Save the full output to a scratch note for the next step. Don't fix anything yet.

- [ ] **Step 3: Run ruff with the planned select set explicitly**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/ \
  --select E4,E7,E9,F,I,UP,SIM,B \
  --target-version py311 \
  --line-length 100 \
  --output-format=concise
```
Expected: same as step 2 or a strict subset. This is the actual gate baseline. Note in a scratch comment whether any E501 findings appear (line-length violations on docstring banners are the only suppression contemplated by the spec).

- [ ] **Step 4: Decide autofix vs noqa strategy from the findings**

Look at the findings:
- If only autofixable findings appear (I001 import-order, F401 unused-imports, UP*-style modernisations): plan is to land them via `--fix` in Task 4.
- If E501 appears on a docstring banner line: plan is to add `# noqa: E501` to those specific lines in Task 4.
- If any other non-autofix finding appears (B-rule bug-likely, SIM-rule simplification): STOP and surface it. The spec says these go to a follow-up bead, not this one. The bead lands a clean gate, not a refactor — but if a non-autofix finding blocks the gate going green, the plan needs amending before proceeding.

No commit in this task — it's investigation only.

---

### Task 2: Create the root pyproject.toml

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write the file**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/pyproject.toml` with this exact content:

```toml
# Front-door Python tooling — config-only, no [project] block.
#
# The front-door hosts 5 Python helpers (test/three_tier_assertions.py,
# test/fake-service.py, test/webhook-receiver.py, demo/render_explanation.py,
# demo/scenario-runner.py) used by demo and integration orchestration.
# Implementation packages live in the sibling repos
# (nthlayer-{common,core,workers,bench,generate,override-adapter}).
#
# The ruff config below mirrors the ecosystem floor from
# nthlayer-common/pyproject.toml. The ruff *version* is pinned at the
# CI invocation site (`.github/workflows/ci.yml`, `python-lint` job),
# not here — the front-door has no venv to lock.
#
# force-exclude = true makes extend-exclude hold even when ruff is
# invoked with explicit paths (e.g. `ruff check test/test_jmy18_smoke.py`).
# test_jmy18_smoke.py is excluded per the nthlayer-frontdoor-audit
# 2026-06-05 §2 — it's a standalone JMY18 smoke test, not an
# integration helper.
[tool.ruff]
target-version = "py311"
line-length = 100
force-exclude = true
extend-exclude = ["test/test_jmy18_smoke.py"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I", "UP", "SIM", "B"]
```

- [ ] **Step 2: Confirm ruff picks up the config**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/ --show-settings 2>&1 | grep -E "(target_version|line_length|select|force_exclude|extend_exclude)" | head -20
```
Expected output includes:
- `target_version: Py311`
- `line_length: 100`
- `force_exclude: true`
- `select` containing `E4, E7, E9, F, I, UP, SIM, B` (or their canonical expansions)
- `extend_exclude` containing `test/test_jmy18_smoke.py`

- [ ] **Step 3: Confirm the exclusion holds on explicit-path invocation**

Run:
```bash
uvx ruff@0.15.15 check test/test_jmy18_smoke.py
```
Expected: `All checks passed!` OR exit 0 with output indicating the file was skipped (ruff prints `warning: No Python files found under the given path(s)` or similar when force-exclude removes the only target). The key signal is **exit code 0** even if the file has lint issues; force-exclude must keep the file out of the gate regardless of how it's named.

- [ ] **Step 4: Re-run the actual gate to get the post-config baseline**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/
```
Expected: matches the Task 1 step 3 finding set exactly. If it doesn't match, something about the config is wrong — investigate before continuing.

- [ ] **Step 5: Commit the config alone**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
git add pyproject.toml
git commit -m "$(cat <<'EOF'
build(u5dw.1): add front-door pyproject.toml with ruff config

Config-only, no [project] block — the front-door hosts demo and
integration helpers but is not itself a PyPI package. Ruff config
mirrors the ecosystem floor from nthlayer-common (py311,
line-length 100, the standard select set). force-exclude = true
keeps test_jmy18_smoke.py out of the gate even on explicit-path
invocation. Ruff version pinned at the CI invocation site, not
here — front-door has no venv to lock.

Bead: opensrm-u5dw.1.
Spec: docs/superpowers/specs/2026-06-09-u5dw1-frontdoor-lint-design.md
EOF
)"
```
Expected: commit succeeds, working tree clean.

---

### Task 3: Apply baseline cleanup to the helpers

**Files:**
- Modify (per Task 1 findings): some subset of `test/three_tier_assertions.py`, `test/fake-service.py`, `test/webhook-receiver.py`, `demo/render_explanation.py`, `demo/scenario-runner.py`.

This task makes the gate go green. Do not introduce behavioural changes — only autofix-class refactors and targeted `# noqa: E501` suppressions per the Task 1 decision.

- [ ] **Step 1: Run ruff autofix in dry-run mode first**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/ --fix --diff
```
Expected: a unified diff showing exactly the changes ruff would apply. Eyeball it:
- Import re-orderings (I001) — fine, land them.
- Unused-import removals (F401) — fine if the import is genuinely unused (read the file context to confirm it's not e.g. a side-effect-only import like `import dotenv`).
- UP-class modernisations (`typing.List` → `list[…]`, etc.) — fine on py311.
- SIM-class simplifications — review each one; refuse if it changes readable structure for no real win.

If anything in the diff looks behavioural or risky, STOP and surface it — this is the line between "clean baseline" and "refactor", and the spec puts non-trivial cleanups in a follow-up bead.

- [ ] **Step 2: Apply the autofixes**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/ --fix
```
Expected: prints the count of fixed findings; the working tree now has modified files matching the dry-run diff.

- [ ] **Step 3: Add `# noqa: E501` suppressions on any docstring banner lines that remain**

Only do this if Task 1 step 3 surfaced E501 findings. For each remaining E501 location, append `# noqa: E501` to the offending line (using `Edit`, not sed). Do not change the line content — the suppression preserves the deliberate banner formatting.

Example pattern (only apply where Task 1 actually flagged):
```python
# ============================================================ noqa: E501
```
becomes — wait, that's a comment so E501 applies to the whole line. The correct shape is:
```python
"""Some long docstring banner exceeding 100 characters that we keep intentionally."""  # noqa: E501
```

If Task 1 step 3 found no E501 findings, skip this step entirely.

- [ ] **Step 4: Re-run the gate to confirm green**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/
```
Expected: `All checks passed!` (exit 0). If anything still flags, return to Step 1 of this task — something in the dry-run was missed.

- [ ] **Step 5: Run the existing shell syntax gate to confirm no collateral damage**

Run:
```bash
find demo test -maxdepth 2 -name '*.sh' -type f -exec bash -n {} \;
```
Expected: no output (silent success). Any FAIL means an earlier step touched a shell script incorrectly — investigate before committing.

- [ ] **Step 6: Commit the cleanup**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
git add test/ demo/
git status
```
Verify the staged set is only the helper `.py` files modified by ruff. Then:
```bash
git commit -m "$(cat <<'EOF'
style(u5dw.1): baseline cleanup of front-door Python helpers

Apply ruff --fix output across the 5 helpers to clear the
new gate. Import re-orderings (I001), unused-import removals
(F401), and py311 modernisations (UP-rules) only — no
behavioural changes. Non-autofix findings deferred to
follow-up beads per the u5dw.1 spec.

Bead: opensrm-u5dw.1.
EOF
)"
```

If Task 1 step 3 found zero findings (best case), skip this entire task — note in the next task's commit message that the baseline was already clean.

---

### Task 4: Add the `python-lint` CI job

**Files:**
- Modify: `.github/workflows/ci.yml` (currently 44 lines, all in one `shell-syntax` job).

- [ ] **Step 1: Read the current ci.yml to know exact insertion point**

Already known from earlier exploration:
- Lines 1-22: header comment block.
- Lines 23-29: `on:` trigger.
- Lines 30-44: single job `shell-syntax`.

The new `python-lint` job goes after `shell-syntax`, indented at the same level (2 spaces under `jobs:`).

- [ ] **Step 2: Replace the header comment block**

Use the Edit tool to swap the old comment for the spec-prescribed version. Old block (lines 3-20, approximate):

```
# Shell-syntax regression guard for the front-door repo.
#
# Post-consolidation this repo hosts no Python code at the root —
# implementation lives in nthlayer-{common,core,workers,bench,generate}
# (each with its own CI). The original ci.yml ran ruff/mypy/pytest
# against src/ tests/ examples/ paths that no longer exist; it failed
# every push from 2026-04-26 onward until this rewrite (opensrm-0buj).
#
# What CI does for the front-door now:
#   - This workflow: bash -n on every demo/ and test/ shell script.
#   - .github/workflows/docs.yml: mkdocs build --strict on docs-site/.
#   - .github/workflows/demo-paths.yml: cmd_start path-resolution test (opensrm-oey5).
#   - .github/workflows/integration-three-tier.yml: nightly cross-repo smoke.
#   - .github/workflows/release.yml: meta-v* tag publish to PyPI.
#
# Anything Python-shaped is the responsibility of the per-component repo.
```

New block:

```
# CI gates for the front-door repo.
#
# Post-consolidation this repo hosts only integration- and demo-shaped
# Python helpers at the root — implementation lives in
# nthlayer-{common,core,workers,bench,generate} (each with its own CI).
# The original ci.yml ran ruff/mypy/pytest against src/ tests/ examples/
# paths that no longer exist; it failed every push from 2026-04-26 onward
# until this rewrite (opensrm-0buj).
#
# What CI does for the front-door now:
#   - shell-syntax (this workflow): bash -n on every demo/ and test/ shell script.
#   - python-lint  (this workflow): ruff check on the 5 root helpers (opensrm-u5dw.1).
#   - .github/workflows/docs.yml: mkdocs build --strict on docs-site/.
#   - .github/workflows/demo-paths.yml: cmd_start path-resolution test (opensrm-oey5).
#   - .github/workflows/integration-three-tier.yml: nightly cross-repo smoke.
#   - .github/workflows/release.yml: meta-v* tag publish to PyPI.
#
# Per-component Python testing remains the responsibility of each sibling repo.
```

- [ ] **Step 3: Add the python-lint job after the shell-syntax job**

Append (do not replace) below the existing `shell-syntax` job, at the same indent under `jobs:`:

```yaml

  python-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: install uv
        uses: astral-sh/setup-uv@v6

      - name: ruff check on test/ and demo/ helpers
        run: uvx ruff@0.15.15 check test/ demo/
```

Note the leading blank line before `python-lint:` so the two jobs are visually separated.

- [ ] **Step 4: Validate the workflow YAML locally**

If `actionlint` is available:
```bash
actionlint .github/workflows/ci.yml
```
Expected: no findings.

If not available, fall back to a YAML parse:
```bash
uvx pyyaml -c 'import yaml,sys; yaml.safe_load(open(".github/workflows/ci.yml")); print("OK")'
```
— if that fails (uvx doesn't ship pyyaml as a callable), use:
```bash
python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci.yml")); print("OK")'
```
Expected: `OK`. If neither python3-with-yaml nor actionlint is available, do a visual review of the indentation and trust GitHub to flag it on push.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci(u5dw.1): add python-lint job for front-door helpers

Parallel to shell-syntax: runs ruff 0.15.15 (pinned at the
invocation site via uvx ruff@VERSION) against test/ and demo/.
~10s job, no venv setup. Header comment updated to reflect
that the front-door now hosts a small set of Python helpers
at the root.

Pin tracks nthlayer-common's resolved ruff version, not the
loose >=0.8 constraint — when common bumps, the front-door
pin gets the same bump in a follow-up.

Bead: opensrm-u5dw.1.
Unblocks: opensrm-314j.
EOF
)"
```

---

### Task 5: Update docs/integration-testing.md

**Files:**
- Modify: `docs/integration-testing.md` (location of the new Lint subsection).

- [ ] **Step 1: Find the right insertion point**

Run:
```bash
grep -n "^##\|^###" docs/integration-testing.md | head -20
```
Look for a heading near the top like "Running the suite", "Running tests", or "Overview". The new `### Lint` subsection goes after the first such "running" section, before deeper-detail content.

- [ ] **Step 2: Insert the Lint subsection**

Using Edit, add after the chosen insertion point:

```markdown
### Lint

The front-door's 5 Python helpers (`test/three_tier_assertions.py`,
`test/fake-service.py`, `test/webhook-receiver.py`,
`demo/render_explanation.py`, `demo/scenario-runner.py`) are linted by
the `python-lint` job in `.github/workflows/ci.yml` using the ecosystem
ruff floor (`py311`, `line-length=100`, the same `select` set as
`nthlayer-common`). Local invocation:

```bash
uvx ruff@0.15.15 check test/ demo/
```

`test/test_jmy18_smoke.py` is excluded — it's a standalone JMY18 smoke
test, not an integration helper.
```

- [ ] **Step 3: Confirm docs build still passes**

If the front-door has a mkdocs config and mkdocs is locally available:
```bash
mkdocs build --strict --config-file docs-site/mkdocs.yml 2>&1 | tail -20
```
Expected: `INFO - Documentation built in N.NN seconds` (or similar). If `docs/integration-testing.md` isn't part of the mkdocs site, this step is a no-op — note that and move on.

- [ ] **Step 4: Commit**

```bash
git add docs/integration-testing.md
git commit -m "$(cat <<'EOF'
docs(u5dw.1): document the python-lint gate

Short Lint subsection in docs/integration-testing.md
pointing at the new CI job and giving the local invocation.

Bead: opensrm-u5dw.1.
EOF
)"
```

---

### Task 6: Smoke-verify the gate isn't a no-op

**Files:** None permanently — temporary edits reverted in the same task.

This is the spec's "deliberately injected F401 causes both local and CI gates to fail" verification. It catches a silent regression: a malformed pyproject.toml or a mis-wired CI step that exits 0 even when ruff would flag.

- [ ] **Step 1: Inject a deliberate F401 finding**

Use Edit to add a new unused import line near the top of `test/fake-service.py`:

```python
import dataclasses  # u5dw.1 smoke-verify — REVERT before merge
```

Choose `dataclasses` because it's stdlib (no install needed), unused in the file, and the comment makes its purpose unmissable.

- [ ] **Step 2: Confirm the local gate flags it**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/
```
Expected: non-zero exit, output containing `F401` and `dataclasses` and `test/fake-service.py`.

If the gate does NOT flag it, the config is wrong — go back to Task 2 and investigate.

- [ ] **Step 3: Revert the injection**

Use Edit to remove the line added in step 1. Then:
```bash
git diff test/fake-service.py
```
Expected: empty diff (file restored to the committed state).

- [ ] **Step 4: Confirm the gate is green again**

Run:
```bash
uvx ruff@0.15.15 check test/ demo/
```
Expected: `All checks passed!`, exit 0.

No commit in this task — the only file changes are reverted in step 3.

---

### Task 7: Push and confirm CI green

**Files:** None.

- [ ] **Step 1: Confirm clean local state**

Run:
```bash
git status
git log --oneline -5
```
Expected: working tree clean. Last 4 commits should be Tasks 2, 3 (if applicable), 4, 5.

- [ ] **Step 2: Push to the remote**

Run:
```bash
git push nthlayer-remote main
```
Note: the repo uses `nthlayer-remote` as its remote name (per the handoff: "ahead of nthlayer-remote/main by 18 commits"). If `nthlayer-remote` is not a configured remote, fall back to `git remote -v` and use whichever remote points at the canonical GitHub repo.

Expected: push succeeds.

- [ ] **Step 3: Watch the CI run**

Run:
```bash
gh run watch --exit-status
```
Expected: both `shell-syntax` and `python-lint` jobs report green. If `python-lint` fails, capture the run number and the failing job log, then triage:
- Toolchain issue (uvx unavailable, network blocked): adjust the workflow.
- Real lint finding only present in CI's Python install (unlikely with `uvx ruff@<pinned>`): investigate the version mismatch.

- [ ] **Step 4: Record the green run number**

Once green, note the run number (`gh run list --limit 1 --json databaseId --jq '.[0].databaseId'`). This goes into the bead-close note in Task 8.

---

### Task 8: Close the bead

**Files:** None.

- [ ] **Step 1: Run the spec's full test plan one more time**

Refer to the spec's "Test plan" section. Confirm:
- `uvx ruff@0.15.15 check test/ demo/` exits 0 locally. ✓
- `uvx ruff@0.15.15 check test/test_jmy18_smoke.py` exits 0 (excluded). ✓
- The `python-lint` CI job passes on `main`. ✓ (run number from Task 7).
- The `shell-syntax` job still passes. ✓
- Injection test: deliberate F401 fails the gate. ✓ (verified in Task 6).

- [ ] **Step 2: Close the bead with the run number in the note**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm
bd close opensrm-u5dw.1 --note "Landed in nthlayer@<HEAD-SHA>. Green CI on run <RUN-NUMBER>. Unblocks opensrm-314j."
```
Substitute `<HEAD-SHA>` (last 7 of `git -C ../nthlayer rev-parse HEAD`) and `<RUN-NUMBER>` (from Task 7 step 4).

- [ ] **Step 3: Verify 314j is now READY**

```bash
bd show opensrm-314j 2>&1 | grep -E "(BLOCKED|READY|BLOCKS|status)"
```
Expected: 314j status flips to READY (no remaining open blockers).

---

## Self-Review

**Spec coverage:**
- ✓ Architecture (root pyproject.toml, no `[project]`, `[tool.ruff]` only) — Task 2.
- ✓ `force-exclude = true` + `extend-exclude` for `test_jmy18_smoke.py` — Task 2, verified in Task 2 step 3.
- ✓ Ruff version pin at invocation site (`uvx ruff@0.15.15`) — Tasks 2-7, consistent.
- ✓ `python-lint` CI job parallel to `shell-syntax` — Task 4.
- ✓ Header comment update — Task 4 step 2.
- ✓ `docs/integration-testing.md` Lint subsection — Task 5.
- ✓ Baseline cleanup (`--fix`, optional `# noqa: E501`) — Tasks 1 + 3.
- ✓ Smoke-verify by injected F401 — Task 6.
- ✓ Test plan items all verified — Task 8 step 1.
- ✓ Out-of-scope items (mypy, shellcheck, sibling bumps, release flow) — none introduced.

**Placeholder scan:** No TBD/TODO. Each step has either exact code, exact commands, or a clearly-bounded decision rule. Task 1 step 4 explicitly handles the "non-autofix finding appears" branch by stopping rather than guessing.

**Type consistency:** Ruff version (`0.15.15`) appears identically in pyproject.toml comment, CI workflow, docs subsection, and every command. Tool name (`python-lint`) appears identically in CI job, header comment, and commit messages. No drift.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-09-u5dw1-frontdoor-lint.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
