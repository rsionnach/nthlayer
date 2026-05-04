# NthLayer: Missing Capabilities Implementation Spec (v2)

**Context:** Five capabilities identified as gaps through competitive research across the observability, AI governance, and reliability landscape (March 2026). Ordered by priority: business outcome binding, learn-to-spec feedback loop, verdict chain correlation, human override ingestion, and pre-execution integration protocol.

**Architecture principles:**

1. **External control plane.** NthLayer sits outside the agent. All data arrives via ingestion (OTel, Prometheus, adapters), not via SDK wrappers inside agent code.
2. **CLI-first, server-optional.** The NthLayer static layer (spec validation, generate, learn recommendations) is a deterministic CLI tool with no long-running processes. The agent layer (measure, correlate, respond) consumes telemetry streams. New capabilities must not introduce mandatory server processes into the core. Any inbound HTTP endpoints are implemented as optional adapter sidecars, not core components.
3. **OTel as the primary data path.** All telemetry (including overrides) flows through OTel as the canonical path. Webhook adapters translate non-OTel sources into OTel events. nthlayer-measure consumes from one source (OTel/Prometheus), not multiple.
4. **OpenSRM is backend-agnostic.** The spec must not reference specific backends (Prometheus metric names, Grafana panel types). It declares intent; nthlayer-generate maps intent to backend-specific implementations.

**Spec format:** OpenSRM is the declarative specification (YAML). NthLayer components (generate, measure, correlate, respond, learn) consume and produce against the spec. Changes below affect both the OpenSRM schema and the NthLayer component implementations.

---

## 1. Business Outcome Binding

### Problem

NthLayer can report that fraud-detection's reversal rate climbed to 3.1% and 340 decisions were made at degraded quality. It cannot report that those 340 decisions cost the business €47,000 in incorrectly approved transactions. Without financial impact, VP Engineering and investor audiences receive SLO percentages when they think in euros. Gartner's prediction that 40%+ of agentic AI projects will be cancelled cites "unclear business value" as a primary driver. Business outcome binding closes this gap.

### OpenSRM Schema Changes

Add an optional `outcomes` block to the spec, sibling to `slos` and `contract`. This block declares the business value of decisions made by this service.

```yaml
spec:
  type: ai-gate
  
  outcomes:
    decision_value:
      correct: 138.50
      currency: EUR
      
      false_positive:
        cost: 0
        category: friction
      false_negative:
        cost: 2400
        category: financial_loss
      
    # Revenue attribution (backend-agnostic: declares the signal name,
    # not a Prometheus metric. nthlayer-generate maps this to the
    # appropriate backend query for the configured provider.)
    revenue:
      attribution: direct
      signal: approved_transaction_value
      
    # Fallback volume estimate. Used ONLY when real-time decision volume
    # metrics are unavailable (i.e. the service is not yet instrumented
    # with OTel decision events). When real-time metrics exist, they
    # take precedence unconditionally.
    volume:
      estimated_daily_decisions: 12000
      peak_multiplier: 2.3
```

The `outcomes` block is optional. Services without it continue to report in SLO percentages. Services with it get financial impact calculations in nthlayer-learn retrospectives and nthlayer-correlate blast radius assessments.

### Schema Definition

```json
{
  "Outcomes": {
    "type": "object",
    "description": "Business value mapping for AI decisions",
    "properties": {
      "decision_value": {
        "type": "object",
        "required": ["correct", "currency"],
        "properties": {
          "correct": {
            "type": "number",
            "description": "Average value of a correct decision in the declared currency"
          },
          "currency": {
            "type": "string",
            "pattern": "^[A-Z]{3}$",
            "description": "ISO 4217 currency code"
          },
          "false_positive": { "$ref": "#/definitions/FailureCost" },
          "false_negative": { "$ref": "#/definitions/FailureCost" }
        }
      },
      "revenue": {
        "type": "object",
        "properties": {
          "attribution": {
            "type": "string",
            "enum": ["direct", "indirect", "supporting"]
          },
          "signal": {
            "type": "string",
            "description": "Logical signal name for revenue attribution. nthlayer-generate maps this to the configured backend (e.g. Prometheus metric, OTel attribute)."
          }
        }
      },
      "volume": {
        "type": "object",
        "properties": {
          "estimated_daily_decisions": {
            "type": "integer",
            "description": "Fallback estimate. Used only when real-time decision volume metrics are unavailable."
          },
          "peak_multiplier": { "type": "number", "default": 1.0 }
        }
      }
    },
    "additionalProperties": false
  },
  "FailureCost": {
    "type": "object",
    "properties": {
      "cost": { "type": "number", "minimum": 0, "description": "Cost per failure in declared currency" },
      "category": {
        "type": "string",
        "enum": ["financial_loss", "friction", "compliance", "reputational", "operational"],
        "description": "Classification of the failure impact"
      }
    }
  }
}
```

### NthLayer Component Changes

**nthlayer-learn:** When producing an incident retrospective, if any affected service has an `outcomes` block:
- Determine decision volume during the incident window: prefer real-time metrics (`gen_ai_decision_total`), fall back to `estimated_daily_decisions` from spec, prorated to the incident duration
- Calculate: `impacted_decisions × failure_cost_per_decision = total_financial_impact`
- Include in the retrospective: `financial_impact: { estimated: 47200, currency: EUR, decisions_affected: 340, failure_mode: false_negative, volume_source: "metric" | "spec_estimate" }`

**nthlayer-correlate:** When computing blast radius, if affected services have `outcomes` blocks:
- Sum the financial exposure across all affected services
- Include in the correlation output: `blast_radius_financial: { total_exposure: 127400, currency: EUR, services_with_impact: 3 }`

**nthlayer-generate:** When generating dashboards for services with `outcomes` blocks:
- Map `revenue.signal` to the configured backend (e.g. Prometheus metric name via the generate provider config)
- Add a panel showing rolling financial impact: `reversal_rate × volume × false_negative_cost`
- Add a panel showing cumulative error budget in currency terms

### Validation Rules

- `currency` must be a valid ISO 4217 code
- `false_positive.cost` and `false_negative.cost` must be >= 0
- If `outcomes` is declared, `decision_value.correct` and `decision_value.currency` are required
- `revenue.signal` must be a valid identifier (alphanumeric + underscores, no spaces)

### Test Scenarios

1. Incident retrospective with outcomes declared and real-time metrics available: verify financial impact uses metric-derived volume, `volume_source: "metric"`
2. Incident retrospective with outcomes declared but no real-time metrics: verify fallback to `estimated_daily_decisions`, `volume_source: "spec_estimate"`
3. Incident retrospective without outcomes: verify no financial fields, no errors
4. Blast radius with mixed services (some with outcomes, some without): verify partial financial calculation
5. Dashboard generation with outcomes: verify `revenue.signal` is mapped through the provider config, not used as a literal metric name
6. Currency validation: verify rejection of invalid currency codes

---

## 2. Learn → Spec Feedback Loop

### Problem

The closed loop (spec → generate → measure → correlate → respond → learn → back to spec) is NthLayer's most powerful positioning claim. Currently the "back to spec" arrow is aspirational. nthlayer-learn produces a retrospective document. A human reads it and might manually update the YAML. That is not a loop, it is a report. The loop closes when nthlayer-learn produces a draft spec change that a human reviews and merges.

### Design

nthlayer-learn produces two outputs from each closed incident:

1. **Retrospective** (existing): human-readable incident summary with timeline, root cause, blast radius, metrics, financial impact
2. **Spec recommendation** (new): a machine-readable set of proposed changes to the OpenSRM manifests of affected services, formatted as a diff or patch

### Spec Recommendation Format

```yaml
apiVersion: opensrm.io/v1
kind: SpecRecommendation
metadata:
  incident: INC-4821
  generated_by: nthlayer-learn
  generated_at: "2026-03-24T14:23:00Z"
  confidence: 0.82
  requires_human_review: true

recommendations:
  - service: fraud-detection
    type: tighten_slo
    field: spec.slos.judgment.reversal_rate.target
    current_value: 0.015
    proposed_value: 0.010
    rationale: >
      INC-4821 showed reversal rate of 3.1% went undetected for 8 minutes.
      Tightening target from 1.5% to 1.0% would have triggered alerting
      4 minutes earlier based on error budget burn rate analysis.
    financial_impact: >
      Earlier detection would have reduced decisions at degraded quality
      from 340 to ~180, saving approximately €23,400 based on the
      declared false_negative cost of €2,400.
    evidence:
      - incident: INC-4821
        metric: reversal_rate_during_incident
        value: 0.031

  - service: fraud-detection
    type: add_deploy_gate
    field: spec.slos.judgment.deploy_gate
    current_value: null
    proposed_value:
      enabled: true
      block_on: reversal_rate
      threshold: 0.02
      evaluation_window: 15m
    rationale: >
      Model v2.3 would have been caught in canary if a judgment SLO
      gate had been present in the deploy pipeline.
    financial_impact: >
      Would have prevented the entire incident. Estimated saving: €47,200
      based on 340 false_negative decisions at €2,400 each (from outcomes
      declaration on fraud-detection).

  - service: config-service
    type: add_resource_limit
    field: spec.instrumentation.resource_limits
    current_value: null
    proposed_value:
      memory_warning: 80%
      memory_critical: 90%
    rationale: >
      INC-4822 was caused by OOM after config change increased cache TTL.
      Adding memory limit thresholds to the spec enables earlier detection.
```

### Recommendation Types

Well-known types (implemented by the recommendation engine):
- `tighten_slo`: propose a tighter SLO target based on incident timing analysis
- `add_deploy_gate`: propose a new deploy gate based on the signal that would have caught the issue pre-production
- `add_dependency`: propose adding an undiscovered dependency to the spec
- `add_resource_limit`: propose infrastructure thresholds
- `update_runbook`: propose runbook changes based on what actually worked during remediation

Custom types (extensible without schema changes):
- `type` field accepts any string. Well-known types get dedicated recommendation engine logic. Unknown types are treated as generic recommendations with `rationale` and `proposed_value` only. This allows the recommendation engine to grow without requiring OpenSRM schema changes for every new recommendation category.

### Implementation

**nthlayer-learn:**
- After producing the retrospective, analyse the incident data to generate recommendations
- Each recommendation includes `confidence` (0-1), `rationale` (human-readable), `evidence` (links to incident data), and optionally `financial_impact` (derived from the service's `outcomes` block if declared, cross-referencing capability 1)
- All recommendations have `requires_human_review: true`. This is hardcoded. NthLayer does not auto-modify specs.

**CLI integration:**
```bash
# Generate recommendations from a closed incident
nthlayer learn --incident INC-4821 --output recommendations

# Apply recommendations as a git diff against the spec repo
nthlayer learn --incident INC-4821 --apply-to /path/to/specs/ --format diff

# Interactive review mode (walk through each, accept/reject/modify)
nthlayer learn --incident INC-4821 --apply-to /path/to/specs/ --interactive

# Create a branch and PR with all accepted recommendations
nthlayer learn --incident INC-4821 --apply-to /path/to/specs/ --pr
# Creates branch: nthlayer/INC-4821-recommendations
# Commit message: "nthlayer-learn: spec recommendations from INC-4821"
# PR body: retrospective summary + per-recommendation rationale + financial impact
```

### Validation Rules

- Recommendations must reference a closed incident
- `proposed_value` must pass OpenSRM schema validation (the resulting spec would be valid)
- `confidence` must be between 0 and 1
- `requires_human_review` cannot be set to false programmatically
- `financial_impact` is included automatically when the affected service has an `outcomes` block; omitted otherwise

### Test Scenarios

1. Incident with SLO breach on a service with `outcomes`: verify `tighten_slo` recommendation includes `financial_impact` with currency figures
2. Incident with SLO breach on a service without `outcomes`: verify recommendation is produced without `financial_impact` field
3. Incident caused by deploy: verify `add_deploy_gate` recommendation is generated
4. Incident with undeclared dependency discovered during correlation: verify `add_dependency` recommendation
5. Custom recommendation type (e.g. `type: add_canary_policy`): verify it passes validation with `rationale` and `proposed_value`
6. Apply recommendations to a spec repo: verify the resulting YAML is valid OpenSRM
7. Interactive mode: verify accept/reject/modify flow
8. PR mode: verify branch creation, commit message, PR body includes financial impact where available

---

## 3. Verdict Chain Correlation

### Problem

The verdict data model already captures decision lineage via `lineage.context` (prior verdicts) and `lineage.children` (subsequent verdicts). nthlayer-correlate currently walks the service dependency graph from OpenSRM specs. It does not walk the verdict chain. When Agent B makes bad decisions because Agent A's upstream output degraded, nthlayer-correlate sees Agent B's reversal rate climbing but cannot identify Agent A as the decision-quality root cause.

### Design

nthlayer-correlate gains a second correlation path: verdict chain traversal, complementing service dependency traversal. During incident correlation, both paths run in parallel and their findings are merged.

### Performance Requirements

Verdict chain traversal must operate within strict bounds:
- **Time budget:** Verdict chain correlation must complete within 5 seconds for up to 10,000 verdicts in the incident window
- **Indexing requirements:** The verdict store must maintain indices on `lineage.context` (for reverse lookups) and on `timestamp` + `service` (for time-windowed queries). If the verdict store is backed by a database, these indices are mandatory.
- **Caching:** Upstream quality baselines (pre-incident confidence/score averages per service) should be cached and refreshed on a configurable interval (default: 5 minutes), not recomputed on every correlation run
- **Early termination:** If step 4 (group by upstream source) produces no upstream with > 10% representation among reversed verdicts, skip the remaining steps and return null for the verdict chain path

### Configuration

```yaml
# nthlayer-correlate config
verdict_chain:
  enabled: true
  max_depth: 2                    # Default 2, configurable for deeper multi-agent workflows
  confidence_decay_per_level: 0.3 # Reduce confidence by 30% per additional depth level
  min_upstream_representation: 0.1 # Skip upstream sources with < 10% of reversed verdicts
  max_verdicts_per_query: 10000   # Safety limit on verdict window query
  baseline_cache_ttl: 300         # Seconds between baseline refreshes
```

### Implementation

**nthlayer-correlate changes:**

When a judgment SLO breach is detected on a service:

1. **Service dependency path** (existing): walk the OpenSRM dependency graph to find infrastructure root causes
2. **Verdict chain path** (new):
   - Query verdicts for the breaching service within the incident window (capped at `max_verdicts_per_query`)
   - Filter to reversed/overridden verdicts
   - Extract `lineage.context` references
   - Group by upstream source service
   - Apply `min_upstream_representation` threshold (early termination if no upstream qualifies)
   - For each qualifying upstream source: compare current quality metrics to cached baseline
   - If degradation detected, flag as verdict chain root cause
   - If `max_depth` > 1, recurse upstream (applying `confidence_decay_per_level`)

The correlation output includes both paths:

```yaml
correlation:
  incident: INC-4823
  
  service_dependency_path:
    root_cause: null
    
  verdict_chain_path:
    root_cause: agent-a
    chain_depth: 1
    confidence: 0.78    # Base confidence, after decay if depth > 1
    evidence:
      - downstream_service: agent-b
        downstream_reversal_rate: 0.047
        upstream_service: agent-a
        upstream_confidence_shift: -0.15
        upstream_score_degradation: "0.87 → 0.71"
        upstream_representation: 0.83   # 83% of reversed verdicts reference agent-a
        sample_verdicts:
          - downstream: vrd_9d3f4e
            upstream_context: vrd_7a1b2c
    assessment: >
      Agent B's judgment quality degradation correlates with declining
      output quality from Agent A. 83% of Agent B's recent reversed
      verdicts reference Agent A verdicts with confidence below 0.75.
```

### OpenSRM Schema Changes

None. The verdict lineage model already exists. This is purely a nthlayer-correlate implementation change.

### Test Scenarios

1. Agent B quality degrades, Agent A quality also degraded: verify verdict chain identifies Agent A
2. Agent B quality degrades, Agent A quality is fine: verify verdict chain path returns null
3. Three-deep chain (C → B → A) with `max_depth: 3`: verify traversal reaches Agent A with confidence decay applied (e.g. 0.78 × 0.7 × 0.7 = 0.38)
4. Mixed incident: infrastructure issue AND verdict chain degradation from a different upstream: verify both paths return independent root causes
5. Service with no verdict lineage (traditional service): verify verdict chain path is skipped gracefully
6. Performance: 10,000 verdicts in window, verify correlation completes within 5 seconds
7. Early termination: no upstream exceeds 10% representation, verify fast null return
8. `max_depth: 1` configured: verify no recursion beyond direct upstream

---

## 4. Human Override Ingestion

### Problem

The Dynatrace 2026 survey shows 69% of AI decisions are currently human-verified. Every human override is a data point for reversal rate calculation. These overrides happen in diverse systems: Slack threads, ticketing tools, custom review UIs, email approvals, CRM workflows. nthlayer-measure needs a standardised ingestion path so judgment SLOs can be computed from real override data regardless of where the override originates.

### Design Principle

**OTel is the primary data path.** Override events are modelled as OTel events with `gen_ai.override.*` attributes. The webhook endpoint and adapters are translation layers that convert non-OTel override sources into OTel events and emit them to the configured OTel collector. nthlayer-measure continues consuming from one source (OTel/Prometheus), not multiple. This preserves the existing architecture.

### Override Event Schema (OTel Canonical Form)

```
Event name: gen_ai.override

Attributes:
  gen_ai.override.decision_id    (string, required)  - The verdict ID being overridden
  gen_ai.override.service        (string, required)  - The service/agent that made the original decision
  gen_ai.override.original_action (string)           - What the agent decided
  gen_ai.override.corrected_action (string, required) - What the human corrected it to
  gen_ai.override.reviewer       (string, required)  - Identifier for the human (hashed by default, see Privacy)
  gen_ai.override.reason         (string)            - Human-provided reason
  gen_ai.override.confidence_at_decision (float)     - Agent's confidence at decision time
  gen_ai.override.source_system  (string)            - Where the override originated
```

This maps directly to the existing NthLayer verdict schema: `outcome.status: overridden`, `outcome.override.by`, `outcome.override.reason`, `outcome.override.corrected_action`.

### Override Adapter (Optional Sidecar)

For organisations where overrides originate from systems that cannot emit OTel natively (Slack, Jira, email), NthLayer provides an optional **override adapter** — a lightweight sidecar process that accepts override events via HTTP and translates them to OTel events emitted to the configured collector.

**This is not a core nthlayer-measure component.** It is a standalone adapter (`nthlayer-override-adapter`) that can be deployed independently. nthlayer-measure never exposes HTTP endpoints directly.

**HTTP interface (on the adapter):**

```
POST /api/v1/overrides
Content-Type: application/json

{
  "decision_id": "vrd_8f2e1a",
  "service": "fraud-detection",
  "original_action": "approve",
  "corrected_action": "escalate_to_review",
  "reviewer": "analyst-047",
  "reason": "Model regression - underwriting-v3 miscalibrated",
  "confidence_at_decision": 0.71,
  "timestamp": "2026-03-24T14:23:00Z",
  "source_system": "internal-review-ui"
}
```

Response: `201 Created` with `{ "override_id": "ovr_abc123", "emitted_to_otel": true }`

**Batch endpoint:**
```
POST /api/v1/overrides/batch
Content-Type: application/json

{
  "overrides": [ ... array of override events ... ]
}
```

Ordering: overrides within a batch are processed in array order. If multiple overrides reference the same `decision_id`, the last one in the array is the final state. This is explicitly documented.

Response: `200 OK` with `{ "accepted": 47, "rejected": 2, "errors": [...] }`

### Source Adapters

Built as plugins for the override adapter. Each translates native events into the override schema.

**Priority (build first):**

1. **OTel passthrough:** For systems already emitting `gen_ai.override.*` events. No adapter needed; nthlayer-measure consumes directly.

2. **Generic webhook relay:** Configurable field mapper for any webhook source:
   ```yaml
   # override-adapter-config.yaml
   adapters:
     - source: jira
       field_mapping:
         decision_id: "issue.customfield_10042"
         corrected_action: "issue.resolution.name"
         reviewer: "issue.assignee.emailAddress"
         timestamp: "issue.updated"
         reason: "issue.resolution.description"
   ```

3. **Slack adapter:** Watches emoji reactions or slash commands. Maps Slack user → reviewer, reaction/command → corrected_action, message context → decision_id.

**Future:** ServiceNow, Microsoft Teams, email.

### nthlayer-measure Integration

When an override OTel event arrives (regardless of whether it came from native instrumentation or the adapter):
1. Look up the verdict by `decision_id` (if verdict store is available)
2. Update the verdict's `outcome.status` to `overridden` and populate `outcome.override`
3. Increment the reversal rate counter for the service
4. If `confidence_at_decision` > 0.85, also increment the high-confidence failure counter
5. Standard OTel metrics are already emitted: `gen_ai_override_reversal_total`, `gen_ai_override_hcf_total`

### Privacy

**Defaults are safe.** GDPR compliance is assumed given Dublin-based development.

- `reviewer` field is **hashed by default** (SHA-256) before storage. To store plaintext, explicitly opt in: `privacy.plaintext_reviewer: true`
- `reason` field is **stored by default** but can be excluded: `privacy.exclude_reason: true`
- All override data respects the same retention policy as verdict data

```yaml
# nthlayer config
overrides:
  privacy:
    plaintext_reviewer: false   # Default: false (hashed)
    exclude_reason: false        # Default: false (stored)
```

### Test Scenarios

1. Override via native OTel event: verify verdict is updated and reversal counter increments (no adapter involved)
2. Override via adapter webhook: verify adapter emits OTel event, nthlayer-measure consumes it, verdict updates
3. Batch import of 100 overrides: verify all processed, metrics correct
4. Batch with duplicate decision_id: verify last-in-array wins
5. Override for unknown decision_id: verify graceful handling (store override, flag as unmatched)
6. Override with confidence_at_decision > 0.85: verify HCF counter increments
7. Privacy defaults: verify reviewer is hashed without any configuration
8. Privacy opt-in: verify reviewer is plaintext when `plaintext_reviewer: true`
9. Slack adapter: verify emoji reaction produces correct OTel event
10. Generic webhook relay: verify YAML field mapping correctly transforms a Jira event
11. Duplicate override (same decision_id, same corrected_action): verify idempotent handling

---

## 5. Pre-execution Integration Protocol

### Problem

CortexHub and similar governance platforms handle pre-execution policy enforcement. NthLayer handles post-execution reliability. There is no defined handshake between them. When nthlayer-measure detects quality degradation and triggers the autonomy ratchet, that signal should propagate to the governance layer. When nthlayer-learn produces recommendations, they should flow to the governance layer as draft policy updates.

### Design

An open webhook-based protocol (the "Governance Bridge") that allows NthLayer to emit signals that governance platforms can consume, and vice versa. Platform-agnostic: defines signal shapes, not implementations.

### NthLayer → Governance (Outbound Signals)

Outbound signals are emitted by existing NthLayer components via HTTP webhooks. No architectural change required — this is the same pattern as nthlayer-respond sending notifications.

**Signal 1: Autonomy Change**

Emitted when nthlayer-measure changes an agent's autonomy level.

```json
{
  "type": "autonomy_change",
  "version": "v1",
  "timestamp": "2026-03-24T14:23:00Z",
  "service": "fraud-detection",
  "previous_level": "autonomous",
  "new_level": "human_review",
  "trigger": {
    "metric": "reversal_rate",
    "current_value": 0.031,
    "threshold": 0.015,
    "window": "7d"
  },
  "incident": "INC-4821",
  "recommended_governance_action": "Tighten approval gate for fraud-detection decisions until autonomy is restored."
}
```

**Signal 2: Spec Recommendation (Policy-relevant)**

Emitted when nthlayer-learn produces a recommendation with governance implications.

```json
{
  "type": "policy_recommendation",
  "version": "v1",
  "timestamp": "2026-03-24T15:00:00Z",
  "service": "fraud-detection",
  "incident": "INC-4821",
  "recommendation": {
    "type": "add_deploy_gate",
    "description": "Gate deploys on reversal rate exceeding 2% during 15-minute evaluation window",
    "confidence": 0.82,
    "financial_impact": "Would have prevented ~€47,200 in false_negative losses"
  },
  "requires_human_review": true
}
```

**Signal 3: Incident Notification**

Emitted when nthlayer-respond opens an incident affecting a governed agent.

```json
{
  "type": "incident_opened",
  "version": "v1",
  "timestamp": "2026-03-24T14:15:00Z",
  "incident": "INC-4821",
  "severity": 2,
  "affected_services": ["fraud-detection", "payment-api", "checkout-service"],
  "root_cause_service": "fraud-detection",
  "root_cause_type": "model_regression"
}
```

### Governance → NthLayer (Inbound Signals)

Inbound signals are received by an optional **governance bridge adapter** (similar architectural pattern to the override adapter — a standalone sidecar, not a core component). The adapter translates inbound signals into events that nthlayer-correlate and nthlayer-measure can consume via the standard OTel path.

**Signal 1: Policy Change Notification**

```json
{
  "type": "policy_updated",
  "version": "v1",
  "timestamp": "2026-03-24T16:00:00Z",
  "service": "fraud-detection",
  "policy_id": "pol-2847",
  "change_type": "tightened",
  "description": "Added human approval gate for transactions > €5000",
  "source_system": "cortexhub"
}
```

The adapter emits this as an OTel event that nthlayer-correlate can use as a signal source (policy changes can cause behavioural changes, similar to config changes or deploys).

**Signal 2: Autonomy Restoration Request**

```json
{
  "type": "autonomy_restore_request",
  "version": "v1",
  "timestamp": "2026-03-24T17:00:00Z",
  "service": "fraud-detection",
  "requested_by": "oncall-lead-047",
  "requested_level": "autonomous",
  "justification": "Model v2.2 restored, reversal rate back to baseline for 2 hours"
}
```

The adapter forwards this to nthlayer-measure which validates against current metrics. If the reversal rate is still above threshold, the restoration is rejected. The ratchet only loosens when the data supports it AND a human requests it.

### Configuration

```yaml
governance_bridge:
  enabled: true
  
  outbound:
    webhook_url: "https://cortexhub.example.com/api/v1/nthlayer-signals"
    auth:
      type: bearer
      token_env: GOVERNANCE_BRIDGE_TOKEN
    signals:
      - autonomy_change
      - policy_recommendation
      - incident_opened
    retry:
      max_attempts: 3
      backoff: exponential
      
  # Inbound handled by the governance bridge adapter sidecar
  # (nthlayer-governance-adapter), not by core nthlayer components
  inbound_adapter:
    enabled: true
    otel_collector_endpoint: "http://localhost:4317"
```

### Protocol Principles

1. **Webhook-based, not SDK-based.** Any platform that can send/receive HTTP can participate.
2. **Versioned.** All signals include `version: v1`. Breaking changes increment the version.
3. **Idempotent.** Re-sending the same signal (same timestamp + service + type) is safe.
4. **Human-in-the-loop by default.** NthLayer can tighten autonomy automatically. Only a human can restore it.
5. **Platform-agnostic.** Defines signal shapes, not implementations. No reference to specific platforms.
6. **Fail-open.** If outbound webhooks are unreachable, NthLayer continues operating (autonomy ratchet still works locally, nthlayer-measure is the authority). If the inbound adapter is unavailable, the governance platform continues enforcing its own policies independently. NthLayer does not depend on the governance bridge for safety; the bridge is a coordination enhancement.

### Test Scenarios

1. nthlayer-measure detects quality drop → verify autonomy_change signal emitted via outbound webhook
2. nthlayer-learn produces recommendation with financial_impact → verify policy_recommendation signal includes financial_impact
3. Governance adapter receives policy_updated → verify OTel event emitted → verify nthlayer-correlate ingests it as a signal source
4. Governance adapter receives autonomy_restore_request when metrics are still bad → verify rejection response
5. Governance adapter receives autonomy_restore_request when metrics have recovered → verify approval
6. Outbound webhook unreachable → verify NthLayer continues operating, retry with backoff
7. Inbound adapter unavailable → verify core NthLayer components unaffected
8. Duplicate signal → verify idempotent handling

---

## 6. End-to-End Composed Flow

This section describes a single test scenario that exercises all five capabilities as an integrated system. This is the definitive proof that the capabilities compose correctly.

### Scenario: Fraud Model Regression with Financial Impact

**Setup:** fraud-detection service has an OpenSRM spec with:
- Judgment SLO: reversal_rate target 0.015, window 7d
- Outcomes: false_negative cost €2,400, estimated_daily_decisions 12,000
- Dependency: upstream agent-a provides risk scoring via verdict lineage
- Governance bridge: connected to a test governance endpoint

**Steps:**

1. **Override ingestion (capability 4):** The Slack adapter forwards 15 emoji-reaction overrides on fraud-detection decisions in a 10-minute window. Each override is translated to an OTel `gen_ai.override` event and emitted to the collector. nthlayer-measure consumes them and updates the reversal rate counter. Privacy: reviewer fields are hashed by default.

2. **Judgment SLO breach detected:** The 15 reversals push fraud-detection's reversal rate to 3.1% (target 1.5%). nthlayer-measure triggers the autonomy ratchet, reducing fraud-detection to human-review mode.

3. **Governance bridge outbound (capability 5):** nthlayer-measure emits an `autonomy_change` signal to the governance platform.

4. **Verdict chain correlation (capability 3):** nthlayer-correlate runs both paths:
   - Service dependency path: checks upstream infrastructure dependencies, finds no issues
   - Verdict chain path: 83% of the reversed verdicts have `lineage.context` referencing agent-a verdicts. agent-a's confidence has shifted -0.15 from baseline. Root cause identified: agent-a output quality degradation.

5. **Incident opened:** nthlayer-respond opens INC-4821. nthlayer-correlate output includes:
   - Service dependency root cause: null
   - Verdict chain root cause: agent-a (confidence: 0.78)
   - Blast radius: fraud-detection, payment-api, checkout-service
   - `blast_radius_financial: { total_exposure: 127400, currency: EUR }` **(capability 1)**

6. **Incident resolved.** Operator rolls back agent-a's model.

7. **Learn → spec feedback (capability 2):** nthlayer-learn produces:
   - Retrospective with `financial_impact: { estimated: 47200, currency: EUR, decisions_affected: 340, failure_mode: false_negative, volume_source: "metric" }`
   - SpecRecommendation with:
     - `tighten_slo` on fraud-detection (1.5% → 1.0%), `financial_impact: "Earlier detection would have saved ~€23,400"`
     - `add_deploy_gate` on agent-a, `financial_impact: "Would have prevented the entire incident (~€47,200)"`
     - `add_dependency` on fraud-detection → agent-a (discovered via verdict chain, not declared in spec)

8. **Governance bridge outbound (capability 5):** nthlayer-learn emits a `policy_recommendation` signal with the deploy gate recommendation and financial impact.

9. **CLI:** `nthlayer learn --incident INC-4821 --apply-to ./specs/ --pr` creates a branch with all three recommendations as YAML diffs. The PR body includes the financial impact figures.

**Verification points:**
- Override events flowed through OTel (not direct HTTP to nthlayer-measure)
- Reviewer fields are hashed in stored verdicts
- Verdict chain correlation identified agent-a, not just "fraud-detection reversal rate is high"
- Financial impact appears in: blast radius, retrospective, spec recommendations, governance bridge signals, and PR body
- The `add_dependency` recommendation proves the learn loop discovered something the spec didn't originally declare
- The resulting YAML (if recommendations are accepted) passes OpenSRM schema validation

---

## Implementation Order

1. **Business outcome binding** — OpenSRM schema addition + nthlayer-learn financial impact + nthlayer-correlate blast radius financial summary + nthlayer-generate dashboard panels. Scope: small-medium.

2. **Learn → spec feedback loop** — SpecRecommendation output format + extensible type system + financial_impact cross-reference + CLI integration + git integration. Scope: medium-large.

3. **Verdict chain correlation** — nthlayer-correlate enhancement with configurable depth, performance constraints, caching, early termination. Scope: medium.

4. **Human override ingestion** — OTel event schema + override adapter sidecar + batch endpoint with ordering + source adapters + privacy-safe defaults. Scope: medium.

5. **Pre-execution integration protocol** — Signal schemas + outbound webhook emitter with retry + governance bridge adapter sidecar + protocol documentation as standalone spec. Scope: medium.

---

## Notes for Claude Code

- All schema changes must be backwards-compatible. Existing OpenSRM manifests without the new fields must continue to validate.
- All new CLI commands should follow the existing pattern (`nthlayer <verb> --flags`).
- The override adapter and governance bridge adapter are **separate processes** (standalone binaries or containers), not built into nthlayer-measure or nthlayer-correlate. They communicate via OTel, preserving the single-ingestion-source architecture.
- OpenSRM fields must not reference specific backends. Use logical signal names (`revenue.signal`) that nthlayer-generate maps through provider configuration.
- Privacy defaults are safe: hash reviewer identity by default, require explicit opt-in for plaintext.
- The governance bridge protocol should be documented as a standalone spec (separate markdown file) so governance platform vendors can implement it without reading the full NthLayer documentation.
- Test coverage expectations: unit tests per capability, integration tests for adapters, and the end-to-end composed flow (section 6) as a single integration test that proves all five capabilities work as a system.
- Recommendation types are extensible: well-known types get dedicated logic, unknown types pass through with rationale and proposed_value only.
- Verdict chain `max_depth` is configurable, not hardcoded. Default 2.
- Batch override processing is ordered: array order, last-for-same-decision-id wins.
