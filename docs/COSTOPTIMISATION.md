# COSTOPTIMISATION.md — Token Cost Optimisation Specification

This document defines the cost optimisation architecture for the OpenSRM ecosystem. Every optimisation follows the ZFC principle: transport does work to reduce what the model needs to process. The model only handles judgment that remains after transport has done everything it can.

This is not an afterthought. Cost decisions are architectural. They must be designed into each component from the start, not retrofitted later.


## Core Principle

**ZFC is a cost optimisation strategy.**

Every token sent to a model represents a judgment call. If the transport layer can reduce the input the model receives (through classification, pre-correlation, caching, context compression, or routing), it reduces cost without reducing judgment quality. The goal is to ensure that every token the model processes is a token that genuinely requires interpretation.


## Component-Level Optimisations

### Arbiter: Tiered Evaluation

The Arbiter evaluates agent output quality. Not every output needs the same evaluation depth. A documentation typo fix and an authentication logic change have fundamentally different risk profiles, and spending the same tokens on both is waste.

#### Risk Classification (Transport)

Before any output reaches the model, the transport layer classifies it by risk. This classification is deterministic (same input always produces the same risk tier) and based on signals that don't require interpretation:

**Signals for classification:**
- Diff size (lines added, removed, modified)
- Files touched (categorised by path patterns: auth/*, payments/*, config/security/* are high-risk; docs/*, README*, *.md are low-risk; tests/* are medium-risk)
- Whether the change touches files that other agents recently modified (overlap increases risk)
- Whether the change modifies function signatures, API contracts, or database schemas versus implementation details
- Language-specific static analysis signals (new dependencies added, permission changes, network calls introduced)

**Risk tiers:**

| Tier | Criteria | Evaluation Approach | Estimated Token Reduction |
|------|----------|--------------------|--------------------------| 
| Minimal | Docs-only, formatting, comments, whitespace | Rule-based pass-through, no model call. Record the score as "auto-approved" with a flag so the self-calibration loop can sample and verify. | ~100% for these outputs |
| Standard | Routine code changes, test updates, small features in non-critical paths | Lightweight model evaluation with compressed prompt. Shorter system instructions, minimal context, focused scoring rubric. | ~50-60% vs full evaluation |
| Deep | Changes to critical paths (auth, payments, data access), large diffs, changes overlapping with recent agent work, schema changes | Full model evaluation with complete context. No cost optimisation applied. | 0% (baseline) |
| Critical | Changes that span multiple services, modify security boundaries, or alter agent behaviour/configuration | Full evaluation with frontier model regardless of default model tier. Extended context including dependency topology. | May cost more than baseline |

**Classification must be configurable per-rig/per-service.** What counts as "critical path" varies by codebase. The OpenSRM manifest should define path patterns and their risk categories so the classification is service-aware:

```yaml
# In the OpenSRM manifest
spec:
  arbiter:
    risk_classification:
      critical_paths:
        - "internal/auth/**"
        - "internal/payments/**"
        - "migrations/**"
      low_risk_paths:
        - "docs/**"
        - "*.md"
        - "*.txt"
      overlap_window: 24h  # flag changes to files touched by other agents within this window
```

#### Self-Calibration Sampling

The minimal tier (auto-approved outputs) skips the model entirely. This creates a blind spot: the Arbiter doesn't know if it's auto-approving bad work. To close this gap, the transport layer randomly samples a configurable percentage (default 5%) of auto-approved outputs and sends them through full evaluation. The results calibrate the classification rules:

- If sampled auto-approvals consistently score well, the classification is working. No action needed.
- If sampled auto-approvals reveal quality issues, the classification rules are too permissive. Tighten the criteria for the minimal tier (fewer path patterns qualify, lower diff size threshold).
- The sampling rate itself can be adjusted by the Arbiter's governance: increase sampling when classification accuracy drops, decrease when it's stable.

This is the self-calibration loop applied to cost optimisation. The system measures whether its cost-saving shortcuts are safe.

#### Expected Impact

In a typical codebase, the distribution of agent outputs by risk tier is roughly: 20-30% minimal (docs, formatting, config), 50-60% standard (routine code), 15-25% deep (critical paths), less than 5% critical (cross-service, security). If the minimal tier costs zero tokens, the standard tier costs half, and deep/critical cost full price, the blended token reduction is approximately 50-65% compared to evaluating everything at full depth.


### SitRep: Pre-Correlation as Cost Elimination

Pre-correlation is the single largest cost optimisation in the ecosystem. It transforms the model's job from "find patterns in thousands of raw events" to "interpret these pre-grouped signals."

#### The Cost Difference

Without pre-correlation: the model receives N raw events (potentially thousands in a 15-minute window at enterprise scale) and must identify which are related, assess temporal proximity, check topology connections, and produce a coherent snapshot. Token count scales linearly with event volume. At enterprise scale this is unsustainable.

With pre-correlation: the transport layer continuously groups related signals, computes temporal proximity scores, indexes changes by affected service, and maintains rolling windows of pre-correlated state. The model receives a structured summary: "here are 4 correlated signal groups, each with pre-computed temporal proximity and topology relevance scores, and 2 candidate changes." Token count scales with the number of meaningful correlations (typically single digits to low tens) regardless of raw event volume.

**The reduction ratio:** If the raw event volume is 10,000 events per 15-minute window and pre-correlation reduces this to 5-15 correlation groups with supporting evidence, the model input is reduced by 99%+ in token terms. The transport cost of pre-correlation (CPU, memory for windowing and grouping) is negligible compared to the token cost of sending raw events to a model.

#### Pre-Correlation Operations (All Transport)

These operations are deterministic and require no model judgment:

- **Temporal grouping:** Events within a configurable time window (default 5 minutes) affecting the same service or dependency chain are grouped together. This is windowed aggregation, not interpretation.
- **Topology-aware grouping:** Events are tagged with the services they affect (from OpenSRM manifest topology). Events affecting services in the same dependency chain are cross-referenced. This is graph traversal, not reasoning.
- **Change indexing:** Change events (via the standardised change event schema) are indexed by affected service and timestamp. When a quality signal fires, the candidate changes are already indexed and retrievable in O(1). This is index maintenance, not correlation.
- **Signal deduplication:** Multiple alerts about the same underlying issue (Prometheus fires the same alert for 5 minutes) are deduplicated to a single signal with a count and duration. This is counting, not judgment.
- **Severity pre-scoring:** Signals are pre-scored by severity based on the SLO targets in the OpenSRM manifest. A latency spike on a service with a p99 target of 200ms that's currently at 500ms gets a higher pre-score than one at 210ms. This is arithmetic, not interpretation.

#### What Remains for the Model

After pre-correlation, the model handles only the judgment that transport cannot:

- Is this correlation causal or coincidental? (A deploy happened 12 minutes before a quality drop. Transport can compute the temporal proximity. Only the model can assess whether the deploy plausibly caused the drop.)
- Which correlation group is most important right now? (Transport pre-scores by severity. The model reasons about competing priorities and business context.)
- What's the natural language summary? (Transport provides structured data. The model produces a human-readable interpretation.)
- What actions should be recommended? (Transport can list available actions. The model reasons about which ones are appropriate given the context.)

#### Snapshot Caching

Batch snapshots (WATCHING mode, every 5 minutes) are the highest-volume model calls in SitRep. Most of these calls are wasted because nothing meaningful changed since the last snapshot.

**Cache implementation (transport):**

1. After pre-correlation, the transport layer computes a content hash of the pre-correlated input (signal groups, change index state, severity pre-scores).
2. If the hash matches the previous cycle's hash, the pre-correlated state hasn't changed meaningfully. Return the cached snapshot without calling the model.
3. If the hash differs, send the pre-correlated input to the model for a fresh snapshot.
4. Store the new snapshot and hash for the next cycle comparison.

**Cache invalidation:**
- Any change in the pre-correlated signal groups invalidates the cache (new signals, resolved signals, changed severity pre-scores).
- Transition to ALERT or INCIDENT mode always invalidates the cache (higher urgency requires fresh assessment).
- A configurable maximum cache TTL (default 15 minutes) forces a fresh evaluation even if the hash hasn't changed, to catch slow-developing situations.

**Expected impact:** During quiet operations (the majority of time), SitRep's token consumption drops to near zero. The model is only called when something actually changes. At enterprise scale, this is the difference between continuous API cost and event-driven API cost.

#### Differential Snapshots

When the cache is invalidated and a new snapshot is needed, the model doesn't need to re-evaluate everything from scratch. The transport layer computes the diff between the previous pre-correlated state and the current one:

- New signal groups (not present in previous cycle)
- Resolved signal groups (present in previous cycle, now gone)
- Changed signal groups (same signals, different severity or count)
- New or resolved changes in the change index

The model receives this diff plus the previous snapshot, and produces an updated snapshot. This is significantly cheaper than producing a snapshot from the full pre-correlated state every time, especially when only one or two signal groups changed out of dozens.


### Mayday: Cost Through Prevention, Not Optimisation

Mayday's agents run during incidents. Incidents are rare and high-stakes. Optimising token cost during an incident is the wrong trade-off because slower or less thorough investigation to save tokens costs more than the tokens saved (in downtime, customer impact, and engineer time).

The cost optimisation for Mayday is making incidents rare and short:

- **Rare:** Better Arbiter measurement catches quality degradation before it escalates. Better SitRep correlation identifies developing problems before they become incidents. The learning loop ensures the same incident pattern doesn't recur.
- **Short:** Pre-correlated SitRep snapshots mean Mayday's Investigation agent starts with context instead of raw data. Structured incident context means agents don't repeat each other's work. Pre-approved safe actions in the OpenSRM manifest mean the Remediation agent can act without waiting for human approval on routine fixes.

The one legitimate optimisation within Mayday: the Communication agent's routine updates (status page refreshes, stakeholder notifications) can use a lighter model than the Investigation and Remediation agents. Communication templates are relatively formulaic compared to hypothesis generation and risk assessment. This is model routing based on task complexity, consistent with ZFC.


### NthLayer: No Model Cost (By Design)

NthLayer is a tool, not an agent. Its current operations (validate, generate, check-deploy, verify) are deterministic and use zero model tokens. This is the baseline that every team gets for free.

The planned agentic extension (`nthlayer infer`) will introduce model cost for codebase analysis. The cost optimisation for this is straightforward: inference results should be cached per-codebase-state. If the codebase hasn't changed (same git commit hash), the previously inferred manifest is still valid. Only re-run inference when the codebase changes, and even then, only analyse the changed files and their dependency neighbourhood rather than the full codebase.


## Cross-Cutting Optimisations

### Prompt Compression

Every model call includes context: OpenSRM manifest, service topology, agent instructions, recent history. This context is largely static between calls. Sending the full manifest and topology on every evaluation wastes tokens on content the model has already processed (in a logical sense, since each call is stateless).

**Implementation:**

- **Manifest summary:** Instead of sending the full OpenSRM manifest on every call, the transport layer extracts only the relevant fields for this specific evaluation. The Arbiter evaluating a diff on service X only needs service X's SLO targets, risk classification rules, and immediate dependencies. Not the full org-wide manifest.
- **Topology pruning:** Instead of sending the complete service topology, send only the subgraph relevant to the current evaluation: the affected service, its direct dependencies, and one hop of upstream/downstream services.
- **Instruction compression:** Agent system prompts should be versioned and optimised for token efficiency. Remove redundant instructions, use concise language, and structure prompts so that context-dependent sections can be conditionally included or excluded based on the evaluation tier.
- **History windowing:** Recent evaluation history (for trend detection) should be summarised rather than sent as raw records. "This agent's last 10 evaluations averaged 0.82 with a declining trend" is cheaper than sending 10 full evaluation records.

**Expected impact:** 20-40% token reduction per model call across all components, compounding across thousands of calls.


### Model Routing

ZFC makes the ecosystem model-agnostic. This means different judgment calls can use different models based on complexity and cost:

| Judgment Type | Recommended Model Tier | Rationale |
|---------------|----------------------|-----------|
| Arbiter: minimal-tier sampling (calibration checks) | Standard | Verifying auto-approvals doesn't need frontier reasoning |
| Arbiter: standard evaluation | Standard | Routine quality scoring on non-critical code |
| Arbiter: deep/critical evaluation | Frontier | Critical path changes need the best available judgment |
| Arbiter: governance decisions | Frontier | Autonomy adjustments are high-stakes meta-decisions |
| SitRep: WATCHING batch snapshots | Standard | Background correlation with pre-digested input |
| SitRep: ALERT snapshots | Frontier | Elevated signals need deeper interpretation |
| SitRep: INCIDENT snapshots | Frontier | Incidents need maximum correlation quality |
| Mayday: Communication updates | Standard | Templated updates with low judgment complexity |
| Mayday: Triage, Investigation, Remediation | Frontier | High-stakes reasoning under pressure |
| NthLayer: infer | Frontier | Codebase analysis requires deep understanding |

**Routing is transport.** The decision about which model to use for a given judgment type is configured, not reasoned about. The transport layer reads the routing table and sends the request to the appropriate model endpoint. No model is involved in deciding which model to use.

**Self-calibration informs routing.** The Arbiter's self-calibration loop measures judgment quality per model tier. If the standard model's quality on routine evaluations drops below threshold, the routing table can be adjusted (either automatically by the Arbiter's governance or manually by the operator) to route more evaluations to the frontier model. Conversely, if a cheaper model consistently matches frontier quality on a particular judgment type, it can be promoted in the routing table to reduce cost.


### Local Model Integration (Future, via lora-forge)

The most significant cost reduction comes from moving routine judgment calls to self-hosted models. If lora-forge's per-role LoRA adapters reach production quality, the cost model shifts from per-token API pricing to fixed compute cost for local inference.

**Architecture:**

- The transport layer routes judgment calls to either a local model endpoint or a remote API endpoint based on the routing table.
- The Arbiter's self-calibration loop measures quality for both local and remote models on the same judgment types.
- When a local model's measured quality meets the threshold for a judgment type, it can be promoted in the routing table (with human approval, per the one-way safety ratchet).
- Frontier API calls are reserved for: edge cases where local model confidence is low, self-calibration reference checks (comparing local judgment against frontier judgment on sampled inputs), and judgment types where local models haven't demonstrated sufficient quality.

**Expected impact:** At maturity, 80-90% of routine Arbiter evaluations and SitRep WATCHING snapshots could run locally, reducing API token cost to a fraction of the full-evaluation baseline. The remaining 10-20% (critical evaluations, incident response, calibration checks) stays on frontier models where quality matters most.

**This is not a near-term optimisation.** It depends on lora-forge producing adapters that demonstrably match frontier quality on specific judgment types. The self-calibration loop is what makes this safe to adopt incrementally: you have data-driven evidence for when local models are good enough, rather than hoping they are.


## Cost Measurement

The Arbiter already tracks cost per agent as a reliability dimension. The cost optimisation architecture adds internal cost measurement for the ecosystem itself:

**Metrics to track per component:**

| Metric | What It Measures | Why It Matters |
|--------|-----------------|----------------|
| `arbiter.evaluations.total` by tier | Distribution of evaluations across risk tiers | Validates that classification is working (most should be standard/minimal) |
| `arbiter.evaluations.tokens` by tier | Token consumption per risk tier | Measures actual cost reduction from tiered evaluation |
| `arbiter.calibration_samples.quality` | Quality scores on sampled auto-approvals | Validates that minimal-tier pass-through is safe |
| `sitrep.snapshots.cached` vs `.generated` | Cache hit rate on batch snapshots | Measures effectiveness of snapshot caching |
| `sitrep.precorrelation.input_events` vs `.output_groups` | Compression ratio of pre-correlation | Measures how much the transport layer reduces model input |
| `sitrep.snapshots.tokens` by mode | Token consumption per snapshot mode | Tracks cost by operational state |
| `mayday.incident.tokens` | Total token consumption per incident | Tracks incident response cost (expected to be high, justified by severity) |
| `ecosystem.model_routing.calls` by model | Distribution of calls across model tiers | Validates routing table is directing appropriately |
| `ecosystem.model_routing.quality` by model | Quality scores by model tier per judgment type | Data for routing table optimisation |

These metrics flow through the same OTel pipeline as everything else in the ecosystem. NthLayer generates dashboards for them from the OpenSRM manifest. The cost of measuring cost is effectively zero since the infrastructure already exists.


## Implementation Priority

Cost optimisations should be implemented in this order, based on impact and complexity:

1. **SitRep pre-correlation** (highest impact, foundational architecture). This must be built into SitRep from day one. It's not an optimisation you add later because the entire snapshot generation pipeline depends on it. Without pre-correlation, SitRep at enterprise scale is economically non-viable.

2. **Arbiter tiered evaluation** (high impact, relatively simple). The risk classification logic is straightforward transport code. The routing to different evaluation depths is a configuration change. The self-calibration sampling is a small addition to the existing self-calibration loop.

3. **Prompt compression** (medium impact, applies everywhere). Each component benefits from sending only relevant context to the model. This can be implemented incrementally, one component at a time.

4. **Snapshot caching** (medium impact, SitRep-specific). Depends on pre-correlation being in place. Simple to implement once the pre-correlated state has a computable hash.

5. **Model routing** (medium impact, cross-cutting). Requires the routing table and per-model quality measurement. Builds on the Arbiter's existing self-calibration infrastructure.

6. **Differential snapshots** (lower impact, SitRep-specific). Refinement of snapshot generation that reduces tokens when only part of the state changed. Depends on caching being in place.

7. **Local model integration** (highest potential impact, longest timeline). Depends on lora-forge or similar producing quality adapters. The Arbiter's self-calibration loop provides the safety net. This is the end-state optimisation that changes the cost curve from linear to mostly fixed.


## Relationship to ZFC

Every optimisation in this document is transport. Classification, caching, compression, routing, pre-correlation, and differential computation are all deterministic operations that reduce what the model needs to process without making any judgment calls. The model's job stays the same (interpret, evaluate, recommend) but it receives less noise and more signal.

This means cost optimisation and judgment quality are aligned, not in tension. A model that receives pre-correlated signal groups instead of raw events doesn't just cost less to run, it produces better correlations because the noise has been removed. A model that receives only the relevant manifest fields instead of the full org-wide spec doesn't just use fewer tokens, it focuses on what matters.

The self-calibration loop is the safety mechanism that prevents cost optimisation from degrading quality. Every shortcut (auto-approval, caching, lighter model) is continuously measured. If quality drops, the shortcut is tightened or removed. Cost savings are only retained when they demonstrably don't hurt judgment quality.
