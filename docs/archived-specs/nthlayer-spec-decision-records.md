# NthLayer Spec: Content-Addressed Decision Records

**Status:** Draft
**Component scope:** nthlayer-observe, nthlayer-respond (agentic components), nthlayer-learn
**Date:** 2026-04-09

---

## Problem

NthLayer's value proposition is mechanical accountability for AI reliability decisions. If assessments and verdicts can be silently modified after creation, post-incident forensics cannot determine whether the system itself made the right call. Additionally, passing full assessment payloads into agent prompt context is wasteful — the same structured data may be referenced by triage, investigation, communication, and remediation agents within a single respond cycle. Finally, the learn loop has no durable record of its own judgments — whether a past action was effective or not is currently ephemeral, which means the system cannot prove it is improving over time.

## Principles

1. **Assessments, verdicts, and evaluations are append-only.** Once written, they are never modified or deleted during their retention window.
2. **Every record is content-addressed.** The hash of the record's canonical form is its identity.
3. **Agents reference by hash, read by summary.** Prompt context carries a pre-computed natural language summary (in the appropriate register) plus the hash. Full structured data is retrievable on demand.
4. **The chain is verifiable.** Any record can be independently verified against its hash. Sequential records are hash-chained so gaps or mutations are detectable.
5. **The loop closes.** Every verdict eventually receives an evaluation recording whether the action achieved the desired outcome. The system proves not just what it did, but whether it was right.

## Record Types

### Assessment

Produced by `nthlayer-observe`. Deterministic. Represents a measured fact about system state.

```
Assessment {
  hash:           string    // SHA-256 of canonical_form
  previous_hash:  string    // hash of prior assessment in this stream (chain link)
  schema_version: string    // e.g. "assessment/v1" — required for payload deserialisation
  timestamp:      ISO-8601
  stream:         string    // e.g. "sli:checkout-service:latency-p99"
  incident_id:    string?   // assigned when assessment triggers or joins a respond cycle
  type:           enum      // threshold_breach | correlation | drift | change_event
  severity:       enum      // critical | warning | info — pre-computed by observe at write time
  payload:        object    // structured data, schema per type
  summaries: {
    technical:    string    // for investigation agent, max 280 chars
    plain:        string    // for communication agent / Slack, max 280 chars
    executive:    string    // for escalation, max 140 chars
  }
}
```

**Canonical form** for hashing: JSON with sorted keys, no whitespace, UTF-8 encoded. The `hash` and `previous_hash` fields are excluded from the canonical form (they are derived, not input).

### Verdict

Produced by agentic components within `nthlayer-respond`. Non-deterministic (LLM-derived). Represents a judgment and a recommended or executed action.

```
Verdict {
  hash:             string    // SHA-256 of canonical_form
  previous_hash:    string    // hash of prior verdict in this agent's stream
  schema_version:   string    // e.g. "verdict/v1"
  timestamp:        ISO-8601
  agent:            string    // e.g. "triage", "investigation", "remediation"
  incident_id:      string    // links this verdict to the triggering incident
  input_hashes:     string[]  // hashes of assessments (and/or prior verdicts) consumed
  prompt_hash:      string    // SHA-256 of the full prompt sent to the LLM
  response_hash:    string    // SHA-256 of the full LLM response (CoT, tool calls, refusals)
  model:            string    // e.g. "claude-sonnet-4-20250514"
  reasoning:        string    // LLM's stated reasoning (may be truncated for storage)
  action:           object    // the recommended/executed action, schema per agent type
  outcome:          enum      // recommended | approved | executed | rejected | expired
  summaries: {
    technical:      string    // for downstream agents, max 280 chars
    plain:          string    // for Slack / human review, max 280 chars
    executive:      string    // for escalation, max 140 chars
  }
}
```

The `prompt_hash` and `response_hash` fields enable full LLM interaction reconstruction from separate stores without embedding payloads in the verdict chain. This is the "residual" — retrievable when needed, not carried by default.

### Evaluation

Produced by `nthlayer-learn`. Closes the feedback loop. Represents a retrospective judgment on whether a verdict's action achieved the desired outcome.

```
Evaluation {
  hash:             string    // SHA-256 of canonical_form
  previous_hash:    string    // hash of prior evaluation in this stream
  schema_version:   string    // e.g. "evaluation/v1"
  timestamp:        ISO-8601
  incident_id:      string    // the incident being evaluated
  verdict_hash:     string    // the specific verdict being evaluated
  method:           enum      // metric_recovery | human_review | timeout | slo_restoration
  outcome:          enum      // effective | ineffective | inconclusive | partial
  evidence_hashes:  string[]  // post-action assessment hashes that support the evaluation
  payload:          object    // structured evaluation data (recovery time, metric deltas, etc.)
  summaries: {
    technical:      string
    plain:          string
  }
}
```

Evaluations are what make the learn loop auditable. Without them, the chain proves what the system *did* but not whether it was *right*. An evaluation references the verdict it judges and the post-action assessments that constitute its evidence — creating a closed loop from measure through respond back to measure.

### Incident Envelope

An incident groups related assessments, verdicts, and evaluations into a single queryable unit. The `incident_id` is assigned by `nthlayer-observe` when a respond cycle is triggered and propagated to all downstream records.

```
Incident {
  id:               string    // UUID, assigned at trigger time
  created_at:       ISO-8601
  trigger_hash:     string    // hash of the assessment that initiated the respond cycle
  stream:           string    // primary stream (from trigger assessment)
  status:           enum      // open | mitigated | resolved | learning | closed
}
```

This is a lightweight index, not a content-addressed record — incidents are mutable (their status changes as the cycle progresses). The immutable records within the incident are the assessments, verdicts, and evaluations.

## Hash Chain Structure

Each record type maintains independent chains per logical stream:

- Assessment chains: one per `stream` value (e.g. per SLI, per correlation rule)
- Verdict chains: one per `agent` value

The `previous_hash` of the first record in any chain is the zero hash (`0x00...00`).

```
Incident: inc-4821
├── Assessment Chain (stream: sli:checkout:latency-p99)
│   ┌──────────┐     ┌──────────┐     ┌──────────┐
│   │ hash: a1 │────▶│ hash: a2 │────▶│ hash: a3 │
│   │ prev: 00 │     │ prev: a1 │     │ prev: a2 │
│   └──────────┘     └──────────┘     └──────────┘
│
├── Verdict Chain (agent: remediation)
│   ┌──────────┐     ┌──────────┐
│   │ hash: v1 │────▶│ hash: v2 │  (v2 = human approval of v1)
│   │ prev: 00 │     │ prev: v1 │
│   │ inputs:  │     │ inputs:  │
│   │  [a1,a2] │     │  [v1]    │
│   └──────────┘     └──────────┘
│
└── Evaluation Chain (incident: inc-4821)
    ┌──────────┐
    │ hash: e1 │
    │ prev: 00 │
    │ verdict: │
    │  v1      │
    │ evidence:│
    │  [a3]    │  ← post-action assessment proving recovery
    └──────────┘
```

Cross-references between chains are via `input_hashes` on verdicts — these point into assessment chains (and optionally other verdict chains) without coupling the chain structures.

## Context Compression

When an agent needs to reason about assessments, the prompt carries the summary register appropriate to that agent's role:

**Investigation agent** receives `technical` summaries:
```
Assessment a8f2c1: Latency p99 for checkout-service breached 500ms SLO at 03:42 UTC. Current: 1247ms. Trend: increasing over 4m window.
Assessment 3b9d2f: Correlated error rate spike on checkout-service. 5xx rate 12.4% (threshold: 1%). Top path: /api/v2/checkout.
Assessment e4c17a: Deploy event detected. checkout-service v2.8.1 → v2.8.2 at 03:38 UTC. Changed files: 3 in payment module.
```

**Communication agent** receives `plain` summaries:
```
Assessment a8f2c1: checkout-service response times are 2.5x slower than normal since 03:42 UTC.
Assessment 3b9d2f: checkout-service is returning errors for about 1 in 8 requests.
Assessment e4c17a: A new version of checkout-service was deployed 4 minutes before the issue started.
```

Each agent gets exactly the compression register it needs. No agent re-summarises. Full payloads remain available via hash lookup if an agent explicitly requests drill-down.

Not:

```json
{"stream":"sli:checkout-service:latency-p99","type":"threshold_breach","payload":{"current_value":1247,"threshold":500,"unit":"ms","window":"5m","slo_id":"checkout-latency","breach_duration_seconds":240,"trend":"increasing","samples":[...]}}
```

The summary is generated at write time by `nthlayer-observe` (for assessments) or the producing agent (for verdicts). Downstream agents receive summaries. Full payloads are available via hash lookup if an agent explicitly requests drill-down.

**Context budget:** A single assessment summary costs ~30 tokens. A full assessment payload costs ~200-500 tokens. For a typical incident with 3-5 correlated assessments referenced by 4 agents, this saves 2,000-8,000 tokens per respond cycle.

## Storage

### v0: SQLite

Sufficient for single-node deployment and demo purposes.

```sql
CREATE TABLE assessments (
  hash            TEXT PRIMARY KEY,
  previous_hash   TEXT NOT NULL,
  schema_version  TEXT NOT NULL,
  timestamp       TEXT NOT NULL,
  stream          TEXT NOT NULL,
  incident_id     TEXT,              -- NULL until a respond cycle claims it
  type            TEXT NOT NULL,
  severity        TEXT NOT NULL,     -- critical | warning | info
  payload         TEXT NOT NULL,     -- JSON
  summaries       TEXT NOT NULL,     -- JSON: {technical, plain, executive}
  canonical       TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE verdicts (
  hash            TEXT PRIMARY KEY,
  previous_hash   TEXT NOT NULL,
  schema_version  TEXT NOT NULL,
  timestamp       TEXT NOT NULL,
  agent           TEXT NOT NULL,
  incident_id     TEXT NOT NULL,
  input_hashes    TEXT NOT NULL,     -- JSON array of strings
  prompt_hash     TEXT NOT NULL,
  response_hash   TEXT NOT NULL,
  model           TEXT NOT NULL,
  reasoning       TEXT NOT NULL,
  action          TEXT NOT NULL,     -- JSON
  outcome         TEXT NOT NULL,
  summaries       TEXT NOT NULL,     -- JSON: {technical, plain, executive}
  canonical       TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE evaluations (
  hash            TEXT PRIMARY KEY,
  previous_hash   TEXT NOT NULL,
  schema_version  TEXT NOT NULL,
  timestamp       TEXT NOT NULL,
  incident_id     TEXT NOT NULL,
  verdict_hash    TEXT NOT NULL,
  method          TEXT NOT NULL,
  outcome         TEXT NOT NULL,
  evidence_hashes TEXT NOT NULL,     -- JSON array of strings
  payload         TEXT NOT NULL,     -- JSON
  summaries       TEXT NOT NULL,     -- JSON: {technical, plain}
  canonical       TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE incidents (
  id              TEXT PRIMARY KEY,
  created_at      TEXT NOT NULL,
  trigger_hash    TEXT NOT NULL,
  stream          TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE prompts (
  hash       TEXT PRIMARY KEY,
  content    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE responses (
  hash       TEXT PRIMARY KEY,
  content    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Chain traversal
CREATE INDEX idx_assessments_stream ON assessments(stream, timestamp);
CREATE INDEX idx_assessments_incident ON assessments(incident_id);
CREATE INDEX idx_verdicts_agent ON verdicts(agent, timestamp);
CREATE INDEX idx_verdicts_incident ON verdicts(incident_id);
CREATE INDEX idx_evaluations_incident ON evaluations(incident_id);
CREATE INDEX idx_evaluations_verdict ON evaluations(verdict_hash);
```

SQLite WAL mode provides append-only semantics at the storage layer. Application-level enforcement: the write path never issues UPDATE or DELETE on these tables.

### Future: PostgreSQL / object store

For multi-node deployments, the same schema maps directly to PostgreSQL. For long-term archival, records can be serialised to content-addressed objects in S3/GCS with a metadata index.

## Verification

A verification pass walks a chain from genesis and confirms:

1. Each record's `hash` matches the SHA-256 of its `canonical` field.
2. Each record's `previous_hash` matches the `hash` of the preceding record in the chain.
3. No gaps exist (chain is contiguous by timestamp within the stream).
4. All `input_hashes` and `evidence_hashes` resolve to existing records.
5. All `prompt_hash` and `response_hash` values resolve to existing entries in the interaction stores.

This can run as a periodic background job in `nthlayer-observe` or as an on-demand CLI command for incident review.

```
$ nthlayer verify --chain assessments --stream "sli:checkout-service:latency-p99"
Chain: sli:checkout-service:latency-p99
Records: 14,281
First: 2026-01-15T08:00:00Z
Last:  2026-04-09T14:22:00Z
Status: VERIFIED ✓

$ nthlayer verify --incident inc-4821
Incident: inc-4821
Assessments: 5 (3 chains) ✓
Verdicts: 4 (2 chains) ✓
Evaluations: 1 ✓
Cross-references: all resolved ✓
Prompts/responses: all present ✓
Status: VERIFIED ✓
```

## Decision Telemetry Bridge (OTel)

Assessments and verdicts are the source of truth. OTel is the discovery and correlation layer. Every record emits an OTel span or event using the `gen_ai.decision.*` and `gen_ai.override.*` semantic conventions from Decision Telemetry:

```
span: gen_ai.decision.verdict
  attributes:
    nthlayer.hash:        "v1a2b3..."
    nthlayer.incident_id: "inc-4821"
    gen_ai.decision.agent: "remediation"
    gen_ai.decision.action: "rollback"
    gen_ai.decision.outcome: "recommended"
    gen_ai.decision.model: "claude-sonnet-4-20250514"
    gen_ai.decision.input_count: 3
```

This means:

- Assessments and verdicts are discoverable via Tempo/Jaeger traces without a separate query path.
- Existing OTel-based alerting and dashboards can trigger on decision events natively.
- The hash attribute is the bridge — click through from a trace span to the full immutable record in the NthLayer store.
- `gen_ai.override.*` attributes capture human approval/rejection events, connecting the Slack interactive button flow to the trace.

The OTel spans are ephemeral (subject to trace retention policies). The content-addressed records are the durable store. OTel is the index; the record store is the archive.

## Component Responsibilities

| Concern | Owner |
|---|---|
| Create assessments, compute hash, assign severity, write to store | nthlayer-observe |
| Generate multi-register assessment summaries at write time | nthlayer-observe |
| Create and manage incident envelopes | nthlayer-observe |
| Create verdicts, compute hash, write to store | Each agentic component (via shared library) |
| Store and retrieve prompts + responses by hash | nthlayer-respond (shared interaction store) |
| Create evaluations, close the learn feedback loop | nthlayer-learn |
| Emit OTel spans for all record types | Shared library (called by each component) |
| Chain verification | nthlayer-observe (background) + CLI |
| Expose records via API for incident review | nthlayer-observe (read API) |

## OpenSRM Implications

This pattern is a candidate for codification in the OpenSRM spec as a normative requirement:

> **Principle: Decision Immutability.** All reliability assessments, automated verdicts, and retrospective evaluations produced by a conforming system MUST be recorded in an append-only, content-addressed store. Records MUST be hash-chained per logical stream. Conforming systems MUST provide a verification mechanism to detect chain tampering or discontinuity. Verdict records MUST capture sufficient provenance (prompt, response, input assessments) to enable full decision reconstruction.

This positions decision traceability as a first-class reliability primitive, not an aftermarket compliance bolt-on — which is exactly the differentiation from tools like Cyris that treat audit trails as the product rather than as infrastructure that enables the product. The Evaluation record type goes further: it demands that conforming systems not only record what they did, but eventually record whether it worked.

## Open Questions

1. **Retention policy.** How long are chains retained? Should `nthlayer-observe` enforce TTL, or is this an operator configuration? Evaluation records may need longer retention than assessments since they represent learning outcomes.
2. **Summary regeneration.** Summaries are part of the canonical form — changing them breaks hashes. If summary generation logic improves, add a non-canonical `summaries_v2` annotation rather than regenerating. This preserves chain integrity while allowing improved human readability of historical records.
3. **Cross-deployment identity.** If NthLayer is deployed across multiple environments, should hashes be namespaced? Or is the stream identifier sufficient?
4. **nthlayer-gate verdicts.** A gate decision ("block this deploy" / "allow this deploy") is a verdict. Gate needs to participate in this system. Does gate maintain its own verdict chain per deployment pipeline, or does it share the remediation agent's chain? Likely its own — gate decisions have a different lifecycle than incident-driven remediation.
5. **Summary register selection.** Who decides which register an agent receives — the agent's own config, or the prompt assembly layer? Leaning toward prompt assembly (the component that constructs agent prompts selects the register based on agent role), keeping agents unaware of the summary system.
6. **Evaluation timing.** When does nthlayer-learn produce an evaluation? Immediately on metric recovery? After a configurable observation window? On human confirmation? Probably configurable per policy — some actions can be evaluated by metric recovery alone, others need human judgment.

## Resolved from Draft v1

- **Verdict chains for approval workflows.** A human approval/rejection via Slack interactive button is a new verdict in the chain (outcome: `approved` or `rejected`), not a mutation. The approval verdict references the original verdict via `input_hashes`. The OTel bridge emits this as a `gen_ai.override.*` event.
- **Learn loop.** Addressed via the Evaluation record type.
