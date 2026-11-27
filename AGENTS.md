# NthLayer front door — agent guide

This repository is the **front door and ecosystem hub** for NthLayer. It
holds no component implementation. What lives here is documentation, the
GitHub Action, the PyPI meta-package, the demo, the cross-repo integration
harness, and tooling that operates on the workspace.

`CLAUDE.md` is the fuller description of the repository: what it hosts,
the hard rules, the release pipeline and the spec references. This file is
the short working guide: commands, layout and workflow. Where the two
disagree, `CLAUDE.md` is right and this file needs fixing.

Until 2026-04-26 this repository was the single-repo generator, and this
file described it (`make test`, `src/nthlayer/`, a `develop` branch, a
per-repo beads file). None of that applies any more. The generator is
[`nthlayer-generate`](https://github.com/rsionnach/nthlayer-generate), and
its conventions are in its own `AGENTS.md`.

## Where code lives

| Looking for | Repository |
|---|---|
| Generator (alerts, dashboards, SLOs, recording rules) | `nthlayer-generate` |
| Manifest parser, verdict model, LLM wrapper, API client | `nthlayer-common` |
| HTTP API, verdict store, case management | `nthlayer-core` |
| observe, measure, correlate, respond, learn | `nthlayer-workers` |
| Operator TUI | `nthlayer-bench` |
| Override ingestion sidecar | `nthlayer-override-adapter` |
| The OpenSRM specification | `opensrm` |

If a change needs a module that a component imports, or anything that
ships in a wheel, it belongs in one of those, not here (`CLAUDE.md`, hard
rule 1).

## Layout

```
action.yml          GitHub Action; delegates to a pinned nthlayer-generate tag
meta-package/       source of `pip install nthlayer` (dependency-only)
demo/               demo.sh orchestrator, demo specs, helper scripts
test/               cross-repo integration harness and the tests of scripts/
scripts/            workspace tooling: eco_doctor, the R5 gate scripts,
                    meta-resolve-check.sh
docs/               specs, design docs, decisions, operational docs
docs-site/          mkdocs source for the published site (mkdocs.yml)
.github/workflows/  CI; CLAUDE.md lists what each workflow runs
```

## Commands

There is no `Makefile`, no `src/` and no root test suite. The root
`pyproject.toml` only configures ruff. Each check is one command, run from
the repository root; these are the commands CI runs.

```bash
# Lint and shell syntax (ci.yml)
uvx ruff@0.15.15 check test/ demo/ scripts/
find demo test scripts -maxdepth 2 -name '*.sh' -type f | xargs -n1 bash -n

# Tests of the workspace tooling in scripts/ (ci.yml); no network
uv run --no-project --with pytest --with pyyaml pytest -q test/test_r5_*.py
bash test/test_eco_doctor.sh

# Demo regression tests; no Docker
bash test/test_demo_paths.sh
bash test/test_demo_start_lock.sh

# Demo specs against the PUBLISHED packages (demo-specs.yml)
uv run --isolated --no-project --python 3.11 \
    --with nthlayer-common --with pytest --with pyyaml \
    pytest -q test/test_demo_specs_load.py
uv run --isolated --no-project --python 3.11 \
    --with nthlayer-generate --with pytest --with pyyaml \
    pytest -q test/test_demo_specs_migrate.py

# Docs site (docs.yml)
pip install mkdocs-material mkdocs-minify-plugin && mkdocs build --strict
```

`--isolated --no-project` matter on the published-package tests: without
them uv resolves the workspace's editable sibling checkouts instead.

The heavier checks need sibling checkouts, Docker, or both. Their exact
commands are in the workflow that runs each and in
`docs/integration-testing.md`:

- `test/test_error_budget_seam.py` (`error-budget-seam.yml`): needs
  `NTHLAYER_ECOSYSTEM_ROOT` pointing at the directory that holds the
  `opensrm` and `nthlayer-generate` checkouts.
- `test/test_otel_collector.py` (`otel-collector.yml`): needs Docker.
- `test/test_jmy18_smoke.py` (`override-binding-smoke.yml`): needs the
  `nthlayer-core` and `nthlayer-override-adapter` checkouts.
- `test/integration-three-tier.sh`, `test/integration-thresholds.sh`,
  `test/e2e-test.sh` (`integration-three-tier.yml`): boot the three tiers
  from sibling checkouts.
- `scripts/meta-resolve-check.sh` (`meta-resolve.yml`): reads PyPI.

Python that belongs to a component is run from that component's checkout,
for example `uv run --directory ../nthlayer-core pytest -q`.

## Conventions

- **Tests.** `docs/testing.md` has the ecosystem's testing conventions and
  `docs/integration-testing.md` the harness cross-reference. Derive
  fixtures from what a spec or a real file says, not from the code under
  test. A test that can skip silently is treated as a bug: list files
  instead of globbing, and fail on a missing checkout.
- **Assertions** go on structured data (exit codes, parsed fields), not on
  raw captured text.
- **Shell.** Scripts in `demo/`, `test/` and `scripts/` must pass
  `bash -n`; `demo/` scripts also run on macOS's bash 3.2.
- **The Python in `scripts/` is standard library (and git) only.**
  `eco_doctor.py` in particular imports nothing from the ecosystem: a
  checker that imported the packages it checks would fail exactly when
  they are broken.
- **`action.yml`** pins its delegated `nthlayer-generate` to a tag, never
  `main`.
- **Design docs** under `docs/superpowers/specs/` and `plans/` are added
  to, not rewritten; a decision goes in `docs/superpowers/decisions/`.

## Git workflow

- Branch from `main`, open a PR to `main`. There is no `develop` branch.
- PRs are merged with a merge commit, and PR titles are plain sentences,
  not conventional-commit subjects, so release-please lists each change
  once.
- Commit subjects are `<type>: <description>` under 72 characters, with
  the bead id in parentheses at the end. `feat`, `fix`, `perf`, `deps` and
  `docs` appear in the meta-package changelog; `chore`, `test`, `ci`,
  `build`, `style` and `refactor` are hidden. Changes under `scripts/` and
  `test/` take `chore`, `test` or `ci`.
- A change that is not doc-only passes the R5 review gate before it
  merges (`docs/r5-gate.md`). Doc-only PRs merge on green CI.
- Run the lint and the tests that cover what you touched before pushing.

## Issue tracking

Work is tracked with [beads](https://github.com/steveyegge/beads) (`bd`).
All beads for the ecosystem live in **one** database, in the `opensrm`
repository. There is no beads database in this repository.

```bash
cd ../opensrm
bd ready --label repo:nthlayer      # unblocked front-door work
bd show <id>
bd update <id> --claim
bd close <id> --reason "..."
```

Front-door beads carry the label `repo:nthlayer`. File a follow-up bead
for anything deliberately left out of a change.

## Releases

Only the meta-package is released from here. release-please opens the
release PR; merging it tags `meta-v<version>`, and `release.yml` publishes
to PyPI by trusted publishing. Nothing is tagged or published by hand.
`CLAUDE.md` ("PyPI meta-package", "CI / Release pipeline") and
`docs/release-runbook.md` have the detail, including the tag namespaces
that must not be mixed.
