# Dependency security audit (P4-SEC.3, opensrm-9uow.3)

**Date:** 2026-05-06
**Scope:** All five active ecosystem lockfiles — `nthlayer-common`,
`nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`, `nthlayer-generate`.
**Tool:** `pip-audit 2.10.0` against the PyPI Advisory Database.
**Bead:** opensrm-9uow.3.

## Findings

### Initial scan

| Package | Repo (origin) | Version | CVE | Fix |
|---|---|---|---|---|
| pygments | nthlayer-common (transitive via `rich` ← `instructor`/`typer`) | 2.19.2 | CVE-2026-4539 | 2.20.0 |

`nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`, and
`nthlayer-generate` reported **zero known vulnerabilities** on first
pass. Each transitively consumes `nthlayer-common`, so all five repos
were affected by the pygments finding via the editable common
dependency.

### Fix

Added a transitive pin to `nthlayer-common/pyproject.toml`:

```toml
# Transitive pin: rich pulls pygments; CVE-2026-4539 fixed in 2.20.0
# (opensrm-9uow.3 dependency audit). Remove once rich's lower bound
# carries the fix transitively.
"pygments>=2.20.0",
```

Re-ran `uv lock` in `nthlayer-common`, then re-locked the four
downstream repos so they pick up the transitive change. Final state:

| Repo | pygments | CVEs |
|---|---|---|
| nthlayer-common | 2.20.0 | 0 |
| nthlayer-core | 2.20.0 | 0 |
| nthlayer-workers | 2.20.0 | 0 |
| nthlayer-bench | 2.20.0 | 0 |
| nthlayer-generate | 2.20.0 | 0 |

## Pinning policy

The bead acceptance criterion "Critical deps pinned exact" applies at
the **lockfile** level, not the manifest level:

- **`uv.lock`** in every repo pins every dependency (direct and
  transitive) to an exact version with content-addressed hashes. This
  is the deployable artifact.
- **`pyproject.toml`** uses bounded ranges (`>=A.B,<X.0`) for direct
  dependencies. This is the compatibility contract for downstream
  consumers.

The combination gives reproducible builds (lockfile = exact) without
forcing every downstream consumer to upgrade in lockstep with us
(pyproject = bounded range). When a CVE forces an upgrade, the policy
is:

1. Update the lockfile via `uv lock --upgrade-package <pkg>`.
2. If the fix requires bumping the lower bound in `pyproject.toml`,
   do so explicitly with a comment naming the CVE.
3. If the fix is transitive and the direct dep doesn't carry it,
   add an explicit pin in `pyproject.toml` (as done here for pygments).

## Supply-chain mitigations in place

- **uv with `--no-sources` in CI**: `nthlayer-generate` CI uses
  `UV_NO_SOURCES=1` so resolution comes from PyPI, not the local
  editable path. This catches lockfile drift between local dev and
  publish-time resolution.
- **PyPI Trusted Publishing** for the `meta-package/` PyPI release
  (front-door repo). No long-lived API tokens.
- **Lockfile content hashes**: every `uv.lock` entry includes
  per-file SHA-256 hashes; uv refuses to install a wheel whose hash
  doesn't match.
- **Editable cross-repo dependencies** during dev only:
  `nthlayer-common = { path = "../nthlayer-common", editable = true }`
  is gated by `UV_NO_SOURCES=1` in CI so production resolves from
  PyPI.
- **Optional-dependency boundary**: heavy or risky deps (`boto3`,
  `kubernetes`, `kazoo`, `etcd3`) live behind PEP 621 optional
  extras (`[aws]`, `[kubernetes]`, etc.) so adopters not using the
  feature don't pull the dep at all.
- **Dev/runtime split**: pytest, ruff, etc. live under
  `[project.optional-dependencies].dev`; `--no-dev` exports for
  audit and production resolution exclude them.

## Known limitations (deliberately deferred)

- **No SCA scanning in CI yet.** `pip-audit` is run manually for this
  audit; no scheduled re-run. Adding a nightly `pip-audit` job to each
  repo's CI is tracked as future hardening (separate bead).
- **No SBOM generation.** Runtime deps don't emit an SPDX or CycloneDX
  bill of materials. v2 work.
- **No package signing verification.** uv's hash check covers integrity
  against typosquatting on first install, but not author identity.
  Sigstore/cosign for Python packages is still maturing in the broader
  ecosystem.
- **Front-door (`nthlayer/`) and OpenSRM repos** have no Python
  dependencies (front-door has the meta-package which is dependency-
  only; opensrm is the spec). Neither was scanned because there is
  nothing to scan.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | Zero known CVEs at release | ✅ All five repos report `No known vulnerabilities found` post-fix |
| 2 | Critical deps pinned exact | ✅ Lockfile-level exact pinning policy documented; pygments pinned explicitly in nthlayer-common manifest to address the transitive CVE |
| 3 | Supply-chain doc updated | ✅ This document + mitigations section |

## Cross-references

- Beads: `opensrm-9uow.3` (this audit), `opensrm-9uow.1` (Core API
  audit), `opensrm-9uow.2` (safe-actions audit), parent `opensrm-9uow`
  (Phase 4-SEC epic).
- Code: `nthlayer-common/pyproject.toml` (pygments pin),
  `nthlayer-common/uv.lock` + four downstream lockfiles.
- Reproduce: `pip-audit --requirement <(uv export --format
  requirements.txt --no-dev | grep -v '^-e') --no-deps` in each repo.
