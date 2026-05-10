# Release runbook

How to ship a release of any nthlayer-ecosystem package. The pipeline
is identical across the seven members; this document is the authoritative
operator-facing reference.

## TL;DR

```
Push Conventional Commits to main
  → release-please opens / updates a release PR
  → review the version bump + CHANGELOG, merge when ready
  → release-please creates the GitHub release tag
  → existing release.yml fires, runs the smoke gate, publishes to PyPI
```

If anything breaks, the smoke gate fails loudly with a structured
report and *blocks the publish*. No yanking required.

## Repo map

| Repo | PyPI package | Pyproject path | Tag pattern |
|---|---|---|---|
| nthlayer-common | `nthlayer-common` | `/pyproject.toml` | `v{X}.{Y}.{Z}` |
| nthlayer-generate | `nthlayer-generate` | `/pyproject.toml` | `v{X}.{Y}.{Z}` |
| nthlayer-core | `nthlayer-core` | `/pyproject.toml` | `v{X}.{Y}.{Z}` |
| nthlayer-workers | `nthlayer-workers` | `/pyproject.toml` | `v{X}.{Y}.{Z}` |
| nthlayer-bench | `nthlayer-bench` | `/pyproject.toml` | `v{X}.{Y}.{Z}` |
| nthlayer (meta) | `nthlayer` | `/meta-package/pyproject.toml` | `meta-v{X}.{Y}.{Z}` |

`opensrm` does not publish to PyPI (spec only).

## Conventional Commits

release-please reads commit messages from `main` to compute the next
version. The taxonomy:

| Prefix | Bumps | Visible in CHANGELOG? |
|---|---|---|
| `feat:` | minor | yes — under "Features" |
| `fix:` | patch | yes — under "Bug Fixes" |
| `perf:` | patch | yes — under "Performance Improvements" |
| `deps:` | patch | yes — under "Dependencies" |
| `refactor:` | patch | yes — under "Code Refactoring" |
| `docs:` | patch | yes — under "Documentation" |
| `chore:` | none | hidden |
| `test:` | none | hidden |
| `ci:` | none | hidden |
| `build:` | none | hidden |
| `style:` | none | hidden |

For the meta-package, `refactor:` is also hidden (no code to refactor).

**Breaking changes** — append `!` after the type or include
`BREAKING CHANGE:` in the commit body. Either bumps major.

```
feat!: drop Python 3.10 support

BREAKING CHANGE: minimum Python is now 3.11.
```

## Releasing — happy path

1. **Land Conventional Commits on main.** Each commit drives the
   version bump + CHANGELOG entry.
2. **Wait for the release PR.** `release-please` opens / updates a PR
   titled `chore(main): release {X}.{Y}.{Z}` within ~30s of each push.
   The PR contains the `pyproject.toml` version bump + a
   `CHANGELOG.md` diff.
3. **Review the release PR.** Verify the version bump matches your
   intent. Check the CHANGELOG entries are well-described (Conventional
   Commit messages become the changelog, so commits should already
   read cleanly).
4. **Merge the release PR.** `release-please` then:
   - Creates a GitHub release at the new tag
   - For most repos: tag is `v{X}.{Y}.{Z}`
   - For the meta-package: tag is `meta-v{X}.{Y}.{Z}`
5. **Watch `release.yml` fire.** Triggered by GitHub release publish.
   Steps: build wheel + sdist → `twine check` → smoke gate (Docker
   container, `tests/smoke/`) → PyPI publish via trusted publishing.
6. **Smoke green → publish completes.** No further action.

## Smoke gate failure triage

The smoke gate runs the package's `tests/smoke/` suite against a
freshly-built wheel inside a clean `python:3.11-slim` container. It
catches:

- Stale `__all__` exports (`test_imports.py::test_all_declared_symbols_resolve`).
- MANIFEST.in / package-data gaps (`test_each_module_imports[*]`).
- Missing runtime deps in the wheel (`pip install` fails or
  ImportError on first import).
- Broken console-script entry points (`test_cli.py::test_console_script_on_path`,
  `test_help_runs_clean`).

When the gate fails:

1. **Read the GitHub Actions job log.** The failing test name and
   stderr identify the class:
   - `Symbols in __all__ failed to resolve` → stale export. Either
     remove the symbol from `__all__` or re-export it.
   - `ModuleNotFoundError` → MANIFEST.in / package-data gap. Verify
     the missing file is included in the wheel
     (`unzip -l dist/*.whl | grep <missing>`).
   - `ImportError: cannot import name 'X' from 'Y'` → stale-dep
     (downstream pin too loose, the bumped dep removed the symbol).
     Bump the lower bound of the affected dep.
   - Console-script `--help` non-zero exit → import-time crash in the
     entry-point module. Run locally to reproduce.
2. **Land a fix on main as a Conventional Commit.** `fix:` if it's a
   bug, `deps:` if it's a dep-pin update.
3. **The release PR auto-updates.** Once green, merge again.

Until the smoke is green, no PyPI promotion happens. There is nothing
to roll back at PyPI.

## Cross-repo dep-bump cascade

Renovate is not used (Mend.io account requirement). Dependabot
handles dep bumps:

- nthlayer-* siblings: grouped into one PR per cycle, labelled
  `ecosystem-bump` + `needs-review`. **Never auto-merged** — semver
  discipline across siblings isn't tight enough to trust patch bumps
  unattended.
- External patch updates: auto-merge on green CI.
- Dev deps (pytest, ruff): auto-merge on patch + minor.
- Major bumps: always require review.

Workflow lives in each repo at `.github/workflows/dependabot-automerge.yml`.

When a sibling release lands on PyPI:

1. Dependabot opens an `nthlayer-ecosystem` PR in each consumer
   within ~24h (Monday 06:00 Europe/Dublin schedule).
2. Reviewer checks the upstream changelog, then merges.
3. The consumer's release-please flow picks up `deps:` from the merge
   and includes the bump in the next release PR.

## Manual rollback (last resort)

If a bad release lands on PyPI:

1. **Yank the version from PyPI** (web UI: project → Releases → Yank
   release). Yank hides the version from new resolves but does NOT
   delete the file. Existing pin'd consumers continue working.
2. **Revert the bad commit on main** with a `revert:` Conventional
   Commit. release-please will open a release PR for the next patch
   version.
3. **Land the actual fix** as a `fix:` commit.
4. **Merge the next release PR** to restore PyPI to a healthy state.

Yanking is final — once yanked, that version cannot be republished
under the same number. Use the next patch.

## Pre-existing dep mismatches (cleanup work)

Two beads track packages whose current pins point at unpublished
versions of nthlayer-common:

- `opensrm-pdoe` — nthlayer-bench pins `nthlayer-common>=1.5.0`;
  PyPI has 0.1.8.
- `opensrm-8bd5` — nthlayer-generate's `cli/migrate_manifest.py`
  imports `convert_v1_to_v2` from `nthlayer_common.manifest.v1_compat`;
  the symbol exists locally (added in opensrm-b22.2) but is not
  published.

Both clear when nthlayer-common's release PR (currently tracking
1.6.0) merges to PyPI. Until then, every dependent package's smoke
gate would block their first release attempt — exactly as designed.

**The unblocking sequence:**

1. Merge the release PR on `nthlayer-common`.
2. Smoke gate runs against common's wheel (no nthlayer deps, smoke is
   75 tests + clean).
3. Trusted publishing pushes 1.6.0 to PyPI.
4. The four downstream packages can now release in any order.

## Quick links

- release-please action: https://github.com/googleapis/release-please-action
- pypa/gh-action-pypi-publish: https://github.com/pypa/gh-action-pypi-publish
- Trusted publishing: https://docs.pypi.org/trusted-publishers/
- Conventional Commits: https://www.conventionalcommits.org/

## Per-repo overrides

If a repo needs to deviate from this runbook (custom test-extras to
install, larger smoke timeout, custom changelog sections), the
deviation lives in the repo's own `release-please-config.json` and
`release.yml`. Document the rationale in the repo's `CLAUDE.md`
under "## CI / Release pipeline".
