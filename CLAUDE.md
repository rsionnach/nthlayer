# nthlayer — project front door

**This repository is the project front door, not an implementation.** Code lives in the six implementation repos (see [README.md](README.md)). This repo holds project-level documentation, the GitHub Action that delegates to nthlayer-generate, and the docs site.

## What stays here

- `README.md` — Project front door content; primary audience is potential adopters and collaborators
- `ARCHITECTURE.md` — (forthcoming) Cross-repo architectural overview
- `action.yml` — GitHub Action for `uses: rsionnach/nthlayer@<tag>`; delegates to nthlayer-generate at a pinned version
- `mkdocs.yml`, `docs-site/`, `docs/`, `documentation/`, `presentations/` — Docs site source + design assets
- `.github/workflows/docs.yml` — Docs site build + GitHub Pages deploy
- `.github/workflows/ci.yml` — Front-door CI (kept; may be slimmed in a follow-up)
- `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, `ATTRIBUTION.md`, `LICENSING_COMPLIANCE.md` — Project metadata
- Git tags `v0.1.0a2`–`v0.1.0a20` — preserved; pinned consumers continue to resolve to historical commits

## What does NOT live here

Implementation code, tests, build system, deployment artefacts, generator examples, generator demo, generator docs, generator-specific scripts. All of those moved to their canonical homes during the 2026-04-26 consolidation.

| Looking for… | Now lives in… |
|---|---|
| Generator code (alerts, dashboards, SLOs, OpenSRM parser) | [`nthlayer-generate`](https://github.com/rsionnach/nthlayer-generate) |
| Verdict model, manifest parser, LLM wrapper, CoreAPIClient | [`nthlayer-common`](https://github.com/rsionnach/nthlayer-common) |
| HTTP API, verdict store, case management | [`nthlayer-core`](https://github.com/rsionnach/nthlayer-core) |
| observe / measure / correlate / respond / learn workers | [`nthlayer-workers`](https://github.com/rsionnach/nthlayer-workers) |
| Operator TUI (situation board, case bench) | [`nthlayer-bench`](https://github.com/rsionnach/nthlayer-bench) |
| OpenSRM specification | [`opensrm`](https://github.com/rsionnach/opensrm) |

## When working in this repo

Most changes here are documentation. The flow is:

1. README/CHANGELOG edits — straightforward markdown changes, no special tooling.
2. Docs site changes — edit `docs-site/`, then push and watch the `docs.yml` workflow deploy to GitHub Pages.
3. `action.yml` changes — these affect every consumer using `uses: rsionnach/nthlayer@<tag>`. Pin to a specific nthlayer-generate tag, never `main`. See [the consolidation plan](https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md) for the version-pinning invariant.

For implementation work, switch to the relevant implementation repo. Each has its own CLAUDE.md describing its conventions.

## Branch + tag policy

- `main` is the published front-door state. PRs land here.
- Tags `v0.1.0a*` are preserved for historical pinning. The next major release tag for this repo will likely follow the action's evolution (e.g. `v1` if `action.yml` is repurposed without breaking changes; `v2` if a clean break is needed).
- Stars and the repo URL must not change — they are first-class social proof and consumer-pinning surfaces.

## Spec + planning references (live in opensrm, not here)

- [Three-tier architecture decision (2026-04-21)](https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-21-spec-revision-summary.md)
- [Six-repo consolidation rationale (2026-04-21)](https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md)
- [Front-door cleanup proposal (2026-04-26)](https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md)
- [v1.5 epic plan (2026-04-21)](https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md)
