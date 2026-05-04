# Spec Revision Summary — Tiered Architecture

**Date:** 2026-04-21
**Purpose:** Summarize changes needed to align spec corpus with three-tier architecture (core/workers/bench) before editing.

---

## Architectural Change Summary

The v2 specs assumed N independent serve processes sharing a SQLite store. The revised architecture has three tiers:

- **Tier 1 — nthlayer-core:** Single process. Owns reliability-critical state: verdict store, case store, change freeze handling, manifest catalogue, HTTP API. In v2: authorise and executor logic.
- **Tier 2 — nthlayer-workers:** Single combined process (v1.5). Internal modules for observe, measure, correlate, respond, learn. Reads from and writes to core exclusively via HTTP API. Worker failure does not affect core.
- **Tier 3 — nthlayer-bench:** Separate process. Textual TUI. Communicates with core via HTTP API.

Key principle: core's availability defines product availability. Worker and bench failures are degradations, not outages.

---

## Per-Spec Changes

### 1. NTHLAYER-SPEC-INDEX-v1 — Moderate revision

- **Document catalogue (§The documents):** Update to reflect three-tier framing. SERVE-MODE becomes the runtime architecture spec describing core, workers, bench rather than per-component serve processes. LEARN/MEASURE/CORRELATE reframed as module specs within workers.
- **Topic index (§Topic index):** Update answers to point at correct tier. E.g., "Where does the store schema live?" → "Core (SERVE-MODE §3)" not "shared store." "What process runs the correlation engine?" → "Workers process (CORRELATE spec, module within workers)."
- **Cross-spec concerns (§Cross-spec concerns):** Update the "Verdicts and storage" concern to note that the store is owned by core, written to by workers via API. Update "Authorisation flow" to note authorise/executor live in core in v2.
- **Reading order (§Reading order recommendations):** Update the Claude Code implementation path to start with the tiered architecture, not per-component serve processes.
- **Spec/implementation boundary (§Specification vs implementation boundary):** Add explicit note: "The three-tier architecture (core, workers, bench) is a property of the NthLayer reference implementation, not of the OpenSRM specification. Alternative implementations may use different process topologies while conforming to the same OpenSRM specification."

### 2. OPENSRM-CORE-v2 — No changes

This is a specification document. It describes what manifests declare, what SLO types exist, and what conformance means. It does not describe process architecture. No revision needed.

### 3. OPENSRM-RBAC-EXTENSION-v2 — Minimal changes

Specification document. Describes authorisation model, policy evaluation, capability tokens. Process-agnostic.

- **§11 (Component Responsibilities):** Currently names nthlayer-authorise and nthlayer-executor as separate components. Update to note that in the tiered model, authorise and executor are modules within nthlayer-core, not independent processes. The logical responsibilities are unchanged; the process boundary moves.
- **§12 (Worked Example):** Update to clarify that the authorise and executor steps happen within the core process, not via inter-process communication.
- All other sections unchanged — they describe the authorization model, not the process topology.

### 4. NTHLAYER-SERVE-MODE-v2.1 — Substantial revision (rename candidate)

This is the most affected spec. Currently describes N independent serve processes. Needs to describe three tiers.

- **Title:** Consider renaming to "NthLayer Runtime Architecture" since "serve mode" implies per-component serving.
- **§1 (Motivation):** Rewrite to explain the tiered architecture and its reliability justification. The "pull over push, SQLite over distributed" principle stays. Add: "A reliability product's architecture must exhibit reliability properties. Collocating audit recording and LLM correlation in one process creates unacceptable blast radius."
- **§2 (Pipeline Overview):** Replace the per-component pipeline diagram with a three-tier diagram:
  - Core: HTTP API, verdict store, case store, change freeze store, manifest catalogue, heartbeat monitoring. In v2: authorise + executor modules.
  - Workers: observe, measure, correlate, respond, learn modules. Single process. Reads core state, writes outputs via core API.
  - Bench: separate process, communicates via core API.
- **§3 (Store):** Reframe as the core's store. Schema stays the same (§3.5 is unchanged). Add: "Workers do not access the store directly — they read from and write to the core exclusively via HTTP API. This is true from v1.5 onwards; there is no transitional direct-DB-read phase. Workers may maintain internal state stores (e.g., correlate's FTS5 index) that are not part of the core's schema."
  - §3.2 (Configuration) — unchanged (WAL, pragmas)
  - §3.4 (Litestream) — unchanged
  - §3.5 (Schema) — unchanged but clarify: this is the core's schema. **Preserve the `rekor_anchors` table definition in v1.5 even though it will be empty.** Forward compatibility is cheap when planned; removing it would force a schema migration in v2.
  - §3.7 (Retention) — retention job runs in core (not in learn)
- **§4 (Component Base Pattern):** Split into two patterns:
  - **Core pattern:** HTTP server + background jobs (retention, heartbeat monitoring, WAL checkpointing). `restore_state → start_api → run_background_jobs`.
  - **Worker module pattern:** Each module in the workers process implements: `restore_state → process_cycle → persist_state`. The workers process orchestrates modules on their configured intervals. Heartbeats emitted by the workers process, not per-module.
- **§5 (Component Technology Stack):** Restructure as tier-to-technology mapping:
  - §5.1 Core: SQLite (WAL), HTTP framework (Starlette or similar), sqlite-utils
  - §5.2 Workers — observe module: prometheus-api-client, prometheus-client, promql-parser
  - §5.3 Workers — measure module: nthlayer-common.llm, Instructor, scipy.stats, scikit-learn
  - §5.4 Workers — correlate module: asyncio + session-window logic (not Bytewax in v1.5), networkx, PD-CEF ingest
  - §5.5 Workers — respond module: asyncio orchestrator, nthlayer-common.llm, Instructor
  - §5.6 Workers — learn module: lineage index maintenance, retention job (delegated to core), retrospective analysis
  - §5.7 Core (v2 additions): Regorus, biscuit-python, PyNaCl
  - §5.8 Shared: nthlayer-common (used by core, workers, and bench)
  - §5 is explicitly scoped to core and workers technology. For Bench technology (Textual, textual-plotext, httpx), cross-reference NTHLAYER-BENCH-v2.1 §3.
  - Remove Bytewax as default for correlate (per C-9.1: asyncio for v1.5)
  - Remove IPLD CIDs as default for verdicts (per C-7.1: string IDs valid for v1.5, CIDs in v2)
- **§6 (Pipeline Latency):** Unchanged conceptually. Pipeline latency still tracked per verdict. Clarify: latency measured from first signal to final output, crossing the core API boundary adds minimal overhead.
- **§7 (Suppression/Dedup):** Unchanged. Logic runs in worker modules; suppression records written to core.
- **§8 (Heartbeats):** Simplify. Core monitors heartbeats. Workers process emits one heartbeat per cycle (not per-module). Bench emits heartbeat to core.
- **§9 (Rekor Anchoring):** Move to v2 deferred section. String IDs in v1.5 mean CID-based Merkle roots are deferred. Document as v2 capability. Note: the `rekor_anchors` table schema is preserved in v1.5 (empty, forward-compatible).
- **§10 (Wire Format):** Adopt CloudEvents envelope now (additive, per C-5.1 resolution). CBOR encoding deferred to v2. **Make explicit: the CloudEvents v1.0 envelope format adopted in v1.5 is stable and will not change in v2. v2 adds CBOR content encoding inside the envelope but the envelope structure, type taxonomy, and attribute naming are frozen from v1.5 onwards.** This gives consumers a stable integration surface.
- **§11 (Alert Schema: PD-CEF):** Unchanged.
- **§12 (Scale-Out):** Add: "The three-tier model's first scale-out step is splitting workers into separate processes per module. This requires no schema changes — each worker process is an independent client of the core API."
- **§13 (Integration Test Harness):** Update to test the three-tier deployment: start core, start workers, inject Prometheus breach, verify chain propagation, verify core API responses, verify Bench can read cases.
- **§14 (Open Questions):** Add the v1.5-vs-v2 boundary decisions (what's deferred: CIDs, CBOR, Rekor, Biscuit/Regorus, authorise/executor).

### 5. NTHLAYER-TELEMETRY-ENVELOPE-v1 — Minimal changes

Wire format spec. Architecture-agnostic.

- **§3.2 (Required Attributes):** Update `source` pattern. Currently `urn:nthlayer:<component>:<deployment_id>`. In tiered model, source should be `urn:nthlayer:core:<deployment_id>` or `urn:nthlayer:workers:<module>:<deployment_id>` or `urn:nthlayer:bench:<deployment_id>`. Minor pattern update.
- All other sections unchanged — CloudEvents format, OTel attributes, PD-CEF schema, decision logs are all process-topology-independent.

### 6. NTHLAYER-COMMON-v1 — Minimal changes

Shared library. Used by both core and workers.

- **§1 (Purpose):** Add: "Used by nthlayer-core for HTTP API, store access, and data models. Used by nthlayer-workers for LLM integration, provider access, and data models. Used by nthlayer-bench for data models and HTTP client to core API."
- **§4 (Store Access):** Add: "In the tiered architecture, direct store access (StorePool) is used by nthlayer-core. Workers submit verdicts/assessments via core's HTTP API. The VerdictStore interface in common provides both direct-access and API-client implementations."
  - Add `CoreAPIClient` alongside `StorePool` as access patterns.
- **§10 (Configuration):** Clarify that single `nthlayer.yaml` has sections for `core:`, `workers:`, `bench:` rather than per-component sections.
- All other sections unchanged. LLM wrapper, provider integrations, identity, telemetry, error handling, data models are tier-independent.

### 7. NTHLAYER-LEARN-v1 — Moderate framing changes

- **§1 (Purpose):** Reframe: "nthlayer-learn is a module within the workers process..." rather than "a component." Ownership list unchanged.
  - Remove IPLD CID as mandatory for v1.5. Add: "v1.5 uses string verdict IDs with JSON encoding. v2 adopts IPLD CIDs with canonical CBOR encoding. Both are valid implementations."
  - Move Rekor anchoring to v2 deferred.
- **§2 (Position in Pipeline):** Update diagram to show learn as a module within workers, writing to core via API. Currently shows learn as standalone component.
- **§3 (Architectural Thesis):** Soften CID absolutism for v1.5:
  - "Content addressing uses real IPLD CIDs" → "v2 adopts IPLD CIDs; v1.5 uses string IDs with a lineage index for equivalent query capability"
  - Tamper evidence paragraph: "v2 anchors to Rekor; v1.5 relies on SQLite WAL integrity and the hash chain in nthlayer-common/records"
- **§4 (Verdict Primitive):** Keep the CID-based shape as the primary specification. Add a clearly-labelled **"§4.X v1.5 Transitional Shape"** subsection that documents the string-ID + JSON-encoding shape. Frame this as the v1.5 implementation path that will be migrated to the CID-based shape in v2 — not as a co-equal alternative. The transitional shape should reference the same field semantics (subject, judgment, outcome, lineage, producer) but with string IDs in place of CIDs and JSON TEXT in place of CBOR BLOB.
- **§5 (Storage):** Lineage index table (additive) stays for both v1.5 and v2 — it's purely a performance improvement that works with string IDs too.
- **§6 (Rekor Anchoring):** Mark entire section as v2 deferred. Add note: "Deferred from v1.5. String IDs cannot produce the content-addressed Merkle roots this section requires. **v1.5 audit integrity relies on SQLite WAL mode (crash-consistent writes), the SHA-256 hash chain in nthlayer-common/records (append-only linkage with fork detection), and the core's exclusive ownership of the store (no direct external writes).** This provides operational integrity without third-party verifiability. v2's Rekor anchoring adds the external tamper-evidence layer."
- **§7 (Retrospective Analysis):** Unchanged. Runs as module in workers.
- **§8 (Retention):** Clarify: retention job runs in core, triggered by core's background scheduler, not by the learn module directly. Learn module can request retention checks.

### 8. NTHLAYER-MEASURE-v1 — Moderate framing changes

- **§1 (Purpose):** Reframe: "nthlayer-measure is a module within the workers process..." Same four responsibilities.
- **§2 (Position in Pipeline):** Update diagram to show measure as a module within workers, reading from core's verdict store (via API), writing evaluations/verdicts to core.
- **§4 (Judgment SLO Evaluation):** Unchanged. The eight evaluator types, evaluation cycle, and evaluator interface are logic that lives in the module regardless of process boundary.
- **§5 (Self-Calibration):** Unchanged.
- **§6 (Autonomy Governance):** Unchanged. The five named levels and ratchet logic are module-internal. Autonomy state written to core.
- **§9 (Output):** Clarify: three output types (judgment_slo_evaluation assessment, quality_breach verdict, autonomy_change verdict) submitted to core via API.
- **§10 (State and Persistence):** Split: module-internal state (calibration history, evaluation cursor) stays in workers' local state. Output verdicts/assessments go to core.

### 9. NTHLAYER-CORRELATE-v1 — Moderate framing + Bytewax changes

- **§1 (Purpose):** Reframe: "nthlayer-correlate is a module within the workers process..."
- **§2 (Position in Pipeline):** Update diagram to show correlate as module in workers, reading from core and external sources, writing to core.
- **§4 (Streaming Substrate):** Substantial change per C-9.1:
  - Rename section to **"Session Window Semantics"** rather than "Streaming Substrate: Bytewax" — the load-bearing property is the session-window grouping behaviour, not the streaming framework
  - Default implementation: asyncio-based session-window logic (events grouped by correlation domain, windows close after 60s gap)
  - Bytewax documented as optional for high-throughput deployments, not as the default
  - Remove Bytewax from v1.5 dependency list
  - Keep the `fold_window` session-window semantics — just implement them in asyncio rather than requiring Bytewax
- **§6 (Topology Integration):** Unchanged. networkx for graph algorithms.
- **§9 (Output):** Clarify: three output types (correlation_snapshot, topology_drift, contract_divergence) submitted to core via API.
- **§10 (State and Persistence):** Split: FTS5 event store is module-internal (per C-9.2). Output verdicts/assessments go to core.

### 10. NTHLAYER-BENCH-v2.1 — Minimal changes

Already a separate process in the spec.

- **§3.4 (Polling & async):** Update from "SQLite WAL accessed via async SQLAlchemy" to "Core HTTP API accessed via httpx." Bench does not access the SQLite store directly; it goes through the core's API. **Add explicit handling notes:**
  - **Connection retries:** Bench must retry on transient HTTP failures (connection refused, 503) with exponential backoff (initial 1s, max 30s). Core restart should not crash Bench.
  - **Cache invalidation:** Bench caches case list and situation board data locally with TTLs (case list: 2-5s, situation board: 30-60s). On write operations (approve, reject, lease), invalidate relevant cache entries immediately rather than waiting for TTL expiry.
  - **Graceful degradation during core restarts:** When core is unreachable, Bench displays last-known state with a prominent "Core unreachable — data may be stale" banner. Read-only browsing of cached data continues. Write operations queue locally and replay on reconnection (with conflict detection via ETags or version fields).
- **§4 (Domain Model):** Unchanged. Case model, leasing, priority — all consumed from core API.
- **§12 (Implementation Phases):** Unchanged. Phases 1-7 are bench-specific development.
- Add note in §3.2 (SaaS delivery via textual-serve): deferred to v2.

---

## Changes NOT Required

- **OPENSRM-CORE-v2:** Specification. Architecture-independent. No changes.
- **OPENSRM-RBAC-EXTENSION-v2:** Specification. Minimal changes (§11, §12 process topology notes only).
- **NTHLAYER-TELEMETRY-ENVELOPE-v1:** Wire format. Architecture-independent except source URN pattern.

---

## v1.5 vs v2 Boundary (captured in spec revisions)

| Capability | v1.5 | v2 |
|-----------|------|-----|
| Verdict identity | String IDs (`vrd-...`) | IPLD CIDv1 (libipld, canonical CBOR) |
| Verdict encoding | JSON TEXT | Canonical CBOR BLOB |
| Tamper evidence | Hash chain (nthlayer-common/records) | Rekor daily Merkle root anchoring |
| Correlation engine | asyncio session windows | Bytewax dataflow (optional) |
| Authorisation | Respond owns execution (safe-actions) | authorise + executor in core (Regorus, Biscuit) |
| LLM wrapper | `llm_call()` + Instructor additive | `LLM` class refactor |
| Content addressing | Two parallel systems coexist | Single IPLD CID system |
| Bench delivery | Local terminal only | textual-serve SaaS |
| Store access | Workers: API for both read and write | Workers: API for both read and write (unchanged) |

---

## Reliability-Thesis Test

For each major decision, does core remain isolated from worker/bench failures?

| Decision | Core isolated? | Notes |
|----------|---------------|-------|
| Workers write to core via API | Yes | Core validates input; worker crash = degraded evaluation, not lost audit trail |
| Bench communicates via API | Yes | Bench crash = no operator UI, core and workers continue |
| Workers maintain internal state (FTS5, calibration) | Yes | Internal state loss = worker restarts from last cursor, core data intact |
| Core owns retention job | Yes | No dependency on worker availability for data hygiene |
| Heartbeats monitored by core | Yes | Core detects worker absence; no inverse dependency |
| CloudEvents adopted in v1.5 | Neutral | Wire format, not failure domain |
| Rekor deferred to v2 | Neutral | Additive capability, no failure path |
