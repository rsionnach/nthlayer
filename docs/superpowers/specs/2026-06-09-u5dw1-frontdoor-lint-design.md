# u5dw.1 — Front-door Python helper lint coverage

**Bead:** `opensrm-u5dw.1` (P2)
**Parent:** `opensrm-u5dw` (closed) → `opensrm-a2ct` (Phase 2 epic, 12/13)
**Blocks:** `opensrm-314j` (CI standardisation)
**Date:** 2026-06-09

## Problem

The front-door repo (`nthlayer/`) hosts 5 Python helpers used by
demo and integration-test orchestration but has no Python tooling:
no `pyproject.toml`, no ruff/mypy config, no CI lint step.
Audit `nthlayer-frontdoor-audit-2026-06-05.md` §21 flagged this as
**0/5 helpers linted**. CI currently only runs `bash -n` on shell
scripts.

The five helpers in scope:

- `test/three_tier_assertions.py`
- `test/fake-service.py`
- `test/webhook-receiver.py`
- `demo/render_explanation.py`
- `demo/scenario-runner.py`

Out of scope: `test/test_jmy18_smoke.py` (standalone JMY18 smoke
test, audit §2); shell-script linting (separate question — `bash
-n` already covers syntax, shellcheck adoption is a follow-up).

## Design

### Architecture

A new `pyproject.toml` at the front-door repo root holds only
`[tool.*]` configuration — no `[project]` block, since the
front-door is not itself a PyPI package (its meta-package release
is published via a separate flow in `release.yml`, with its own
inline metadata).

Config contents:

```toml
# Ecosystem ruff floor (mirrors nthlayer-common). Pinned via the CI
# job's ruff version, not via a [project] dependency block — the
# front-door has no Python venv.
[tool.ruff]
target-version = "py311"
line-length = 100
force-exclude = true
extend-exclude = ["test/test_jmy18_smoke.py"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I", "UP", "SIM", "B"]
```

Three points worth flagging:

- **No mypy.** These helpers are stdlib-HTTP-server / prometheus
  exporter / scenario YAML driver shapes. They don't share a
  package surface that benefits from type checking. Ruff covers
  the actual signal (unused imports, undefined names, simple
  refactors). Matches what `nthlayer-bench` ships.
- **`force-exclude = true` + `extend-exclude`.** `extend-exclude`
  alone is bypassed when ruff is invoked with explicit paths.
  `force-exclude` makes the exclusion hold regardless of
  invocation, so `ruff check test/test_jmy18_smoke.py` skips the
  file the same way `ruff check test/` does. Cheap parity
  insurance.
- **Ruff version pinned in CI, not in pyproject.** The front-door
  has no venv to lock; the pin lives at the invocation site (see
  below).

### CI wiring

Add a second job to `.github/workflows/ci.yml`, parallel to the
existing `shell-syntax` job:

```yaml
python-lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: astral-sh/setup-uv@v6
    - name: ruff check on test/ and demo/ helpers
      run: uvx ruff@0.15.15 check test/ demo/
```

The pin `ruff@0.15.15` matches what
`nthlayer-common/uv.lock` resolves today (constraint `>=0.8`
ratchets to 0.15.15 at lock time). If a sibling repo bumps ruff,
the front-door pin gets the same bump in a follow-up commit — the
discipline is "the front-door floor tracks
nthlayer-common's resolved version", not "always latest".

No venv setup, no editable installs, no `uv sync`. `uvx` downloads
the pinned ruff wheel, runs it, exits. ~10-15s job.

### Header-comment update

`.github/workflows/ci.yml` opens with a comment block claiming
"this repo hosts no Python code at the root — implementation lives
in nthlayer-{common,core,workers,bench,generate}". Post-this-bead
that's no longer literally true: 5 helpers live at the root and
get linted. Edit the comment to:

> Post-consolidation this repo hosts only integration- and
> demo-shaped Python helpers at the root — implementation lives in
> nthlayer-{common,core,workers,bench,generate} (each with its own
> CI). The original ci.yml ran ruff/mypy/pytest against
> src/ tests/ examples/ paths that no longer exist; it failed
> every push from 2026-04-26 onward until this rewrite
> (opensrm-0buj). The `python-lint` job (opensrm-u5dw.1) covers
> the 5 root helpers via a pinned `uvx ruff`.

### Docs update

`docs/integration-testing.md` gains a short **Lint** subsection
near the top, after the existing "Running the suite" content:

> ### Lint
>
> The front-door's 5 Python helpers are linted by the
> `python-lint` job in `.github/workflows/ci.yml` using the
> ecosystem ruff floor (`py311`, `line-length=100`, the same
> `select` set as `nthlayer-common`). Local invocation:
>
> ```bash
> uvx ruff@0.15.15 check test/ demo/
> ```
>
> `test/test_jmy18_smoke.py` is excluded — it's a standalone JMY18
> smoke test, not an integration helper.

### Baseline cleanup

Before the CI job lands, run `uvx ruff@0.15.15 check test/ demo/
--fix` once locally to confirm a clean baseline. Findings that
autofix get committed in the same change as the config. Findings
that don't autofix:

- E501 (line-too-long) on a few existing docstring banners is
  expected — suppress with `# noqa: E501` on the specific lines
  rather than weakening the line-length rule globally.
- Any other non-autofix finding gets triaged in a follow-up bead,
  not in this one; this bead lands a clean gate, not a refactor.

## Out of scope

- mypy / sloppylint / any other gate beyond ruff.
- `test/test_jmy18_smoke.py` (explicitly excluded per audit §2).
- shell-script linting (shellcheck adoption — separate follow-up
  if wanted).
- The front-door meta-package release flow (`release.yml`) — has
  its own inline metadata, not touched here.
- Sibling-repo ruff version bumps — tracked separately; the
  front-door floor follows nthlayer-common in a follow-up after
  each common bump.

## Test plan

- `uvx ruff@0.15.15 check test/ demo/` exits 0 locally on a clean
  branch tip.
- `uvx ruff@0.15.15 check test/test_jmy18_smoke.py` exits 0 (file
  excluded by `force-exclude`), confirming the exclusion holds
  when the file is named explicitly.
- The new `python-lint` CI job passes on the PR.
- The existing `shell-syntax` job continues to pass (no
  regression in the parallel job).
- A deliberately injected `F401` (unused import) in
  `test/fake-service.py` causes both local and CI gates to fail —
  smoke-confirm the gate isn't a no-op. Revert before merging.

## Verification → close

When all five test-plan items pass, close the bead with a brief
note linking the CI run number that proves green. `opensrm-314j`
is then unblocked.
