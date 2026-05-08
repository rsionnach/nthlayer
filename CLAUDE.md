# nthlayer — project front door + ecosystem hub

## NthLayer at a glance

**NthLayer is an open-source reliability platform for SREs.** It compiles service reliability requirements — SLOs, alerts, dashboards, deployment gates, dependency graphs — into observable production infrastructure, then runs an autonomous reliability runtime that observes services, judges their health, correlates incidents, responds to breaches, and learns from outcomes. Built on the [OpenSRM specification](https://github.com/rsionnach/opensrm).

The ecosystem spans seven active repositories: one specification (`opensrm`), one shared library (`nthlayer-common`), one compiler (`nthlayer-generate`), three runtime tiers (`nthlayer-core` / `nthlayer-workers` / `nthlayer-bench`), and this front-door + ecosystem hub (`nthlayer/`). The marketing site (`nthlayer-site`) is a separate concern. **This repository (`nthlayer/`) is the project front door + ecosystem hub** — it hosts the GitHub Action, the PyPI meta-package, ecosystem-wide documentation, integration test infrastructure, demo materials, and the architectural design corpus. Implementation code lives in the per-tier repos.

NthLayer is in **v1.5 development**. The three-tier architecture (core + workers + bench) is being actively built; the six-repo consolidation completed 2026-04-26. Production-ready usage today centres on `nthlayer-generate` plus the OpenSRM spec; runtime tiers are under integration testing for v1.5.

## Components

Each active component has its own CLAUDE.md:

- `nthlayer/` — project front door + ecosystem hub (this repo). Hosts `meta-package/` (PyPI source — `pip install nthlayer`), `action.yml`, `test/`, `demo/`, `docs/`, project documentation. No implementation code.
- `nthlayer-generate/` — pure deterministic compiler: specs → artifacts (Python, stateless, no runtime).
- `nthlayer-core/` — Tier 1 reliability-critical HTTP API server: verdict store, case management. CLI: `nthlayer serve`.
- `nthlayer-workers/` — Tier 2 consolidated runtime process (Apache 2.0): five internal modules — observe, measure, correlate, respond, learn. Communicates with core via HTTP API only.
- `nthlayer-bench/` — Tier 3 Textual TUI operator interface. Communicates with core via HTTP API only.
- `opensrm/` — OpenSRM specification (no code deps).
- `nthlayer-common/` — shared library: LLM wrappers, providers, identity resolution, errors, tier definitions, manifest parser, decision records, verdict model.

Separate concern (not in the active count):

- `nthlayer-site/` — marketing/demo site (separate concern; HTML/JS, no Python; no CLAUDE.md yet).

Deprecated standalone repos (consolidated into nthlayer-workers 2026-04-26): `nthlayer-observe/`, `nthlayer-learn/`, `nthlayer-measure/`, `nthlayer-correlate/`, `nthlayer-respond/`. Each has a PyPI deprecation release that emits a `DeprecationWarning`.

## What this repo hosts

- `README.md` — project front door content; primary audience is potential adopters
- `action.yml` — GitHub Action for `uses: rsionnach/nthlayer@<tag>`; delegates to nthlayer-generate at a pinned version
- `mkdocs.yml`, `docs-site/`, `documentation/`, `presentations/` — docs site source + design assets
- `docs/` — project-level documentation:
  - `docs/specs/` — current NthLayer specifications (Spec Index, Serve Mode v2.1, Bench v2.1, Common, Telemetry Envelope, Learn, Measure, Correlate)
  - `docs/roadmap/` — proposed/upcoming feature specs (Discovery, Drift Detection, Execution & Change Events, Missing Capabilities)
  - `docs/archived-specs/` — superseded or shipped specs preserved as historical record (see `docs/archived-specs/README.md` for archival criteria)
  - `docs/superpowers/` — architectural design docs: per-phase plans (`plans/`) and per-component design specs (`specs/`)
  - `docs/testing.md`, `docs/COSTOPTIMISATION.md`, `docs/metrics-contract.md` — cross-cutting operational docs
- `test/` — cross-repo integration test infrastructure
- `demo/` — runnable cascading-failure scenario, demo orchestrator (`demo.sh`), example OpenSRM specifications
- `.github/workflows/`:
  - `docs.yml` — docs site build + GitHub Pages deploy
  - `ci.yml` — front-door CI
  - `release.yml` — meta-package release to PyPI (triggered on `meta-v*` tags)
  - `integration-three-tier.yml` — cross-repo three-tier integration test (`workflow_dispatch` + nightly cron)
  - `publish-docker.yml` — Docker image publish
- `meta-package/` — source for `pip install nthlayer`. Dependency-only; pins core/workers/bench/generate at matching versions.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, `ATTRIBUTION.md`, `LICENSING_COMPLIANCE.md` — project metadata
- Git tags `v0.1.0a2`–`v0.1.0a20` — preserved; pinned consumers continue to resolve to historical commits

## What does NOT live here

Implementation code, build system, deployment artefacts, generator examples, generator demo, generator-specific scripts.

| Looking for… | Now lives in… |
|---|---|
| Generator code (alerts, dashboards, SLOs, OpenSRM parser) | [`nthlayer-generate`](https://github.com/rsionnach/nthlayer-generate) |
| Verdict model, manifest parser, LLM wrapper, CoreAPIClient | [`nthlayer-common`](https://github.com/rsionnach/nthlayer-common) |
| HTTP API, verdict store, case management | [`nthlayer-core`](https://github.com/rsionnach/nthlayer-core) |
| observe / measure / correlate / respond / learn workers | [`nthlayer-workers`](https://github.com/rsionnach/nthlayer-workers) |
| Operator TUI (situation board, case bench) | [`nthlayer-bench`](https://github.com/rsionnach/nthlayer-bench) |
| OpenSRM specification | [`opensrm`](https://github.com/rsionnach/opensrm) |

## When working in this repo

Most changes are documentation, ecosystem specs, or test/demo infrastructure:

1. **README/CHANGELOG edits** — straightforward markdown.
2. **Docs site changes** — edit `docs-site/`, push, watch `docs.yml` deploy to GitHub Pages.
3. **Spec and design doc edits** — files under `docs/specs/`, `docs/roadmap/`, `docs/archived-specs/`, `docs/superpowers/`. Update relevant cross-references in CLAUDE.md when shape or location changes.
4. **Test/demo infrastructure** — `test/integration-three-tier.sh` exercises the three-tier stack; `demo/demo.sh` drives the cascading-failure scenario. See script headers for invocation, and `docs/superpowers/specs/` for design rationale.

**`action.yml` changes are different.** They affect every consumer using `uses: rsionnach/nthlayer@<tag>`, including downstream production CI pipelines. Pin the action's delegated invocation to a specific `nthlayer-generate` tag, never `main` — drift in the delegated version is a silent regression for every consumer. The pinning invariant and the option-2 delegation rationale are in [the consolidation plan](docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md).

For implementation work, switch to the relevant component repo. Each has its own CLAUDE.md describing its conventions.

## Ecosystem root workspace

The parent directory (`nthlayer-ecosystem/`) is **not a git repository** — it hosts sibling clones of every active member plus three local-only convenience files:

- `pyproject.toml` — editable-deps workspace config. `uv sync` from the ecosystem root builds a single `.venv/` with all five Python members (`nthlayer-common`, `nthlayer-generate`, `nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`) installed editable. Cross-repo edits land immediately.
- `CLAUDE.md` — ecosystem-level agent instructions (member taxonomy, "always operate inside a member repo" rule).
- `README.md` — workspace overview for new contributors.

These files are never committed; CI and per-repo `uv sync` use each member's own `pyproject.toml` + `uv.lock`. The workspace pyproject is dev-convenience only. See the bead `opensrm-hty.6` (RM.6) for the rationale.

## Branch + tag policy

- `main` is the published front-door state. PRs land here.
- Tags `v0.1.0a*` — preserved for historical pinning (legacy generator releases); resolve to historical commits, not updated.
- Tags `meta-v*` — PyPI meta-package releases. Each `meta-v` tag triggers `.github/workflows/release.yml` and publishes to PyPI.
- Stars and the repo URL must not change — first-class social proof and consumer-pinning surfaces.

## PyPI meta-package

`meta-package/` is the authoritative source for `pip install nthlayer`:

- **Purpose:** friendly entry point for evaluators, demos, and local dev. For production, install individual tiers.
- **Content:** dependency-only (`packages = []`); no Python modules, no console scripts.
- **Pinning:** each release pins all four sub-packages at the same version (e.g. `==1.0.0`). nthlayer-common is a transitive dep.
- **Tag namespace:** `meta-v*` (e.g. `meta-v1.0.0`). Separate from legacy `v0.1.0a*` and from sub-package tags.
- **First release:** `meta-v1.0.0` — published; `pip install nthlayer==1.0.0` resolves the full ecosystem closure.
- **Workflow:** `.github/workflows/release.yml` (triggered on `meta-v*` push + `workflow_dispatch`). Trusted publishing.

## Spec + planning references

Current ecosystem specs live in this repo at `docs/specs/`. Architectural design docs at `docs/superpowers/`. Key references:

- [Three-tier architecture decision](docs/superpowers/specs/2026-04-21-spec-revision-summary.md) — the v1.5 architectural foundation
- [Six-repo consolidation rationale](docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md) — why the active repos are shaped the way they are
- [Front-door cleanup proposal](docs/superpowers/specs/2026-04-26-nthlayer-frontdoor-cleanup-proposal.md) — the plan that turned this repo into the ecosystem hub
- [v1.5 epic plan](docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md) — task tree and phase structure for v1.5 delivery
- [Phase 0 decisions ratified](docs/superpowers/plans/2026-04-21-phase-0-decisions.md) — pre-implementation auth, policy, and team-filtering decisions
- [V2 reconciliation report](docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md) — per-spec reconciliation of v2 design discrepancies
- [Core API security audit](docs/superpowers/specs/2026-05-06-core-api-security-audit.md) — P4-SEC.1 audit of nthlayer-core server.py + store.py (opensrm-9uow.1): SQL injection SAFE, error leakage FIXED (`_store_error_response`), input validation ACCEPTABLE, path injection SAFE; known limitations deferred to v2: no auth/CORS/rate-limiting/body-size-limit; related beads: opensrm-9uow.2 (safe-actions), opensrm-9uow.3 (dependencies)
- [Dependency security audit](docs/superpowers/specs/2026-05-06-dependency-security-audit.md) — P4-SEC.3 pip-audit scan of all five active lockfiles (opensrm-9uow.3): one CVE found (pygments 2.19.2, CVE-2026-4539 via `rich ← instructor/typer`), fixed via `pygments>=2.20.0` transitive pin in `nthlayer-common/pyproject.toml`; all five repos re-locked to pygments 2.20.0; pinning policy (uv.lock = exact, pyproject.toml = bounded ranges) and supply-chain mitigations documented

OpenSRM specification (the format itself) lives in [`opensrm`](https://github.com/rsionnach/opensrm).

## Integration testing

Three test surfaces:

- `test/integration-chain.sh` — verdict chain acceptance test (seeded, no Prometheus). See script header.
- `test/integration-three-tier.sh` — P5.1 three-tier ship-readiness test (real core API + workers + bench-via-API). Boots Docker stack, drives reversal_rate breach via fake-service, asserts verdict chain end-to-end. CI integration: `.github/workflows/integration-three-tier.yml` (workflow_dispatch + nightly cron 04:00 UTC, timeout 15 min).
- `test/e2e-test.sh` — 9-step CLI-driven E2E test (opensrm-saun.2). See script header.

For worker pipeline architecture see [`docs/superpowers/specs/2026-04-25-p3-e1-respond-coordinator-worker-design.md`](docs/superpowers/specs/2026-04-25-p3-e1-respond-coordinator-worker-design.md). For demo orchestration see `demo/demo.sh` header and `demo/scenario-cascading-failure.yaml`.

**`test/integration-three-tier.sh` — harness details:**

Env overrides: `CORE_PORT` (default 8000), `FAKE_PORT` (default 8001), `PROMETHEUS_URL` (default `http://localhost:9090`), `LATENCY_BUDGET_SECONDS` (default 30).

Repo resolution: `FRONTDOOR_ROOT` = this repo root; `WORKSPACE_ROOT` = `FRONTDOOR_ROOT/..` — resolves sibling repos the same way in both local sibling-repo layout and CI checkout layout.

`RUN_BENCH` (`uv run --directory nthlayer-bench`) is used for running the assertions helper (not just bench commands) because `test/three_tier_assertions.py` imports `nthlayer_bench.sre.case_bench`.

Boot sequence (always-fresh):
1. `docker compose up -d prometheus` — Prometheus only; Grafana/AlertManager omitted (flaky file-mount, not queried by assertions)
2. Poll Prometheus `/-/ready` (60s)
3. Start `fake-service.py --name fraud-detect --type ai-gate` (15s health check)
4. Start `nthlayer serve` with `NTHLAYER_STORE_PATH` + `NTHLAYER_MANIFESTS_DIR`; poll `/health` (30s); sanity-check `GET /manifests` returns ≥1 manifest
5. Start `nthlayer-workers serve` with `NTHLAYER_LLM_STUB=canned` and all cycle intervals 5s (`--collect-interval 5 --measure-interval 5 --correlate-interval 5 --respond-interval 5`); poll for first heartbeat (30s)

Trigger: `POST /control {"reversal_rate": 0.08, "rps": 100}` to fake-service.

Verdict chain assertions (timeouts chosen for the Prometheus 2m window):
1. `wait-verdict-type quality_breach --service fraud-detect` (180s)
2. `wait-assessment-kind correlation_snapshot` (30s)
3. `wait-verdict-type triage` (60s)
4. `wait-case --service fraud-detect` (60s)
5. `wait-assessment-kind retrospective` (60s) — falls back to `calibration_signal` (60s) if no retrospective yet

Strong lineage: `assert-lineage TRIAGE_ID QUALITY_BREACH_ID` walks `GET /verdicts/{id}/ancestors`. `correlation_snapshot` is an assessment (not a verdict), so the ancestry is walked transitively through verdicts.

Bench-via-API: `fetch-case-via-bench --state pending` directly imports `nthlayer_bench.sre.case_bench.fetch_case_bench` — proves the bench logic layer reads through core API.

Latency budget: `assert-latency QUALITY_BREACH_AT CASE_AT LATENCY_BUDGET_SECONDS` — defined as `quality_breach.created_at` → `case.created_at`; excludes Prometheus window staleness and bench-fetch overhead.

`run_assertion()` pattern: `output=$(...) || fail; eval "${output}"` — the two-step form is load-bearing; the compact `eval "$(…)"` silently swallows assertion failures when the helper produces empty stdout.

Teardown trap (EXIT/INT/TERM): kills workers → core → fake-service in order; runs `docker compose down --remove-orphans`; on failure moves work dir to `/tmp/three-tier-debug-$(date +%s)` and prints known-blocker guidance.

**`.github/workflows/integration-three-tier.yml` — CI details:**

- Triggers: `workflow_dispatch` + cron `0 4 * * *` (nightly 04:00 UTC). NOT on push/PR (takes ~5 min, boots Docker).
- Checks out all 5 repos (`nthlayer`, `nthlayer-common`, `nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`) at `ref: main`. Pinning trade-off: `main` is correct while components co-evolve in v1.5; switch to released versions post-v1.0.
- Installs: `uv` via `astral-sh/setup-uv@v7`; `jq` via apt; `prometheus-client` via pip3 (for fake-service).
- On failure: prints `core.log` (last 100 lines) and `workers.log` (last 200 lines) inline, then uploads `/tmp/three-tier-debug-*` as artifact `three-tier-debug-logs` (7-day retention, `if-no-files-found: ignore`).
- Security: no untrusted GitHub event input flows into shell commands.

<!-- Drop when opensrm-saun.1.2 and opensrm-saun.1.3 close. -->
**Known blockers (auto-failure expected until closed):**
- `opensrm-saun.1.2` — CloudEvents envelope contract mismatch: respond verdicts rejected by core (HTTP 422 missing_fields). Symptom: test reaches "Wait for respond → triage verdict" and times out.
- `opensrm-saun.1.3` — AttributeError in RemediationAgent on canned-LLM responses. Worker keeps running but remediation hits the degraded path.

## v2 migration decisions

Spec reconciliation report: [`docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md`](docs/superpowers/specs/2026-04-20-v2-reconciliation-report.md).

### Repo consolidation (decided 2026-04-21)

Six-repo Option B adopted: opensrm + nthlayer-common + nthlayer-generate + nthlayer-core + nthlayer-workers + nthlayer-bench, plus nthlayer/ (this repo, ecosystem hub) and nthlayer-site/ (separate). Workers consolidates the deprecated standalone observe/measure/correlate/respond/learn repos. Verdict data model moved from nthlayer-learn to `nthlayer_common.verdicts`. Front-door URL preserved (GitHub stars travel with URL). See [`docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md`](docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md).

### Three-tier runtime architecture (decided 2026-04-21)

Tier 1 (`nthlayer-core`) owns state and HTTP API; Tier 2 (`nthlayer-workers`) is the worker process; Tier 3 (`nthlayer-bench`) is the operator TUI. All cross-tier communication is HTTP via `CoreAPIClient`; workers and bench never touch SQLite directly. `NTHLAYER-SERVE-MODE-v2.1` rewritten around this model. See [`docs/superpowers/specs/2026-04-21-spec-revision-summary.md`](docs/superpowers/specs/2026-04-21-spec-revision-summary.md).

### Phase 0 decisions (ratified 2026-04-21)

Auth flow, policy evaluation, team filtering, Regorus vs regopy, and v1.5-first scoping all ratified. Notable: case priority is derived from blast_radius × incident context (not auto-P0); default policy posture is deny-by-default for production/staging, allow-by-default for dev/ephemeral; CloudEvents envelope is frozen across v1.5/v2; workers use HTTP API for both reads and writes from day one. See [`docs/superpowers/plans/2026-04-21-phase-0-decisions.md`](docs/superpowers/plans/2026-04-21-phase-0-decisions.md).

### v1.5 vs v2 boundary

| Capability | v1.5 | v2 |
|-----------|------|-----|
| Verdict identity | String IDs (`vrd-...`) | IPLD CIDv1 (canonical CBOR) |
| Verdict encoding | JSON TEXT | Canonical CBOR BLOB |
| Tamper evidence | Hash chain (nthlayer-common/records) | Rekor daily Merkle root anchoring |
| Correlation engine | asyncio session windows | Bytewax dataflow (optional) |
| Authorisation | Respond owns execution (safe-actions) | authorise + executor in core (Regorus, Biscuit) |
| LLM wrapper | `llm_call()` + Instructor additive | `LLM` class refactor |
| Bench delivery | Local terminal only | textual-serve SaaS |

### v1.5 implementation plan

63 tasks across 8 phases (Phase 0 decisions, Repo Migration RM.1–RM.7, Phases 1–5, Docs, Security). Phase 1 builds primitives (CoreAPIClient, CloudEvents, store schema, core HTTP API); Phase 2 completes core (manifest parser, catalogue); Phase 3 implements workers; Phase 4 builds the bench TUI; Phase 5 wires three-tier integration tests, demo, and release. Tech stack: Python 3.11+, SQLite WAL, Starlette, httpx, Instructor, Textual, scipy, networkx, opentelemetry-sdk.

Canonical plan with task-by-task detail and current progress: [`docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md`](docs/superpowers/plans/2026-04-21-nthlayer-v1.5-epic-tree.md). Per-component design specs are co-located in `docs/superpowers/specs/`.
