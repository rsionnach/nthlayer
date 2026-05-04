# Repository Consolidation Recommendation

**Date:** 2026-04-21
**Purpose:** Recommend 4-repo vs 6-repo structure for tiered architecture. Migration plan.

---

## Current State

The ecosystem monorepo at `nthlayer-ecosystem/` contains 8 standalone git repos (subtrees) plus ecosystem-level infrastructure:

| Directory | Git | Python src files | Role |
|-----------|-----|-----------------|------|
| `nthlayer/` | standalone repo | 227 | Compiler (specs → artifacts) |
| `nthlayer-observe/` | standalone repo | 47 | Runtime SLO assessment |
| `nthlayer-learn/` | standalone repo | 10 | Verdict data primitive |
| `nthlayer-measure/` | standalone repo | 41 | Quality measurement |
| `nthlayer-correlate/` | standalone repo | 29 | Signal correlation |
| `nthlayer-respond/` | standalone repo | 35 | Incident response |
| `nthlayer-common/` | standalone repo | 45 | Shared library |
| `opensrm/` | standalone repo | 0 | Specification + schemas |
| `nthlayer-site/` | subdirectory (no .git) | 0 | Marketing site (also exists at ~/Documents/GitHub/nthlayer-site) |

Ecosystem-level (not in any component repo):
- `test/` — Docker compose, fake services, e2e test, webhook receiver
- `demo/` — Demo orchestrator, scenario runner, specs
- `docs/` — Cross-cutting specs and plans
- `CLAUDE.md` — Ecosystem-level instructions
- 9 spec documents (`NTHLAYER-*.md`, `OPENSRM-*.md`)

### Current cross-dependencies

```
nthlayer         → nthlayer-common
nthlayer-observe → nthlayer-common, nthlayer-learn
nthlayer-measure → nthlayer-common, nthlayer-learn
nthlayer-correlate → nthlayer-common, nthlayer-learn
nthlayer-respond → nthlayer-common, nthlayer-learn
```

All cross-deps use `path = "../nthlayer-common"` style editable installs. No PyPI publishing yet.

---

## Option A: Four Repos

```
opensrm/              — Specification (OPENSRM-CORE, OPENSRM-RBAC-EXTENSION, schemas, examples)
nthlayer/             — Core + common + generate (compiler)
nthlayer-workers/     — Workers process (observe, measure, correlate, respond, learn modules)
nthlayer-bench/       — Operator terminal (Textual TUI)
```

### Layout

```
opensrm/
├── OPENSRM-CORE-v2.md
├── OPENSRM-RBAC-EXTENSION-v2.md
├── spec/                    (JSON schemas)
├── conventions/             (OTel semantic conventions)
├── examples/                (example manifests)
└── action/                  (GitHub Action)

nthlayer/
├── src/nthlayer/
│   ├── common/              (merged from nthlayer-common/src/nthlayer_common/)
│   │   ├── llm.py
│   │   ├── errors.py
│   │   ├── tiers.py
│   │   ├── records/
│   │   ├── providers/
│   │   ├── identity/
│   │   └── ...
│   ├── generate/            (renamed from current nthlayer compiler code)
│   │   ├── cli/
│   │   ├── specs/
│   │   ├── generators/
│   │   ├── slos/
│   │   ├── dashboards/
│   │   └── ...
│   ├── core/                (NEW: Tier 1 process)
│   │   ├── api.py           (HTTP API)
│   │   ├── store.py         (unified SQLite store)
│   │   ├── retention.py
│   │   ├── heartbeat.py
│   │   └── cli.py
│   └── learn/               (verdict data model, shared by core and workers)
│       ├── models.py
│       ├── store.py
│       ├── serialise.py
│       └── ...
├── specs/                   (implementation specs: SERVE-MODE, COMMON, LEARN, TELEMETRY)
├── test/                    (Docker compose, fake services, e2e)
├── demo/                    (demo orchestrator)
└── pyproject.toml

nthlayer-workers/
├── src/nthlayer_workers/
│   ├── observe/             (from nthlayer-observe/src/nthlayer_observe/)
│   ├── measure/             (from nthlayer-measure/src/nthlayer_measure/)
│   ├── correlate/           (from nthlayer-correlate/src/nthlayer_correlate/)
│   ├── respond/             (from nthlayer-respond/src/nthlayer_respond/)
│   ├── learn/               (retrospective analysis, calibration — NOT the data model)
│   ├── runner.py            (module orchestrator)
│   └── cli.py
├── specs/                   (MEASURE, CORRELATE module specs)
├── tests/
└── pyproject.toml           (depends on nthlayer[common])

nthlayer-bench/
├── src/nthlayer_bench/
│   ├── app.py               (Textual app)
│   ├── screens/
│   ├── widgets/
│   └── cli.py
├── specs/                   (BENCH spec)
├── tests/
└── pyproject.toml           (depends on nthlayer[common])
```

### Maintenance overhead

| Factor | Assessment |
|--------|-----------|
| **CI pipelines** | 4 repos × 1 pipeline = manageable. opensrm has no CI (spec only). |
| **Cross-repo dependency management** | nthlayer-workers and nthlayer-bench depend on nthlayer. One dep to track. During dev, `path = "../nthlayer"` editable installs. |
| **Version coordination** | Three Python packages (nthlayer, nthlayer-workers, nthlayer-bench) need compatible versions. Single semver with lockstep release is simplest. |
| **PR review** | Changes to common affect all three. In 4-repo model, common change = PR to nthlayer, then update deps in workers/bench. Friction when common changes frequently (which it will during v1.5 buildout). |
| **Code navigation** | IDE needs 4 repos open. Acceptable. |
| **nthlayer package complexity** | nthlayer becomes a large package: common + generate + core + learn data model. 300+ source files. Logical but big. |
| **Risk:** common change breaks workers | Path deps mitigate during dev. PyPI pinning mitigates in production. But during active development, this is the #1 friction source. |

### Pros
- Matches tiered architecture exactly (core, workers, bench)
- Fewer repos = fewer CI configs, fewer version bumps
- Common code in same repo as core = no cross-repo PRs for most changes

### Cons
- nthlayer package becomes large (common + generate + core + learn)
- Breaking common change requires coordinating across 3 repos even during dev
- `nthlayer` name overloaded: is it the compiler? the core? the package?

---

## Option B: Six Repos

```
opensrm/              — Specification
nthlayer-common/      — Shared library (used by all Python packages)
nthlayer-generate/    — Compiler (specs → artifacts), renamed from nthlayer
nthlayer/             — Core process (Tier 1) — NEW, takes the nthlayer name
nthlayer-workers/     — Workers process (Tier 2)
nthlayer-bench/       — Operator terminal (Tier 3)
```

### Layout

```
opensrm/              (unchanged from Option A)

nthlayer-common/
├── src/nthlayer_common/     (current nthlayer-common, unchanged)
│   ├── llm.py
│   ├── errors.py
│   ├── records/
│   ├── providers/
│   ├── identity/
│   └── ...
├── tests/
└── pyproject.toml

nthlayer-generate/
├── src/nthlayer_generate/   (renamed from nthlayer/src/nthlayer/)
│   ├── cli/
│   ├── specs/
│   ├── generators/
│   ├── slos/
│   ├── dashboards/
│   └── ...
├── tests/
└── pyproject.toml           (depends on nthlayer-common)

nthlayer/                    (NEW: Core process)
├── src/nthlayer/            (package name is `nthlayer` — `pip install nthlayer` gives you the core)
│   ├── api.py               (HTTP API)
│   ├── store.py             (unified SQLite store)
│   ├── retention.py
│   ├── heartbeat.py
│   └── cli.py
├── specs/                   (SERVE-MODE, LEARN)
├── tests/
└── pyproject.toml           (depends on nthlayer-common)

nthlayer-workers/
├── src/nthlayer_workers/
│   ├── observe/
│   ├── measure/
│   ├── correlate/
│   ├── respond/
│   ├── learn/               (retrospective analysis module, imports verdict model from nthlayer-common)
│   ├── runner.py
│   └── cli.py
├── specs/                   (MEASURE, CORRELATE module specs)
├── tests/
└── pyproject.toml           (depends on nthlayer-common only; communicates with core via HTTP API)

nthlayer-bench/
├── src/nthlayer_bench/
│   ├── app.py
│   ├── screens/
│   ├── widgets/
│   └── cli.py
├── specs/                   (BENCH spec)
├── tests/
└── pyproject.toml           (depends on nthlayer-common only; communicates with core via HTTP API)
```

### Maintenance overhead

| Factor | Assessment |
|--------|-----------|
| **CI pipelines** | 6 repos × 1 pipeline. opensrm and nthlayer-common are small/stable. |
| **Cross-repo dependency management** | Workers/bench depend on common + core. Two deps to track. Generate depends on common only. |
| **Version coordination** | Five Python packages. Lockstep semver still simplest. |
| **PR review** | Common change = PR to nthlayer-common, then bump in 4 downstream repos. More friction than Option A. BUT: common is expected to stabilize first (it's Phase 1). After that, friction drops. |
| **Code navigation** | IDE needs 6 repos. Acceptable with workspace config. |
| **Package sizes** | Each package is focused: common (45 files), generate (~227), core (~20-30 new), workers (~160 merged), bench (new). Clean separation. |
| **Risk:** common change breaks downstream | Same as Option A but affects 4 repos not 2. Mitigated by common stabilizing early. |

### Pros
- Each package has a single clear responsibility
- `nthlayer-common` changes are isolated — downstream repos bump explicitly
- `nthlayer-generate` (compiler) is cleanly separated from runtime — different release cadence, different users
- `nthlayer` name reserved for the product's core process (the thing users run)
- Smaller packages = easier to reason about, easier to test
- No name overloading

### Cons
- More repos = more CI config, more version bumps
- Common changes during early development create cross-repo PRs
- nthlayer-learn's data model needs to be importable by both core and workers — either lives in common or core, workers depends on core

---

## Decision: Six Repos (Option B) — Plus nthlayer-site

**Seven repos total.** Six Python repos plus one static site repo:

```
opensrm/              — Specification (CNCF submission candidate)
nthlayer-common/      — Shared library
nthlayer-generate/    — Compiler (renamed from current nthlayer/)
nthlayer/             — Core process (Tier 1). Package name: `nthlayer`. pip install nthlayer gives you the core.
nthlayer-workers/     — Workers process (Tier 2)
nthlayer-bench/       — Operator terminal (Tier 3)
nthlayer-site/        — Marketing/demo site (HTML/JS, no Python)
```

**Reasoning:**

1. **Name clarity.** `pip install nthlayer` gives you the core — the thing you run. `pip install nthlayer-generate` gives you the compiler — a build tool. This matches how users think about the product.

2. **Separation of concerns is load-bearing.** The compiler has fundamentally different users, release cadence, and dependency profile from the runtime. Forcing them into one package creates coupling with no benefit.

3. **Common stabilizes first.** The early-phase friction of cross-repo PRs is real but temporary. `nthlayer-common` is Phase 1 work; by Phase 2, its interface is stable and downstream repos bump versions rather than coordinating code changes.

4. **Clean dependency graph (no cycles).**
   ```
   opensrm (spec, no code deps)
   nthlayer-common (no deps on other nthlayer packages)
   nthlayer-generate → nthlayer-common
   nthlayer (core) → nthlayer-common
   nthlayer-workers → nthlayer-common (communicates with core via HTTP API, not import)
   nthlayer-bench → nthlayer-common (communicates with core via HTTP API, not import)
   nthlayer-site (no Python deps)
   ```
   Workers and bench do NOT depend on core as a Python package. The only Python import dependency is common.

5. **Verdict data model lives in common.** `nthlayer_common.verdicts` (models, serialise, store, sqlite_store) imported by core, workers, and bench. The learn "module" in workers handles retrospective analysis, not the data model.

6. **nthlayer-site stays independent.** It's already a separate repo at `~/Documents/GitHub/nthlayer-site`. HTML/JS, no Python, different toolchain. No reason to fold it into a Python repo.

---

## Ecosystem Root Structure

`nthlayer-ecosystem/` remains a lightweight workspace root. **No git submodules.** Simple editable-install configuration for development.

```
nthlayer-ecosystem/
├── README.md                 (workspace overview, setup instructions)
├── pyproject.toml            (workspace-level: uv workspace or pip editable installs for all repos)
├── CLAUDE.md                 (ecosystem-level instructions)
├── test/                     (Docker compose, fake services, e2e tests — stays here)
├── demo/                     (demo orchestrator, scenario runner — stays here)
├── docs/                     (cross-cutting specs, plans)
├── opensrm/                  (git repo)
├── nthlayer-common/          (git repo)
├── nthlayer-generate/        (git repo)
├── nthlayer/                 (git repo — core)
├── nthlayer-workers/         (git repo)
├── nthlayer-bench/           (git repo)
└── nthlayer-site/            (git repo, or symlink to ~/Documents/GitHub/nthlayer-site)
```

**test/ and demo/ stay at ecosystem root**, not in nthlayer-core. Rationale: e2e tests and demos exercise the full stack (core + workers + fake services + Docker infrastructure). They depend on all repos being present. Putting them in core would create a false impression that they test only the core.

**Dev setup:** A workspace-level `pyproject.toml` (or `uv` workspace config) provides editable installs of all Python packages. `uv sync` from the ecosystem root installs everything.

---

## Spec-to-Repo Mapping

| Spec document | Target repo | Rationale |
|---------------|-------------|-----------|
| NTHLAYER-SPEC-INDEX-v1 | `nthlayer-ecosystem/` (root) | Cross-cutting navigation; references all repos |
| OPENSRM-CORE-v2 | `opensrm/` | Specification document |
| OPENSRM-RBAC-EXTENSION-v2 | `opensrm/` | Specification document |
| NTHLAYER-SERVE-MODE-v2.1 (→ "Runtime Architecture") | `nthlayer/` (core) | Describes core's store, API, and tier architecture |
| NTHLAYER-TELEMETRY-ENVELOPE-v1 | `nthlayer-common/` | Wire format used by all components; lives with the shared library |
| NTHLAYER-COMMON-v1 | `nthlayer-common/` | Describes its own repo |
| NTHLAYER-LEARN-v1 | `nthlayer/` (core) | Verdict data model owned by core (via common import); lineage/retention logic in core |
| NTHLAYER-MEASURE-v1 | `nthlayer-workers/` | Module spec for the measure module |
| NTHLAYER-CORRELATE-v1 | `nthlayer-workers/` | Module spec for the correlate module |
| NTHLAYER-BENCH-v2.1 | `nthlayer-bench/` | Describes its own repo |

---

## nthlayer-common API-Stability Obligation

`nthlayer-common` is a shared dependency of every other Python package. This creates an explicit stability obligation:

1. **Semantic versioning is strict.** Breaking changes increment the major version. Downstream packages pin to `nthlayer-common>=X.Y,<X+1`.
2. **Interface changes require downstream impact assessment.** Before merging a common change, verify it doesn't break core, workers, bench, or generate. The ecosystem root's editable-install setup makes this a single `uv sync && pytest` across all repos.
3. **Stabilize early, change rarely.** Common is Phase 1 work. By Phase 2, its public API should be stable. New functionality is additive (new modules, new functions); existing signatures don't change without major version bump.
4. **The verdict data model (`nthlayer_common.verdicts`) is the most stability-critical surface.** It's imported by every repo. Schema changes here are migration events.
5. **During active v1.5 development**, common changes are expected to be frequent. This is accepted. The discipline is: run the full test suite across all repos before merging to common's main branch.

---

## Migration Plan

### Phase M1: Create nthlayer-generate from existing nthlayer

1. Copy `nthlayer/` → `nthlayer-generate/`
2. Rename package: `nthlayer` → `nthlayer_generate` in `pyproject.toml`, `src/` directory, all imports
3. Update CLI entry point: `nthlayer-generate` (keep `nthlayer` as alias for backward compat)
4. Update dependency: `nthlayer-common>=0.1.7`
5. Run existing nthlayer test suite against renamed package
6. Original `nthlayer/` directory preserved during transition (deleted in M5)

### Phase M2+M4 (combined): Move verdict model to common AND create workers per component

Rather than moving the verdict model to common first (M2) and then moving component code to workers separately (M4), combine them per component to avoid double-updating imports:

1. Move verdict data model to common:
   - `nthlayer-learn/lib/python/nthlayer_learn/models.py`, `serialise.py`, `store.py`, `sqlite_store.py` → `nthlayer-common/src/nthlayer_common/verdicts/`
   
2. For each component (observe, measure, correlate, respond), in one pass:
   - Move source: `nthlayer-observe/src/nthlayer_observe/` → `nthlayer-workers/src/nthlayer_workers/observe/`
   - Update all imports simultaneously: `from nthlayer_learn` → `from nthlayer_common.verdicts`, `from nthlayer_observe` → `from nthlayer_workers.observe`
   - Run that component's tests before moving to the next

3. Move learn module (retrospective, CLI) → `nthlayer-workers/src/nthlayer_workers/learn/`

4. Add module runner/orchestrator (`runner.py`, `cli.py`)

5. Workers depends on `nthlayer-common` only. Outputs go to core via HTTP API.

6. Validate: all existing test suites pass with new import paths.

### Phase M3: Create nthlayer (core)

1. New repo: `nthlayer/` (after original renamed to nthlayer-generate in M1)
2. Package name: `nthlayer` (Python import: `import nthlayer`, pip: `pip install nthlayer`)
3. Implement: HTTP API skeleton, unified store schema (from SERVE-MODE §3.5 including empty `rekor_anchors`), retention job, heartbeat monitor
4. Core depends on `nthlayer-common`
5. Test: core starts, serves API, accepts verdict submissions, case queries

M2+M4 and M3 can run in parallel (both start after M1).

### Phase M4b: Create nthlayer-bench

1. New repo: `nthlayer-bench/`
2. Greenfield implementation per BENCH spec
3. Depends on `nthlayer-common`
4. Communicates with core via HTTP API

Starts after M3 (needs core API).

### Phase M5: Cleanup

1. Delete original component directories: `nthlayer-observe/`, `nthlayer-learn/`, `nthlayer-measure/`, `nthlayer-correlate/`, `nthlayer-respond/`, original `nthlayer/`
2. Distribute spec documents to target repos per the spec-to-repo mapping above
3. Update ecosystem root: workspace `pyproject.toml`, `CLAUDE.md`, `README.md`
4. Update all per-repo CLAUDE.md files

### Preserved during migration

- All git history preserved per-repo
- All existing tests continue to pass at each phase (imports updated, logic unchanged)
- Existing CLI entry points preserved as aliases where needed
- `nthlayer-site/` stays as-is (separate repo)
- `opensrm/` stays as-is
- `test/` and `demo/` stay at ecosystem root

### Migration sequencing

```
M1 (rename nthlayer → nthlayer-generate)
  ↓
M2+M4 (verdict model to common + create workers)  ←── parallel with M3
M3 (create core)                                   ←── parallel with M2+M4
  ↓
M4b (create bench)  ← needs core API from M3
  ↓
M5 (cleanup)        ← after all above validated
```
