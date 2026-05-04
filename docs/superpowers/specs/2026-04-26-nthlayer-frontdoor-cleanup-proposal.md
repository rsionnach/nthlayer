# nthlayer/ Front-Door Repurpose — Cleanup Proposal

**Date:** 2026-04-26
**Status:** Approved 2026-04-26 with resolutions appended below.
**Context:** Repo consolidation Step 4-post — convert `nthlayer/` from generator-code repo to documentation front-door. Repo URL must not change (17 GitHub stars travel with the URL).

## Approval resolutions (2026-04-26)

Rob approved the proposal with three clarifications resolved before commit. Each "delete or move" ambiguity from the original proposal has been resolved to a concrete action with one-line reason. The mkdocs triangle is decided. The `action.yml` version-pinning and tag-preservation invariants are recorded.

### Resolution 1 — Concrete actions for ambiguous items

| Item | Resolution | Reason |
|---|---|---|
| `.github/workflows/deployment-gate.yml` | **MOVE → `nthlayer-generate/.github/workflows/`** | Showcases the `uses: rsionnach/nthlayer@...` action against `examples/services/checkout-service.yaml`; both action and examples now belong with `nthlayer-generate`. |
| `.github/workflows/sync-awesome-alerts.yml` + `scripts/sync_awesome_alerts.py` | **MOVE → `nthlayer-generate/`** | Workflow + script sync alert templates into the alert template tree, which lives in `nthlayer-generate/src/nthlayer_generate/alerts/templates/`. Workflow goes where its target lives. |
| `examples/` | **MOVE → `nthlayer-generate/examples/`** | All contents (`services/`, `slos/`, `cicd/`, `opensrm/`, `uat/`, `environments/`) are inputs for the generator. |
| `UAT.md` | **DELETE** | Point-in-time UAT plan from pre-v1.5; references the legacy `examples/uat/payment-api.yaml` CLI flow that has since been replaced by per-component test suites + `test/integration-chain.sh`. Not active. |
| `CICD_PROLIFERATION_PLAN.md` | **MOVE → `opensrm/plans/archive/2026-04-26-cicd-proliferation-plan-pre-v1.5.md`** with archived-status header | Strategic framing (Docker image + GitHub Action + drift detection as a CI/CD distribution strategy) still informs how to position the new tier architecture, even though the implementation details are stale. Don't lose the framing; mark archived. |
| `GETTING_STARTED.md` | **MOVE → `nthlayer-generate/GETTING_STARTED.md`** | Generator developer onboarding belongs with the generator codebase. |
| `demo/` (entire dir incl. `fly-app/`, `vhs/`, all `.md`) | **MOVE → `nthlayer-generate/demo/`** | All materials (Grafana Cloud setup, Fly.io deploy app, dashboard imports, VHS recordings, value-prop docs) demonstrate the generator. The cross-component v1.5 demo lives separately at `nthlayer-ecosystem/demo/`. |
| `scripts/sync_awesome_alerts.py` | MOVE → `nthlayer-generate/scripts/` | (covered above with workflow) |
| `scripts/regenerate_hybrid_dashboards.py` | **MOVE → `nthlayer-generate/scripts/`** | Generator dashboard regeneration tool. |
| `scripts/push_demo_metrics.py` | **MOVE → `nthlayer-generate/scripts/`** | Synthetic demo metric pusher used by the generator demo (Grafana Cloud showcase). |
| `scripts/validate_dashboard_metrics.py` | **MOVE → `nthlayer-generate/scripts/`** | Generator-CI dashboard metric validation. |
| `scripts/lint/` (4 shell scripts) | **MOVE → `opensrm/scripts/lint/`** | Repo-level lint policies (exception handling, orphan TODOs, unstructured logging) are project-wide governance, not generator-specific. |
| `scripts/sync_beads_to_github.py` | **MOVE → `opensrm/scripts/`** | Beads live in opensrm Dolt DB; GitHub-issue mirroring is opensrm-level governance. |
| `scripts/create-audit-issue.sh` | **MOVE → `opensrm/scripts/`** | Audit-issue creation = project-level governance. |
| `scripts/prune_roadmap.py` | **DELETE** | One-shot bead/roadmap admin script; work completed. |
| `scripts/update_beads.py` | **DELETE** | One-shot bead admin script; work completed. |
| `scripts/try_create_schedule.py` | **DELETE** | Named "try_" — exploratory PagerDuty API debugging script. |
| `scripts/try_pagerduty_api.py` | **DELETE** | Named "try_" — exploratory PagerDuty API debugging script. |

After all moves, `nthlayer/scripts/` will be empty and gets deleted with it.

### Resolution 2 — mkdocs / docs-site / site triangle

**Decision (per Rob's recommendation, awaiting confirmation): KEEP the documentation site.**

A central "what is NthLayer, how do components fit together, why does this exist" layer adds value beyond a README — especially for visitors evaluating the project. Keeps:

- `mkdocs.yml` — site config
- `.github/workflows/docs.yml` — site build + deploy
- `docs-site/` — site source (mkdocs source `.md` files)
- `documentation/` — additional documentation assets (audit, decks/, etc.)
- `presentations/` — presentation assets

Deletes:
- `site/` — mkdocs build OUTPUT. Already gitignored (`.gitignore` line 26: `site/`). No tracked content; nothing to remove from git.

### Resolution 3 — `action.yml` delegation pin + git tag preservation

`action.yml` decision is **option 2 (delegate to nthlayer-generate)** with explicit version pinning:

> The repurposed `action.yml` MUST pin to a specific tagged release of nthlayer-generate (e.g. `nthlayer-generate@v1.0.0`), NOT to `main`. Updates to the front-door action are explicit (a deliberate version bump in `action.yml`); they are NEVER implicit via nthlayer-generate's default branch. This prevents breaking changes in nthlayer-generate from silently breaking front-door consumers using `uses: rsionnach/nthlayer@v0.1.0a20`.

The specific tag to pin to is Rob's choice and lands in the **third commit** of the cleanup sequence (see "Sequencing" below), not in the cleanup commit itself.

**Git tag preservation (verified 2026-04-26):** The current `nthlayer/` repo has 19 tags (`v0.1.0a2` through `v0.1.0a20`). Tags are git refs separate from branches and files; the cleanup commit only deletes files, so tags survive untouched. Consumers using `uses: rsionnach/nthlayer@v0.1.0a20` (or any other tag) will continue to resolve to the historical commit pointed at by that tag — which still has the full generator code, since deletions don't propagate backwards through history. **Do not run any tag-deletion commands.**

### Updated sequencing

Three commits in this order, each separately pushable:

1. **Cleanup commit** (this proposal) — delete duplicates + items in the "what goes" list + items resolved to DELETE above. Items resolved to MOVE are deleted from `nthlayer/` AND copied into their destination repos in the same logical operation (the destination repos get their own commits).
2. **README + ARCHITECTURE.md commit** — Rob provides content; replaces `README.md` and adds `ARCHITECTURE.md`.
3. **`action.yml` repurpose commit** — repoint to nthlayer-generate with a specific tag pin, per Resolution 3.



The current `nthlayer/` repo still contains the OLD generator code (`src/nthlayer/`, `tests/`, `policies/`, `plugins/`, etc.) — all of it has been migrated to `nthlayer-generate/src/nthlayer_generate/`. The cleanup is "delete the duplicate."

## What stays (project-level documentation only)

### Top-level files
- `README.md` — Rob will replace with documentation-first content (project front door, links to all implementation repos, dev.to article series link).
- `CHANGELOG.md` — keep, append a "Repurposed as project front door (2026-04-26)" entry.
- `CONTRIBUTING.md` — keep; may need rewording to reflect "this is the front door, contribute to specific implementation repos for code changes."
- `AGENTS.md` — keep (agent guidance for the repo, generic).
- `CLAUDE.md` — keep (project-level Claude guidance).
- `ATTRIBUTION.md` — keep.
- `LICENSING_COMPLIANCE.md` — keep.
- `.gitignore` — keep.
- `.gitattributes` — keep.
- `.pre-commit-config.yaml` — keep if there's anything to lint after cleanup; otherwise remove.

### Directories
- `.github/` — KEEP with edits:
  - `.github/ISSUE_TEMPLATE/` — keep
  - `.github/dependabot.yml` — depends on whether the repo still has Python deps. After cleanup, no `pyproject.toml`, so dependabot has nothing to scan. Either delete or keep as no-op. **Recommend delete.**
  - `.github/workflows/`:
    - `ci.yml` — generator CI, **delete**
    - `deployment-gate.yml` — exercises the action, **delete or move to nthlayer-generate**
    - `docs.yml` — **keep** (docs build for the front-door — likely mkdocs deploy)
    - `publish-docker.yml` — generator Docker publish, **delete**
    - `push-demo-metrics.yml` — generator demo metric push, **delete**
    - `release.yml` — generator PyPI release, **delete** (front-door does not publish a Python package)
    - `sync-awesome-alerts.yml` — sounds like alert-template sync; **delete or move to nthlayer-generate** (where the alert templates live)
- `docs/` — keep (architecture.md, conventions.md, golden-principles.md, plans/, generate-capability-audit.md). These are project-level architectural docs.
- `documentation/` — KEEP, AUDIT (this directory has decks/, README.md, etc. — looks like it predates `docs/` and may overlap; worth a manual review pass).
- `presentations/` — KEEP (presentations about NthLayer for talks / dev.to article assets).
- `examples/` — **MOVE TO nthlayer-generate** then delete from front-door. These are generator examples, not documentation examples.
- `archive/` — **DELETE** (per the directory name — already-archived material).

### Possibly-keep, needs your call
- `mkdocs.yml` — **keep IF docs.yml workflow is kept** for the mkdocs site. Otherwise delete.
- `docs-site/` — built mkdocs output staging? **likely keep** if mkdocs.yml stays; review contents.
- `site/` — appears to be built mkdocs output, should be in `.gitignore` if not already; **delete tracked content** if it's a build artifact.
- `scorecard.png` — **keep** (scorecard image likely used in README).
- `opensrm-v1-full-spec.md` — **MOVE TO opensrm/specs/** then delete. Specs belong in the opensrm repo per the consolidation plan.
- `plans/` — **MOVE TO opensrm/docs/superpowers/plans/** then delete. Project plans belong with specs in opensrm.

## What goes (delete from this repo; in some cases, after migration to elsewhere)

### Code, build, deploy
- `src/` — delete (already in nthlayer-generate as `src/nthlayer_generate/`).
- `tests/` — delete (generator tests, in nthlayer-generate).
- `pyproject.toml` — delete (front-door no longer publishes a Python package; PyPI `nthlayer` package now comes from `nthlayer-core/`).
- `uv.lock` — delete (no Python deps to lock once pyproject.toml is gone).
- `Makefile` — delete (build automation for the deleted code).
- `Dockerfile` — delete (containerised generator; nthlayer-generate has its own if needed).
- `docker-compose.yml` — delete.
- `dist/` — delete (build artifact).
- `htmlcov/` — delete (coverage output; should be gitignored too).
- `generated/` — delete (generator output staging).

### Generator-specific content
- `policies/` — already in nthlayer-generate; delete from front-door.
- `plugins/` — already in nthlayer-generate; delete from front-door.
- `demo/` — generator demo content; delete (or move pieces to nthlayer-generate / demo at ecosystem root).
- `scripts/` — generator-related scripts; delete unless any are documentation-build scripts (audit).

### Internal planning docs / generator-specific docs
- `UAT.md` — UAT plan for the generator; **delete or move to nthlayer-generate**.
- `CICD_PROLIFERATION_PLAN.md` — internal plan; **delete or move to opensrm/plans**.
- `GETTING_STARTED.md` — generator getting-started; **move to nthlayer-generate** then delete.
- `MIGRATION.md` — generator migration guide (runtime → nthlayer-observe, but observe is now deprecated → workers); content is stale. **Delete.**

### Untracked files in working tree
- `robtest2.yaml`, `robtest3.yaml` — already pending deletion in git status; commit the deletions.
- `plans/active/2026-04-16-demo-improvement-accountability-portfolio.md` — untracked. Either commit (if it should live in this repo) or move to opensrm and untrack.
- `alert_stats.json` — generator artifact; delete.

## Critical decision: `action.yml` (the public GitHub Action)

The `action.yml` file at the repo root is the GitHub Action consumed by users via `uses: rsionnach/nthlayer@main` in their CI/CD. Deleting it breaks every consumer. Three options:

1. **Keep `action.yml` but mark it deprecated** — leave the file in place, update the description to say "deprecated; see nthlayer-generate/action.yml". The action itself would not work (no underlying code), but the URL stays valid and consumers get a clear error.
2. **Update `action.yml` to delegate to nthlayer-generate** — point the action's runtime at `nthlayer-generate`'s release, so existing `uses:` references continue to function. Requires nthlayer-generate to expose the same CLI surface.
3. **Delete the action entirely** — breaks every existing consumer hard. Most aggressive; not recommended for a repo with 17 stars.

**Recommendation: option 2.** The 17 stars are likely from people who have actually used the action; preserving its function preserves the social proof signal. nthlayer-generate already has the generator CLI — wiring `action.yml` to invoke it is a small change.

This decision belongs to Rob and is documented here for tracking, not actioned in this cleanup commit.

## Sequencing

The cleanup commit will land in two passes:

1. **Cleanup commit (this proposal)** — delete unambiguous duplicates (src/, tests/, build artifacts) and items in the "what goes" list above. `action.yml` is **left in place pending option 1/2/3 decision.** mkdocs.yml + docs-site/ kept pending docs.yml workflow decision.
2. **README + ARCHITECTURE.md commit (Rob provides content)** — replace README.md with the new front-door content; add ARCHITECTURE.md.

Items requiring migration to other repos (examples → nthlayer-generate, opensrm-v1-full-spec.md → opensrm, plans → opensrm) are noted but **not actioned here** — they are separate commits in the destination repos.
