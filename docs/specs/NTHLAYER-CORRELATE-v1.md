# nthlayer-correlate — v1-draft

**Status:** Draft for implementation
**Date:** 2026-04-19
**Scope:** NthLayer reference implementation; not part of OpenSRM specification

---

## 1. Purpose

nthlayer-correlate is the continuous signal-correlation component of the NthLayer ecosystem. It consumes alerts and observability signals, groups related signals into situational snapshots with natural-language summaries, and surfaces correlation-shaped findings (topology drift, contract divergence, cascading failures) as verdicts consumable by downstream components.

The component exists because raw alert streams produce operator overload. Grouping related signals into fewer, larger situational snapshots reduces that overload, and adding natural-language summaries makes the snapshots comprehensible without requiring operators to manually reassemble context.

## 2. Position in the Pipeline

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ observe  │ ─→  │ measure  │ ─→  │correlate │ ─→  respond
└──────────┘     └──────────┘     └──────────┘
                                       ↑
                                       │ (also consumes)
                                       │
                            ┌──────────┴──────────┐
                            │ External alerts     │
                            │ OTel servicegraph   │
                            │ OpenSRM manifests   │
                            └─────────────────────┘
```

Inputs:
- Assessments from nthlayer-observe (SLO status, burn rates, drift signals)
- Judgment-SLO evaluations from nthlayer-measure
- External alerts via a PD-CEF-compatible ingest endpoint
- OTel servicegraph connector metrics (observed topology)
- OpenSRM manifests (declared topology, dependencies, contracts)

Outputs:
- Correlation-snapshot assessments with natural-language summaries
- Topology-drift verdicts (declared-not-observed, observed-not-declared)
- Contract-divergence verdicts (promise versus actual)
- Cascade findings (when related symptoms span services)

## 3. Architectural Thesis

Three load-bearing choices distinguish nthlayer-correlate from conventional alert aggregators:

**Declarative topology as ground truth, observed topology as reality check.** OpenSRM manifests tell us what services depend on what; OTel servicegraph tells us what actually calls what. The correlate engine uses both and flags the delta.

**Continuous pre-correlation, not on-demand query.** Alerts are grouped into situational snapshots continuously as they arrive, via a streaming dataflow. Operators consuming snapshots see pre-computed groupings, not ad-hoc query results. This is the shape where the natural-language summary becomes tractable — you're summarising a snapshot that already coheres, not inferring structure on the fly.

**Natural-language summary is the output shape.** The snapshot is a structured object; the summary is prose. Downstream components (Bench, respond's triage agent) consume both, preferring the summary for human-legibility and the structure for machine processing. This is the "humans read prose, not graphs" thesis applied to correlation.

## 4. Streaming Substrate: Bytewax

### 4.1 Why Bytewax

Bytewax (bytewax/bytewax, Apache-2.0) is a Python-native streaming dataflow engine with a Rust core (Timely Dataflow). Three properties matter for nthlayer-correlate:

- **Python-first.** The dataflow is defined in Python, not via a Python SDK over a Java/Scala engine. The NL summarisation logic and the LLM integration live naturally alongside the streaming logic.
- **Session windows via `fold_window`.** The "group related signals within a short time of each other" primitive is a session window. Bytewax's `fold_window` supports event-time and processing-time session windows directly.
- **Active maintenance.** Regular commits through 2025, issue triage through April 2026.

Alternatives rejected: Faust-streaming (thin maintenance, Kafka-only), PyFlink (JVM overhead, wrong tool), Apache Beam (too heavyweight), custom asyncio (loses the dataflow abstractions that make the code comprehensible).

### 4.2 Dataflow shape

```python
from bytewax.dataflow import Dataflow
from bytewax.operators import input, fold_window, map
from bytewax.operators.window import SessionWindower, EventClockConfig

flow = Dataflow("correlate")

# Input: PD-CEF alerts from the shared store's alert table
alerts = input("alerts", flow, AlertSource())

# Group into session windows keyed by service + correlation-domain
#   correlation-domain is derived from manifest ownership + dependency graph
keyed = map("key_alerts", alerts, key_by_correlation_domain)

# Session window: alerts within 60s of each other in the same domain
windowed = fold_window(
    "session_group",
    keyed,
    clock=EventClockConfig(dt_getter=lambda a: a.timestamp, wait_for_system_duration=timedelta(seconds=30)),
    windower=SessionWindower(gap=timedelta(seconds=60)),
    builder=lambda: SituationSnapshot(),
    folder=lambda snapshot, alert: snapshot.add(alert),
)

# Enrich: add topology context, declared-vs-observed drift
enriched = map("enrich", windowed, enrich_with_topology)

# Summarise: LLM produces NL description of the snapshot
summarised = map("summarise", enriched, summarise_with_llm)

# Output: write snapshot verdicts to the store
output("snapshots", summarised, SnapshotSink())
```

### 4.3 State persistence

Bytewax supports checkpointing to external state stores. nthlayer-correlate persists window state to SQLite (same shared store as the rest of the pipeline) so windows survive component restarts. Session windows that haven't yet closed at restart time resume from their last-checkpointed state.

## 5. Input: PD-CEF Alert Schema

All alerts entering correlate conform to a PD-CEF superset. The PD-CEF core fields are:

```json
{
  "summary": "payment-service error rate above threshold",
  "source": "prometheus",
  "severity": "critical",
  "component": "payment-service",
  "group": "payments",
  "class": "latency",
  "custom_details": { "p99_latency_ms": 2100 },
  "dedup_key": "payment-service:error-rate",
  "timestamp": "2026-04-19T09:32:15Z"
}
```

NthLayer-specific extensions live under `nthlayer.alert.*`:

```json
{
  "nthlayer.alert.service_cid": "bafyrei...",
  "nthlayer.alert.slo_cid": "bafyrei...",
  "nthlayer.alert.burn_rate": 47.2,
  "nthlayer.alert.contract_ref": "contract:payments/authorisation"
}
```

### 5.1 Ingest paths

Three paths to get alerts into the PD-CEF format:

**Direct producers.** nthlayer-observe and nthlayer-measure write assessments in PD-CEF form directly. No translation needed.

**Webhook ingest.** `POST /alerts` accepts PD-CEF-conformant JSON. Prometheus Alertmanager, Grafana, external incident systems can all produce PD-CEF-compatible webhooks or be wrapped in a thin translator.

**OTel log bridge.** OTel log records can be mapped to PD-CEF fields via the OTel Collector's transform processor. This is how NthLayer integrates with organisations that have an OTel-centric observability stack.

### 5.2 Deduplication

Alerts with the same `dedup_key` within a configurable window (default 60 seconds) are deduplicated at ingest. The dedup cache is persisted in the component_state table so dedup survives restarts.

## 6. Topology Integration

### 6.1 Declared topology

From OpenSRM manifests: a service's `dependencies` block declares what other services it depends on, with expected contracts. correlate loads all manifests at startup and on change events, building an in-memory graph keyed by service reference.

### 6.2 Observed topology

From OTel servicegraph connector metrics:

- `traces_service_graph_request_total{client="A",server="B"}` — edge count
- `traces_service_graph_request_server_seconds{client="A",server="B"}` — latency histogram
- `virtual_node_peer_attributes` — external dependencies

These metrics are scraped from the configured Prometheus endpoint on the same cycle as nthlayer-observe's SLO computation.

### 6.3 Drift detection

On each processing cycle, correlate compares declared to observed:

- **Declared edge, not observed.** Manifest says A → B; no traffic seen. Could be dead code, manifest error, or new service not yet receiving traffic.
- **Observed edge, not declared.** Traffic seen A → C; manifest doesn't mention C. Undocumented dependency — caller is exposed to a risk they don't know about.
- **Guarantee mismatch.** A declares expected availability 99.9% from B; B's contract promises 99.5%. Caller is exposed.

Drift findings are emitted as `topology_drift` verdicts with structured `before`/`after` and a prose explanation.

### 6.4 Graph library

`networkx` for the in-memory graph. Its API is well-known, performance is adequate for up to a few thousand services, and the algorithms (transitive closure, reachability, shortest path for cascade reasoning) are mature.

## 7. Situation Snapshots

### 7.1 Shape

```python
@dataclass
class SituationSnapshot:
    cid: CID
    created_at: datetime
    window_start: datetime
    window_end: datetime

    # Signals in the window
    alerts: list[Alert]
    assessments: list[Assessment]

    # Topology context
    affected_services: list[ServiceRef]
    blast_radius: list[ServiceRef]  # services transitively dependent on affected set

    # Declared context
    active_contracts: list[ContractRef]
    contract_divergences: list[ContractDivergence]

    # Natural-language summary
    summary: str              # produced by LLM
    confidence: float         # LLM's confidence in the summary

    # Correlations drawn
    correlations: list[Correlation]
```

### 7.2 Correlation types

Four correlation types are identified by the current dataflow:

**Temporal.** Multiple alerts in the same window targeting related services.
**Topological.** Alerts in the blast radius of a common upstream failure.
**Contractual.** Alerts that match the breach semantics of a declared contract.
**Pattern-match.** Alerts matching a previously-recorded situation signature (future work — see §13).

### 7.3 Blast radius computation

Given a set of affected services S, the blast radius is the set of services in the declared-topology graph that transitively depend on any service in S. Computed with networkx's `descendants()`.

This is the *declared* blast radius. The observed blast radius (which callers actually broke) is visible in subsequent windows as alerts propagate. The gap between declared blast radius (theoretical) and observed blast radius (actual) is itself a signal — either callers are more resilient than expected (and the declared expectation is overstated) or less resilient (and graceful-degradation declarations aren't being honoured).

## 8. Natural-Language Summary

### 8.1 Shape of the task

Given a situation snapshot — a structured object with alerts, topology context, and correlations — produce a short prose summary an operator can read in 10 seconds and understand the current state.

### 8.2 Prompt construction

The snapshot is serialised to a compact prompt with three sections:

1. **What's happening.** The alert summaries, severity, affected services.
2. **What it connects to.** The topology — which services are upstream, which downstream, which contracts are active.
3. **What's notable.** The correlations the dataflow drew, the drift findings, the contract divergences.

The LLM is asked to produce a 2-4 sentence summary in operator-legible language. Explicit instructions:

- Lead with the most impactful fact
- Prefer service names and concrete numbers over generalities
- Name the blast radius if it crosses service boundaries
- Do not speculate on root cause unless the correlation is explicit in the input
- Do not recommend actions (that's respond's job)

### 8.3 LLM call

Via the nthlayer-common LLM wrapper with Instructor for structured output:

```python
class SnapshotSummary(BaseModel):
    summary: str = Field(max_length=500, description="2-4 sentence operator-legible summary")
    confidence: float = Field(ge=0.0, le=1.0, description="LLM's confidence the summary is accurate")
    notable_omissions: list[str] = Field(default_factory=list, description="Things the LLM thinks it lacks context for")

response = await llm.complete(
    prompt=snapshot_to_prompt(snapshot),
    response_model=SnapshotSummary,
    model=config.summary_model,  # typically a smaller, faster model
)
```

The Instructor wrapper handles JSON-mode validation, retry on schema violation, and partial streaming if the model supports it.

### 8.4 Quality measurement

Summary quality is measurable: nthlayer-measure evaluates a sample of summaries against operator reactions (did they correctly identify the situation? did they miss something important?). The summariser is itself an agent subject to a judgment SLO. Summary quality that drops below threshold triggers the autonomy ratchet (see nthlayer-measure spec).

## 9. Output: Verdicts

correlate emits three verdict types:

### 9.1 correlation_snapshot

The primary output. Written on each closed session window.

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.verdict.correlation_snapshot.v1",
  "source": "urn:nthlayer:correlate:eu-west",
  "id": "bafyrei...cid",
  "time": "2026-04-19T09:32:15Z",
  "data": {
    "nthlayer.snapshot.window_start": "2026-04-19T09:31:00Z",
    "nthlayer.snapshot.window_end": "2026-04-19T09:32:00Z",
    "nthlayer.snapshot.affected_services": ["payment-service", "checkout-service"],
    "nthlayer.snapshot.blast_radius": ["payment-service", "checkout-service", "notification-service"],
    "nthlayer.snapshot.alert_count": 7,
    "nthlayer.snapshot.summary": "...",
    "nthlayer.snapshot.correlations": [...]
  }
}
```

### 9.2 topology_drift

Emitted when declared and observed topology diverge.

```json
{
  "type": "io.nthlayer.verdict.topology_drift.v1",
  "data": {
    "nthlayer.drift.type": "observed_not_declared",
    "nthlayer.drift.caller": "checkout-service",
    "nthlayer.drift.callee": "fraud-detection",
    "nthlayer.drift.evidence_window": "24h",
    "nthlayer.drift.request_count": 12847
  }
}
```

### 9.3 contract_divergence

Emitted when observed reliability of a dependency diverges from its contract.

```json
{
  "type": "io.nthlayer.verdict.contract_divergence.v1",
  "data": {
    "nthlayer.divergence.contract_ref": "contract:fraud/fraud-check-api",
    "nthlayer.divergence.promised_availability": 0.995,
    "nthlayer.divergence.observed_availability": 0.987,
    "nthlayer.divergence.measurement_window": "24h",
    "nthlayer.divergence.dependent_services": ["payment-service", "checkout-service"]
  }
}
```

## 10. State and Persistence

Per the serve-mode base pattern:

- Bytewax window state is checkpointed to SQLite every 30 seconds
- Dedup cache is persisted in `component_state.dedup_cache`
- Graph state is reconstructed from OpenSRM manifests at startup (idempotent rebuild)
- Heartbeats every 10 seconds with state payload including `active_windows`, `snapshots_produced_last_cycle`, `summarisation_latency_p99_ms`

## 11. Performance Characteristics

Order-of-magnitude expectations for a mid-sized deployment (~500 services, ~1000 alerts per hour at baseline, bursts to ~100 alerts per minute during incidents):

- Alert ingest to window membership: < 100ms p99
- Window close to snapshot produced: < 500ms p99 (dominated by topology enrichment)
- Snapshot to summary: 1-3 seconds p99 (dominated by LLM call)
- End-to-end alert-to-snapshot latency: < 5 seconds p99

LLM calls are the bottleneck. Use of a smaller, faster model for summarisation (Claude Haiku or GPT-4o-mini tier) is intentional — the larger models don't materially improve summary quality at this shape of task and their latency hurts.

## 12. Failure Modes

**LLM unavailable.** correlate continues to produce snapshot verdicts without summaries; downstream components degrade to consuming the structured content only. Summary quality-SLO breach is emitted.

**Bytewax window corruption.** Checkpoint restore fails. correlate drops to empty state and re-builds windows from fresh alerts. Historical windows are lost (acceptable — alerts are in the store anyway).

**OTel servicegraph unavailable.** Topology drift detection is paused. Declared topology still informs blast-radius reasoning. A degraded-input verdict is emitted so operators see "topology drift cannot be detected right now."

**OpenSRM manifest unparseable.** The specific service is excluded from topology reasoning; other services unaffected. Manifest-error verdict emitted.

**Alert burst beyond Bytewax throughput.** Back-pressure builds in the input queue. At a configurable threshold, alerts are dropped with a suppression audit record. Alternative is to over-provision the dataflow workers.

## 13. Future Work

**Pattern-match correlations.** When a situation matches a previously-recorded snapshot signature, emit a "this looks like $prior_incident" correlation with a link to the prior case. Requires a signature function over snapshots (probably embedding-based) and a similarity search. Not v1.

**Active-incident-aware windowing.** During an active incident, the session-gap shortens (aggregate more aggressively). On incident resolution, gap returns to baseline. Simple heuristic, probably v1.5.

**Cross-deployment correlation.** Multiple NthLayer deployments (dev/staging/prod, or multi-region prod) sharing correlation-relevant signals. Out of scope for v1 but a natural extension.

## 14. References

- Bytewax: https://bytewax.io/
- PD-CEF: https://support.pagerduty.com/docs/pd-cef
- OTel servicegraph connector: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/connector/servicegraphconnector
- networkx: https://networkx.org/
- Instructor: https://github.com/567-labs/instructor
- OpenSRM v2 (source of declared topology)
- OpenSRM serve mode v2.1 (store, heartbeats, base pattern)

## 15. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1-draft | 2026-04-19 | Initial spec |
