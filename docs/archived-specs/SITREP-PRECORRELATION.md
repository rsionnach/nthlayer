# SITREP-PRECORRELATION.md — Pre-Correlation Architecture Specification

This document defines the pre-correlation architecture for SitRep. Pre-correlation is the single most important architectural decision in SitRep because it determines the boundary between what the transport layer processes and what the model sees. Without pre-correlation, SitRep at any meaningful scale is economically non-viable (the model receives thousands of raw events per snapshot cycle). With pre-correlation, the model receives a handful of structured signal groups regardless of event volume.

This must be built into SitRep from day one. It is not an optimisation added later. The entire snapshot generation pipeline depends on receiving pre-correlated groups rather than raw events. Retrofitting pre-correlation means rewriting the core pipeline.


## Core Principle

**Index first, retrieve selectively.**

All incoming signals are indexed into a searchable store, grouped by service, time window, and topology. When the model needs a snapshot, the transport layer queries the store for relevant signal groups rather than scanning everything. The model receives a structured summary ("here are 4 correlated groups with 2 candidate changes") not the raw index. The raw events never reach the model.

This is the same pattern Context Mode uses for coding session context (chunk content into FTS5, surface BM25-ranked matches, raw data never enters the context window) applied to observability signals at production scale.


## Architecture Overview

```
Event Sources                 Ingestion Layer              Indexed Store
(Prometheus, OTel,     ──▶    (webhooks, NATS,      ──▶    (SQLite FTS5,
 change events,                or Kafka depending          PostgreSQL, or
 Arbiter scores,               on deployment tier)         ClickHouse)
 custom webhooks)
                                                                │
                                                                │ query
                                                                ▼
                                                      Pre-Correlation Engine
                                                      (temporal grouping,
                                                       topology grouping,
                                                       change indexing,
                                                       severity pre-scoring,
                                                       deduplication)
                                                                │
                                                                │ structured output
                                                                ▼
                                                      Snapshot Generator
                                                      (token budget, priority
                                                       tiers, cache/diff,
                                                       model prompt assembly)
                                                                │
                                                                │ pre-digested input
                                                                ▼
                                                           Model (judgment)
                                                      (interpret correlations,
                                                       assess causality,
                                                       produce snapshot,
                                                       recommend actions)
```

Every box above the model is transport. The model handles only the judgment that remains after transport has done everything it can.


## The Three Layers

### Layer 1: Ingestion

Ingestion receives events from external sources and writes them to the indexed store. The ingestion layer is an interface with multiple implementations depending on deployment tier.

**Event schema.** Every event entering SitRep conforms to a common envelope:

```typescript
interface SitRepEvent {
  id: string;                    // unique event ID
  timestamp: string;             // ISO 8601
  source: string;                // originating system (prometheus, arbiter, github, etc.)
  type: EventType;               // alert | metric_breach | change | quality_score | verdict | custom
  service: string;               // affected service name (from OpenSRM manifest or event metadata)
  environment: string;           // production, staging, etc.
  severity: number;              // 0.0-1.0, pre-scored by ingestion based on SLO targets
  payload: Record<string, any>;  // source-specific data
  topology: {                    // optional, enriched from OpenSRM manifest if available
    dependencies: string[];      // services this one depends on
    dependents: string[];        // services that depend on this one
  };
  ttl: number;                   // seconds until this event expires from the store
}
```

**Event types:**

| Type | Source Examples | What It Represents |
|------|---------------|-------------------|
| `alert` | Prometheus alertmanager, PagerDuty, custom webhooks | Something has breached a threshold |
| `metric_breach` | Prometheus, Datadog, CloudWatch | A metric has crossed an SLO boundary |
| `change` | OpenSRM change event schema, GitHub webhooks, ArgoCD, model registries | Something was deployed, updated, or modified |
| `quality_score` | Arbiter | An agent's output quality score |
| `verdict` | Arbiter, Mayday, any verdict-producing system | A structured judgment record (verdict) from another component. Verdicts from the Arbiter carry quality assessments, verdicts from Mayday carry triage/investigation/remediation judgments. SitRep indexes them alongside other events and includes them in pre-correlation (e.g., a quality score drop correlated with a deploy). |
| `custom` | Any webhook | Anything else the operator wants SitRep to correlate |

**Ingestion implementations:**

| Implementation | When to Use | How It Works |
|---------------|-------------|--------------|
| `WebhookIngester` | Tier 1 (small deployments) | HTTP server accepting POST requests with event payloads. Writes directly to the indexed store. Simple, no infrastructure dependencies. |
| `NATSIngester` | Tier 2 (medium deployments) | Subscribes to NATS subjects. Handles concurrent producers that would overwhelm direct webhook writes. Writes to the indexed store from a single consumer. |
| `KafkaIngester` | Tier 3 (enterprise) | Subscribes to Kafka topics. Consumer groups, partitioning, backpressure, exactly-once delivery. Required when event volume exceeds what a single consumer can process. |
| `PollingIngester` | Any tier, for sources that don't push | Periodically polls sources (Prometheus API, GitHub API) and converts responses to SitRepEvents. Configurable poll intervals per source. |

The ingestion layer is defined as an interface:

```typescript
interface Ingester {
  start(): Promise<void>;
  stop(): Promise<void>;
  onEvent(handler: (event: SitRepEvent) => Promise<void>): void;
}
```

Every ingester calls the same handler. The handler writes events to the indexed store. The pre-correlation engine doesn't know or care which ingester produced the event.

**Severity pre-scoring at ingestion.** When an event arrives, the ingestion layer pre-scores its severity if an OpenSRM manifest is available. A latency metric at 500ms for a service with a p99 SLO target of 200ms gets a higher severity score than the same metric at 210ms. This is arithmetic, not judgment. The formula:

```
severity = min(1.0, (current_value - target_value) / target_value)
```

For alerts without SLO context, severity defaults to what the source declares (or 0.5 if undeclared). The model can override severity during snapshot interpretation, but the pre-score gives the pre-correlation engine a useful ordering signal.


### Layer 2: Indexed Store

The indexed store persists events with full-text search capability and time-based querying. It is the working memory of the pre-correlation engine.

**Store interface:**

```typescript
interface EventStore {
  // Write
  insert(event: SitRepEvent): Promise<void>;
  insertBatch(events: SitRepEvent[]): Promise<void>;

  // Query by time window
  getByTimeWindow(start: string, end: string, options?: {
    service?: string;
    type?: EventType;
    minSeverity?: number;
  }): Promise<SitRepEvent[]>;

  // Full-text search across event payloads
  search(query: string, options?: {
    limit?: number;
    timeWindow?: { start: string; end: string };
    service?: string;
  }): Promise<SitRepEvent[]>;

  // Get events affecting a service and its dependency neighbourhood
  getByTopology(service: string, hops?: number): Promise<SitRepEvent[]>;

  // Change index: get recent changes that could explain a signal
  getRecentChanges(service: string, windowMinutes?: number): Promise<SitRepEvent[]>;

  // Maintenance
  expireOld(beforeTimestamp: string): Promise<number>;  // returns count deleted
  getStats(): Promise<StoreStats>;

  // State hashing for cache invalidation
  getStateHash(timeWindow: { start: string; end: string }): Promise<string>;
}
```

**Store implementations:**

#### SQLite FTS5 (Default, Tier 1)

The default backend. Zero infrastructure dependencies. Works out of the box.

**Schema:**

```sql
-- Core events table
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  source TEXT NOT NULL,
  type TEXT NOT NULL,
  service TEXT NOT NULL,
  environment TEXT NOT NULL,
  severity REAL NOT NULL DEFAULT 0.5,
  payload TEXT NOT NULL,  -- JSON
  dependencies TEXT,       -- JSON array
  dependents TEXT,         -- JSON array
  ttl INTEGER NOT NULL DEFAULT 86400,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Full-text search index on payload content
CREATE VIRTUAL TABLE events_fts USING fts5(
  id,
  service,
  source,
  type,
  payload_text,  -- flattened text extraction from payload JSON
  content=events,
  content_rowid=rowid,
  tokenize='porter'
);

-- Time-based queries (most common access pattern)
CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_service_time ON events(service, timestamp DESC);
CREATE INDEX idx_events_type_time ON events(type, timestamp DESC);

-- Change index for rapid change attribution
CREATE INDEX idx_events_changes ON events(type, service, timestamp DESC)
  WHERE type = 'change';

-- TTL cleanup
CREATE INDEX idx_events_expiry ON events(created_at, ttl);
```

**FTS5 with BM25 ranking.** When the pre-correlation engine searches for related events, it uses BM25 ranking (the same algorithm Context Mode uses) to surface the most relevant matches. Porter stemming means "deploying", "deployed", and "deployment" all match the same stem. This matters when correlating signals across sources that use different terminology for the same concept.

**Maintenance.** A background task runs every 5 minutes to expire events past their TTL. Default TTL is 24 hours for alerts and metric breaches, 7 days for changes (longer because change attribution often looks back further), and 30 days for quality scores (the Arbiter needs historical data for trend detection).

**Capacity.** SQLite handles tens of thousands of events per day comfortably. At 1,000 events per hour (a reasonable volume for a deployment with 50-100 services), the database stays under 100MB with default TTLs. FTS5 queries over this volume return in single-digit milliseconds.

#### PostgreSQL (Tier 2)

For deployments that need concurrent read/write access from multiple SitRep instances, or that already have PostgreSQL infrastructure. Same schema structure, using PostgreSQL's `tsvector` and `tsquery` for full-text search instead of FTS5. GIN indexes replace SQLite's FTS5 virtual tables.

PostgreSQL also supports `LISTEN/NOTIFY` for real-time event notification to the pre-correlation engine, avoiding the polling loop that SQLite requires.

Specification of the PostgreSQL schema is deferred. Document the interface contract and build SQLite first. PostgreSQL is a drop-in replacement that implements the same `EventStore` interface.

#### ClickHouse (Tier 3)

For enterprise deployments processing millions of events per day. ClickHouse's columnar storage and time-series optimisations make it ideal for the access patterns SitRep needs (time-windowed aggregations, service-filtered queries, high insert throughput). Full-text search uses ClickHouse's `ngramBF` or `tokenbf_v1` bloom filter indexes rather than FTS5.

Specification of the ClickHouse schema is deferred. Document the interface contract and build SQLite first.


### Layer 3: Pre-Correlation Engine

The pre-correlation engine reads from the indexed store and produces structured signal groups. It runs continuously in the background, maintaining a rolling view of correlated state. When the snapshot generator needs a snapshot, the correlated state is already built.

**Pre-correlation operations (all transport, all deterministic):**

#### Temporal Grouping

Events within a configurable time window (default 5 minutes) affecting the same service are grouped together. Multiple alerts about the same service within 5 minutes become a single signal group with a count, duration, and peak severity.

```typescript
interface TemporalGroup {
  service: string;
  timeWindow: { start: string; end: string };
  events: SitRepEvent[];
  count: number;
  peakSeverity: number;
  duration: number;  // seconds between first and last event
}
```

This is windowed aggregation. No interpretation involved.

#### Topology-Aware Grouping

Events are cross-referenced against the service dependency topology (from OpenSRM manifests or from the topology data in the event envelope). If service A depends on service B, and both have alerts in the same time window, they're linked into a correlation group with a note about the dependency direction.

```typescript
interface TopologyCorrelation {
  primaryService: string;
  relatedServices: Array<{
    service: string;
    relationship: 'depends_on' | 'depended_by';
    events: SitRepEvent[];
  }>;
  topologyPath: string[];  // the dependency chain connecting them
}
```

This is graph traversal over a known topology. No reasoning required.

#### Change Indexing

Change events (via the OpenSRM change event schema) are indexed by affected service and timestamp. The change index is a continuously maintained lookup: "for service X, what changed in the last N minutes?" When a quality signal or alert fires, the candidate changes are already indexed and retrievable in O(1).

```typescript
interface ChangeCandidate {
  change: SitRepEvent;           // the change event itself
  affectedService: string;
  temporalProximity: number;     // seconds between change and signal
  sameService: boolean;          // was the change on the same service as the signal?
  dependencyRelated: boolean;    // was the change on a dependency of the signalling service?
}
```

This is index maintenance. The pre-correlation engine doesn't decide whether a change caused a problem (that's judgment for the model). It provides the candidate list with computed proximity metrics.

#### Signal Deduplication

Multiple alerts about the same underlying issue (Prometheus fires the same alert every evaluation cycle for 15 minutes) are deduplicated to a single signal with a count and duration. Deduplication key: `(source, service, alert_name_or_metric, environment)`. Events with the same dedup key within the same temporal window are collapsed.

#### Severity Pre-Scoring (Enrichment)

If events arrive without severity pre-scores (because the ingestion layer didn't have SLO context), the pre-correlation engine enriches them by looking up the service's SLO targets from the OpenSRM manifest. This is a second chance at pre-scoring, not a duplicate. Events that were already scored at ingestion keep their scores.

#### Correlation Group Assembly

The final output of the pre-correlation engine is a set of correlation groups, each representing a cluster of related signals:

```typescript
interface CorrelationGroup {
  id: string;
  priority: number;              // computed from peak severity and service tier
  summary: string;               // machine-generated summary (template, not model)
  services: string[];            // all services involved
  signals: TemporalGroup[];      // the grouped signals
  topology: TopologyCorrelation | null;  // topology links if applicable
  changeCandidates: ChangeCandidate[];   // recent changes that might explain this
  firstSeen: string;             // when the earliest event in this group occurred
  lastUpdated: string;           // when the most recent event arrived
  eventCount: number;            // total events across all signals
}
```

The `summary` field is a template-generated string, not model output. Example: "3 alerts on payment-api (latency p99 breach) with 1 recent change (deploy v2.3.1, 12 minutes ago), correlated with 2 alerts on checkout-service (dependency)." This gives the model a quick orientation before it reads the structured data.


## Snapshot Generation

The snapshot generator takes the current set of correlation groups and produces input for the model. This is where the token budget, priority tiers, caching, and differential updates apply.

### Token Budget

Every snapshot has a configurable token budget (default 4,000 tokens). The budget determines how many correlation groups the model receives. Groups are sorted by priority (computed from severity and service tier) and included until the budget is exhausted.

```typescript
interface SnapshotBudget {
  maxTokens: number;              // default 4000
  reservedForInstructions: number; // tokens reserved for system prompt (default 500)
  reservedForHistory: number;      // tokens reserved for trend context (default 500)
  availableForGroups: number;      // maxTokens - reserved amounts
}
```

If the budget is tight, lower-priority groups are dropped (not truncated). The model receives complete information about fewer groups rather than incomplete information about many groups. Partial information leads to worse judgment.

### Priority Tiers

Correlation groups are assigned to priority tiers:

| Tier | Criteria | Budget Allocation |
|------|----------|------------------|
| P0: Critical | Severity > 0.8 AND service tier is critical | Always included, even if budget exceeded |
| P1: High | Severity > 0.6 OR topology correlation with P0 group | Included if budget allows |
| P2: Medium | Severity > 0.3 | Included if budget allows after P0 and P1 |
| P3: Low | Everything else | Included only if significant budget remains |

If a P0 group alone exceeds the budget, the budget is exceeded (safety over cost). This should be rare and indicates the token budget is configured too low for the deployment's complexity.

### Snapshot Caching

In WATCHING mode (batch snapshots every 5 minutes), most cycles produce no meaningful change. The caching mechanism avoids calling the model when nothing has changed:

1. After the pre-correlation engine produces the current set of correlation groups, the snapshot generator computes a content hash of the groups (sorted by ID for determinism).
2. If the hash matches the previous cycle's hash, return the cached snapshot. No model call.
3. If the hash differs, proceed to model call with the new groups.
4. Store the new snapshot and hash for the next cycle.

**Cache invalidation:**
- Any change in correlation groups (new groups, resolved groups, changed severity, new events in existing groups) changes the hash.
- Transition to ALERT or INCIDENT mode always invalidates the cache.
- Maximum cache TTL of 15 minutes (configurable) forces a fresh evaluation even if the hash hasn't changed, catching slow-developing situations.

**Expected impact:** During quiet operations (majority of time), SitRep's model costs drop to near zero. The model is only called when something actually changes.

### Differential Snapshots

When the cache is invalidated and a new snapshot is needed, the transport layer computes the diff between the previous correlation state and the current state:

```typescript
interface CorrelationDiff {
  newGroups: CorrelationGroup[];        // not present last cycle
  resolvedGroups: string[];             // present last cycle, gone now (by ID)
  updatedGroups: Array<{
    id: string;
    changes: string[];                  // human-readable list of what changed
    currentState: CorrelationGroup;
  }>;
  unchangedGroupCount: number;          // how many groups didn't change
}
```

The model receives the diff plus the previous snapshot, and produces an updated snapshot. This is cheaper than producing a full snapshot from scratch when only one or two groups changed out of dozens.


## Model Interface

When the snapshot generator determines that a model call is needed, it assembles a prompt from the pre-correlated data. The model's job is limited to judgment that transport cannot provide:

**What the model receives:**
- Correlation groups (structured, pre-prioritised, within token budget)
- The previous snapshot (for differential assessment)
- Service context from OpenSRM manifests (SLO targets, service tiers, dependency topology)
- Trend context (summary of recent history, e.g. "this service had 3 incidents in the past 7 days")

**What the model produces:**
- A situation snapshot (structured assessment of current state)
- Causal assessment for each correlation group ("this is likely caused by the deploy 12 minutes ago" or "this correlation is temporal but probably coincidental because the services are unrelated")
- Priority ranking (which group needs attention first, and why)
- Recommended actions (what should be investigated, what can wait)
- Confidence scores on its assessments (used by the self-calibration loop)

**What the model does NOT do:**
- The model does not query the indexed store. All queries are done by transport before the model sees anything.
- The model does not compute temporal proximity, severity scores, or topology relationships. These are pre-computed.
- The model does not decide which events to look at. The priority tiers and token budget determine this.
- The model does not format the output for downstream consumers. Transport handles serialisation.

### Snapshot Output as Verdicts

The model's output is parsed into verdicts rather than a bespoke schema. Each correlation assessment becomes a verdict. The overall snapshot becomes a parent verdict linking to the individual correlations via lineage.

**Per-correlation verdict:**

Each correlation group that the model assesses produces a verdict via `verdict.create()`:

```typescript
// For each correlation group the model assesses:
verdict.create({
  subject: {
    type: "correlation",
    service: primaryAffectedService,
    ref: correlationGroupId,
    summary: "deploy v2.3.1 correlated with latency spike on payment-api"
  },
  judgment: {
    action: "flag",                    // flag | watch | escalate
    confidence: 0.74,
    reasoning: "temporal proximity 12 minutes, same dependency chain, deploy touches connection pooling config",
    tags: ["latency", "deploy", "payment-api"]
  },
  producer: {
    system: "sitrep",
    model: modelUsed
  }
});
```

**Snapshot-level verdict (parent):**

The overall snapshot is a parent verdict that links to all individual correlation verdicts and carries the overall assessment:

```typescript
verdict.create({
  subject: {
    type: "correlation",
    service: null,                     // system-wide assessment
    ref: snapshotCycleId,
    summary: "Situation snapshot: 2 active correlation groups, 1 P0"
  },
  judgment: {
    action: "escalate",               // escalate | alert | watch
    confidence: 0.68,
    reasoning: "P0 group on payment-api with recent deploy correlation. Recommend ALERT state transition."
  },
  producer: { system: "sitrep" },
  lineage: {
    children: [correlationVerdict1.id, correlationVerdict2.id]
  }
});
```

**What downstream consumers receive:**

Mayday queries the verdict store for SitRep's correlation verdicts (not a bespoke API):

```typescript
const sitrepContext = verdictStore.query({
  producerSystem: "sitrep",
  subjectType: "correlation",
  timeRange: last30Minutes,
  minConfidence: 0.3
});
```

Dashboards and human operators see correlation verdicts in the verdict feed (Grafana panels generated by NthLayer, or the `nthlayer-learn review` CLI).

**State transition recommendation:**

If the model recommends a state transition (e.g., WATCHING → ALERT), this is included in the snapshot-level verdict's reasoning and tags (e.g., `tags: ["state_transition:alert"]`). The transport layer reads the tag and makes the transition decision. This keeps state transitions as transport decisions informed by model judgment, not model-controlled.

This replaces the previous `SituationSnapshot` interface. The verdict schema is the output contract. Downstream consumers don't need to understand a SitRep-specific schema. They read verdicts.


## Agent States

SitRep operates in four states. The pre-correlation engine runs the same way in all states. What changes is the snapshot generation frequency and the model tier used.

| State | Snapshot Frequency | Model Tier | Cache TTL | Trigger |
|-------|-------------------|------------|-----------|---------|
| WATCHING | Every 5 minutes | Standard | 15 minutes | Default state |
| ALERT | Every 1 minute | Frontier | 5 minutes | Any P0 or multiple P1 correlation groups |
| INCIDENT | Every 30 seconds | Frontier | No cache | External incident declaration or Mayday activation |
| DEGRADED | Every 2 minutes | Standard | 10 minutes | SitRep's own model calls are failing or slow |

State transitions are determined by the pre-correlation engine's output (transport), not by the model. If a P0 correlation group appears, SitRep transitions to ALERT without waiting for the model's opinion. The model can recommend state transitions in its snapshot output, but the transport layer makes the immediate transition decisions.

DEGRADED mode is for when SitRep itself is having problems (model API down, store queries slow). In this state, snapshots are generated from the pre-correlated data using templates rather than model calls, providing a degraded-but-functional situational picture until the model is available again.


## Deployment Tiers

### Tier 1: Small Deployments (up to ~100 services)

```
Event Sources ──▶ WebhookIngester ──▶ SQLite FTS5 ──▶ Pre-Correlation ──▶ Model
```

- No streaming infrastructure required
- Events arrive via HTTP webhooks or polling
- SQLite as the indexed store (single file, zero dependencies)
- Handles up to ~1,000 events per hour comfortably
- Single SitRep process
- Cost: minimal (model calls only when things change, cached otherwise)

**This is where most teams start.** It works out of the box, requires no infrastructure beyond SitRep itself, and scales surprisingly far before you need to move up.

### Tier 2: Medium Deployments (~100-1,000 services)

```
Event Sources ──▶ NATS ──▶ NATSIngester ──▶ PostgreSQL ──▶ Pre-Correlation ──▶ Model
```

- NATS handles concurrent producers (hundreds of sources writing simultaneously)
- PostgreSQL handles concurrent reads from multiple SitRep instances (if running replicas for HA)
- `LISTEN/NOTIFY` for real-time event notification to the pre-correlation engine
- Handles tens of thousands of events per hour
- Can run multiple SitRep instances behind a load balancer

### Tier 3: Enterprise (~1,000+ services, millions of events/minute)

```
Event Sources ──▶ Kafka ──▶ KafkaIngester ──▶ ClickHouse ──▶ Pre-Correlation ──▶ Model
```

- Kafka for ingestion (consumer groups, partitioning, backpressure, exactly-once delivery)
- ClickHouse for the indexed store (columnar storage, time-series optimised, handles massive query volume)
- Topic/partition design maps to OpenSRM service topology
- Multiple SitRep instances with partitioned responsibility (each instance handles a subset of services)
- Full HA with failover

### What Doesn't Change Across Tiers

The pre-correlation engine, snapshot generator, model interface, and snapshot schema are identical across all three tiers. The only things that change are the ingester implementation and the store implementation. This is why the interface contracts are critical: they're the stable layer that everything above depends on.


## Integration Points

### OpenSRM Manifests

SitRep reads OpenSRM manifests for:
- Service topology (dependency graph for topology-aware grouping)
- SLO targets (for severity pre-scoring)
- Service tiers (for priority tier assignment)
- Change event schema (for normalised change ingestion)

Manifests are optional. Without them, SitRep still works but with reduced correlation quality (no topology grouping, default severity scores, no SLO-aware pre-scoring).

### Arbiter

Arbiter quality scores arrive as `quality_score` events. The pre-correlation engine treats them like any other signal: they're indexed, grouped, and correlated. When an agent's quality drops and a recent change is in the change index, SitRep correlates them. This is how "the model was swapped from Claude to Gemini 15 minutes before quality dropped" surfaces automatically.

### Mayday

When Mayday activates for an incident, it queries SitRep for the current situation snapshot. Because the snapshot is already built (pre-correlation runs continuously), Mayday gets context in milliseconds rather than waiting for a fresh analysis. SitRep transitions to INCIDENT mode (faster snapshot cycles, no caching) for the duration.

### NthLayer

NthLayer generates dashboards for SitRep's operational metrics:
- Event ingestion rate and backlog
- Pre-correlation group count over time
- Snapshot cache hit rate
- Model call frequency and token consumption
- Store size and query latency

These metrics are emitted as OTel metrics by SitRep's transport layer.

### Change Events

Change events from all sources (normalised via the OpenSRM change event schema) are first-class events in SitRep. They arrive through the same ingestion layer as everything else, are indexed in the same store, and are cross-referenced by the pre-correlation engine during change attribution. AI-specific changes (prompt updates, model version swaps, adapter deployments, formula revisions) are treated identically to traditional changes (deploys, config updates, feature flag toggles).


## Self-Calibration

SitRep measures its own judgment quality through verdict accuracy queries. Every correlation verdict the model produces is a judgment that can be measured:

- **Correlation accuracy:** `verdict.accuracy(producer="sitrep", subject_type="correlation")`. When SitRep says two signals are causally related, was that correct? Measured by human overrides (verdict resolved as overridden) and by whether the recommended actions resolved both signals (verdict resolved as confirmed).
- **Priority accuracy:** Did the model correctly identify which group needed attention first? Measured by human override patterns (humans investigated a different group first, overriding the priority).
- **State transition accuracy:** When SitRep recommended transitioning to ALERT, was that appropriate? Measured by whether an actual incident followed.

These measurements feed into the Arbiter via the same verdict accuracy mechanism used for all agents. The Arbiter queries `verdict.accuracy(producer="sitrep")` and tracks SitRep's judgment SLOs. If SitRep's correlation accuracy drops, the Arbiter detects it and can trigger governance actions.


## Interaction Contracts

SitRep declares what it provides and what it expects via a contract manifest (see ECOSYSTEM-GAPS.md for the full contract specification):

```yaml
# sitrep.contracts.yaml
component: sitrep

provides:
  correlation_verdicts:
    description: "Correlation assessments linking signals to potential causes"
    verdict_types: [correlation]
    freshness:
      watching: 5m
      alert: 1m
      incident: 30s
    availability:
      target: 0.99
    degradation:
      on_model_unavailable: "produce template-based verdicts with confidence 0.0"
      on_store_unavailable: "buffer in memory up to 1000 events, drop oldest beyond that"

consumes: {}
```

Mayday's contract for consuming SitRep verdicts is defined in MAYDAY.md. The contract validation tool (`opensrm validate-contracts`) verifies compatibility between SitRep's provides and Mayday's consumes.


## Scenario Replay

SitRep supports scenario replay for regression testing of correlation quality (see ECOSYSTEM-GAPS.md for the full scenario specification):

```bash
sitrep replay --scenario scenarios/payment-api-deploy.yaml
```

Replay ingests the scenario's event stream through the pre-correlation engine and snapshot generator, produces verdicts, and compares them against the scenario's expected outcomes. This is the regression suite for correlation quality.

Scenarios are stored in `sitrep/scenarios/` and come from three sources: real incidents (anonymised and exported from Mayday's post-incident processing), synthetic scenarios (hand-crafted to test specific correlation capabilities), and hybrid scenarios (real patterns with synthetic variations).

The pre-correlation engine (temporal grouping, topology grouping, change indexing) is fully testable via replay without a model. The model is only needed for the interpretation step, which can be mocked for transport-layer replay testing.


## Degradation Behaviour

SitRep's degradation follows the staleness policy defined in the OpenSRM manifest (see ECOSYSTEM-GAPS.md for the full staleness policy specification):

| Failure | Behaviour |
|---------|-----------|
| Model API unavailable | Enter DEGRADED state. Pre-correlation continues (transport). Produce template-based correlation verdicts with `confidence: 0.0`. Resume model-based verdicts when API recovers. |
| Event store unavailable | Buffer events in memory up to configured max. Drop oldest beyond that. Produce verdicts noting "operating from in-memory buffer, limited history". Flush buffer when store recovers. |
| OTel Collector unavailable | Buffer OTel events locally. Verdict creation and storage continue (separate path from OTel emission). |
| Webhook ingester overloaded | Return 429 (rate limit). Events may be lost. Emit `sitrep_ingestion_dropped_total` metric via fallback path. |
| Prometheus unavailable | Pre-correlation operates without live metric enrichment. Severity pre-scoring uses SLO targets from manifest only (no comparison against current values). |


## Implementation Priority

Build these in order:

1. **Event schema and store interface.** Define the `SitRepEvent` type (including `verdict` as an event type), the `EventStore` interface, and the `CorrelationGroup` type. These are the contracts that everything else depends on.

2. **SQLite FTS5 store implementation.** The default backend. Schema, FTS5 indexes, insert, query, search, TTL cleanup. Test thoroughly since this is the foundation.

3. **WebhookIngester.** HTTP server that accepts events and writes them to the store. Simplest ingestion path, gets the pipeline working end to end.

4. **Pre-correlation engine.** Temporal grouping, deduplication, severity pre-scoring, correlation group assembly. This can be tested against the SQLite store with synthetic events without needing a model.

5. **Change indexing.** Extend the pre-correlation engine with the change candidate lookup. Test with synthetic change events correlated against synthetic alert events.

6. **Topology-aware grouping.** Requires OpenSRM manifest parsing. Extend the pre-correlation engine to cross-reference events against the dependency graph.

7. **Snapshot generator with caching.** Token budget, priority tiers, content hashing, cache invalidation. Can be tested with mock model responses. Output is verdict creation, not a bespoke schema.

8. **Verdict integration.** Add verdict library as a dependency. Snapshot generator produces correlation verdicts via `verdict.create()` with lineage. OTel events emitted automatically as side-effect.

9. **Model interface.** Prompt assembly, response parsing into verdict fields. This is where the model gets wired in.

10. **Agent state machine.** WATCHING/ALERT/INCIDENT/DEGRADED transitions, frequency changes, model tier routing. Degradation produces template-based verdicts with `confidence: 0.0`.

11. **Contract manifest and scenario replay.** Declare SitRep's contract. Implement `nthlayer-correlate replay` for regression testing.

12. **Differential snapshots.** Correlation diff computation, differential prompt assembly. Optimisation that builds on the caching layer.

13. **NATSIngester and PostgreSQL store.** Tier 2 implementations. Same interfaces, different backends.

14. **KafkaIngester and ClickHouse store.** Tier 3 implementations. Same interfaces, different backends.

Items 1-9 constitute a working Tier 1 SitRep with verdict output. Items 10-11 add operational maturity. Items 12-14 are optimisations and scale-up paths.


## Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| **VERDICT.md** | SitRep produces correlation verdicts. The verdict schema is the output format. |
| **VERDICT-INTEGRATION.md** | Details the specific code changes for integrating verdicts into SitRep. |
| **MAYDAY.md** | Mayday consumes SitRep's correlation verdicts as incident context. Mayday's contract for consuming SitRep is defined there. |
| **ECOSYSTEM-GAPS.md** | Contract manifests, scenario replay, staleness policy, and notification configuration that SitRep participates in. |
| **COSTOPTIMISATION.md** | Pre-correlation is Priority 1. Snapshot caching (Priority 4), differential snapshots (Priority 6), and model routing by agent state (Priority 5) are specified in both documents. |
| **BRIEF.md** | SitRep's component description, README structure, and ecosystem context. |
