# NthLayer Specification Index — v1

**Purpose:** Navigation layer over the NthLayer v2 specification corpus. If you need to know X, this document tells you which spec to read and which section within it.

**Corpus:** Eight specification documents plus one OSS delegation research report, produced April 2026.

---

## The documents

### Specifications

1. **[OPENSRM-CORE-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-CORE-v2.md)** — The OpenSRM specification. Declarative format for service reliability. Composes OpenSLO, Backstage, CloudEvents, OpenAPI, AsyncAPI, OTel GenAI semconv. Original contribution: judgment SLOs, reliability contracts, dependencies-with-expected-guarantees. Not tied to NthLayer implementation.

2. **[OPENSRM-RBAC-EXTENSION-v2.md](https://github.com/rsionnach/opensrm/blob/main/OPENSRM-RBAC-EXTENSION-v2.md)** — Extension to OpenSRM for unified human/agent authorisation. Introduces Principals, Actions, Capability Tokens, Authorisation Policies, preconditions, ChangeFreeze. Implementation uses Rego (via Regorus), Biscuit tokens, optional SPIFFE.

3. **NTHLAYER-SERVE-MODE-v2.1.md** — The runtime pipeline for NthLayer reference implementation. Pull-based, SQLite+WAL shared store, heartbeats, retention, Rekor anchoring, scale-out upgrade path.

4. **NTHLAYER-BENCH-v2.1.md** — Terminal-native operator interface. Situation board, case bench, case detail. Built with Textual + textual-serve + textual-plotext + Sparkline.

5. **NTHLAYER-CORRELATE-v1.md** — Streaming correlation engine. Bytewax dataflow, session windows, NL summaries, topology drift and contract divergence detection.

6. **NTHLAYER-LEARN-v1.md** — Verdict data primitive. IPLD CIDs, hash-chained lineage, three-phase verdict lifecycle, Sigstore Rekor anchoring, retrospective analysis, retention maintenance.

7. **NTHLAYER-MEASURE-v1.md** — Judgment SLO evaluation. Statistical conservatism, self-calibration, one-way autonomy ratchet, LLM-as-judge for text-shaped outcomes.

8. **NTHLAYER-COMMON-v1.md** — Shared library. LLM wrapper (httpx + Instructor, no LiteLLM), store access primitives, provider integrations, identity resolution, telemetry, data models.

9. **NTHLAYER-TELEMETRY-ENVELOPE-v1.md** — Wire format consolidation. CloudEvents envelope, OTel gen_ai attributes, PD-CEF alert schema, decision log format, upstream contribution strategy.

### Supporting document (non-normative)

**NthLayer OSS Delegation Strategy** — Research report mapping OpenSRM surface to OSS primitives. Impact-vs-effort ranking. Referenced from OpenSRM core §16.3 as an implementation-guidance pointer.

---

## Topic index

### Architecture and concepts

| Question | Document | Section |
|---|---|---|
| What is OpenSRM's relationship to OpenSLO, Backstage, OTel, etc.? | OPENSRM-CORE | §2 |
| What's the architectural thesis for NthLayer? | NTHLAYER-SERVE-MODE | §1, §3 |
| What is a verdict and how does its lifecycle work? | NTHLAYER-LEARN | §4 |
| What is Zero Framework Cognition in NthLayer's implementation? | NTHLAYER-COMMON | §2, §13 |
| How does the pipeline compose? (flow diagram) | NTHLAYER-SERVE-MODE | §2 |
| Why pull over push? Why SQLite not PostgreSQL? | NTHLAYER-SERVE-MODE | §1, §12 |
| Why the one-way autonomy ratchet? | NTHLAYER-MEASURE | §6.4 |

### OpenSRM manifest authoring

| Question | Document | Section |
|---|---|---|
| What does a full manifest look like? | OPENSRM-CORE | §3 |
| How do classical SLOs work (availability, latency, etc.)? | OPENSRM-CORE | §4 |
| How do judgment SLOs work? | OPENSRM-CORE | §5 |
| What are the eight standard judgment SLO types? | OPENSRM-CORE | §5.2.1 – §5.2.8 |
| How are reliability contracts declared? | OPENSRM-CORE | §6 |
| How are dependencies with expected guarantees declared? | OPENSRM-CORE | §7 |
| How does template inheritance work? | OPENSRM-CORE | §9 |
| How do change freezes work and how do external systems publish them? | OPENSRM-RBAC | §7 |

### Authorisation

| Question | Document | Section |
|---|---|---|
| How do principals work (human/agent/system)? | OPENSRM-RBAC | §3 |
| How do actions work and where are they declared? | OPENSRM-RBAC | §4 |
| How does policy evaluation work? | OPENSRM-RBAC | §5 |
| How does the YAML DSL compile to Rego? | OPENSRM-RBAC | §5.2 |
| What goes into a capability token (Biscuit)? | OPENSRM-RBAC | §6 |
| How does SPIFFE integrate? | OPENSRM-RBAC | §8 |
| How do preconditions work (rate-limit, change-freeze, etc.)? | OPENSRM-RBAC | §4.4 |
| What's the full authorisation flow end-to-end? | OPENSRM-RBAC | §12; TELEMETRY-ENVELOPE §10.1 |

### Pipeline runtime

| Question | Document | Section |
|---|---|---|
| What's the store schema? | NTHLAYER-SERVE-MODE | §3.5 |
| How does each component map to OSS substrates? | NTHLAYER-SERVE-MODE | §5 |
| How does the component base pattern work? | NTHLAYER-SERVE-MODE | §4 |
| How are heartbeats emitted and consumed? | NTHLAYER-SERVE-MODE | §8 |
| How does active-incident suppression and dedup work? | NTHLAYER-SERVE-MODE | §7 |
| How is SQLite backed up (Litestream)? | NTHLAYER-SERVE-MODE | §3.4 |
| What's the integration test shape? | NTHLAYER-SERVE-MODE | §13 |
| How is scale-out achieved when needed? | NTHLAYER-SERVE-MODE | §12 |

### Verdicts and data model

| Question | Document | Section |
|---|---|---|
| What verdict types exist? | OPENSRM-RBAC | §10; TELEMETRY-ENVELOPE §3.4 |
| How are CIDs computed? | NTHLAYER-LEARN | §4.2 |
| How does hash-chaining work? | NTHLAYER-LEARN | §4.3 |
| What are the three verdict phases? | NTHLAYER-LEARN | §4.4, §4.5, §4.6 |
| How are outcomes resolved? | NTHLAYER-LEARN | §4.5 |
| How is Rekor anchoring done? | NTHLAYER-LEARN | §6 |
| How does retention work? | NTHLAYER-LEARN | §8 |
| What's the lineage index for? | NTHLAYER-LEARN | §5.2 |

### Correlation

| Question | Document | Section |
|---|---|---|
| What does nthlayer-correlate produce? | NTHLAYER-CORRELATE | §2, §9 |
| How is the Bytewax dataflow structured? | NTHLAYER-CORRELATE | §4.2 |
| What's the PD-CEF alert schema with NthLayer extensions? | NTHLAYER-CORRELATE §5; TELEMETRY-ENVELOPE §5 |
| How is topology drift detected? | NTHLAYER-CORRELATE | §6.3 |
| How are natural-language summaries generated? | NTHLAYER-CORRELATE | §8 |
| How does blast-radius computation work? | NTHLAYER-CORRELATE | §7.3 |

### Judgment SLO evaluation

| Question | Document | Section |
|---|---|---|
| How is each SLO type evaluated? | NTHLAYER-MEASURE | §4 |
| How does self-calibration work? | NTHLAYER-MEASURE | §5 |
| What are the autonomy levels? | NTHLAYER-MEASURE | §6.1 |
| When does autonomy get reduced automatically? | NTHLAYER-MEASURE | §6.3 |
| How is audit sampling handled? | NTHLAYER-MEASURE | §7 |
| How is LLM-as-judge calibrated? | NTHLAYER-MEASURE | §8 |

### Operator experience

| Question | Document | Section |
|---|---|---|
| What does the situation board look like? | NTHLAYER-BENCH | §5.1 |
| What does a case look like in the bench? | NTHLAYER-BENCH | §5.2 |
| How is a case opened and resolved? | NTHLAYER-BENCH | §5.3 |
| How is reasoning captured (tags, prose)? | NTHLAYER-BENCH | §6 |
| How are Biscuit tokens displayed to operators? | NTHLAYER-BENCH | §7 |
| What does concurrent operator handling look like? | NTHLAYER-BENCH | §4.4, §10 |
| When do cases escalate to on-call? | NTHLAYER-BENCH | §11 |
| How is SaaS delivery achieved (textual-serve)? | NTHLAYER-BENCH | §3.2 |

### Wire formats and telemetry

| Question | Document | Section |
|---|---|---|
| What does an event look like on the wire? | TELEMETRY-ENVELOPE | §3.6, §10 |
| What's the type taxonomy? | TELEMETRY-ENVELOPE | §3.4 |
| Which OTel gen_ai attributes are adopted? | TELEMETRY-ENVELOPE | §4.2 |
| What's the gen_ai.decision.* proposal? | TELEMETRY-ENVELOPE | §4.3, §8 |
| How does NthLayer SIEM-integrate? | TELEMETRY-ENVELOPE | §6.3 |
| What's the decision log format? | TELEMETRY-ENVELOPE | §6 |
| What's the upstream contribution strategy? | TELEMETRY-ENVELOPE | §8 |

### Implementation and operations

| Question | Document | Section |
|---|---|---|
| What Python libraries should components use? | NTHLAYER-COMMON | §12 |
| What's explicitly not a dependency? (LiteLLM, LangChain, etc.) | NTHLAYER-COMMON | §2, §13 |
| How is the LLM wrapper structured? | NTHLAYER-COMMON | §3 |
| How is cost accounting done? | NTHLAYER-COMMON | §3.4 |
| How is configuration loaded? | NTHLAYER-COMMON | §10 |
| How is OTel telemetry emitted? | NTHLAYER-COMMON | §7 |

---

## Cross-spec concerns

Several concerns span multiple specs. These are the headline ones:

### Verdicts and their storage

- Wire format: TELEMETRY-ENVELOPE §3, §4
- Content-addressing: NTHLAYER-LEARN §4.2
- Storage schema: NTHLAYER-SERVE-MODE §3.5
- Verdict types: OPENSRM-RBAC §10
- Producer responsibilities: each component spec

### The authorisation flow

- Principals and actions: OPENSRM-RBAC §3, §4
- Policy evaluation: OPENSRM-RBAC §5
- Capability tokens: OPENSRM-RBAC §6
- Operator approval UX: NTHLAYER-BENCH §5.3, §7
- Execution: OPENSRM-RBAC §11.2
- Decision logs: TELEMETRY-ENVELOPE §6
- Full worked example: OPENSRM-RBAC §12

### Judgment SLOs

- Declaration: OPENSRM-CORE §5
- Evaluation: NTHLAYER-MEASURE §4
- Calibration signals: NTHLAYER-LEARN §7.2
- Autonomy governance: NTHLAYER-MEASURE §6
- Telemetry: TELEMETRY-ENVELOPE §4

### Correlation

- Signal ingest: NTHLAYER-CORRELATE §5
- Topology (declared): OPENSRM-CORE §7
- Topology (observed): NTHLAYER-CORRELATE §6.2
- Drift detection: NTHLAYER-CORRELATE §6.3
- Contracts: OPENSRM-CORE §6
- Output verdicts: NTHLAYER-CORRELATE §9

### Rekor anchoring

- Mechanism: NTHLAYER-LEARN §6
- Storage: NTHLAYER-SERVE-MODE §9
- Anchor table schema: NTHLAYER-SERVE-MODE §3.5

### CloudEvents + OTel wire format

- Full format spec: TELEMETRY-ENVELOPE (entire document)
- Used by every component that writes verdicts

---

## Reading order recommendations

### For Claude Code starting implementation

Read in this order. Skip nothing in the first four.

1. **This index** (you're here).
2. **OPENSRM-CORE v2** — the specification being implemented against.
3. **OPENSRM-RBAC-EXTENSION v2** — the authorisation model.
4. **NTHLAYER-SERVE-MODE v2.1** — how components run, where they store state.
5. **NTHLAYER-TELEMETRY-ENVELOPE v1** — the wire format for everything.
6. **NTHLAYER-COMMON v1** — the shared library each component depends on.
7. **NTHLAYER-LEARN v1** — the verdict primitive.
8. **NTHLAYER-MEASURE v1**, **NTHLAYER-CORRELATE v1**, **NTHLAYER-BENCH v2.1** — in whatever order the implementation phase requires.

### For CNCF Sandbox submission preparation

1. **OPENSRM-CORE v2** — what's being submitted.
2. **OPENSRM-CORE v2 §14** — CNCF positioning rationale.
3. **OPENSRM-CORE v2 §2** — relationship to other standards.
4. **NTHLAYER-TELEMETRY-ENVELOPE v1 §8** — upstream contribution strategy.
5. The rest of OpenSRM core for substance.
6. **NthLayer OSS Delegation Strategy** — supporting research.

### For external contributors

1. **This index**.
2. **OPENSRM-CORE v2** — only if contributing to the specification itself.
3. Otherwise: the specific component spec they're contributing to.
4. **NTHLAYER-COMMON v1** — how the code is structured.
5. **NTHLAYER-TELEMETRY-ENVELOPE v1** — the wire format contract.

### For potential adopters evaluating NthLayer

1. **OPENSRM-CORE v2 §1** — what OpenSRM is.
2. **OPENSRM-CORE v2 §5** — judgment SLOs (the differentiating contribution).
3. **NTHLAYER-BENCH v2.1 §1–5** — what the operator experience looks like.
4. **NTHLAYER-SERVE-MODE v2.1 §1, §3** — what's involved in running it.
5. **NTHLAYER-COMMON v1 §12** — what dependencies are involved.

### For compliance/audit reviewers

1. **OPENSRM-RBAC-EXTENSION v2** — the authorisation model.
2. **OPENSRM-RBAC-EXTENSION v2 §9** — decision logs and audit trail.
3. **NTHLAYER-LEARN v1 §6** — Rekor anchoring for tamper evidence.
4. **NTHLAYER-TELEMETRY-ENVELOPE v1 §6** — decision log wire format and SIEM integration.
5. **NTHLAYER-SERVE-MODE v2.1 §9** — Rekor anchor storage.

---

## Specification vs implementation boundary

Critical distinction worth restating:

**Specification documents** describe what must be true:
- OPENSRM-CORE v2 — the OpenSRM specification
- OPENSRM-RBAC-EXTENSION v2 — extension to OpenSRM

These are deliberately tool-agnostic. Conformance does not require using any specific library. They're candidates for CNCF Sandbox submission.

**Implementation specifications** describe how the NthLayer reference implementation works:
- NTHLAYER-SERVE-MODE v2.1
- NTHLAYER-BENCH v2.1
- NTHLAYER-CORRELATE v1
- NTHLAYER-LEARN v1
- NTHLAYER-MEASURE v1
- NTHLAYER-COMMON v1
- NTHLAYER-TELEMETRY-ENVELOPE v1

These name specific libraries, specific OSS substrates, and specific architectural choices. They describe *one valid implementation* of OpenSRM, not the only one.

The distinction matters for several reasons:

- An alternative implementation (e.g., a Go-based implementation, or a hosted SaaS) could conform to OPENSRM-CORE and OPENSRM-RBAC-EXTENSION without using any of the NthLayer ecosystem code.
- When proposing OpenSRM to CNCF, only the specification documents are the proposal. The implementation is reference material.
- When writing articles or talks about OpenSRM as a standard, reference the specification. When talking about the NthLayer product, reference the implementation.

---

## Revision history

| Version | Date | Changes |
|---|---|---|
| 1 | 2026-04-19 | Initial index covering eight specs produced in four waves |
