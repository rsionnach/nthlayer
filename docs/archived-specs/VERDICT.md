# VERDICT.md — The Atomic Unit of AI Judgment

Verdicts are to AI decision quality what beads are to task management: a single, universal primitive that makes judgment trackable, measurable, and learnable.

Any system where an AI makes a decision (approving code, correlating signals, triaging incidents, moderating content, generating recommendations) can emit verdicts. Any system that wants to measure whether those decisions were correct can consume them. Verdicts are independent of the OpenSRM ecosystem, independent of any specific agent framework, and independent of any specific model provider.

**Repo: `verdict`** (separate, standalone, like Beads)


## What Is a Verdict?

A verdict is a structured record of an AI judgment. It captures what was evaluated, what the AI decided, how confident it was, and (eventually) whether the decision was correct.

Every verdict has three phases:

1. **Judgment** (filled at decision time): what was the input, what did the AI decide, why, and how confident is it?
2. **Outcome** (filled later): was the decision confirmed, overridden by a human, or contradicted by downstream evidence?
3. **Lineage** (optional): which other verdicts informed this one, and which verdicts does this one inform?

The outcome phase is what makes verdicts powerful. Most AI systems record their decisions but never close the loop on whether those decisions were right. Verdicts make the loop explicit and queryable.


## Schema

```yaml
verdict:
  # Identity
  id: "vrd-2026-03-07-00142"           # unique, globally
  version: 1                            # schema version
  timestamp: "2026-03-07T14:22:00Z"     # when the judgment was made

  # Who made this judgment
  producer:
    system: "arbiter"                    # component or application name
    instance: "arbiter-prod-01"          # optional, for multi-instance deployments
    model: "claude-sonnet-4-20250514"    # optional, which model produced the judgment
    prompt_version: "v2.3"               # optional, for tracking prompt changes

  # What was evaluated
  subject:
    type: "agent_output"                 # agent_output | correlation | triage | investigation |
                                         # remediation | review | classification | recommendation |
                                         # moderation | custom
    agent: "code-reviewer"               # optional, the agent whose output is being judged
    service: "webapp"                     # optional, the service context
    environment: "production"            # optional
    ref: "git:abc123..def456"            # pointer to the input (git ref, snapshot ID, URL, etc.)
    summary: "14-line diff to auth middleware"  # human-readable summary of what was evaluated
    content_hash: "sha256:9f86d08..."    # hash of the input content, for replay verification

  # The judgment itself
  judgment:
    action: "approve"                    # approve | reject | flag | escalate | defer | custom
    score: 0.82                          # overall quality score, 0.0-1.0 (optional)
    confidence: 0.78                     # how confident the producer is in this judgment, 0.0-1.0
    dimensions:                          # optional, breakdown by quality dimension
      correctness: 0.9
      completeness: 0.75
      safety: 0.85
    reasoning: "Auth check is sound. Missing rate limit on new endpoint."
    tags: ["auth", "security", "api"]    # optional, for filtering and aggregation

  # What happened after (updated asynchronously)
  outcome:
    status: "pending"                    # pending | confirmed | overridden | partial | superseded | expired
    resolution: null                     # human-readable description of what actually happened
    override:                            # filled if a human or downstream signal contradicts
      by: "human:rob"                    # who overrode (human:name, system:component, or auto:rule)
      at: null                           # when
      action: null                       # what the override changed the action to
      reasoning: null                    # why the override happened
    ground_truth:                        # filled when objective evidence is available
      signal: null                       # what provided the ground truth (test failure, incident, metric, human review)
      value: null                        # what the correct judgment would have been
      detected_at: null                  # when the ground truth became available
    closed_at: null                      # when this verdict's outcome was finalised

  # Lineage (optional)
  lineage:
    parent: null                         # verdict ID that this one responds to or overrides
    children: []                         # verdict IDs that were produced in response to this one
    context: []                          # verdict IDs that informed this judgment (read, not responded to)

  # Metadata
  metadata:
    cost_tokens: 1247                    # optional, tokens consumed producing this judgment
    cost_currency: 0.003                 # optional, estimated cost in USD
    latency_ms: 2340                     # optional, time to produce this judgment
    ttl: 7776000                         # seconds until this verdict can be expired (default 90 days)
    custom: {}                           # extension point for domain-specific data
```


## Outcome Statuses

| Status | Meaning | Calibration Signal |
|--------|---------|-------------------|
| `pending` | No outcome yet. The judgment stands but hasn't been validated. | None (not counted in accuracy metrics until resolved) |
| `confirmed` | A human or downstream signal confirmed the judgment was correct. | Positive (the AI was right) |
| `overridden` | A human or downstream signal contradicted the judgment. | Negative (the AI was wrong, the override is the ground truth) |
| `partial` | The judgment was partially correct. Some dimensions were right, others wrong. | Mixed (contributes to per-dimension accuracy, not binary accuracy) |
| `superseded` | A newer verdict on the same subject replaced this one (e.g., re-evaluation with more context). | None (the superseding verdict carries the calibration signal) |
| `expired` | The TTL elapsed without the outcome being resolved. | Weak negative (an unresolved verdict might indicate the judgment wasn't important enough to validate, or the feedback loop is broken) |


## Lineage

Lineage is what turns isolated verdicts into a traceable decision chain. When Mayday's Investigation agent reads SitRep's correlation verdicts and produces its own root cause verdict, the lineage records that relationship:

```
SitRep correlation verdict (vrd-001)
  "deploy v2.3.1 caused latency spike, confidence 0.71"
    │
    └─▶ Mayday investigation verdict (vrd-002, context: [vrd-001])
          "root cause: deploy v2.3.1 removed connection pooling, confidence 0.65"
            │
            ├─▶ Mayday remediation verdict (vrd-003, parent: vrd-002)
            │     "rollback to v2.3.0, confidence 0.90"
            │
            └─▶ Human override verdict (vrd-004, parent: vrd-002)
                  "root cause correct but remediation should be hotfix, not rollback"
                  (overrides vrd-003, confirms vrd-002)
```

When vrd-004 confirms vrd-002 (investigation was right) and overrides vrd-003 (remediation was wrong), both SitRep and Mayday's investigation agent get positive calibration signals, and Mayday's remediation agent gets a negative one. All from one human action.

Lineage is optional. A standalone verdict (no parent, no context, no children) is perfectly valid. Lineage adds value when multiple components interact, but a single system using verdicts to track its own accuracy doesn't need it.


## Subject Types

The `subject.type` field indicates what kind of judgment the verdict records. Verdicts are intentionally not limited to code review or SRE use cases. Any AI decision is a valid subject.

| Type | Example Producer | Example Judgment |
|------|-----------------|-----------------|
| `agent_output` | Arbiter | "This code review output is correct and complete" |
| `correlation` | SitRep | "This deploy caused this latency spike" |
| `triage` | Mayday Triage Agent | "This incident is severity 2" |
| `investigation` | Mayday Investigation Agent | "Root cause is misconfigured connection pool" |
| `remediation` | Mayday Remediation Agent | "Rollback to v2.3.0 will resolve this" |
| `review` | Code reviewer, document reviewer | "This PR is ready to merge" |
| `classification` | Content moderator | "This content is safe" |
| `recommendation` | Any recommender system | "User would enjoy this product" |
| `moderation` | Trust and safety system | "This message violates policy" |
| `custom` | Any domain-specific AI | Domain-specific judgment |


## Verdict Operations (Transport Library)

The verdict library is small, deterministic, and transport-only. No model calls. No judgment. It handles creation, linking, outcome updates, queries, and serialisation.

### Core Operations

```
create(subject, judgment, producer) → Verdict
  Creates a new verdict with a generated ID, current timestamp, and pending outcome.

link(verdict, parent?, context?) → Verdict
  Sets lineage fields. Returns updated verdict.

resolve(verdict, status, override?, ground_truth?) → Verdict
  Updates the outcome phase. Transitions status from pending to the resolved state.
  This is the operation that closes the loop.

supersede(old_verdict, new_verdict) → (Verdict, Verdict)
  Marks old_verdict as superseded, sets new_verdict as the replacement.
  Used when re-evaluation produces a different judgment.
```

### Query Operations

```
by_producer(system, time_range?) → [Verdict]
  All verdicts from a specific producer.

by_subject(service?, agent?, type?, time_range?) → [Verdict]
  All verdicts about a specific subject.

by_status(status, producer?, time_range?) → [Verdict]
  All verdicts with a specific outcome status.

by_lineage(verdict_id, direction: up | down | both) → [Verdict]
  Traverse the verdict chain up (to parents/context) or down (to children).

unresolved(producer?, max_age?) → [Verdict]
  All pending verdicts, optionally filtered by producer and age.
  This is the "what haven't we validated yet?" query.

accuracy(producer, time_range?, dimension?) → AccuracyReport
  Computes accuracy metrics from resolved verdicts:
  - confirmation_rate: confirmed / (confirmed + overridden)
  - override_rate: overridden / (confirmed + overridden)
  - partial_rate: partial / total_resolved
  - pending_rate: pending / total (how much of the feedback loop is still open)
  - mean_confidence_on_correct: average confidence on confirmed verdicts
  - mean_confidence_on_incorrect: average confidence on overridden verdicts
  - calibration_gap: difference between confidence and actual accuracy
  If dimension is specified, computes per-dimension accuracy.
```

### Serialisation

Verdicts serialise to JSON or YAML. The canonical format is JSON for machine consumption and YAML for human readability (in Git, in documentation, in examples). Both are interchangeable.

Verdicts also emit as OTel events following semantic conventions (defined below). The OTel emission is how verdicts flow into Prometheus for NthLayer to query.


## OTel Semantic Conventions for Verdicts

Verdicts are the data primitive. OTel semantic conventions are the transmission format. The verdict library maps between the two automatically.

When a verdict is about a generative AI decision (which covers all OpenSRM ecosystem use cases: Arbiter evaluations, SitRep correlations, Mayday triage), it emits using the `gen_ai.*` OTel semantic conventions that the broader OTel community is developing. This maintains alignment with every other tool that speaks OTel's gen_ai conventions.

### Mapping: Verdict Schema → OTel gen_ai.* Conventions

| Verdict Field | OTel Attribute | Notes |
|--------------|----------------|-------|
| `verdict.id` | `gen_ai.decision.id` | Unique decision identifier |
| `verdict.producer.system` | `gen_ai.system` | Which system produced the judgment |
| `verdict.producer.model` | `gen_ai.request.model` | Which model was used |
| `verdict.subject.agent` | `gen_ai.decision.agent` | The agent being evaluated |
| `verdict.subject.service` | `service.name` | Standard OTel service identifier |
| `verdict.judgment.action` | `gen_ai.decision.action` | approve, reject, flag, etc. |
| `verdict.judgment.score` | `gen_ai.decision.score` | Quality score 0.0-1.0 |
| `verdict.judgment.confidence` | `gen_ai.decision.confidence` | Producer confidence 0.0-1.0 |
| `verdict.metadata.cost_tokens` | `gen_ai.usage.input_tokens` + `gen_ai.usage.output_tokens` | Token consumption |
| `verdict.outcome.override.by` | `gen_ai.override.actor` | Who overrode |
| `verdict.outcome.override.action` | `gen_ai.override.action` | What the override changed |
| `verdict.outcome.override.reasoning` | `gen_ai.override.reasoning` | Why the override happened |

### Events

| OTel Event Name | When Emitted | Trigger |
|----------------|--------------|---------|
| `gen_ai.decision.created` | When a verdict is produced | `verdict.create()` |
| `gen_ai.override.recorded` | When a human overrides a verdict | `verdict.resolve(status: overridden)` |
| `gen_ai.decision.confirmed` | When a verdict is confirmed correct | `verdict.resolve(status: confirmed)` |

### Metrics (for Prometheus via OTel Collector)

These are the same `gen_ai_*` metrics defined in BRIEF.md. Verdicts are the source records from which these metrics are computed:

| Metric Name | Type | Labels | Derived From |
|------------|------|--------|-------------|
| `gen_ai_decision_total` | counter | system, agent, dimension, environment | Count of `verdict.create()` calls |
| `gen_ai_decision_score` | gauge | system, agent, dimension, environment | `verdict.judgment.score` |
| `gen_ai_decision_confidence` | gauge | system, agent, environment | `verdict.judgment.confidence` |
| `gen_ai_override_reversal_total` | counter | system, agent, environment | Count of `verdict.resolve(status: overridden)` calls |
| `gen_ai_override_correction_total` | counter | system, agent, environment | Count of `verdict.resolve(status: partial)` calls |
| `gen_ai_decision_cost_tokens` | counter | system, agent, environment | `verdict.metadata.cost_tokens` |
| `gen_ai_decision_cost_currency` | gauge | system, agent, environment | `verdict.metadata.cost_currency` |

NthLayer queries these metrics from Prometheus to generate judgment SLO recording rules and deploy gates. The metrics are standard `gen_ai_*` OTel metrics. NthLayer doesn't know or care that they originate from verdicts.

### Non-gen-AI Use Cases

For systems that use verdicts outside of generative AI contexts (traditional ML classifiers, rule-based systems with human review, manual decision tracking), the verdict library can emit OTel events using a `decision.*` namespace or custom attributes. The verdict schema is the same regardless of namespace. The OTel mapping is configured per-producer based on context. The default mapping uses `gen_ai.*` because that's what the OpenSRM ecosystem needs.


## Storage

Verdicts are small (typically 1-4 KB each). Storage options match the ecosystem's tiered model:

| Tier | Store | Notes |
|------|-------|-------|
| Tier 1 | SQLite | Single file, zero dependencies. A year of verdicts from a small deployment (100 verdicts/day) is ~150 MB. |
| Tier 2 | PostgreSQL | Concurrent access, full-text search on reasoning fields, LISTEN/NOTIFY for real-time verdict consumption. |
| Tier 3 | ClickHouse | Columnar storage for analytics over millions of verdicts. Time-series optimised for the accuracy queries. |
| Any tier | Git | For evaluation datasets (curated verdicts with known outcomes). Versioned, reviewable, diffable. |

The verdict library abstracts storage behind an interface:

```
interface VerdictStore {
  put(verdict: Verdict): Promise<void>
  get(id: string): Promise<Verdict | null>
  query(filter: VerdictFilter): Promise<Verdict[]>
  update_outcome(id: string, outcome: Outcome): Promise<Verdict>
  accuracy(filter: AccuracyFilter): Promise<AccuracyReport>
  expire(before: string): Promise<number>
}
```

The same interface contract as the EventStore in SITREP-PRECORRELATION.md. Different data, same pattern.


## How Verdicts Solve Each Gap

### Replay and Simulation

Every verdict contains a `subject.ref` pointing to the input and a `subject.content_hash` for integrity verification. To replay:

1. Query historical verdicts for a producer and time range
2. For each verdict, retrieve the original input using `subject.ref`
3. Verify the input hasn't changed using `subject.content_hash`
4. Run the current version of the producer against the same input
5. Compare the new verdict's judgment against the original

The diff between original and replayed verdicts is your regression report. If the new version produces better judgments (higher confirmation rate when compared against known outcomes), the change is an improvement. If it produces worse judgments, it's a regression.

```bash
verdict replay --producer arbiter --from 2026-02-01 --to 2026-03-01
# Re-evaluates all inputs from that period with the current model/prompt
# Diffs new judgments against originals
# Reports: X improved, Y regressed, Z unchanged
# Compares against known outcomes where available
```

This is a CLI command in the verdict library, not a component-specific feature.

### Evaluation Datasets

An evaluation dataset is a collection of verdicts with resolved outcomes stored in Git:

```
eval/
├── arbiter/
│   ├── code-review-good-output.yaml      # verdict with outcome: confirmed
│   ├── code-review-subtle-bug.yaml       # verdict with outcome: overridden
│   ├── code-review-security-issue.yaml   # verdict with outcome: overridden
│   └── ...
├── sitrep/
│   ├── causal-correlation.yaml           # verdict with outcome: confirmed
│   ├── coincidental-correlation.yaml     # verdict with outcome: overridden
│   └── ...
└── mayday/
    ├── correct-triage-sev2.yaml
    ├── incorrect-triage-sev1.yaml
    └── ...
```

Each file is a complete verdict with a known outcome. On day one, these are hand-crafted. Over time, real verdicts with resolved outcomes are curated into the evaluation set. Running the evaluation suite is:

```bash
verdict eval --producer arbiter --dataset eval/arbiter/
# Runs each input through the current producer
# Compares judgments against known outcomes
# Reports accuracy, per-dimension accuracy, calibration gap
```

### Self-Calibration

Self-calibration is the `accuracy()` query over resolved verdicts:

```bash
verdict accuracy --producer arbiter --window 30d
# confirmation_rate: 0.94
# override_rate: 0.06
# calibration_gap: 0.03 (confidence averages 0.81, actual accuracy 0.94)
# mean_confidence_correct: 0.84
# mean_confidence_incorrect: 0.62
```

When the override rate exceeds the target in the OpenSRM manifest, the Arbiter's governance kicks in. But the calibration data is just verdict math, computed by the verdict library, available to any consumer.

### Agent Interaction Contracts

Components don't exchange bespoke formats. They exchange verdicts. When Mayday queries SitRep, it receives SitRep's recent correlation verdicts. The contract is:

- Verdicts have a defined schema (always parseable)
- Verdicts have a timestamp (staleness is computable)
- Verdicts have confidence (reliability is explicit)
- Verdicts have lineage (provenance is traceable)

The fallback behaviour when a producer is unavailable: the consumer operates on the most recent cached verdicts, noting their age. If cached verdicts are older than a configurable threshold, the consumer produces its own verdicts with reduced confidence and a note in the reasoning ("operating on stale SitRep data, last update 7 minutes ago").

### Graceful Degradation

A degraded component still produces verdicts. The degradation signal is in the verdict itself:

- Model unavailable: `confidence: 0.0`, `reasoning: "template-based, model unavailable"`, `producer.model: null`
- Stale input: `confidence: reduced`, `reasoning: "based on data from 12 minutes ago"`
- Partial failure: `confidence: reduced`, `metadata.custom.degradation: "otel_collector_unreachable"`

Downstream consumers read the confidence and degrade their own verdicts accordingly. The degradation cascades through confidence, not through separate error-handling paths.

### Adversarial Robustness

The gap between `judgment.score` and `outcome.status` is the gaming detection signal:

```bash
verdict gaming-check --producer arbiter --agent code-reviewer --window 90d
# Outputs agents where high scores systematically diverge from outcomes:
# code-reviewer: score avg 0.88, outcome confirmation rate 0.71
#   → ALERT: 17-point gap suggests evaluation gaming or prompt misalignment
# doc-writer: score avg 0.79, outcome confirmation rate 0.81
#   → OK: score slightly undershoots reality (conservative, not gaming)
```

This query is simple but only possible because verdicts track both the judgment and the outcome. Without both sides, gaming is invisible.

### Human Interface

Humans interact with verdicts in three ways:

1. **Review:** Read a verdict's judgment and reasoning. See what the AI decided and why.
2. **Resolve:** Confirm or override the verdict. This is the feedback that generates calibration data.
3. **Query:** Ask questions like "show me all overridden verdicts from this week" or "what's the Arbiter's accuracy on security-tagged verdicts?"

The verdict viewer doesn't need to be a custom dashboard. It can be:
- A CLI: `nthlayer-learn list --status overridden --producer arbiter --last 7d`
- A Grafana dashboard (NthLayer generates panels from verdict metrics)
- A Slack notification when a verdict has been pending too long
- A Git-based review flow (verdicts stored as YAML, outcomes added via PR)

The human interface is emergent from the verdict format, not designed separately.

### Configuration Complexity

The verdict library adds one configuration item to each component: where to store verdicts (SQLite path, PostgreSQL connection, ClickHouse connection). Everything else (schema, serialisation, OTel emission, accuracy computation) is handled by the library with sensible defaults.

For teams adopting the ecosystem incrementally, verdicts work at every stage:
- Using just the Arbiter? The Arbiter produces verdicts, stores them locally, humans resolve them through whatever interface they have.
- Adding SitRep? SitRep produces its own verdicts and can read the Arbiter's. Lineage links them automatically.
- Adding Mayday? Mayday consumes SitRep's verdicts and produces its own. The full chain is traceable.

No component needs to know about any other component's internals. They all speak verdicts.


## Impact on Existing Specs

### BRIEF.md

The five-component ecosystem becomes six: opensrm, **verdict**, arbiter, nthlayer, sitrep, mayday. Verdict sits below the others in the dependency graph (every component depends on the verdict library, none depend on each other). The component taxonomy gains a new category:

- **Data Primitives** (schema + transport library, no reasoning): Verdict

The `gen_ai_decision_*` and `gen_ai_override_*` metric names in BRIEF.md remain correct. Verdicts are the source records from which those metrics are derived, but the OTel emission uses the `gen_ai.*` namespace to maintain alignment with the broader OTel community's semantic conventions. The naming relationship is: verdicts produce `gen_ai.*` metrics, not the other way around.

Judgment SLOs remain judgment SLOs. The verdict is the unit of measurement. The SLO is what you measure. "This agent's reversal rate must stay below 5%" is a judgment SLO. The reversal rate is computed from overridden verdicts. The naming reflects the domain (judgment quality), not the implementation (verdict records).

### Arbiter

The Arbiter's evaluation output becomes a verdict. The quality scores, dimensions, confidence, and reasoning it already produces map directly to the verdict schema. The Arbiter's self-calibration loop becomes `nthlayer-learn accuracy --producer arbiter`. The Arbiter's governance decisions are informed by verdict accuracy metrics rather than a separate calibration subsystem.

The Arbiter becomes more universal: any system that produces verdicts can be measured by the Arbiter. The Arbiter doesn't need per-system adapters for quality measurement. It needs one adapter: "convert your output to a verdict." For systems that already produce verdicts natively, no adapter is needed at all.

### SITREP-PRECORRELATION.md

The SitRepEvent schema gains `verdict` as an event type. Verdicts from other components (Arbiter quality verdicts, change events) arrive in SitRep as events and are indexed in the pre-correlation store alongside alerts and metric breaches.

SitRep's output changes from a bespoke SituationSnapshot schema to one or more correlation verdicts. Each correlation assessment ("this deploy caused this alert cluster") is a verdict with `subject.type: correlation`. The snapshot as a whole can be a parent verdict with individual correlation verdicts as children.

The pre-correlation engine's internal structures (TemporalGroup, TopologyCorrelation, CorrelationGroup) remain unchanged since they're transport. The change is at the output boundary: the snapshot generator produces verdicts instead of a custom schema.

### COSTOPTIMISATION.md

Verdict storage and emission add marginal cost (small JSON records, lightweight OTel events). The cost optimisation strategies are unchanged. The tiered evaluation in the Arbiter still applies (low-risk outputs get lighter evaluation, producing lower-cost verdicts). The pre-correlation in SitRep still applies (the model receives pre-digested input and produces verdicts, not raw correlation).

One new cost dimension: the replay and evaluation infrastructure consumes model tokens when re-evaluating historical inputs. This is offline cost (not in the production path) and is controllable (run replays on a schedule, sample rather than replay everything, use a cheaper model for replay evaluation).


## Repo Structure

```
verdict/
├── README.md                    # What verdicts are, why they exist, quick start
├── SPEC.md                      # The full schema specification (this document, refined)
├── schema/
│   ├── verdict.json             # JSON Schema for validation
│   └── verdict.yaml             # YAML example with annotations
├── conventions/
│   ├── otel-events.md           # OTel event semantic conventions
│   └── otel-metrics.md          # OTel metric semantic conventions (verdict_*)
├── lib/                         # Transport library (implementations by language)
│   ├── python/                  # Python: create, link, resolve, query, accuracy
│   ├── go/                      # Go: same operations
│   └── typescript/              # TypeScript: same operations
├── stores/                      # Storage implementations
│   ├── sqlite/                  # Default store
│   ├── postgres/                # Tier 2 store
│   └── clickhouse/              # Tier 3 store
├── cli/                         # CLI for replay, eval, accuracy, gaming-check
├── eval/                        # Example evaluation datasets
│   ├── code-review/
│   ├── correlation/
│   └── triage/
├── ECOSYSTEM.md                 # How verdicts integrate with OpenSRM components
└── CONTRIBUTING.md
```

The lib implementations should be minimal. The Python library is probably 500-800 lines. The core operations (create, link, resolve, query, accuracy) are straightforward data manipulation. The store interface is a thin wrapper around SQL queries. The CLI is a thin wrapper around the library.


## Implementation Priority

1. **Schema definition** (verdict.json, verdict.yaml). The contract that everything else depends on.
2. **Python library** with SQLite store. Enough to integrate with the Arbiter (Python) immediately.
3. **CLI** for replay, eval, accuracy, gaming-check. Developer-facing tools for working with verdicts.
4. **OTel semantic conventions**. How verdicts flow to Prometheus for NthLayer to query.
5. **Go library** with SQLite store. For SitRep and Mayday if they're implemented in Go.
6. **TypeScript library**. For JavaScript/TypeScript agent systems.
7. **PostgreSQL and ClickHouse stores**. Scale-up paths.
8. **Evaluation datasets**. Curated verdicts with known outcomes for bootstrapping calibration.

Items 1-4 give you a working verdict system integrated with the Arbiter. Items 5-8 extend it to the rest of the ecosystem and to external consumers.


## The Pitch

**For the OpenSRM ecosystem:** Verdicts are the primitive that turns five independent tools into a system that learns. Without verdicts, each component measures its own quality in its own way. With verdicts, every judgment in the ecosystem is recorded in the same format, linked through lineage, and measured through the same accuracy queries. One human override propagates calibration signals to every component in the chain.

**For anyone else:** If your AI makes decisions and you want to know whether those decisions are good, emit verdicts. You get replay (regression test your judgment quality), calibration (measure accuracy over time), and a human feedback loop (let people confirm or override, and track the results). No framework required. No ecosystem required. Just a schema and a small library.

**The Beads parallel:** Steve Yegge made task management universal by defining one primitive (the bead) that any system can produce and consume. Verdicts do the same for judgment quality. Beads track "what work needs to be done." Verdicts track "was this AI decision correct." Both are simple, both are stored in Git-compatible formats, both work standalone, and both become more powerful when systems share them.
