# NthLayer v2 Specification Reconciliation Report

**Date:** 2026-04-20
**Scope:** v2 spec corpus (9 documents) versus existing codebase (v1/v1.5)
**Purpose:** Identify what confirms, extends, and conflicts with existing implementation before creating any work items.

---

## How to read this report

For each spec document, three lists:

- **Confirms existing** — spec describes what is already implemented correctly. No action needed.
- **Extends existing** — spec adds fields, methods, or behaviour to something that exists. Implementation should preserve backward compatibility where possible; migrations flagged where not.
- **Conflicts with existing** — spec describes something different from what is implemented. Each conflict has a recommendation but awaits your resolution: **migrate code**, **update spec**, or **keep parallel with rationale**.

---

## Executive Summary: Critical Gaps

Before the per-spec detail, the five highest-impact structural gaps:

1. **Verdict identity scheme.** Current: string IDs (`vrd-YYYY-MM-DD-{uuid}-{seq}`). Spec: IPLD CIDv1 computed from canonical CBOR via `libipld`. This touches every component that reads or writes verdicts. Migration is a one-time rewrite with a compatibility shim during transition.

2. **Two parallel content-addressing systems.** `nthlayer-learn` has `Verdict` with string IDs in `verdicts.db`. `nthlayer-common/records/` has `Assessment`, `Verdict`, `Evaluation`, `Incident` with SHA-256 hashes on canonical JSON in `decisions.db`. The spec replaces both with a single IPLD CID system. These need to converge.

3. **Store architecture.** Current: each component owns its own SQLite database (assessments.db, verdicts.db, scores.db, events.db, incidents.db, decisions.db). Spec: single shared SQLite store with unified 8-table schema (SERVE-MODE §3.5). This is a fundamental architectural change.

4. **LLM wrapper interface.** Current: `llm_call(system, user, model)` is a synchronous function wrapped in `asyncio.to_thread()`. Spec: `LLM` class with `complete()` and `stream()` async methods, Instructor integration for structured outputs, cost-accounting OTel events per call. Every LLM-calling component is affected.

5. **Missing components.** `nthlayer-authorise`, `nthlayer-executor`, and `nthlayer-bench` do not exist. These are entirely new implementations required by RBAC, SERVE-MODE, and BENCH specs respectively.

---

## 1. NTHLAYER-SPEC-INDEX-v1

Navigation document only. No implementation implications. Confirms the specification/implementation boundary distinction that we should respect throughout.

---

## 2. OPENSRM-CORE-v2

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| SLO concept with targets and windows | `nthlayer/src/nthlayer/specs/manifest.py` — `ReliabilityManifest` has SLO list | §4 |
| Dependency declarations | Demo specs declare dependencies (`fraud-detect` → `payment-api`) | §7 |
| Three-tier system (critical/standard/low) | `nthlayer-common/src/nthlayer_common/tiers.py` — `TIER_CONFIGS` | §3 (metadata) |
| Manifest validation at load time | `nthlayer/src/nthlayer/specs/loader.py` validates on parse | §4.4 |
| PromQL in SLO indicators | Demo specs and OpenSRM examples use PromQL | §4.3 |
| Judgment SLO concept exists | `nthlayer-measure` evaluates reversal rate, calibration | §5 (partial) |
| Compiler produces observability artifacts | `nthlayer` generates Sloth SLO specs, Prometheus alerts, dashboards | §4.3 |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| 8 formal judgment SLO types | Reversal rate + calibration partially implemented in nthlayer-measure | Add: HCF, audit sampling, outcomes, escalation, segments, stability | §5.2.1–§5.2.8 |
| Reliability contracts | Not implemented | New first-class cross-service promises tied to OpenAPI operations | §6 |
| Template inheritance | Not implemented | Single-level template extension for manifest scaling | §9 |
| Change events on manifest mutation | Not implemented | CloudEvents v1.0 emission on manifest changes | §10 |
| Instrumentation requirements section | Not in manifests | Declare required metrics/traces/logs/events per service | §8 |
| Statistical requirements | Partial (basic reversal rate math) | Brier score, ECE, confidence intervals, segment variance | §5.3 |
| Breach actions (declarative) | Code-defined triggers in nthlayer-measure | Manifest-declared: notify, create_case, reduce_autonomy, action_request | §5.4 |
| Contract divergence as correlation signal | Not implemented | Expectation vs contract divergence types | §7.1 |

### Conflicts with existing

#### CONFLICT C-2.1: Manifest apiVersion and kind

- **Current:** `apiVersion: srm/v1`, `kind: ServiceReliabilityManifest` (30+ YAML files across nthlayer/, opensrm/, demo/)
- **Spec:** `apiVersion: opensrm.nthlayer.io/v2`, `kind: ServiceManifest`
- **Impact:** Every manifest file, the parser in `nthlayer/src/nthlayer/specs/`, and all example/demo YAML files
- **Recommendation:** Migrate code. Add v2 parser alongside v1 parser with auto-detection. Migrate examples progressively. The v1 parser can remain for backward compatibility during transition.

#### CONFLICT C-2.2: SLO format — bespoke vs OpenSLO v1

- **Current:** Bespoke YAML with `slos:` list containing inline `indicators:` with PromQL
- **Spec:** OpenSLO v1 documents, embedded inline or via `$ref`, with OpenSRM annotations
- **Impact:** nthlayer compiler's SLO parsing, Sloth generator, error budget calculator, all manifest examples
- **Recommendation:** Migrate code. OpenSLO v1 is a CNCF standard; adopting it strengthens the CNCF submission story. Existing PromQL stays; the envelope changes.

#### CONFLICT C-2.3: Ownership model — bespoke vs Backstage entity refs

- **Current:** Manifest has `team:`, `runbook:`, `oncall:` with inline roster/rotation/escalation config
- **Spec:** Backstage entity references (`backstage.io/component-ref: "component:default/<service>"`) with `owner: {group, escalation, technical_contact}` as Backstage refs
- **Impact:** nthlayer-common identity resolution, nthlayer-respond on-call resolution, all manifests
- **Recommendation:** This may be a "keep parallel" case. Backstage refs only work for organisations that deploy Backstage. The current inline on-call config is more self-contained. **Question for you:** Do you want Backstage refs to be required, optional-with-fallback, or a parallel path?

#### CONFLICT C-2.4: Dependency format — simple vs contract-referenced

- **Current:** `dependencies: [{service: "fraud-detect", type: "ai-gate"}]`
- **Spec:** Dependencies with `contract_ref`, `expected_availability`, `expected_latency_p99`, `fallback`
- **Impact:** Manifest schema, nthlayer-correlate topology loading, nthlayer-observe blast radius
- **Recommendation:** Migrate code. The v1 format is a subset; v2 adds optional fields. Can be additive if new fields are optional.

---

## 3. OPENSRM-RBAC-EXTENSION-v2

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| Safe actions concept | `nthlayer-respond/src/nthlayer_respond/safe_actions/` — registry + webhook dispatch | §4 |
| Approval flow exists | `nthlayer-respond/src/nthlayer_respond/server.py` — Starlette approval server | §12 (step 5) |
| Principal kinds (human/agent) | nthlayer-respond agents have types (triage, investigation, etc.) | §3 |
| Action parameters with schema | `safe-actions.yaml` has parameter definitions | §4 |

### Extends existing (all new capabilities)

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| Rego policy evaluation | No policy engine | Regorus (Rust+PyO3) evaluating Rego bundles | §5.3 |
| Biscuit capability tokens | No tokens | Ed25519-signed, one-shot, time-windowed, parameter-bound | §6 |
| ChangeFreeze first-class kind | No freeze concept | Declarative freeze documents consumed by preconditions | §7 |
| SPIFFE workload identity | No workload identity | Optional py-spiffe for SVID-based agent auth | §8 |
| OTel decision logs | No decision logging | CloudEvents-wrapped OTel log records for SIEM | §9 |
| 8 standard preconditions | No preconditions | Rego modules: no-change-freeze, rate-limit, error-budget, etc. | §4.4 |
| YAML DSL → Rego compilation | No policy DSL | AuthorisationPolicy kind compiles to Rego | §5.1–§5.2 |
| All-match deny-wins evaluation | No policy evaluation | Normative evaluation order | §5.4 |
| Auth verdict types | Only triage/investigation/remediation/communication | action_request, approval, capability, denial, execution, operator_note | §10 |
| Revocation list | No revocation | Token hash revocation with 30s best-effort poll | §6.5 |

### Conflicts with existing

#### CONFLICT C-3.1: Execution ownership — respond vs authorise + executor

- **Current:** `nthlayer-respond` owns the entire flow: triage → investigation → communication → remediation including safe action execution via `SafeActionRegistry` and webhook dispatch
- **Spec:** Execution is split across three components:
  - `nthlayer-respond` emits `action_request` verdicts (proposes actions, does NOT execute)
  - `nthlayer-authorise` evaluates policy and issues `capability` or `denial` verdicts
  - `nthlayer-executor` verifies capability tokens and dispatches to execution bindings
- **Impact:** Fundamental architectural change to nthlayer-respond. The safe_actions/ directory and webhook dispatch move to nthlayer-executor. nthlayer-respond's remediation agent stops executing and starts requesting.
- **Recommendation:** Migrate code. This is the core v2 contribution — separating "deciding what to do" from "being allowed to do it" from "actually doing it." The spec is right; the current approach lacks audit trail and policy enforcement. This is also the v1.5 vs v2-direct decision point.

#### CONFLICT C-3.2: Action declarations — code-defined vs manifest-declared

- **Current:** Safe actions defined in `registry/safe-actions.yaml` as a standalone file loaded by nthlayer-respond
- **Spec:** Actions declared in each service's manifest under `actions:` with JSON Schema parameters, blast_radius, preconditions, approval_level
- **Impact:** Manifest schema, action loading, policy evaluation context
- **Recommendation:** Migrate code. Actions belong in the manifest because they're service-specific declarations. The registry file becomes the migration source.

---

## 4. NTHLAYER-SERVE-MODE-v2.1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| Components have serve subcommands | All 4 runtime components have `serve` CLI command | §2 |
| SQLite WAL mode | `nthlayer-learn`, `nthlayer-observe` both use `PRAGMA journal_mode=WAL` | §3.2 |
| Pull-based polling | Components poll stores/Prometheus, not event-driven | §1 |
| Pipeline: observe → measure → correlate → respond | E2E test exercises this exact chain | §2 |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| Component base pattern | Each component has ad-hoc serve loop | Formal: restore_state → heartbeat → process_cycle → persist_state | §4 |
| Heartbeat mechanism | Not implemented | 10s heartbeats with cycles_completed, last_cycle_duration, etc. | §8 |
| Pipeline latency in verdicts | Not tracked | `pipeline_latency_ms` field on every verdict | §6 |
| `chain_depth` in verdicts | Not tracked | Chain depth incremented per lineage hop | §6 |
| Active-incident suppression | Not implemented | Upstream components suppress duplicates when incident active | §7 |
| Semantic dedup | Not implemented | Identical (service + SLO + breach_class) within 60s deduped | §7 |
| Suppressions table | Not implemented | Audit trail for suppressed verdicts with reason | §3.5 |
| Litestream backup | Not configured | Continuous WAL backup to S3 | §3.4 |
| Retention maintenance | Not implemented | Daily pruning job per table retention policy | §3.7 |
| Rekor anchoring table | Not implemented | `rekor_anchors` table for daily Merkle root records | §3.5 |
| Integration test harness (§13) | `e2e-test.sh` exists but doesn't verify pipeline latency | Full harness with latency p99 < 30s assertion | §13 |

### Conflicts with existing

#### CONFLICT C-4.1: Store architecture — per-component vs unified

- **Current:**
  - `nthlayer-observe`: `assessments.db` (SQLiteAssessmentStore)
  - `nthlayer-learn`: `verdicts.db` (SQLiteVerdictStore)
  - `nthlayer-measure`: `scores.db` (SQLiteScoreStore)
  - `nthlayer-correlate`: `events.db` (FTS5 event store)
  - `nthlayer-respond`: `incidents.db` (SQLiteContextStore)
  - `nthlayer-common`: `decisions.db` (SQLiteDecisionRecordStore)
- **Spec:** Single shared SQLite store with 8 tables: verdicts, assessments, cases, change_freezes, heartbeats, component_state, suppressions, rekor_anchors
- **Impact:** Every component's store code. Connection management centralised in nthlayer-common's `StorePool`.
- **Recommendation:** Migrate code. The unified store is load-bearing for the pipeline — components need to read each other's outputs without cross-database queries. Migration order: define schema in nthlayer-common first, then migrate components one at a time.

#### CONFLICT C-4.2: Verdict table schema

- **Current (nthlayer-learn):** `verdicts(id TEXT PK, version INT, timestamp TEXT, data TEXT, producer_system TEXT, subject_type TEXT, subject_agent TEXT, subject_service TEXT, outcome_status TEXT, ttl INT, closed_at TEXT)`
- **Current (nthlayer-common/records):** `verdicts(hash TEXT PK, previous_hash TEXT, schema_version TEXT, timestamp TEXT, agent TEXT, incident_id TEXT, input_hashes TEXT, prompt_hash TEXT, response_hash TEXT, model TEXT, ...)`
- **Spec:** `verdicts(cid TEXT PK, type TEXT, service TEXT, created_at TIMESTAMP, pipeline_latency_ms INT, chain_depth INT, parent_cids TEXT, content BLOB)`
- **Impact:** Two existing schemas need to converge into one new schema.
- **Recommendation:** Migrate code. The spec schema is the target. Write a migration that:
  1. Creates the v2 schema
  2. Re-encodes existing verdicts as canonical CBOR and computes CIDs
  3. Populates the lineage index from existing parent references
  4. This is the single highest-risk migration in the entire v2 effort.

#### CONFLICT C-4.3: Assessment table schema

- **Current (nthlayer-observe):** `assessments(id TEXT, timestamp TEXT, service TEXT, assessment_type TEXT, producer TEXT, data_json TEXT)`
- **Current (nthlayer-common/records):** `assessments(hash TEXT PK, previous_hash TEXT, stream TEXT, timestamp TEXT, type TEXT, severity TEXT, payload TEXT, summaries TEXT, ...)`
- **Spec:** `assessments(cid TEXT PK, kind TEXT, service TEXT, created_at TIMESTAMP, content BLOB)`
- **Impact:** Two existing assessment schemas converge into one.
- **Recommendation:** Migrate code. Same pattern as verdict migration.

#### CONFLICT C-4.4: Cases and heartbeats tables — don't exist

- **Current:** No cases table (nthlayer-bench doesn't exist). No heartbeats table.
- **Spec:** Both are new tables in the unified store.
- **Impact:** Additive. No migration conflict, but depends on unified store being in place first.
- **Recommendation:** Purely additive once C-4.1 is resolved.

---

## 5. NTHLAYER-TELEMETRY-ENVELOPE-v1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| OTel semantic conventions for naming | `nthlayer/src/nthlayer/metrics/standards/otel_semconv.py` imports OTel semconv | §4.2 |

### Extends existing (almost entirely new)

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| CloudEvents v1.0 envelope | Not implemented | Required wrapper for all NthLayer events | §3 |
| Event type taxonomy | No taxonomy | 5 categories × ~20 subtypes with strict naming pattern | §3.4 |
| gen_ai.* OTel attributes | Naming constants imported but never emitted | Actual emission on LLM calls and evaluations | §4.2 |
| nthlayer.decision.* attributes | Not implemented | Proposed upstream attributes for decision metadata | §4.3 |
| nthlayer.verdict.* attributes | Not implemented | Verdict metadata attributes on events | §4.4 |
| PD-CEF alert schema superset | nthlayer-correlate ingests alerts but no formal schema | Formal PD-CEF superset with NthLayer extensions | §5 |
| Decision log format | Not implemented | OPA-inspired field vocabulary for auth decisions | §6 |
| Change events | Not implemented | manifest_changed, change_freeze_declared/lifted | §7 |
| SIEM integration path | Not implemented | OTel Collector → Elasticsearch/Splunk/Datadog | §6.3 |

### Conflicts with existing

#### CONFLICT C-5.1: Event serialization — JSON vs CBOR + CloudEvents

- **Current:** All events are simple JSON objects written to SQLite TEXT columns.
- **Spec:** Canonical CBOR for CID computation, JSON for wire format, CloudEvents v1.0 envelope for all emitted events.
- **Impact:** Every component that writes events. The CBOR is for identity; the JSON is for wire; the CloudEvents is for external consumption.
- **Recommendation:** Migrate code. This is coupled to the verdict identity migration (C-4.2). The CloudEvents wrapping is additive — it wraps existing content, it doesn't replace it.

---

## 6. NTHLAYER-COMMON-v1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| LLM wrapper exists | `nthlayer_common/llm.py` — `llm_call()` function | §3 |
| Provider routing (Anthropic/OpenAI) | Model string parsed to select API endpoint | §3.2 |
| Error hierarchy | `NthLayerError`, `ExitCode`, `@main_with_error_handling` | §9 |
| Tier definitions | `TIER_CONFIGS` in `tiers.py` | (referenced throughout) |
| Provider integrations | Prometheus, Grafana, PagerDuty, Mimir providers | §5 |
| Identity resolution (7-strategy) | `identity/` directory with resolver + normalizer | §6 |
| httpx as HTTP client | Used throughout nthlayer-common and all components | §12 |
| Zero Framework Cognition | No LangChain/CrewAI/etc. imports anywhere in codebase | §2, §13 |
| No LiteLLM | Confirmed: not in any pyproject.toml or import | §2 |
| Pydantic for data models | Used in nthlayer-common, nthlayer (generator) | §8 |
| YAML prompt loading | `prompts.py` loads prompt templates | §10 (partial) |
| Retry with backoff | `tenacity` used in nthlayer-common | §9.2 |
| Circuit breakers | `circuitbreaker` package in nthlayer-common | §9.3 |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| Instructor integration | NOT used anywhere (confirmed: 0 imports) | Required for all structured LLM outputs | §3.3 |
| Cost-accounting OTel events | Not implemented | Every LLM call emits gen_ai.* and nthlayer.llm.* OTel events | §3.4 |
| OTel tracing (get_tracer, get_meter) | Not implemented (only naming constants in nthlayer generator) | Full OTel SDK integration for traces, metrics, logs | §7 |
| Self-metrics (/metrics endpoint) | Not implemented in common (nthlayer-respond has basic metrics) | Standard Prometheus metrics: cycle_duration, verdicts_written, etc. | §7.3 |
| VerdictStore with CID operations | String-ID-based VerdictStore in nthlayer-learn | CID-based with `query_ancestors()`, `query_descendants()` | §4.3 |
| StorePool connection management | Per-component ad-hoc connections | Singleton pool with configurable size | §4.1 |
| Testing primitives | Partial (MemoryStore in nthlayer-learn) | Mock LLM provider, fake Prometheus, verdict builders | §11 |
| Rate limits per component | Not implemented | Per-component LLM rate limits to prevent starvation | §3.5 |
| Configuration from single nthlayer.yaml | Per-component YAML configs | `Config.load()` from single file with component subsections | §10 |

### Conflicts with existing

#### CONFLICT C-6.1: LLM wrapper interface — function vs class

- **Current:** `llm_call(system, user, model, max_tokens, timeout, retry) → LLMResponse` — synchronous function, uses `asyncio.to_thread()` for SDK calls, returns raw text response
- **Spec:** `LLM` class with:
  - `async complete(prompt, *, model, max_tokens, temperature, response_model, tools, timeout) → LLMResponse`
  - `async stream(...) → AsyncIterator[LLMChunk]`
  - `response_model` parameter for Instructor-backed structured outputs
  - Native async throughout (no `to_thread`)
- **Impact:** Every component that calls `llm_call()` (measure, correlate, respond). All callers wrap in `asyncio.to_thread(llm_call(...))` today; they'd switch to `await llm.complete(...)`.
- **Recommendation:** Migrate code. The spec interface is strictly better: async, structured outputs, streaming. Existing `llm_call()` can be preserved as a compatibility shim during transition that delegates to the new class. Callers migrate one at a time.

#### CONFLICT C-6.2: Data models — two parallel Verdict types

- **Current:**
  1. `nthlayer_learn.models.Verdict` — dataclass with string `id`, `Subject`, `Judgment`, `Outcome`, `Lineage`, `Producer`, `Metadata`
  2. `nthlayer_common.records.models.Verdict` — dataclass with SHA-256 `hash`, `previous_hash`, `agent`, `incident_id`, prompt/response hashes
- **Spec:** Single `Verdict` model in nthlayer-common with CID, `VerdictType`, parent_cids, pipeline_latency_ms, chain_depth
- **Impact:** Both existing Verdict types need to converge. nthlayer-learn's is closer to the spec shape; nthlayer-common/records' has useful accountability fields (prompt_hash, response_hash).
- **Recommendation:** Migrate code. The spec Verdict is the target. Prompt/response hashes from the records model can be carried as fields in the new model's content blob. The records module (`nthlayer-common/records/`) should be deprecated once the unified store is in place.

#### CONFLICT C-6.3: Configuration — per-component vs unified

- **Current:** Each component has its own config file: `measure.yaml`, correlate config in `SitRepConfig`, respond config in `RespondConfig`
- **Spec:** Single `nthlayer.yaml` with component subsections, loaded via `Config.load()`
- **Impact:** All component startup code, all config dataclasses
- **Recommendation:** Migrate code. Can be done progressively — new `Config.load()` reads single file but also falls back to per-component files during transition.

---

## 7. NTHLAYER-LEARN-v1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| Verdict concept | `nthlayer_learn.models.Verdict` dataclass | §4 |
| Subject, Judgment, Outcome, Lineage, Producer | All exist as dataclasses in `models.py` | §4.1 |
| VerdictStore ABC with MemoryStore + SQLiteVerdictStore | `store.py` + `sqlite_store.py` | §4 |
| Parent/children lineage references | `Lineage` has `parent` and `children` fields | §5 (partial) |
| Outcome tracking (pending/confirmed/overridden/partial/superseded/expired) | `Outcome.status` enum matches | §4.5 |
| TTL/retention (90 day default) | `Metadata.ttl` field, `closed_at` column | §8 |
| Retrospective analysis | `retrospective.py` exists | §7 |
| VerdictFilter for queries | `VerdictFilter` + `AccuracyFilter` in `store.py` | §4 (partial) |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| Lineage index table | Parent/children stored in verdict JSON | Separate `lineage(descendant_cid, ancestor_cid, hop_distance)` table with transitive closure | §5.2 |
| Rekor anchoring | Not implemented | Daily Merkle root → Sigstore Rekor via sigstore-python | §6 |
| 5 formal outcome resolution paths | Outcome can be set but resolution paths not formalized | Lineage resolution, calibration sampling, downstream signal, score-outcome divergence, expiry | §4.5 |
| CalibrationSignal dataclass | Not implemented | `CalibrationSignal(decision_cid, expressed_confidence, observed_outcome, calibration_delta)` | §7.2 |
| Retention with referential integrity | Simple TTL-based deletion | Delete only if no younger rows reference the verdict | §8 |

### Conflicts with existing

#### CONFLICT C-7.1: Verdict identity — string ID vs IPLD CID

- **Current:** `id: str` formatted as `vrd-YYYY-MM-DD-{8char-uuid}-{seq:05d}` — assigned at creation time, not derived from content
- **Spec:** `cid: str` — IPLD CIDv1 computed from canonical CBOR encoding of the verdict's content via `libipld`. Content-addressed: identical content produces identical CID; content change produces different CID.
- **Impact:** This is the single most fundamental change. Every component that creates, references, or queries verdicts is affected. The lineage model changes from "parent ID string" to "parent CID derived from content hash."
- **Recommendation:** Migrate code. Content addressing is load-bearing for the tamper-evidence guarantee. Migration path:
  1. Add `libipld` dependency, implement CID computation
  2. New verdicts get CIDs; old verdicts keep string IDs with a compatibility flag
  3. One-time migration job re-encodes existing verdicts and computes CIDs
  4. Drop string ID support after migration

#### CONFLICT C-7.2: Verdict storage format — JSON TEXT vs CBOR BLOB

- **Current:** `data TEXT NOT NULL` — verdict serialized as JSON string
- **Spec:** `content BLOB NOT NULL` — verdict serialized as canonical CBOR (deterministic byte sequence required for CID computation)
- **Impact:** Coupled to C-7.1. All verdict serialization/deserialization code.
- **Recommendation:** Migrate code. CBOR is required for deterministic CID computation. JSON round-trips do not preserve field order deterministically across languages.

#### CONFLICT C-7.3: Lineage storage — inline vs indexed

- **Current:** `Lineage.parent` (single parent ID), `Lineage.children` (list of child IDs), stored inside the verdict JSON blob
- **Spec:** `parent_cids` as JSON array column on verdict row, plus separate `lineage` table with pre-computed transitive closure (descendant_cid, ancestor_cid, hop_distance)
- **Impact:** Lineage queries change from "parse JSON, walk graph" to "index lookup." Significantly better performance for "find all ancestors/descendants" queries.
- **Recommendation:** Migrate code. The lineage index is purely additive and dramatically improves query performance.

---

## 8. NTHLAYER-MEASURE-v1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| Quality evaluation pipeline | `ModelEvaluator` in pipeline/evaluator.py | §4 |
| Tiered evaluation (minimal/standard/deep/critical) | `tiering/` directory with auto-promotion | §4 (referenced via SERVE-MODE §5) |
| Calibration/self-measurement | `calibration/` — MAE, precision, recall, false accept rate | §5 |
| Degradation detection | `detection/` — reversal rate, dimension scores, confidence | §4.2 (breach detection) |
| Autonomy governance (one-way ratchet) | `governance/` — `ErrorBudgetGovernance.check_agent()` | §6 |
| Reversal rate tracking | Implemented as core degradation dimension | §4.4 (worked example) |
| LLM-as-judge for outcomes | ModelEvaluator uses LLM calls for quality scoring | §8 |
| Dimension-based scoring | `QualityScore.dimensions: dict[str, float]` | §4 |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| 8 formal evaluator types | Reversal rate + general quality scoring | Formal evaluators for each: reversal_rate, HCF, audit_sampling, outcomes, escalation, segments, stability, calibration | §4.1 |
| Evaluator Protocol interface | No formal protocol | `JudgmentSLOEvaluator` protocol with `evaluate()` and `statistical_requirements()` | §4.3 |
| Self-calibration pipeline (formal) | Basic calibration exists | Stratified daily sampling, independent re-evaluation against ground truth, per-evaluator agreement rate | §5.2 |
| Evaluator agreement SLO | Not formalized | Recursive: measure's evaluators have own judgment SLOs; terminates at first level + quarterly human audit | §5.3–§5.4 |
| 5 named autonomy levels | Governance has level concept but not these names | observer, advisor, limited-autonomous, autonomous, fully-autonomous | §6.1 |
| Audit sampling with stratification | Not implemented | Stratified sampling rates (overall + per-segment), queued for human review via Bench | §7 |
| Confidence intervals on evaluations | Basic metrics only | 95% coverage binomial CIs on all rate metrics | §4.4, §5.3 |

### Conflicts with existing

#### CONFLICT C-8.1: Evaluation output format

- **Current:** `QualityScore` dataclass with `eval_id: str`, `dimensions: dict`, `confidence: float`, `score: float`, stored in `SQLiteScoreStore`
- **Spec:** Three distinct output types:
  - `judgment_slo_evaluation` assessment (CID, not verdict)
  - `quality_breach` verdict (CID, triggers breach actions)
  - `autonomy_change` verdict (CID, records ratchet movement)
- **Impact:** nthlayer-measure's output surface changes from one type to three. Store changes from separate `SQLiteScoreStore` to shared verdict/assessment store.
- **Recommendation:** Migrate code. The three-type model is cleaner — assessments are continuous outputs; verdicts are decisions. Current QualityScore maps most naturally to `judgment_slo_evaluation` assessment.

#### CONFLICT C-8.2: Store — separate vs shared

- **Current:** `SQLiteScoreStore` in its own database with `evaluations`, `overrides`, `governance_log` tables
- **Spec:** Writes assessments and verdicts to shared store (SERVE-MODE §3.5)
- **Impact:** Store migration. `overrides` table concept may need rethinking in v2 context.
- **Recommendation:** Migrate code. Depends on C-4.1 (unified store) being resolved first.

#### CONFLICT C-8.3: Autonomy levels — existing vs spec

- **Current:** Governance has its own level scheme with numeric thresholds
- **Spec:** 5 named levels: observer → advisor → limited-autonomous → autonomous → fully-autonomous, with specific reduction rules (single breach low severity → one-level drop, etc.)
- **Impact:** Governance logic rewrite to use named levels and specified reduction rules
- **Recommendation:** Migrate code. The spec's 5-level scheme is more precise and integrates with RBAC policy (agent autonomy_level is a policy input).

---

## 9. NTHLAYER-CORRELATE-v1

### Confirms existing

| What | Evidence | Spec reference |
|------|----------|----------------|
| Signal correlation engine | `CorrelationEngine` in correlation/ | §4 |
| Event ingestion (webhook) | `WebhookIngester` — raw asyncio TCP | §5 |
| Temporal grouping | `TemporalGroup` dataclass, grouping logic in engine | §7.2 |
| Topology from manifests | Dependencies loaded from OpenSRM YAML | §6.1 |
| NL summary generation | `reasoning.py` — LLM-based causal analysis | §8 |
| State machine | `AgentState`: WATCHING → ALERT → INCIDENT → DEGRADED | §10 |
| Dedup by key | Dedup cache in component state | §5.2 |
| Prometheus alert ingestion | `prometheus.py` fetches alerts and metric breaches | §5.1 |

### Extends existing

| What | Current state | Spec addition | Spec reference |
|------|---------------|---------------|----------------|
| OTel servicegraph integration | Not implemented | Observed topology from `traces_service_graph_request_total` metrics | §6.2 |
| Declared vs observed topology drift | Not implemented as separate detection | Formal drift types: declared_not_observed, observed_not_declared, guarantee_mismatch | §6.3 |
| Contract divergence detection | Not implemented | promised vs observed availability/latency per contract | §9.3 |
| Blast radius via networkx | Blast radius partially computed | Formal transitive dependent computation via `networkx.descendants()` | §7.3 |
| Structured situation snapshots | Partial (CorrelationGroup) | Formal shape: window, alerts, assessments, affected_services, blast_radius, contracts, correlations | §7.1 |
| PD-CEF alert schema formalization | Alerts ingested but no formal schema | Formal PD-CEF superset with NthLayer extensions | §5 |

### Conflicts with existing

#### CONFLICT C-9.1: Streaming architecture — asyncio polling vs Bytewax

- **Current:** Raw asyncio TCP webhook ingester + FTS5 queries for temporal grouping. Poll-based correlation on timer.
- **Spec:** Bytewax dataflow with session windows (`fold_window`, 60s gap), checkpointed to SQLite. Continuous pre-correlation as events arrive.
- **Impact:** Core architecture of nthlayer-correlate's ingestion and grouping pipeline.
- **Recommendation:** This needs your input. Two options:
  - **Option A: Migrate to Bytewax.** Better correctness guarantees for windowing, more principled state management, checkpoint/recovery built-in. But adds a significant new dependency and rewrites the core pipeline.
  - **Option B: Update spec to match reality.** The current asyncio + FTS5 approach works. Session window semantics can be implemented without Bytewax (they're just "group events with gaps < 60s"). Bytewax adds value at scale but may be premature for current deployment sizes.
  - **My lean:** Option B for v1.5, Option A for v2. The current approach is functional; Bytewax adds most value at higher event volumes.

#### CONFLICT C-9.2: Event store — FTS5 vs shared store

- **Current:** Separate SQLite FTS5 event store optimized for text search (BM25 ranking, Porter stemming)
- **Spec:** Events written to shared verdict/assessment store. No separate FTS5 store mentioned.
- **Impact:** nthlayer-correlate's query patterns rely heavily on FTS5 for signal retrieval.
- **Recommendation:** Keep parallel with rationale. FTS5 is a query optimization, not a data model choice. Correlate can write verdicts to the shared store AND maintain a local FTS5 index for its own queries. The spec doesn't forbid additional indexes.

#### CONFLICT C-9.3: Output types — generic vs specialized

- **Current:** Produces `correlation` type verdicts via nthlayer-learn
- **Spec:** Three distinct output types:
  - `correlation_snapshot` assessment (continuous pre-correlated windows)
  - `topology_drift` verdict (declared vs observed divergence)
  - `contract_divergence` verdict (promised vs observed)
- **Impact:** Output surface changes from one type to three. Consumers (nthlayer-respond) need to handle new types.
- **Recommendation:** Migrate code. The three-type model is more precise and maps cleanly to different consumer actions.

---

## 10. NTHLAYER-BENCH-v2.1

### Confirms existing

Nothing — nthlayer-bench does not exist. This is a greenfield implementation.

### Extends existing

Everything in the spec is new. Key capabilities to implement:

| What | Spec reference |
|------|----------------|
| Textual TUI framework | §3.1 |
| Case store with atomic leasing | §4.4 |
| Situation board (prose-first) | §5.1 |
| Case bench with priority grouping | §5.2 |
| Case detail with briefing + policy context | §5.3 |
| Reasoning capture (tags + prose) | §6 |
| Biscuit token display (prose, not Datalog) | §7 |
| Retrospective signal flow | §8 |
| Team-based filtering (default to team, toggle all) | §5.2 |
| Notification policy (P0 5min, P1 10min escalation) | §11 |
| textual-serve for SaaS delivery | §3.2 |
| 7 implementation phases | §12 |

### Conflicts with existing

None.

---

## Cross-Cutting Conflicts

These conflicts span multiple specs and affect the overall migration strategy:

### CONFLICT C-X.1: Two content-addressing systems must converge

- **System A (nthlayer-learn):** String IDs (`vrd-...`), JSON serialization, single `verdicts` table
- **System B (nthlayer-common/records):** SHA-256 on canonical JSON, `(hash, previous_hash)` chains, 6 tables (assessments, verdicts, evaluations, incidents, prompts, responses)
- **Spec target:** IPLD CIDv1 on canonical CBOR via libipld, single unified store with `lineage` index
- **Impact:** Both systems need to be replaced by the spec's system. System B's accountability fields (prompt_hash, response_hash, model) should be carried forward as content fields in the new verdict model.
- **Recommendation:** Migrate code. The unified IPLD system is the target. System B's `prompts` and `responses` tables provide useful content-addressed lookup and could be retained as an optimization (prompt dedup across components), but the chain linkage moves to CIDs.

### CONFLICT C-X.2: Manifest format migration affects the entire ecosystem

- **v1 format:** `apiVersion: srm/v1`, `kind: ServiceReliabilityManifest`, bespoke SLO syntax, inline ownership
- **v2 format:** `apiVersion: opensrm.nthlayer.io/v2`, `kind: ServiceManifest`, OpenSLO v1, Backstage refs
- **Impact:** 30+ YAML files across nthlayer/, opensrm/, demo/. The nthlayer compiler, nthlayer-observe SLO collector, and all components that load manifests.
- **Recommendation:** Migrate code with backward compatibility. The nthlayer compiler should accept both v1 and v2 formats (auto-detection on apiVersion). New manifests use v2. Old manifests migrate progressively. A `nthlayer migrate-manifest` command could automate the conversion.

---

## Dependency Summary

New libraries required by v2 that are not in any current pyproject.toml:

| Library | Purpose | Spec reference | Confidence in choice |
|---------|---------|----------------|---------------------|
| `libipld` (MarshalX/python-libipld) | IPLD CID generation, canonical CBOR encoding | LEARN §4.2 | High — Rust+PyO3, MIT, named in spec |
| `instructor` (567-labs/instructor) | Structured LLM outputs with automatic retry | COMMON §3.3 | High — named in spec, active maintenance |
| `sigstore-python` | Rekor anchoring for tamper evidence | LEARN §6 | High — named in spec, Apache-2.0 |
| `Textual` (textualize/textual) | TUI framework for nthlayer-bench | BENCH §3.1 | High — named in spec |
| `textual-serve` | SaaS delivery for Bench | BENCH §3.2 | High — named in spec |
| `textual-plotext` | Charts in Bench | BENCH §3.3 | Medium — could defer |
| `Regorus` (microsoft/regorus) | Rego policy evaluation | RBAC §5.3 | High — named in spec, Rust+PyO3 |
| `biscuit-python` | Capability tokens | RBAC §6 | High — named in spec, Eclipse Foundation |
| `PyNaCl` | Ed25519 signing for tokens and Rekor | RBAC §6.3, LEARN §6 | High — PyCA-maintained |
| `Bytewax` | Streaming dataflow (if adopted) | CORRELATE §4 | Medium — see C-9.1 |
| `networkx` | Graph algorithms for blast radius | CORRELATE §6.4 | High — already indirect dep via scipy |
| `py-spiffe` | SPIFFE workload identity (optional) | RBAC §8 | Low priority — operational improvement |
| `opentelemetry-api/sdk/exporter-otlp` | Full OTel integration | COMMON §7, §12 | High — named in spec |
| `sqlite-utils` | Store access utilities | COMMON §12 | Medium — evaluate vs raw sqlite3 |

---

## Decision Points for Your Review

Please mark each conflict with one of:
- **migrate code** — change implementation to match spec
- **update spec** — change spec to match implementation
- **keep parallel** — both coexist with explicit rationale

### Structural decisions (blocking Phase 0):

| ID | Conflict | My recommendation | Your decision |
|----|---------|-------------------|---------------|
| C-4.1 | Per-component stores → unified store | migrate code | |
| C-7.1 | String verdict IDs → IPLD CIDs | migrate code | |
| C-7.2 | JSON TEXT → CBOR BLOB | migrate code | |
| C-6.1 | `llm_call()` function → `LLM` class + Instructor | migrate code | |
| C-3.1 | respond owns execution → authorise + executor split | migrate code | |
| C-X.1 | Two content-addressing systems → one IPLD system | migrate code | |
| C-X.2 | Manifest v1 → v2 format | migrate code (with v1 compat) | |

### Architectural decisions (blocking Phase 1):

| ID | Conflict | My recommendation | Your decision |
|----|---------|-------------------|---------------|
| C-9.1 | asyncio polling → Bytewax streaming | keep parallel (asyncio for v1.5, Bytewax for v2) | |
| C-9.2 | FTS5 event store vs shared store | keep parallel (FTS5 as query optimization) | |
| C-6.2 | Two Verdict types → one unified type | migrate code | |
| C-6.3 | Per-component config → single nthlayer.yaml | migrate code | |

### Format/schema decisions:

| ID | Conflict | My recommendation | Your decision |
|----|---------|-------------------|---------------|
| C-2.1 | apiVersion srm/v1 → opensrm.nthlayer.io/v2 | migrate code | |
| C-2.2 | Bespoke SLO → OpenSLO v1 | migrate code | |
| C-2.3 | Inline ownership → Backstage entity refs | need your input (required vs optional?) | |
| C-2.4 | Simple deps → contract-referenced deps | migrate code (additive) | |
| C-3.2 | Code-defined safe actions → manifest-declared actions | migrate code | |
| C-4.2 | Verdict table schema migration | migrate code | |
| C-4.3 | Assessment table schema migration | migrate code | |
| C-5.1 | JSON events → CBOR + CloudEvents | migrate code | |
| C-7.3 | Inline lineage → indexed lineage table | migrate code | |
| C-8.1 | QualityScore → 3 output types | migrate code | |
| C-8.2 | Separate score store → shared store | migrate code | |
| C-8.3 | Custom autonomy levels → 5 named levels | migrate code | |
| C-9.3 | Generic correlation → 3 specialized output types | migrate code | |

---

## What I'm NOT flagging

These are areas where the spec describes something that doesn't exist yet but also doesn't conflict with anything:

- nthlayer-bench (greenfield)
- nthlayer-authorise (greenfield)
- nthlayer-executor (greenfield)
- ChangeFreeze kind (additive)
- Preconditions Rego modules (additive)
- Heartbeat mechanism (additive)
- Suppression table (additive)
- Retention maintenance job (additive)
- Rekor anchoring (additive)
- All telemetry envelope additions (additive)
- All nthlayer.* OTel attributes (additive)

These become tasks in Phase 1–4, not conflicts to resolve.
