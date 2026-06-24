# nthlayer — project front door + ecosystem hub

This repo is the **project front door + ecosystem hub**. It hosts the
GitHub Action, the PyPI meta-package, ecosystem-wide documentation,
integration test infrastructure, demo materials, and the architectural
design corpus. **Implementation code does not live here** — it lives
in the per-tier component repos.

## Stack

- Documentation, shell scripts, YAML, and a meta-package
  `pyproject.toml`. No application code.
- Bash for `demo/`, `test/`. Python is brought in via `uv run
  --directory <repo>` against sibling component repos.

## Build / test / lint / run commands

→ See `AGENTS.md` (existing canonical Core Commands section + project
roadmap + conventions).

## NthLayer at a glance

NthLayer is an open-source reliability platform for SREs. It compiles
service reliability requirements (SLOs, alerts, dashboards, deployment
gates, dependency graphs) into observable production infrastructure,
then runs an autonomous reliability runtime that observes, judges,
correlates, responds, and learns. Built on the
[OpenSRM specification](https://github.com/rsionnach/opensrm).

The ecosystem spans seven active repositories: one specification
(`opensrm`), one shared library (`nthlayer-common`), one compiler
(`nthlayer-generate`), three runtime tiers (`nthlayer-core` /
`nthlayer-workers` / `nthlayer-bench`), and this front door
(`nthlayer/`). The marketing site (`nthlayer-site`) is a separate
concern.

NthLayer is in **v1.5 development**. The three-tier architecture
(core + workers + bench) is being actively built; the six-repo
consolidation completed 2026-04-26. Production-ready usage today
centres on `nthlayer-generate` plus the OpenSRM spec; runtime tiers
are under integration testing for v1.5.

## Components

Each active component has its own `CLAUDE.md`.

- `nthlayer/` — project front door + ecosystem hub (this repo).
  Hosts `meta-package/` (PyPI source — `pip install nthlayer`),
  `action.yml`, `test/`, `demo/`, `docs/`, project documentation. No
  implementation code.
- `nthlayer-generate/` — pure deterministic compiler: specs →
  artifacts (Python, stateless, no runtime).
- `nthlayer-core/` — Tier 1 reliability-critical HTTP API server:
  verdict store, case management. CLI: `nthlayer serve`.
- `nthlayer-workers/` — Tier 2 consolidated runtime process (Apache
  2.0): five internal modules — observe, measure, correlate, respond,
  learn. Communicates with core via HTTP API only.
- `nthlayer-bench/` — Tier 3 Textual TUI operator interface.
  Communicates with core via HTTP API only.
- `opensrm/` — OpenSRM specification (no code deps).
- `nthlayer-common/` — shared library: LLM wrappers, providers,
  identity resolution, errors, tier definitions, manifest parser,
  decision records, verdict model.

Active sibling repo: `nthlayer-override-adapter/` — override-event
sidecar (opensrm-jmy.7 + jmy.18). Own repo, own release-please, own
Dockerfile. Console script: `nthlayer-override-adapter serve`.

Separate concern (not in the active count):
`nthlayer-site/` — marketing/demo site (HTML/JS, no Python).

Deprecated standalone repos (`nthlayer-observe`, `nthlayer-learn`,
`nthlayer-measure`, `nthlayer-correlate`, `nthlayer-respond`) were
consolidated into nthlayer-workers 2026-04-26 and removed from local
disk 2026-05-08 under `opensrm-hty.7` (RM.7). Each has a PyPI
deprecation release (`v1.0.0`) emitting `DeprecationWarning`; upstream
GitHub repos remain for historical reference. **Do not reintroduce
them.**

## What does NOT live here

Implementation code, build system, deployment artefacts, generator
examples, generator-specific scripts.

| Looking for… | Now lives in… |
|---|---|
| Generator code (alerts, dashboards, SLOs, OpenSRM parser) | [`nthlayer-generate`](https://github.com/rsionnach/nthlayer-generate) |
| Verdict model, manifest parser, LLM wrapper, CoreAPIClient | [`nthlayer-common`](https://github.com/rsionnach/nthlayer-common) |
| HTTP API, verdict store, case management | [`nthlayer-core`](https://github.com/rsionnach/nthlayer-core) |
| observe / measure / correlate / respond / learn workers | [`nthlayer-workers`](https://github.com/rsionnach/nthlayer-workers) |
| Operator TUI (situation board, case bench) | [`nthlayer-bench`](https://github.com/rsionnach/nthlayer-bench) |
| OpenSRM specification | [`opensrm`](https://github.com/rsionnach/opensrm) |

## What this repo hosts

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`,
  `ATTRIBUTION.md`, `LICENSING_COMPLIANCE.md` — project metadata.
- `action.yml` — GitHub Action for `uses: rsionnach/nthlayer@<tag>`;
  delegates to nthlayer-generate at a pinned version.
- `mkdocs.yml`, `docs-site/`, `documentation/`, `presentations/` —
  docs site source + design assets.
- `docs/` — project-level documentation:
  - `docs/specs/` — current NthLayer specifications.
  - `docs/roadmap/` — proposed/upcoming feature specs.
  - `docs/archived-specs/` — superseded/shipped specs preserved as
    historical record.
  - `docs/superpowers/` — architectural design docs
    (`plans/` + `specs/`).
  - `docs/testing.md`, `docs/COSTOPTIMISATION.md`,
    `docs/metrics-contract.md` — cross-cutting operational docs.
  - `docs/integration-testing.md` — five-test-surface harness
    cross-reference (new under the auto-memory retirement).
  - `docs/release-runbook.md` — operator runbook for the full
    ecosystem-wide release pipeline (Phase 5).
- `test/` — cross-repo integration test infrastructure (see
  `docs/integration-testing.md`).
- `demo/` — runnable cascading-failure scenario, `demo.sh`
  orchestrator, example OpenSRM specifications.
- `.github/workflows/`:
  - `docs.yml` — docs site build + GitHub Pages deploy.
  - `ci.yml` — `bash -n` syntax check across `demo/` and
    `test/` *.sh (opensrm-0buj).
  - `demo-paths.yml` — `cmd_start` path-resolution regression test
    (opensrm-oey5).
  - `demo-start-lock.yml` — `cmd_start` concurrent-invocation lock
    regression test (opensrm-36es).
  - `release.yml` — meta-package release to PyPI (triggered on
    `meta-v*` tags).
  - `integration-three-tier.yml` — cross-repo three-tier integration
    test (`workflow_dispatch` + nightly cron).
  - `publish-docker.yml` — Docker image publish.
- `meta-package/` — source for `pip install nthlayer`. Dependency-
  only; pins core / workers / bench / generate at matching versions.
- Git tags `v0.1.0a2`–`v0.1.0a20` — preserved; pinned consumers
  continue to resolve to historical commits.

## Hard rules

These are load-bearing — wrong-side mistakes break downstream
consumers, scramble the release pipeline, or pollute the ecosystem
hub with implementation drift.

1. **No application code in this repo.** Implementation lives in the
   per-tier repos. If a change feels like Python source, you are in
   the wrong repo. The exception is `meta-package/pyproject.toml`,
   which is dependency-only (no modules).

2. **`action.yml` consumers are external production CI.** Pin the
   action's delegated invocation to a specific `nthlayer-generate`
   tag, **never `main`** — drift in the delegated version is a
   silent regression for every consumer. The pinning invariant and
   the option-2 delegation rationale are in
   `docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md`.

3. **The repo URL and stars are first-class social proof — do not
   change them.** Consumer pinning lives at this URL. Same applies
   to legacy tag `v0.1.0a*`: preserved for historical pinning,
   resolves to historical commits, not updated.

4. **Tag namespaces are disjoint.**
   - `v0.1.0a*` — legacy generator releases (historical).
   - `meta-v*` — PyPI meta-package releases. Triggers `release.yml`.
   - Sub-package `v*` tags live in their own repos.

   Do not push a tag in the wrong namespace.

5. **The workspace root is not a git repo.** The parent dir
   (`nthlayer-ecosystem/`) hosts sibling clones of every active
   member plus three local-only convenience files (`pyproject.toml`,
   `CLAUDE.md`, `README.md`). Never committed. CI and per-repo
   `uv sync` use each member's own `pyproject.toml` + `uv.lock`. The
   workspace pyproject is dev-convenience only. Rationale:
   `opensrm-hty.6` (RM.6).

6. **`docs/superpowers/specs/` and `docs/superpowers/plans/` are
   load-bearing planning surfaces, not historical notes.** Adding to
   them is fine; rewriting an existing decision record is not — it
   destroys the audit trail.

## When working in this repo

Most changes are documentation, ecosystem specs, or test/demo
infrastructure. Implementation work goes in the relevant component
repo (each has its own CLAUDE.md describing its conventions).

- README / CHANGELOG edits — straightforward markdown.
- Docs site changes — edit `docs-site/`, push, watch `docs.yml`
  deploy to GitHub Pages.
- Spec and design doc edits — files under `docs/specs/`,
  `docs/roadmap/`, `docs/archived-specs/`, `docs/superpowers/`.
  Update relevant cross-references in CLAUDE.md when shape or
  location changes.
- Test/demo infrastructure — `test/integration-three-tier.sh`
  exercises the three-tier stack; `demo/demo.sh` drives the
  cascading-failure scenario. See script headers for invocation,
  `docs/integration-testing.md` for the cross-reference, and
  `docs/superpowers/specs/` for design rationale.

## PyPI meta-package

`meta-package/` is the authoritative source for
`pip install nthlayer`:

- **Purpose:** friendly entry point for evaluators, demos, and local
  dev. For production, install individual tiers.
- **Content:** dependency-only (`packages = []`); no Python modules,
  no console scripts.
- **Pinning:** each release pins all four sub-packages at explicit
  versions; they are not guaranteed to match. `nthlayer-generate`
  follows its own versioning baseline (currently `==1.1.0`);
  `nthlayer-core`, `nthlayer-workers`, and `nthlayer-bench` are
  aligned (currently `==1.6.0`). `nthlayer-common` is a transitive
  dep.
- **Tag namespace:** `meta-v*` (e.g. `meta-v1.0.0`). Separate from
  legacy `v0.1.0a*` and from sub-package tags.
- **First release:** `meta-v1.0.0` — published;
  `pip install nthlayer==1.0.0` resolves the full ecosystem closure.
- **Workflow:** `.github/workflows/release.yml` (triggered on
  `meta-v*` push + `workflow_dispatch`). Trusted publishing.

## CI / Release pipeline

The nthlayer front-door repo uses `googleapis/release-please-action@v4`
for the meta-package. Config: `release-please-config.json` (package
type `python`, component `meta`, package path `meta-package/`) +
`.release-please-manifest.json` (version anchor at `meta-package/`).
Tags follow `meta-v*` (e.g. `meta-v1.0.0`), kept separate from the
legacy `v0.1.0a*` generator tags and from sub-package tags. Commit
taxonomy: `feat` / `fix` / `perf` / `deps` / `docs` surface in the
changelog; `chore` / `test` / `ci` / `build` / `style` / `refactor`
are hidden (refactor also hidden here, unlike the library repos).

**No smoke gate.** The meta-package is dependency-only
(`packages = []`, no Python modules, no console scripts). Nothing to
smoke-test at install time — the gate pattern used by the four library
repos does not apply here. `release.yml` goes straight from
`twine check` to PyPI trusted-publishing.

**Dependabot** (`.github/dependabot.yml`): declares the `uv` ecosystem
pointing at `/meta-package` (where `pyproject.toml` and `uv.lock`
live) on a Monday-morning Europe/Dublin schedule. Sibling `nthlayer-*`
packages grouped into a single weekly PR. **No `github-actions`
ecosystem entry** for the front-door workflows because those workflows
pin to `main` by convention. Auto-merge policy in
`.github/workflows/dependabot-automerge.yml`: external patch and dev
patch/minor auto-merge; sibling packages and any major bump require
review.

`release-please.yml` mints a short-lived GitHub App token
(`actions/create-github-app-token@v3`, App `nthlayer-release-bot`,
secrets `RELEASE_APP_ID` / `RELEASE_APP_PRIVATE_KEY`) and passes it to
`release-please-action@v4` as `token:`, so release PRs are authored by
the App identity rather than `GITHUB_TOKEN`. This makes PR CI run
ungated and lets the `meta-v*` release tag auto-fire `release.yml` — it
retires the former manual `GITHUB_TOKEN` cascade-block workaround
(opensrm-l58r / lt91). NOTE: `release.yml` here is single-trigger
(`push: tags: meta-v*` + `workflow_dispatch`), so the l58r
double-trigger dedup does **not** apply.

For the full cross-repo release procedure — coordinating per-library
release-please runs, bumping the meta-package pins, and post-release
PyPI verification — see `docs/release-runbook.md` (added Phase 5).

## Spec + planning references (canonical entry points)

Architectural design docs live under `docs/superpowers/`. The
following are the load-bearing references; the full list is in
`docs/superpowers/specs/` and `docs/superpowers/plans/`.

- Three-tier architecture decision:
  `docs/superpowers/specs/2026-04-21-spec-revision-summary.md`.
- Six-repo consolidation rationale:
  `docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md`.
- Front-door cleanup proposal:
  `docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md`.
- v1.5 epic plan:
  `docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md`.
- Phase 0 decisions ratified:
  `docs/superpowers/plans/2026-04-21-phase-0-decisions.md`.
- V2 reconciliation report:
  `docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md`.
- Core API security audit (P4-SEC.1):
  `docs/superpowers/specs/2026-05-06-core-api-security-audit.md`.
- Dependency security audit (P4-SEC.3):
  `docs/superpowers/specs/2026-05-06-dependency-security-audit.md`.
- Override Adapter Sidecar design + plan (opensrm-jmy.7):
  `docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`
  + `docs/superpowers/plans/2026-05-15-jmy7-override-adapter-sidecar.md`.
- Override Verdict-Binding Path design + plan (opensrm-jmy.18):
  `docs/superpowers/specs/2026-05-20-jmy18-override-verdict-binding-design.md`
  + `docs/superpowers/plans/2026-05-20-jmy18-override-verdict-binding.md`.

OpenSRM specification (the format itself) lives in
[`opensrm`](https://github.com/rsionnach/opensrm).

## v1.5 vs v2 boundary (summary)

| Capability | v1.5 | v2 |
|-----------|------|-----|
| Verdict identity | String IDs (`vrd-...`) | IPLD CIDv1 (canonical CBOR) |
| Verdict encoding | JSON TEXT | Canonical CBOR BLOB |
| Tamper evidence | Hash chain (nthlayer-common/records) | Rekor daily Merkle root anchoring |
| Correlation engine | asyncio session windows | Bytewax dataflow (optional) |
| Authorisation | Respond owns execution (safe-actions) | authorise + executor in core (Regorus, Biscuit) |
| LLM wrapper | `llm_call()` + Instructor additive | `LLM` class refactor |
| Bench delivery | Local terminal only | textual-serve SaaS |

Per-spec reconciliation in
`docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md`.

## Where to find detail

- Integration testing harness, demo.sh guards, three-tier boot
  sequence: `docs/integration-testing.md`.
- AGENTS.md (long form): project vision, roadmap, project layout,
  development patterns, git workflow, beads integration.
- Per-component CLAUDE.md files describe each component's conventions.
- Project memory / Rob's preferences across sessions:
  `~/.claude/projects/-Users-robfox-Documents-GitHub-nthlayer-ecosystem/memory/MEMORY.md`.
- Beads: `cd opensrm && bd ready --json`.
