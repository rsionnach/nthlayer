# NthLayer Serve Mode — v2.1-draft

**Status:** Draft for implementation
**Supersedes:** NTHLAYER-SERVE-MODE-V2.md v2.0-draft
**Date:** 2026-04-19

---

## Delta Summary

This revision aligns the serve-mode pipeline with the technology choices from the RBAC extension v1.1 and the OSS delegation research. The architectural model (pull-based pipeline, shared SQLite WAL store, long-running serve processes, heartbeats, semantic deduplication, active-incident suppression, persistent hysteresis) is unchanged. What changes is the substrate for several components:

| v2.0 (hand-rolled or unspecified) | v2.1 (delegated) | Rationale |
|---|---|---|
| Prometheus integration in nthlayer-observe | **`prometheus-api-client` + `prometheus-client` + `promql-parser`** | Mature libraries, no need to reinvent |
| SQLite backup/DR unspecified | **Litestream sidecar** | Actively revived, continuous backup to object storage |
| Verdict IDs as opaque strings | **IPLD CIDs via `libipld`** | Content-addressed, shareable, verifiable |
| Decision/verdict wire format bespoke | **CloudEvents v1.0 envelope + OTel logs** | CNCF-graduated, SIEM-ready |
| Topology drift detection unspecified | **OTel servicegraph connector** | Observed-reality layer for topology |
| Alert schema bespoke | **PD-CEF superset** | Every major monitoring tool speaks it |
| Correlation engine hand-rolled | **Bytewax dataflow** (see nthlayer-correlate spec) | Python-native, Rust core, session windows |
| Future push coordination TBD | **NATS JetStream** (pre-selected upgrade) | CNCF-incubating, asyncio-native |
| External tamper evidence absent | **Sigstore Rekor** daily Merkle root anchoring | Third-party verifiable, zero operational cost |
| LLM JSON handling ad-hoc | **Instructor** in nthlayer-common | Automatic retry on validation, partial streaming |

The biggest architectural additions in v2.1 are Rekor anchoring (§9) and the explicit mapping of each component to its OSS substrate (§5).

---

## 1. Motivation

Unchanged from v2.0.

The NthLayer ecosystem consists of multiple components (observe, measure, correlate, respond, authorise, executor, learn) that cooperate via a shared store. Running each as a long-lived serve process with persistent state, heartbeats, and pull-based coordination keeps the operational surface small and the failure modes predictable.

The guiding principle: **pull over push, polling over callbacks, SQLite over distributed systems, until a real constraint forces otherwise.** For a solo-developer project and most production deployments, this is the correct default. Scale-out upgrade paths (NATS JetStream, PostgreSQL) are documented in §12.

## 2. Pipeline Overview

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ observe  │ ─→  │ measure  │ ─→  │correlate │
└──────────┘     └──────────┘     └──────────┘
                                        │
                                        ▼
                                  ┌──────────┐
                                  │ respond  │
                                  └──────────┘
                                        │
                                        ▼
                                  ┌──────────┐     ┌──────────┐
                                  │authorise │ ─→  │ executor │
                                  └──────────┘     └──────────┘
                                        │                │
                                        └────────────────┘
                                                │
                                                ▼
                                          ┌──────────┐
                                          │  learn   │
                                          └──────────┘
```

All components:
- Read from and write to the shared store
- Emit heartbeats every 10 seconds
- Persist their processing state (last-processed cursor, hysteresis state, dedup caches)
- Stamp pipeline latency into each verdict they produce

## 3. Store

### 3.1 Substrate

**SQLite with WAL mode.** Single file, zero additional daemons. Not a distributed database, not multi-master, not horizontally scalable. For the design point (one NthLayer deployment serving one organisation), this is adequate and simple.

### 3.2 Configuration

```python
conn = sqlite3.connect(path, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=5000")
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA mmap_size=268435456")  # 256MB
```

Writes use `BEGIN IMMEDIATE` to acquire the write lock atomically. Periodic `PRAGMA wal_checkpoint(TRUNCATE)` prevents unbounded WAL growth (every 10 minutes or 10,000 writes, whichever comes first).

### 3.3 Access via `sqlite-utils`

For ergonomics, components access the store via `sqlite-utils` (simonw/sqlite-utils) for schema migration, bulk inserts, and query building. Raw `sqlite3` for hot paths.

### 3.4 Backup and DR via Litestream

**Litestream** (benbjohnson/litestream, v0.5.x series, revived October 2025 after Fly.io refocused on it). Runs as a sidecar process. Ships continuous WAL backups to S3/Tigris/Backblaze/any S3-compatible endpoint.

```yaml
# litestream.yml
dbs:
  - path: /var/lib/nthlayer/store.db
    replicas:
      - type: s3
        bucket: nthlayer-backups
        path: production/store.db
        retention: 720h  # 30 days
```

Recovery: `litestream restore` rebuilds the SQLite file from any replicated point. RPO typically < 1 second; RTO is however long the restore takes (minutes for a gigabyte-scale store).

**Skipped:** LiteFS. FUSE + Consul is operational overhead without proportional gain for solo-dev. DuckDB — correct as a read-only analytics lens over the SQLite file, not as the primary store (DuckDB's own docs state multi-process writes to a shared file are unsupported).

### 3.5 Schema

Core tables:

```sql
-- Verdicts (hash-chained, content-addressed)
CREATE TABLE verdicts (
    cid TEXT PRIMARY KEY,              -- IPLD CID
    type TEXT NOT NULL,                -- assessment | action_request | approval | capability | denial | execution | operator_note
    service TEXT,
    created_at TIMESTAMP NOT NULL,
    pipeline_latency_ms INTEGER,       -- cumulative latency from first verdict in chain
    chain_depth INTEGER,               -- number of ancestors
    parent_cids TEXT,                  -- JSON array of parent CIDs
    content BLOB NOT NULL              -- canonical JSON, CBOR-encoded
);

CREATE INDEX idx_verdicts_service_created ON verdicts(service, created_at);
CREATE INDEX idx_verdicts_type_created ON verdicts(type, created_at);

-- Assessments (component outputs that aren't decisions)
CREATE TABLE assessments (
    cid TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    kind TEXT NOT NULL,                -- slo_status | correlation_snapshot | judgment_slo_evaluation
    created_at TIMESTAMP NOT NULL,
    content BLOB NOT NULL
);

-- Cases (Bench domain model)
CREATE TABLE cases (
    cid TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    priority TEXT NOT NULL,
    state TEXT NOT NULL,               -- pending | leased | resolved | expired
    created_at TIMESTAMP NOT NULL,
    underlying_verdict TEXT NOT NULL,
    service TEXT,
    briefing TEXT,
    lease_holder TEXT,
    lease_expires_at TIMESTAMP,
    resolution_cid TEXT                -- verdict CID of the resolution
);

-- ChangeFreeze documents (see RBAC §7)
CREATE TABLE change_freezes (
    name TEXT PRIMARY KEY,
    declared_by TEXT NOT NULL,
    declared_at TIMESTAMP NOT NULL,
    active_from TIMESTAMP NOT NULL,
    active_until TIMESTAMP NOT NULL,
    lifted_at TIMESTAMP,
    lifted_by TEXT,
    content BLOB NOT NULL              -- full document
);

-- Heartbeats (component liveness)
CREATE TABLE heartbeats (
    component TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    last_seen TIMESTAMP NOT NULL,
    state TEXT,                        -- JSON with component-specific state
    PRIMARY KEY (component, instance_id)
);

-- Component state (persistent across restarts)
CREATE TABLE component_state (
    component TEXT PRIMARY KEY,
    last_cursor TIMESTAMP,             -- last processed verdict time
    hysteresis_state BLOB,             -- JSON, component-specific
    dedup_cache BLOB                   -- JSON, component-specific
);

-- Suppression audit (what was suppressed and why)
CREATE TABLE suppressions (
    id INTEGER PRIMARY KEY,
    suppressed_at TIMESTAMP NOT NULL,
    component TEXT NOT NULL,
    suppressed_verdict_cid TEXT NOT NULL,
    reason TEXT NOT NULL,              -- active_incident | dedup | hysteresis
    related_verdict_cid TEXT           -- incident, original dedup target, etc.
);

-- Rekor anchor log (daily Merkle root submissions)
CREATE TABLE rekor_anchors (
    anchor_date DATE PRIMARY KEY,
    merkle_root TEXT NOT NULL,
    rekor_log_index INTEGER,           -- Rekor's returned index
    rekor_uuid TEXT,
    anchored_at TIMESTAMP NOT NULL
);
```

### 3.6 Concurrent access

Single writer serialization is enforced by SQLite's `BEGIN IMMEDIATE`. Multiple readers via WAL. Components that produce verdicts serialize their writes; the store is not a concurrency primitive.

### 3.7 Retention

Defaults (configurable):

| Table | Retention | Notes |
|---|---|---|
| verdicts | 365 days | Audit-relevant, longer for compliance deployments |
| assessments | 90 days | Roll up into longer-term metrics via nthlayer-learn |
| cases | 365 days | Operator decision history |
| change_freezes | active indefinitely, lifted 90 days | |
| heartbeats | 1 day | Continuously overwritten |
| component_state | current only | Latest value per component |
| suppressions | 90 days | For audit replay |
| rekor_anchors | permanent | Small rows, high value |

Retention maintenance runs as a daily job; one component (typically `nthlayer-learn`) owns it.

## 4. Component Base Pattern

Every serve-mode component implements the same base pattern:

```python
class ComponentServer:
    async def serve(self):
        await self.restore_state()
        while not self.stop_event.is_set():
            await self.emit_heartbeat()
            await self.process_cycle()
            await self.persist_state()
            await self.sleep_until_next_cycle()

    async def restore_state(self):
        """Load last_cursor, hysteresis_state, dedup_cache from store"""

    async def emit_heartbeat(self):
        """Write to heartbeats table"""

    async def process_cycle(self):
        """Component-specific processing"""
        raise NotImplementedError

    async def persist_state(self):
        """Write component_state row atomically"""
```

This pattern ensures:

- State survives restarts (hysteresis, dedup caches)
- Component health is observable (heartbeats)
- No in-memory-only critical state
- Clean shutdown

## 5. Component Technology Stack

Each component's substrate (established by the delegation research):

### 5.1 nthlayer-observe

**Responsibilities:** Poll Prometheus, compute SLO assessments, detect drift.

**Stack:**
- `prometheus-api-client` — querying Prometheus for SLI values
- `prometheus-client` — emitting nthlayer-observe's own metrics
- `promql-parser` — validating PromQL in manifest SLO definitions at load time
- `sqlite-utils` — store access
- For topology drift: reads OTel servicegraph connector output (Prometheus metrics `traces_service_graph_request_total`, `traces_service_graph_request_server_seconds`)

**Output:** assessments (slo_status verdicts), emitted with CloudEvents + OTel semantic conventions.

### 5.2 nthlayer-measure

**Responsibilities:** Evaluate AI agent output quality via LLM, track judgment SLOs, calibrate, govern autonomy (one-way ratchet).

**Stack:**
- `nthlayer-common.llm` — model-agnostic LLM wrapper (httpx-based)
- `Instructor` (567-labs/instructor, MIT) — structured outputs with automatic retry, partial streaming, validation reask loops
- `scikit-learn.calibration` — calibration curves, Brier score
- `scipy.stats` — confidence intervals

**Output:** judgment SLO evaluation assessments, autonomy-change verdicts.

### 5.3 nthlayer-correlate

**Responsibilities:** Continuously group signals into situational snapshots with natural-language summaries.

**Stack:**
- `Bytewax` — streaming dataflow engine. Session windows via `fold_window`. Python-native API, Rust Timely Dataflow core.
- Input: PD-CEF alert schema (NthLayer uses a superset of PD-CEF for alert envelope)
- Input: OTel servicegraph connector metrics for topology
- Input: OpenSRM manifests for declared topology

**Output:** correlation_snapshot assessments with NL summaries.

(See dedicated nthlayer-correlate spec in Wave 3.)

### 5.4 nthlayer-respond

**Responsibilities:** Multi-agent incident response. Specialised agents (triage, investigation, communication, remediation) under a deterministic orchestrator.

**Stack:**
- **Custom orchestrator.** No LangGraph, CrewAI, AutoGen, or similar — all own reasoning in ways incompatible with Zero Framework Cognition.
- `asyncio` state machine for orchestration
- `nthlayer-common.llm` for agent calls
- `Instructor` for structured agent outputs
- Optionally: `PydanticAI` as a typed-tool sub-executor behind the orchestrator (narrow adoption)

**Output:** action_request verdicts, investigation assessments, incident-scoped ChangeFreeze documents.

### 5.5 nthlayer-authorise

**Responsibilities:** Evaluate authorisation policies, issue capability tokens or denials.

**Stack:**
- `Regorus` (microsoft/regorus) — Rego evaluation. Fallback: `regopy`.
- `biscuit-python` — capability token signing
- `PyNaCl` — Ed25519 signing primitives; optionally `hvac` for Vault-backed signing
- `py-spiffe` (optional) — SPIFFE SVID consumption where SPIRE is deployed

**Output:** capability verdicts, denial verdicts, OTel decision log records.

### 5.6 nthlayer-executor

**Responsibilities:** Execute authorised actions with verification and rollback.

**Stack:**
- `biscuit-python` — token verification
- `httpx` — webhook-binding HTTP calls
- `kubernetes` (official Python client) — kubernetes-rollout binding
- Custom dispatch for other bindings

**Output:** execution verdicts.

### 5.7 nthlayer-learn

**Responsibilities:** Verdict lineage, content-addressing, retrospective analysis, Rekor anchoring, retention maintenance.

**Stack:**
- `libipld` (MarshalX/python-libipld) — IPLD CID generation
- `sigstore-python` — Rekor anchoring
- `sqlite-utils` — store access
- Retention maintenance job

**Output:** retrospective assessments, calibration signals, Rekor anchor records.

(See dedicated nthlayer-learn spec in Wave 3.)

### 5.8 Shared: nthlayer-common

**Responsibilities:** Shared library.

**Stack:**
- `httpx` — HTTP client (no LiteLLM; see delegation research for 2026 supply-chain incident)
- `Instructor` — structured LLM outputs
- Native SDKs for Anthropic, OpenAI where full features needed
- `prometheus-client` — metrics
- OTel Python SDK — tracing
- `pydantic` — data models

## 6. Pipeline Latency

Every verdict carries:

```json
{
  "pipeline_latency_ms": 2347,
  "chain_depth": 4
}
```

`pipeline_latency_ms` is cumulative — the time from the first verdict in the chain to this verdict's creation. `chain_depth` is the count of ancestors. Together, these let monitoring answer "how long is it taking to go from signal to action?" without reconstructing chains.

## 7. Active-Incident Suppression and Semantic Deduplication

Unchanged from v2.0.

When an incident is active on a service, upstream components (observe, measure, correlate) suppress duplicate verdicts for the same service. Suppression is logged in the `suppressions` table. When the incident resolves, suppression lifts.

Semantic dedup: identical symptoms emerging within a short window (default 60 seconds) for the same service+SLO+breach-class are deduplicated to one verdict. Subsequent emissions update the existing verdict's `last_seen` timestamp rather than creating new verdicts.

## 8. Heartbeats and Health

Each component writes to `heartbeats` every 10 seconds:

```json
{
  "component": "nthlayer-observe",
  "instance_id": "observe-eu-west-1",
  "last_seen": "2026-04-19T09:32:15Z",
  "state": {
    "cycles_completed": 14728,
    "last_cycle_duration_ms": 347,
    "verdicts_written_last_cycle": 3,
    "errors_last_cycle": 0
  }
}
```

A pipeline-health indicator can be computed by checking each expected component's `last_seen`. If any component hasn't heartbeat in 30 seconds, the pipeline is considered degraded.

## 9. Rekor Anchoring (new in v2.1)

### 9.1 Rationale

Content-addressed verdicts give internal integrity (any tamper invalidates the CID). Rekor anchoring gives external, third-party-verifiable tamper evidence at essentially zero cost. This materially strengthens the compliance and audit story.

### 9.2 Mechanism

Daily (configurable: hourly for high-volume deployments):

1. `nthlayer-learn` computes a Merkle root over all verdicts written in the prior 24 hours, ordered by CID
2. The root is signed with the deployment's Ed25519 key
3. The signed root is submitted to the public Sigstore Rekor instance via `sigstore-python`
4. The resulting Rekor log index and UUID are recorded in `rekor_anchors` table

One Rekor entry per day is well below Rekor's 100KB cap and the Sigstore public good absorbs the availability concern.

### 9.3 Verification

Any third party with access to the verdicts can:

1. Compute the Merkle root over the claimed verdict set
2. Query Rekor for the anchor by date
3. Verify the signature matches the deployment's public key
4. Verify the Merkle root matches

This gives independent tamper evidence without NthLayer or the deployment operator being able to silently modify the audit trail.

## 10. Wire Format: CloudEvents + OTel

All verdicts and assessments are emitted as CloudEvents v1.0 with OTel semantic convention attributes on the payload:

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.verdict.execution.v1",
  "source": "urn:nthlayer:executor:eu-west",
  "id": "bafyrei...fhq3",
  "time": "2026-04-19T09:32:15Z",
  "datacontenttype": "application/json",
  "traceparent": "00-...",

  "data": {
    "gen_ai.system": "nthlayer-executor",
    "gen_ai.evaluation.name": "rollback-deployment",
    "gen_ai.evaluation.score.value": 1.0,
    "gen_ai.evaluation.score.label": "success",
    "gen_ai.response.id": "bafyrei...fhq3",

    "nthlayer.verdict.type": "execution",
    "nthlayer.verdict.parent_cids": ["bafyrei...parent1", "bafyrei...parent2"],
    "nthlayer.verdict.pipeline_latency_ms": 2347,
    "nthlayer.verdict.chain_depth": 4,

    "nthlayer.execution.capability_cid": "bafyrei...cap1",
    "nthlayer.execution.binding": "kubernetes-rollout",
    "nthlayer.execution.target": "deployment/payment-service",
    "nthlayer.execution.outcome": "success",
    "nthlayer.execution.verification_passed": true
  }
}
```

The `gen_ai.*` attributes follow OTel semantic conventions (v1.39.0+). The `nthlayer.*` attributes are our extensions; we propose `nthlayer.verdict.*` and the decision-specific subset upstream to the OTel GenAI SIG as `gen_ai.decision.*`.

## 11. Alert Schema: PD-CEF Superset

nthlayer-respond and nthlayer-correlate both consume alerts. The alert schema is a PD-CEF (PagerDuty Common Event Format) superset:

```json
{
  "summary": "payment-service error rate above threshold",
  "source": "prometheus",
  "severity": "critical",
  "component": "payment-service",
  "group": "payments",
  "class": "latency",
  "custom_details": { "p99_latency_ms": 2100, ... },
  "dedup_key": "payment-service:error-rate",

  "nthlayer.alert.service_cid": "bafyrei...",
  "nthlayer.alert.slo_cid": "bafyrei...",
  "nthlayer.alert.burn_rate": 47.2
}
```

Every major monitoring tool speaks PD-CEF; adopting it means zero translation effort for most input sources. NthLayer-specific fields live under the `nthlayer.*` namespace.

## 12. Scale-Out Upgrade Path

v2.1 commits to the SQLite + polling default. The upgrade path:

### 12.1 When to upgrade

- Polling latency becomes a product constraint (case creation should appear in Bench within seconds, not tens of seconds)
- Write volume exceeds SQLite's single-writer capacity (rough rule: >100 writes/second sustained)
- Multi-deployment coordination becomes necessary

### 12.2 Upgrade path

**Phase A: NATS JetStream for push coordination.** Keep SQLite as store of record; add NATS for notifications ("a new action_request was written"). Components subscribe to subjects rather than polling. `nats-py` is asyncio-native, first-class.

**Phase B: PostgreSQL with LISTEN/NOTIFY + SELECT FOR UPDATE SKIP LOCKED.** When scale-out requires a real database with push coordination. This is the combined endgame.

**Not on the path:** Kafka (solo-dev operational overhead), LiteFS (FUSE+Consul for HA gains that don't exist yet at this scale), DuckDB as primary store (unsupported for multi-writer).

## 13. Integration Test Harness

End-to-end integration test:

```python
async def test_pipeline_happy_path():
    """Test the full chain: observe → measure → correlate → respond → authorise → executor → learn"""

    # Arrange
    store = await bootstrap_test_store()
    components = await start_all_serve_components(store)

    # Inject a fake Prometheus metric breach
    await inject_prometheus_breach(service="payment-service", slo="availability")

    # Assert chain propagation
    await eventually(lambda: verdict_exists(store, type="slo_status", service="payment-service"))
    await eventually(lambda: verdict_exists(store, type="correlation_snapshot"))
    await eventually(lambda: verdict_exists(store, type="action_request"))
    # ... and so on through the chain

    # Verify pipeline latency is bounded
    final_verdict = await get_latest_verdict(store, type="execution")
    assert final_verdict.pipeline_latency_ms < 30_000  # 30s p99

    # Verify Rekor anchoring (if enabled)
    if rekor_enabled:
        await run_rekor_anchor_job(store)
        assert rekor_anchor_exists_for_today(store)
```

Run this test early and keep it passing throughout development. It's the spec-contract enforcer.

## 14. Open Questions

Resolved from v2.0:
- ~~SQLite backup/DR~~ → Litestream sidecar (§3.4)
- ~~External tamper evidence~~ → Sigstore Rekor anchoring (§9)
- ~~Alert schema~~ → PD-CEF superset (§11)
- ~~Correlation engine substrate~~ → Bytewax (§5.3, fuller in correlate spec)
- ~~Scale-out path~~ → NATS then PostgreSQL (§12)

Still open:
- **OTel upstream contribution timing.** We're emitting `nthlayer.verdict.*` and `nthlayer.decision.*` attributes pending upstream acceptance. Timing of proposal to OTel GenAI SIG is a product decision.
- **Multi-region deployment.** Cross-region NthLayer deployments are future work; a region's Rekor anchor is global but the store is local.
- **Component dependency health.** If nthlayer-observe's Prometheus is down, what does the Bench surface? Currently: silence. Should it surface "upstream degraded"? Probably yes, but the UX is non-obvious.

## 15. References

- Litestream: https://litestream.io/
- sqlite-utils: https://sqlite-utils.datasette.io/
- prometheus-api-client: https://pypi.org/project/prometheus-api-client/
- prometheus-client: https://pypi.org/project/prometheus-client/
- promql-parser: https://pypi.org/project/promql-parser/
- Bytewax: https://bytewax.io/
- NATS JetStream: https://docs.nats.io/nats-concepts/jetstream
- sigstore-python: https://github.com/sigstore/sigstore-python
- libipld: https://github.com/MarshalX/python-libipld
- PD-CEF: https://support.pagerduty.com/docs/pd-cef
- CloudEvents: https://cloudevents.io/
- OTel GenAI semconv: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Instructor: https://github.com/567-labs/instructor
- RBAC extension v1.1 (authorise/executor details)
- Bench v2.1 (operator surface)

## 16. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 2.0-draft | 2026-04-18 | Initial serve-mode spec |
| 2.1-draft | 2026-04-19 | Adopted Litestream, Bytewax, PD-CEF, CloudEvents+OTel wire format; added Rekor anchoring (§9); mapped each component to OSS substrate (§5); committed scale-out upgrade path (§12) |
