# NthLayer Telemetry and Envelope Specification — v1-draft

**Status:** Draft for implementation
**Date:** 2026-04-19
**Scope:** NthLayer reference implementation; defines wire formats for the NthLayer ecosystem. Parts of this spec (specifically the OTel `gen_ai.decision.*` attributes) are candidates for upstream contribution to the OpenTelemetry GenAI Special Interest Group.

---

## 1. Purpose

Every component in the NthLayer ecosystem produces events and telemetry. Every component also consumes events from other components and from external systems. Wire-format consistency is load-bearing: a verdict written by nthlayer-authorise must be parseable by nthlayer-learn, nthlayer-measure, the Bench, and any external system consuming the audit trail. A misalignment anywhere produces silent data loss or misinterpretation.

This specification consolidates the wire formats referenced across the other NthLayer specs into a single authoritative document:

1. The **CloudEvents v1.0 envelope** used for all verdicts, assessments, and change events
2. The **OpenTelemetry GenAI semantic conventions** adopted for decision telemetry, including the shipped `gen_ai.evaluation.result` event and the proposed `gen_ai.decision.*` extension
3. The **PD-CEF alert schema** superset used by nthlayer-correlate and nthlayer-respond
4. The **decision log format** used by nthlayer-authorise, borrowing field vocabulary from OPA's schema
5. The **upstream contribution strategy** for moving NthLayer-proposed attributes into OTel semantic conventions

The goal is that Claude Code and any contributor implementing NthLayer components have a single reference for "what does this event look like on the wire" without cross-referencing five specs.

## 2. Design Principles

**Layered format.** CloudEvents envelope on the outside, OTel semantic conventions in the payload, NthLayer-specific attributes under a reserved namespace. Each layer owned by an existing standard where one exists; NthLayer's contributions clearly scoped.

**Namespace discipline.** NthLayer-specific attributes live under `nthlayer.*` with sub-namespaces by concern (`nthlayer.verdict.*`, `nthlayer.alert.*`, `nthlayer.authorisation.*`). This keeps them identifiable and prevents collisions with upstream attributes if or when they're standardised.

**Propose upstream where relevant.** Where NthLayer defines attributes that aren't organisation-specific (the `gen_ai.decision.*` set in particular), the intent is to propose these upstream to the OTel GenAI SIG rather than maintain them as permanent NthLayer extensions. The upstream path is documented explicitly (§8).

**SIEM-compatible by construction.** CloudEvents envelopes with OTel attributes map cleanly to standard log-shipping infrastructure. No bespoke transport or encoding is required for compliance audiences that need SIEM integration.

## 3. CloudEvents Envelope

### 3.1 Version

All NthLayer events use CloudEvents v1.0 (CNCF graduated, January 2024). The `specversion` field is always `"1.0"`.

### 3.2 Required attributes

Every NthLayer event populates all required CloudEvents attributes:

| Attribute | Type | Value pattern |
|---|---|---|
| `specversion` | string | `"1.0"` |
| `type` | string | `"io.nthlayer.<category>.<subtype>.v<n>"` (see §3.4) |
| `source` | URI-reference | `"urn:nthlayer:<component>:<deployment_id>"` |
| `id` | string | CID of the event content (IPLD CID, see nthlayer-learn §4.2) |
| `time` | RFC3339 timestamp | Creation time |

### 3.3 Optional attributes

Standard CloudEvents optional attributes are used where applicable:

| Attribute | Purpose |
|---|---|
| `datacontenttype` | Always `"application/json"` in NthLayer |
| `subject` | Service or resource the event is about (e.g., `"component:default/payment-service"`) |
| `traceparent` | W3C traceparent for distributed trace propagation |
| `tracestate` | W3C tracestate |

### 3.4 Type taxonomy

The `type` attribute follows `io.nthlayer.<category>.<subtype>.v<n>`:

| Category | Subtypes | Purpose |
|---|---|---|
| `verdict` | `action_request`, `approval`, `capability`, `denial`, `execution`, `operator_note`, `autonomy_change`, `quality_breach`, `topology_drift`, `contract_divergence`, `correlation_snapshot` | Decision or decision-adjacent records |
| `assessment` | `slo_status`, `judgment_slo_evaluation`, `burn_rate`, `drift_signal` | Continuous component outputs that are not decisions |
| `change` | `manifest_changed`, `change_freeze_declared`, `change_freeze_lifted` | Declarative-document lifecycle events |
| `audit` | `authorisation_decision` | Compliance-grade decision records (see §6) |
| `alert` | `raised`, `resolved`, `updated` | PD-CEF-compatible alert lifecycle (see §5) |

The version suffix (`.v1`, `.v2`) allows the schema to evolve without breaking consumers. Schema changes that add optional fields do not bump the version; changes that modify required fields or semantics do.

### 3.5 Source URN pattern

The `source` attribute uses a URN reflecting the component and deployment:

- `urn:nthlayer:observe:production-eu`
- `urn:nthlayer:authorise:production-eu`
- `urn:nthlayer:respond.triage-agent:production-eu`

For agents, the sub-component (agent type) is included after a dot.

### 3.6 Full example

A complete `execution` verdict:

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.verdict.execution.v1",
  "source": "urn:nthlayer:executor:production-eu",
  "id": "bafyreiabc123...",
  "time": "2026-04-19T09:32:15.423Z",
  "datacontenttype": "application/json",
  "subject": "component:default/payment-service",
  "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01",

  "data": {
    "gen_ai.system": "nthlayer-executor",
    "gen_ai.evaluation.name": "payments.rollback-deployment",
    "gen_ai.evaluation.score.value": 1.0,
    "gen_ai.evaluation.score.label": "success",
    "gen_ai.response.id": "bafyreiabc123...",

    "nthlayer.verdict.type": "execution",
    "nthlayer.verdict.parent_cids": ["bafyrei...cap", "bafyrei...approval"],
    "nthlayer.verdict.pipeline_latency_ms": 2347,
    "nthlayer.verdict.chain_depth": 4,

    "nthlayer.execution.capability_cid": "bafyrei...cap",
    "nthlayer.execution.binding": "kubernetes-rollout",
    "nthlayer.execution.target": "deployment/payment-service",
    "nthlayer.execution.outcome": "success",
    "nthlayer.execution.verification_passed": true,
    "nthlayer.execution.duration_ms": 847
  }
}
```

## 4. OpenTelemetry GenAI Attributes

### 4.1 Alignment principle

NthLayer adopts OTel GenAI semantic conventions wherever they fit. The `gen_ai.*` namespace on the payload is authoritative — nthlayer-specific attributes never shadow or rename `gen_ai.*` attributes that exist upstream.

### 4.2 Adopted from OTel semconv v1.39.0+

The following attributes and events are consumed and emitted as specified upstream:

**Base attributes (on traces and events):**

- `gen_ai.system` — the component or agent emitting the event
- `gen_ai.request.model` — LLM model identifier, when applicable
- `gen_ai.response.model` — actual model served
- `gen_ai.response.id` — model provider's response identifier
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `gen_ai.usage.cached_tokens` (Anthropic prompt caching)
- `gen_ai.usage.reasoning_tokens` (reasoning models)

**`gen_ai.evaluation.result` event (shipped in v1.39.0, August 2025):**

- `gen_ai.evaluation.name` — what was evaluated (typically the action or decision name)
- `gen_ai.evaluation.score.value` — numeric score (0.0-1.0 conventional)
- `gen_ai.evaluation.score.label` — categorical label ("success", "failure", "partial", etc.)
- `gen_ai.evaluation.explanation` — human-readable reasoning
- `gen_ai.response.id` — identifier of the response being evaluated

This event is used by nthlayer-measure for judgment-SLO outcome reporting. Its shape covers roughly 70% of what NthLayer needs for decision telemetry; the remaining 30% is the decision-specific namespace below.

### 4.3 Proposed `gen_ai.decision.*` (for upstream contribution)

The following attributes describe properties of decisions that the current OTel GenAI conventions do not cover. NthLayer emits these under `nthlayer.decision.*` pending upstream adoption, at which point the namespace migrates to `gen_ai.decision.*`. Consumers should treat both namespaces as equivalent during the migration window.

| Attribute | Type | Description |
|---|---|---|
| `nthlayer.decision.type` | string | `"triage" \| "investigate" \| "remediate" \| "approve" \| "classify" \| "route" \| "escalate"` |
| `nthlayer.decision.reversible` | bool | Whether this decision can be reversed cleanly |
| `nthlayer.decision.autonomous` | bool | Whether this decision executed without human approval |
| `nthlayer.decision.blast_radius` | string | `"ephemeral" \| "dev" \| "staging" \| "production"` |
| `nthlayer.decision.reversal_of` | string | CID of a decision this one reverses |
| `nthlayer.decision.approval_required` | string | `"none" \| "single-human" \| "dual-human" \| "emergency"` |
| `nthlayer.decision.approval_satisfied` | bool | Whether the required approval was recorded |
| `nthlayer.decision.confidence` | float | Producer's confidence, 0.0-1.0 |
| `nthlayer.decision.calibration_class` | string | Post-outcome classification: `"accurate" \| "overconfident" \| "underconfident"` |

These attributes were selected because they answer questions the existing `gen_ai.*` conventions cannot:

- *Was this reversible?* Critical for auditing autonomous systems
- *Did a human approve?* Critical for fiduciary compliance
- *What's the blast radius?* Critical for understanding actual risk exposure
- *How confident was the producer?* Critical for calibration analysis

See §8 for the upstream contribution path.

### 4.4 NthLayer-specific attributes (not upstream candidates)

Attributes specific to NthLayer's data model that are unlikely to generalise upstream:

**`nthlayer.verdict.*` (verdict metadata):**

- `nthlayer.verdict.type` — verdict type from §3.4
- `nthlayer.verdict.parent_cids` — array of parent CID strings
- `nthlayer.verdict.pipeline_latency_ms` — cumulative pipeline latency
- `nthlayer.verdict.chain_depth` — ancestor count
- `nthlayer.verdict.lineage_reasoning` — prose reasoning about relationships

**`nthlayer.snapshot.*` (correlation snapshots):**

- `nthlayer.snapshot.window_start` — session window start
- `nthlayer.snapshot.window_end` — session window end
- `nthlayer.snapshot.affected_services` — array of service refs
- `nthlayer.snapshot.blast_radius` — array of service refs (transitively affected)
- `nthlayer.snapshot.alert_count` — number of alerts in window
- `nthlayer.snapshot.summary` — natural-language summary
- `nthlayer.snapshot.correlations` — structured correlation findings

**`nthlayer.authorisation.*` (decision log specifics, see §6):**

- `nthlayer.authorisation.matched_rules` — array of policy rule references
- `nthlayer.authorisation.required_approvals` — required approval types
- `nthlayer.authorisation.deny_reasons` — reasons for denial, if denied
- `nthlayer.authorisation.bundle_revision` — policy bundle version

**`nthlayer.execution.*` (execution metadata):**

- `nthlayer.execution.capability_cid` — CID of the capability token consumed
- `nthlayer.execution.binding` — execution binding used (webhook, kubernetes, command)
- `nthlayer.execution.target` — target resource
- `nthlayer.execution.outcome` — success/failure/partial
- `nthlayer.execution.verification_passed` — post-execution verification result
- `nthlayer.execution.duration_ms` — execution wall time

**`nthlayer.drift.*` (topology drift):**

- `nthlayer.drift.type` — `"declared_not_observed" \| "observed_not_declared" \| "guarantee_mismatch"`
- `nthlayer.drift.caller` / `nthlayer.drift.callee` — the edge in question
- `nthlayer.drift.evidence_window` — observation window for the drift finding

**`nthlayer.divergence.*` (contract divergence):**

- `nthlayer.divergence.contract_ref` — contract identifier
- `nthlayer.divergence.promised_*` / `nthlayer.divergence.observed_*` — promised vs actual values
- `nthlayer.divergence.measurement_window`
- `nthlayer.divergence.dependent_services` — services exposed to this divergence

**`nthlayer.autonomy.*` (autonomy changes):**

- `nthlayer.autonomy.agent` — agent identifier
- `nthlayer.autonomy.previous_level` / `nthlayer.autonomy.new_level`
- `nthlayer.autonomy.direction` — `"reduced"` or `"elevated"`
- `nthlayer.autonomy.reason` — structured or prose reason
- `nthlayer.autonomy.automatic` — whether this was ratcheted down automatically or human-initiated
- `nthlayer.autonomy.breach_slo_cids` — SLOs whose breach triggered the change

**`nthlayer.breach.*` (SLO/quality breaches):**

- `nthlayer.breach.slo_cid` — the judgment SLO that breached
- `nthlayer.breach.service` — affected service
- `nthlayer.breach.slo_type` — reversal_rate, high_confidence_failure, etc.
- `nthlayer.breach.observed_value` / `nthlayer.breach.target`
- `nthlayer.breach.severity` — marginal/moderate/severe
- `nthlayer.breach.actions_triggered` — array of action names

**`nthlayer.evaluation.*` (SLO evaluation assessments):**

- `nthlayer.evaluation.slo_cid` — the SLO being evaluated
- `nthlayer.evaluation.service`
- `nthlayer.evaluation.type` — SLO type
- `nthlayer.evaluation.value` / `nthlayer.evaluation.target`
- `nthlayer.evaluation.status` — healthy/marginal/breach
- `nthlayer.evaluation.confidence_interval` — `[lower, upper]`
- `nthlayer.evaluation.sample_size`
- `nthlayer.evaluation.evaluator_degraded` — whether the evaluator itself is self-reporting as unreliable

## 5. PD-CEF Alert Schema Superset

All alerts entering nthlayer-correlate conform to a PD-CEF superset. This gives zero-translation compatibility with the dominant alert-tool ecosystem while adding NthLayer-specific context.

### 5.1 PD-CEF core fields

These fields are as defined by PagerDuty Common Event Format:

| Field | Type | Description |
|---|---|---|
| `summary` | string | Short human-readable description |
| `source` | string | Where the alert came from (e.g., `"prometheus"`, `"grafana"`) |
| `severity` | string | `"info" \| "warning" \| "error" \| "critical"` |
| `component` | string | The affected component or service |
| `group` | string | Logical grouping (e.g., team, domain) |
| `class` | string | Alert class (e.g., `"latency"`, `"availability"`, `"saturation"`) |
| `custom_details` | object | Provider-specific additional fields |
| `dedup_key` | string | Deduplication key; identical keys within the dedup window merge |
| `timestamp` | RFC3339 | When the alert was raised |

### 5.2 NthLayer extensions

NthLayer-specific fields under `nthlayer.alert.*`:

| Field | Type | Description |
|---|---|---|
| `nthlayer.alert.service_cid` | CID | Content-addressed ref to the service manifest |
| `nthlayer.alert.slo_cid` | CID | The SLO this alert relates to |
| `nthlayer.alert.burn_rate` | float | Current burn rate if relevant |
| `nthlayer.alert.contract_ref` | string | Contract identifier if relevant |
| `nthlayer.alert.priority` | string | `"P0" \| "P1" \| "P2" \| "P3"` |

### 5.3 CloudEvents wrapping

An alert is a CloudEvent with:

- `type: io.nthlayer.alert.raised.v1` (or `.resolved.v1`, `.updated.v1`)
- `source`: the producer of the alert
- `data`: the PD-CEF-superset body

Example:

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.alert.raised.v1",
  "source": "urn:nthlayer:observe:production-eu",
  "id": "bafyrei...alert",
  "time": "2026-04-19T09:32:15Z",
  "data": {
    "summary": "payment-service error rate above threshold",
    "source": "prometheus",
    "severity": "critical",
    "component": "payment-service",
    "group": "payments",
    "class": "latency",
    "custom_details": { "p99_latency_ms": 2100 },
    "dedup_key": "payment-service:error-rate",
    "timestamp": "2026-04-19T09:32:15Z",
    "nthlayer.alert.service_cid": "bafyrei...svc",
    "nthlayer.alert.slo_cid": "bafyrei...slo",
    "nthlayer.alert.burn_rate": 47.2,
    "nthlayer.alert.priority": "P1"
  }
}
```

### 5.4 Ingest from external producers

External alert systems (Prometheus Alertmanager, Grafana, external SIEMs) typically do not emit CloudEvents-wrapped PD-CEF. nthlayer-correlate provides a webhook ingest endpoint that accepts raw PD-CEF payloads and wraps them in the CloudEvents envelope at ingest time. The source URN in the wrapper identifies the external system.

## 6. Decision Log Format

nthlayer-authorise emits a decision log record for every authorisation decision. This is separate from the capability or denial verdict — the verdict records what was decided; the decision log records why.

### 6.1 Field vocabulary

Borrowing from OPA's decision-log schema (which is mature and SIEM-friendly):

| Field | Type | Description |
|---|---|---|
| `decision_id` | ULID | Unique decision identifier |
| `timestamp` | RFC3339 | When the decision was made |
| `principal` | object | `{kind, id, attributes}` from RBAC §3 |
| `action` | string | `{service}.{action_id}` from RBAC §4 |
| `request_parameters_hash` | string | `"sha256:..."` hash of the request parameters |
| `decision` | string | `"allow" \| "deny" \| "pending_approval"` |
| `matched_rules` | array of strings | Policy rules that matched |
| `required_approvals` | array of strings | Approval types required |
| `approvals_received` | array of CIDs | Approval verdicts consulted |
| `deny_reasons` | array of strings | If denied |
| `evaluation_duration_ms` | integer | Policy evaluation wall time |
| `bundle_revision` | string | Policy bundle version |
| `evaluator` | string | `"regorus" \| "regopy"` — which evaluator produced this decision |
| `labels` | object | Deployment labels (environment, region, etc.) |

### 6.2 Wire format

Wrapped in CloudEvents:

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.audit.authorisation_decision.v1",
  "source": "urn:nthlayer:authorise:production-eu",
  "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "time": "2026-04-19T09:32:15Z",
  "subject": "component:default/payment-service",
  "traceparent": "00-...",
  "data": {
    "decision_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    "timestamp": "2026-04-19T09:32:15Z",
    "principal": {
      "kind": "agent",
      "id": "triage-agent-01",
      "attributes": {
        "agent.type": "triage",
        "agent.version": "1.4.2",
        "agent.autonomy_level": "limited-autonomous"
      }
    },
    "action": "payments.rollback-deployment",
    "request_parameters_hash": "sha256:abcd1234...",
    "decision": "pending_approval",
    "matched_rules": ["production-tightening.rules[0]"],
    "required_approvals": ["dual-human"],
    "approvals_received": [],
    "deny_reasons": [],
    "evaluation_duration_ms": 12,
    "bundle_revision": "acme-policies-v2.3.1",
    "evaluator": "regorus",
    "labels": {
      "environment": "production",
      "nthlayer_instance": "eu-west"
    }
  }
}
```

### 6.3 SIEM integration

Decision logs can be shipped to any standard log destination via the OTel Collector. The CloudEvents + structured-data shape maps cleanly to Elasticsearch, Splunk, Datadog Logs, and other destinations. No bespoke parsing required.

### 6.4 Correlation with verdicts

The decision log's `decision_id` appears in the corresponding capability or denial verdict under `nthlayer.authorisation.decision_id`. This lets an auditor start from a decision log entry and find the downstream verdict chain (or start from a verdict and find the governing decision log).

## 7. Change Events

Declarative-document lifecycle events (OpenSRM manifest changes, ChangeFreeze declarations) use CloudEvents with OpenSRM-specific payload.

### 7.1 Manifest changed

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.change.manifest_changed.v1",
  "source": "urn:opensrm:catalogue:production",
  "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "time": "2026-04-19T09:32:15Z",
  "subject": "component:default/payment-service",
  "data": {
    "manifest_cid_before": "bafyrei...old",
    "manifest_cid_after": "bafyrei...new",
    "change_type": "slo_modified",
    "changed_by": "user:default/jane.doe",
    "commit_ref": "git:abc123..."
  }
}
```

### 7.2 ChangeFreeze lifecycle

ChangeFreeze declarations and lifts emit events:

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.change.change_freeze_declared.v1",
  "source": "urn:nthlayer:respond:production-eu",
  "id": "bafyrei...freeze",
  "time": "2026-04-19T09:32:15Z",
  "data": {
    "freeze_name": "incident-INC-2026-04-01847",
    "declared_by": "nthlayer-respond",
    "scope": {
      "environments": ["production"],
      "services": ["payment-service", "checkout-service"]
    },
    "active_from": "2026-04-19T09:32:15Z",
    "active_until": "2026-04-19T10:32:15Z",
    "exceptions": [
      {"action_ids": ["rollback-deploy", "scale-up"]}
    ],
    "reason": "Incident on payment-service"
  }
}
```

## 8. Upstream Contribution Strategy

### 8.1 What to propose upstream

The `gen_ai.decision.*` attribute set in §4.3 is the primary upstream candidate. These attributes describe properties of any AI-system decision and generalise beyond NthLayer's specific architecture.

Rationale for upstream proposal rather than permanent NthLayer ownership:

- Decision properties (reversibility, autonomy, blast radius, approval chain) are not NthLayer-specific; any AI system making consequential decisions needs them
- Having them in upstream semconv means interoperability with observability platforms building GenAI features
- Position NthLayer as a contributor to the standard rather than a divergent alternative
- Lower long-term maintenance — upstream owns the schema, NthLayer just emits

### 8.2 Contribution process

The OpenTelemetry GenAI SIG meets weekly and accepts attribute proposals through the following path:

1. Open an issue in `open-telemetry/semantic-conventions` describing the proposed attributes and the use cases they cover
2. Draft a PR with YAML definitions in the `model/gen-ai/` directory
3. Present the proposal at a GenAI SIG meeting (sign up via the SIG's public calendar)
4. Iterate based on SIG feedback (typically 2-4 weeks)
5. Merge when approved; the attributes ship in the next semconv release

Relevant prior art that informs the pitch:

- Issue #2665 (`gen_ai.task.*` feedback attributes) — similar shape
- Issue #2468 (audit-log semantic conventions) — overlapping concern
- The `gen_ai.evaluation.result` event that shipped in v1.39.0 — established precedent for decision-adjacent telemetry

### 8.3 NthLayer migration plan

While `gen_ai.decision.*` is not yet upstream, NthLayer emits these attributes under `nthlayer.decision.*`. On upstream acceptance:

1. Add dual-emission: the same values emitted under both `nthlayer.decision.*` and `gen_ai.decision.*`
2. Consumers migrate to reading `gen_ai.decision.*`
3. After a deprecation window (two minor versions), stop emitting `nthlayer.decision.*`

Dual-emission during migration prevents breaking consumers that haven't yet updated.

### 8.4 Attributes that stay NthLayer-owned

Not every NthLayer-specific attribute is an upstream candidate. These are explicitly NthLayer-permanent:

- `nthlayer.verdict.*` — specific to NthLayer's hash-chained verdict model
- `nthlayer.snapshot.*` — specific to nthlayer-correlate's windowed-correlation output
- `nthlayer.authorisation.*` — specific to NthLayer's authorisation model (Biscuit, Rego, etc.)
- `nthlayer.execution.*` — specific to NthLayer's executor model
- `nthlayer.drift.*` / `nthlayer.divergence.*` — specific to OpenSRM's declared-vs-observed topology reasoning
- `nthlayer.autonomy.*` — specific to NthLayer's autonomy ratchet model
- `nthlayer.breach.*` / `nthlayer.evaluation.*` — specific to NthLayer's judgment SLO evaluation

These are described as conventions within this spec but are not proposed upstream because they bake in NthLayer's architectural choices.

## 9. Validation and Conformance

### 9.1 Schema enforcement

Every component writing events via nthlayer-common passes through a validation layer that enforces:

- CloudEvents required attributes are present and well-formed
- The `type` attribute matches a known pattern from §3.4
- `gen_ai.*` attributes, where present, conform to upstream OTel semconv
- `nthlayer.*` attributes, where present, conform to this spec

Invalid events fail at write time rather than corrupting the store.

### 9.2 Schema versioning

Events declare their version in the `type` attribute (`.v1`, `.v2`). Consumers switch parsing based on the version. Within a major version, fields may be added but not removed or semantically changed.

### 9.3 Forward compatibility

Consumers should ignore unknown `nthlayer.*` attributes they don't recognise (forward compatibility). Producers may emit attributes not yet in this spec as long as they're under a reserved namespace and documented elsewhere.

## 10. Examples

### 10.1 A complete authorisation flow

Seven events that constitute a full action lifecycle, with their types and key attributes:

**1. `action_request` verdict.** The agent proposes an action.
```
type: io.nthlayer.verdict.action_request.v1
source: urn:nthlayer:respond.triage-agent:production-eu
data:
  nthlayer.verdict.type: action_request
  nthlayer.verdict.parent_cids: [bafyrei...snapshot]
  nthlayer.decision.type: remediate
  nthlayer.decision.autonomous: false
  nthlayer.decision.blast_radius: production
  nthlayer.decision.confidence: 0.87
  gen_ai.system: triage-agent
```

**2. `authorisation_decision` log.** authorise evaluates policy.
```
type: io.nthlayer.audit.authorisation_decision.v1
source: urn:nthlayer:authorise:production-eu
data:
  decision: pending_approval
  matched_rules: [production-tightening.rules[0]]
  required_approvals: [dual-human]
  evaluator: regorus
```

**3. First `approval` verdict.** An operator approves in the Bench.
```
type: io.nthlayer.verdict.approval.v1
source: urn:nthlayer:bench:production-eu
data:
  nthlayer.verdict.parent_cids: [bafyrei...action_request]
  nthlayer.decision.type: approve
```

**4. Second `approval` verdict.** Second operator approves.
```
(as above)
```

**5. `capability` verdict.** authorise issues a Biscuit token.
```
type: io.nthlayer.verdict.capability.v1
source: urn:nthlayer:authorise:production-eu
data:
  nthlayer.verdict.parent_cids: [bafyrei...approval1, bafyrei...approval2]
  nthlayer.authorisation.decision_id: 01ARZ3NDEK...
```

**6. `execution` verdict.** executor runs the action.
```
type: io.nthlayer.verdict.execution.v1
source: urn:nthlayer:executor:production-eu
data:
  nthlayer.verdict.parent_cids: [bafyrei...cap]
  nthlayer.execution.binding: kubernetes-rollout
  nthlayer.execution.outcome: success
  gen_ai.evaluation.score.value: 1.0
  gen_ai.evaluation.score.label: success
```

**7. Retrospective `outcome` update.** learn resolves the outcome.
```
(stored in outcome_resolutions table; emitted as assessment if downstream signals arrive)
```

All seven events share `traceparent` so the whole flow is reconstructable from trace telemetry alone.

### 10.2 A correlation snapshot

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.verdict.correlation_snapshot.v1",
  "source": "urn:nthlayer:correlate:production-eu",
  "id": "bafyrei...snap",
  "time": "2026-04-19T09:33:00Z",
  "data": {
    "nthlayer.verdict.type": "correlation_snapshot",
    "nthlayer.snapshot.window_start": "2026-04-19T09:32:00Z",
    "nthlayer.snapshot.window_end": "2026-04-19T09:33:00Z",
    "nthlayer.snapshot.affected_services": ["payment-service", "checkout-service"],
    "nthlayer.snapshot.blast_radius": ["payment-service", "checkout-service", "notification-service"],
    "nthlayer.snapshot.alert_count": 7,
    "nthlayer.snapshot.summary": "Payment-service error rate rose to 4.7% starting 09:31:47, correlating with deployment v2.47.3. Checkout-service is reporting increased downstream errors. Blast radius includes notification-service via the payment-confirmation hook.",
    "nthlayer.snapshot.correlations": [
      {"type": "temporal", "evidence": [...]},
      {"type": "topological", "cause_candidate": "payment-service"}
    ]
  }
}
```

## 11. Consumer Guidance

### 11.1 For component authors

- Use nthlayer-common's event-construction helpers; don't hand-roll
- Set `traceparent` from the current OTel context — this is usually automatic
- Populate `nthlayer.verdict.parent_cids` with the CIDs that informed this verdict
- Don't invent new `nthlayer.*` sub-namespaces without proposing them in this spec first

### 11.2 For downstream consumers (including external SIEMs)

- Match on `type` prefix (`io.nthlayer.verdict.`, `io.nthlayer.assessment.`, etc.) to route
- `source` URNs are unique per component per deployment; deduplicate on `id`
- Unknown attributes under `nthlayer.*` should be preserved but not interpreted
- `gen_ai.*` attributes conform to upstream semconv; use standard GenAI observability tools to interpret

### 11.3 For the OTel GenAI SIG (when the upstream proposal lands)

- The `nthlayer.decision.*` set in §4.3 is the proposed contribution
- Dual-emission during migration window is specified in §8.3
- NthLayer-specific attributes (see §8.4) are not proposed upstream

## 12. Future Work

**Binary payload formats.** CloudEvents supports binary content types (e.g., Protocol Buffers); for high-volume deployments this reduces wire overhead. Not v1.

**Schema registry.** Publishing the JSON Schemas for each event type to a public registry would enable better tooling for consumers. Not v1, but straightforward to add.

**Additional upstream proposals.** Beyond `gen_ai.decision.*`, other candidates include agent-state-observability attributes and operational-change-event conventions. Scope for future OTel SIG engagement.

## 13. References

- CloudEvents v1.0: https://github.com/cloudevents/spec
- OpenTelemetry GenAI semconv: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry semconv v1.39.0 release notes: https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.39.0
- PD-CEF: https://support.pagerduty.com/docs/pd-cef
- OPA decision log schema: https://www.openpolicyagent.org/docs/management-decision-logs
- OTel GenAI SIG: https://github.com/open-telemetry/community/tree/main/projects/gen-ai
- nthlayer-learn spec (CID generation)
- RBAC extension v1.1 (authorisation flow)
- nthlayer-correlate v1 (alert schema, correlation snapshots)
- OpenSRM core v2 (change events)

## 14. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1-draft | 2026-04-19 | Initial consolidation of wire formats across the NthLayer ecosystem |
