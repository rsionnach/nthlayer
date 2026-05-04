# NthLayer Cross-Component Integration Spec (v3)

## Status

All five components pass individual test suites (4,419 tests). Cross-component integration is tested indirectly through replay scenarios with mocked upstream outputs. No live chain exists from measure → correlate → respond → learn.

This spec is split into two clearly separated work streams:

- **Part A: Core Integration** — product features that ship to users. Cross-component wiring, verdict types, CLI modes, and OTel alignment. This is the priority.
- **Part B: Test & Demo Infrastructure** — fake services, Docker Compose, scenario runners, and end-to-end test scripts. These validate Part A and enable the real demo. They are not product features. They are built after Part A is functionally complete.

## Critical Instruction for Claude Code

**Before implementing any section of this spec, audit the existing code.** Every section includes an "Audit First" block that lists specific files, classes, schemas, and output formats to inspect. The schemas and CLI examples in this spec are proposals based on external analysis. The existing code is the authority. Where the existing implementation already covers a capability, extend it. Do not create parallel structures.

Specifically:
- Read the existing verdict schema and its field definitions before proposing verdict type extensions
- Read the existing nthlayer-measure adapters and output formats before building the Prometheus polling mode
- Read the existing nthlayer-correlate replay scenario fixtures to understand what input format correlate already expects
- Read the existing nthlayer-respond coordinator and its input expectations
- Read the existing nthlayer-learn CLI and its incident/verdict query interface
- Read the existing nthlayer-generate Prometheus rule templates to extract the actual metric names and PromQL expressions

Do not assume the proposals in this spec are correct. Verify against the code, adapt where needed, and document any deviations.

---

# PART A: CORE INTEGRATION

---

## A1. Verdicts as the Universal Data Format

### Principle

The verdict is the fundamental data unit of the NthLayer ecosystem. Every component makes a judgment. Every judgment is a verdict. The verdict store is the integration layer. Components do not pass files to each other; they read from and write to the shared verdict store. The trigger chain (measure invoking correlate as a subprocess) still exists for control flow, but the data handoff happens through the store.

### Verdict Types

The existing verdict schema was designed for AI decision tracking (action, confidence, outcome, override). The cross-component integration requires additional verdict types for infrastructure judgments. Each type uses the common verdict fields (id, timestamp, service, confidence, evidence, lineage) but adds type-specific fields.

**Proposed verdict types:**

| Type | Written by | Purpose |
|------|-----------|---------|
| `decision` | External (AI agents) | An AI agent made a decision. Existing type. |
| `evaluation` | nthlayer-measure | Measure assessed a service's SLO state (judgment or traditional). |
| `correlation` | nthlayer-correlate | Correlate identified a root cause from correlated signals. |
| `incident` | nthlayer-respond | Respond opened (or updated) an incident. |
| `retrospective` | nthlayer-learn | Learn captured the post-incident analysis and spec recommendations. |

**Common fields (all verdict types):**

```
id              — unique verdict identifier (existing)
timestamp       — when the judgment was made (existing)
service         — the service this verdict concerns (existing)
confidence      — how confident the component is in this judgment (existing)
evidence        — array of supporting data points (existing)
lineage.context — references to prior verdicts that informed this one (existing)
lineage.children — subsequent verdicts that reference this one (existing)
verdict_type    — NEW: one of decision | evaluation | correlation | incident | retrospective
```

**Type-specific fields (proposals — verify against existing schema):**

`evaluation` verdicts:
```
slo_type        — "judgment" | "traditional"
slo_name        — "reversal_rate" | "error_budget_burn" | "latency_p99" | etc.
target          — the declared SLO target from the spec
current_value   — the measured value
breach           — true | false
consecutive     — number of consecutive evaluation windows above/below threshold
autonomy_action — { previous, new } if the ratchet was triggered, null otherwise
related_signals — array of compound signals (model version change, confidence shift, etc.)
```

`correlation` verdicts:
```
trigger_verdict  — the evaluation verdict ID that triggered this correlation
root_causes      — array of { service, type, confidence, evidence }
blast_radius     — array of { service, impact: "direct" | "downstream", slo_breached }
timeline         — reconstructed event timeline
```

`incident` verdicts:
```
incident_id     — human-readable incident identifier (INC-4821)
severity        — integer
status          — "open" | "closed"
closed_at       — timestamp (null while open)
root_cause      — { service, type, correlation_verdict_id }
blast_radius    — array of affected services
actions_taken   — array of { type, detail }
```

`retrospective` verdicts:
```
incident_verdict_id — the incident verdict this retrospective analyses
duration_minutes    — incident duration
decisions_affected  — count of decisions made at degraded quality
financial_impact    — { estimated, currency, failure_mode, volume_source } (if outcomes block exists)
recommendations     — array of spec change recommendations
```

### How the Verdict Chain Tells the Story

For a single incident, the verdict chain looks like:

```
evaluation verdict (measure)
  ↑ lineage.context
correlation verdict (correlate)
  ↑ lineage.context
incident verdict (respond)
  ↑ lineage.context
retrospective verdict (learn)
```

Walking the lineage from the retrospective back to the evaluation tells the complete story: what was detected, what was the root cause, what action was taken, and what was learned. This is the audit trail. This is what the live topology event feed displays.

### Audit First

Before implementing verdict types, Claude Code must:
1. Read the existing verdict schema definition (likely in nthlayer-learn or nthlayer-measure). Document every field, its type, and which components currently read/write it.
2. Determine whether `verdict_type` or an equivalent discriminator already exists.
3. Identify whether the existing schema can accommodate the type-specific fields via an extensible `metadata` or `detail` object, or whether the schema needs new top-level fields.
4. Check how the verdict store (SQLite) is structured. Are verdicts stored in a single table or multiple? What indexes exist on `lineage.context`?
5. Check whether nthlayer-correlate currently reads from the verdict store at all, or only from fixtures.
6. Document findings before proposing implementation.

---

## A2. OTel Semantic Conventions for Metrics

### Principle

NthLayer is OTel-native. The metrics that services export, the recording rules that nthlayer-generate produces, and the queries that nthlayer-measure executes should all reference OpenTelemetry semantic conventions for GenAI, not custom metric names.

### The Three-Column Metrics Contract

The metrics alignment table has three columns:

| OTel Semantic Convention | Prometheus Metric Name (after OTel Collector export) | nthlayer-generate Recording Rule Output |
|--------------------------|------------------------------------------------------|----------------------------------------|
| `gen_ai.client.operation.duration` | `gen_ai_client_operation_duration_seconds` (histogram) | (used in latency SLO recording rules) |
| `gen_ai.decision` event counter | `gen_ai_decisions_total{service, action}` | (used in reversal rate denominator) |
| `gen_ai.override` event counter | `gen_ai_overrides_total{service}` | (used in reversal rate numerator) |
| `gen_ai.override` with confidence > threshold | `gen_ai_overrides_hcf_total{service}` | (used in HCF rate numerator) |
| `gen_ai.evaluation.score.value` | `gen_ai_evaluation_score{service}` (histogram) | (used in confidence calibration) |
| Standard HTTP metrics | `http_server_request_duration_seconds` (histogram) | (used in latency SLO recording rules) |
| Standard HTTP metrics | `http_server_requests_total{status}` | (used in error rate SLO recording rules) |

**This table is a proposal.** The actual OTel conventions may have different attribute names, and the Prometheus export mapping depends on the OTel Collector's Prometheus exporter configuration. The table must be verified against:
1. The actual OTel GenAI semantic conventions (https://opentelemetry.io/docs/specs/semconv/gen-ai/)
2. The OTel Collector Prometheus exporter's naming rules
3. What nthlayer-generate actually produces today

### What This Means for Each Component

**nthlayer-generate:** The PromQL in recording rules and alerting rules must reference the OTel-derived Prometheus metric names, not custom names. If generate currently uses custom metric names, the templates need updating.

**nthlayer-measure:** The Prometheus queries in the polling mode must reference the same OTel-derived names. Measure queries the recording rule outputs (which nthlayer-generate produced) and the raw OTel-derived metrics.

**Fake services (Part B):** Must export metrics with names matching the OTel Collector Prometheus export convention. The simplest path is to use the `prometheus_client` library with metric names that match what an OTel Collector would produce. The purist path is to have fake services emit OTel metrics to a real OTel Collector which exports to Prometheus. For the initial integration, the simple path is fine as long as the names match.

### Audit First

Before implementing OTel alignment, Claude Code must:
1. Run `nthlayer generate` against a representative ai-gate spec and a traditional service spec
2. Extract every metric name referenced in the generated PromQL (inputs) and every recording rule output name
3. Compare to the OTel GenAI semantic conventions
4. Compare to the OTel Collector Prometheus exporter naming convention
5. Document the gaps: which metric names in the generate templates are custom vs OTel-aligned?
6. Determine the scope of change: is it a template variable rename, or a structural change to the PromQL?
7. Document findings before proposing changes

---

## A3. nthlayer-measure: Prometheus Polling Mode

### Problem

nthlayer-measure currently evaluates data passed to it via adapters and test fixtures. It needs the ability to poll Prometheus directly, read both traditional alert state and judgment SLO metrics, and write evaluation verdicts when thresholds are crossed.

### New CLI Modes

```bash
# Single evaluation cycle (for testing and scripting)
nthlayer measure --evaluate-once \
  --prometheus-url http://localhost:9090 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db

# Continuous evaluation loop (for production)
nthlayer measure --watch \
  --prometheus-url http://localhost:9090 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db \
  --eval-interval 30s
```

`--evaluate-once` is the priority. Build it before `--watch`.

### Evaluation Logic

Each evaluation cycle:

**Step 1: Read traditional alert state.**

Query Prometheus: `ALERTS{alertstate="firing"}`

Returns every currently-firing alert with its labels. Prometheus's own `for` duration has already handled basic flapping. No AlertManager involvement. Parse alert labels to extract service name, SLO type, severity, current value, threshold.

**Step 2: Read judgment SLO metrics.**

For each ai-gate service in the specs, query the recording rule output metrics (names determined by the A2 metrics contract). Compare to targets declared in the OpenSRM spec.

**Step 3: Evaluate with hysteresis.**

For judgment SLOs:
- **Breach detection:** metric exceeds threshold for N consecutive evaluation windows (configurable, default 3)
- **Recovery detection:** metric below threshold for M consecutive windows (configurable, default 5)
- Asymmetric to prevent oscillation

For traditional SLOs:
- Prometheus's `for` duration already handles hysteresis. Measure reads `ALERTS{}` which only contains alerts that survived the `for` window. No additional hysteresis from measure.

Hysteresis state persists between evaluation cycles via the verdict store or a state file.

**Step 4: Compound conditions (enhancement, not blocker).**

When a judgment SLO breach is detected, check for correlated signals: model version change, confidence distribution shift. Include in the evaluation verdict's `related_signals`. Initial implementation can skip this and emit a verdict with empty `related_signals`.

### Outputs

- Write an `evaluation` verdict to the verdict store for each detected breach or state change
- Trigger the autonomy ratchet when judgment SLO error budget is exhausted (write autonomy change to the verdict)
- Log evaluation summary

### Audit First

Before implementing, Claude Code must:
1. Read the existing nthlayer-measure adapters (webhook, gastown, devin). How do they receive data? What do they output?
2. Read the existing evaluation pipeline. What does measure currently produce when it detects an issue?
3. Read the existing governance module. How does the autonomy ratchet currently work? What triggers it? What does it write?
4. Read the existing verdict integration in measure. How does measure currently write verdicts? What fields does it populate?
5. Read the existing trend tracking. Does measure already maintain state between evaluations?
6. Determine how much of the Prometheus polling logic can be implemented as a new adapter alongside the existing ones vs requiring changes to the core evaluation pipeline.
7. Document findings before implementing.

### Tests (Unit/Component Level, Mocked Prometheus)

1. Healthy metrics → no evaluation verdict with breach=true
2. Judgment SLO above threshold for N windows → evaluation verdict emitted
3. Judgment SLO above threshold for N-1 windows → no breach (hysteresis)
4. Traditional alert in ALERTS{} → evaluation verdict with slo_type "traditional"
5. Flapping around threshold → hysteresis prevents oscillation
6. Recovery after M windows → recovery verdict
7. Autonomy ratchet triggers on error budget exhaustion
8. State persistence between `--evaluate-once` invocations

---

## A4. nthlayer-correlate: Live Data Sources + Verdict Store Integration

### Problem

nthlayer-correlate runs against replay fixtures. It needs to read from real Prometheus and the real verdict store, and write its own correlation verdicts.

### Changes Required

```bash
nthlayer correlate \
  --trigger-verdict <verdict-id> \
  --prometheus-url http://localhost:9090 \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db
```

When triggered (either by measure's subprocess invocation or manually):

1. Read the trigger verdict from the verdict store (the `evaluation` verdict that detected the breach)
2. Read the dependency graph from OpenSRM specs
3. Query Prometheus for correlated signals across the blast radius (error rate, latency, judgment metrics per service). Query window: 30 minutes before the trigger verdict's timestamp to now.
4. Read the verdict store for recent `decision` and `evaluation` verdicts on affected services (quality context, confidence trends)
5. Run the existing correlation algorithm (temporal grouping, topology grouping, change indexing, dedup)
6. Write a `correlation` verdict to the verdict store with `lineage.context` referencing the trigger evaluation verdict

### The Gap to Close

Identify every place in correlate's code where data is loaded from fixtures. Each needs a conditional path: if `--prometheus-url` and `--verdict-store` are provided, query live; otherwise, use fixtures. Replay scenarios must continue working.

### Audit First

Before implementing, Claude Code must:
1. Read the existing correlate CLI entry point. What flags does it accept? What input format does it expect?
2. Read the replay scenario fixtures. What structure does the fixture data have? What fields does correlate read from it?
3. Read the event store module. How does correlate currently ingest events?
4. Read the snapshot generation module. What does correlate currently output? In what format?
5. Determine whether correlate already reads from a verdict store or only from event fixtures
6. Map every fixture read to the equivalent Prometheus query or verdict store query
7. Document findings before implementing.

### Tests (Mocked Prometheus HTTP Responses)

1. Trigger verdict for fraud-detect, mocked degraded metrics → correlation verdict with root cause fraud-detect
2. Trigger verdict for payment-api (downstream), mocked upstream degradation → traces to fraud-detect
3. Trigger verdict with healthy metrics everywhere → low-confidence or no root cause
4. Verdict store contains quality context → included in correlation evidence
5. Correlation verdict's `lineage.context` correctly references the trigger evaluation verdict

---

## A5. nthlayer-respond: Verdict Store Integration

### Problem

nthlayer-respond needs to read correlate's verdict from the verdict store and write its own incident verdict.

### Changes Required

```bash
nthlayer respond \
  --trigger-verdict <verdict-id> \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db \
  --notify stdout
```

Respond reads the correlation verdict from the store, determines severity from root cause and blast radius, and:

1. Writes an `incident` verdict to the verdict store with `lineage.context` referencing the correlation verdict
2. Sends notifications via configured channel

### Notification Channels

`--notify stdout` (prints payload), `--notify-webhook <url>` (HTTP POST). Not hardcoded to any specific system.

### Audit First

Before implementing, Claude Code must:
1. Read the existing respond coordinator state machine. What input does it currently expect?
2. Read the existing approval flow. Does respond already interact with a verdict store?
3. Read the safe action registry. What actions can respond currently take?
4. Read the replay scenario inputs. What format does respond currently consume?
5. Determine the minimal change to have respond read from the verdict store instead of (or in addition to) its current input format
6. Document findings before implementing.

### Tests

1. Correlation verdict in store → incident verdict written with correct severity and blast radius
2. Correlation verdict with no root causes → low-severity incident or skip (configurable)
3. Notification payload on stdout contains incident ID, root cause, blast radius
4. Incident verdict's `lineage.context` references the correlation verdict

---

## A6. nthlayer-learn: Verdict Chain Consumption

### Problem

nthlayer-learn needs to consume the full verdict chain for a closed incident and produce a retrospective verdict.

### Changes Required

```bash
nthlayer learn \
  --incident-verdict <verdict-id> \
  --specs-dir ./specs/ \
  --verdict-store ./verdicts.db
```

Learn reads the incident verdict, walks `lineage.context` back through the correlation and evaluation verdicts, queries the verdict store for all `decision` verdicts during the incident window, and produces:

1. A `retrospective` verdict in the verdict store with `lineage.context` referencing the incident verdict
2. The retrospective includes: timeline (reconstructed from the verdict chain), root cause detail, blast radius, verdict count, duration, and financial_impact (if the service has an `outcomes` block)
3. Spec recommendations (if implemented per the missing capabilities spec)

### Audit First

Before implementing, Claude Code must:
1. Read the existing learn CLI. What flags does it accept? How does it currently receive incident data?
2. Read the existing verdict CRUD. What query capabilities exist?
3. Read the existing accuracy queries. How does learn currently analyse verdict data?
4. Determine whether learn already walks verdict lineage or only queries by time window
5. Determine the format of learn's current output (retrospective). Is it JSON, markdown, or something else?
6. Document findings before implementing.

### Tests

1. Closed incident verdict in store with full lineage chain → retrospective verdict with correct timeline and root cause
2. Verdict store populated with decision verdicts during incident window → retrospective includes verdict count
3. Service with `outcomes` block → financial_impact present in retrospective
4. Service without `outcomes` block → financial_impact absent, no errors
5. Retrospective verdict's `lineage.context` references the incident verdict

---

## A7. Trigger Chain

### Problem

When measure detects a breach, correlate needs to run. When correlate produces a verdict, respond needs to run.

### Design

**Direct subprocess invocation.** Measure writes an evaluation verdict, then invokes `nthlayer correlate --trigger-verdict <id>` as a subprocess. Correlate writes a correlation verdict, then invokes `nthlayer respond --trigger-verdict <id>` as a subprocess.

The data handoff happens through the verdict store. The subprocess invocation is the control flow. Each component reads its input from the store and writes its output to the store.

**Learn is not in the automatic chain.** It runs after a human closes the incident:

```bash
nthlayer incident close <verdict-id>
nthlayer learn --incident-verdict <verdict-id> --specs-dir ./specs/ --verdict-store ./verdicts.db
```

### Error Handling

If correlate fails (non-zero exit), measure logs the error and does not invoke respond. The evaluation verdict remains in the store. Measure continues its evaluation loop and will re-detect the breach on the next cycle.

If respond fails, the correlation verdict remains in the store. Each component's verdict is persisted before the next is invoked, so the chain can be retried from any point.

### Configuration

```yaml
# nthlayer measure config
trigger:
  correlate:
    enabled: true
    args:
      --prometheus-url: "http://localhost:9090"
      --specs-dir: "./specs/"
      --verdict-store: "./verdicts.db"
  respond:
    enabled: true
    args:
      --specs-dir: "./specs/"
      --verdict-store: "./verdicts.db"
      --notify: "stdout"
```

If `trigger.correlate.enabled` is false, measure writes evaluation verdicts but does not invoke correlate. This allows measure to run standalone.

### Audit First

Before implementing, Claude Code must:
1. Check whether any component already invokes another as a subprocess
2. Check how measure currently triggers downstream actions (does it call webhooks, write files, or only return exit codes?)
3. Determine how the verdict store path is shared between components (environment variable, config file, CLI flag?)
4. Document findings before implementing.

### Tests

1. Measure writes evaluation verdict → correlate invoked with correct verdict ID
2. Correlate writes correlation verdict → respond invoked with correct verdict ID
3. Correlate fails → respond NOT invoked, error logged, evaluation verdict still in store
4. Trigger disabled → evaluation verdict written, correlate not invoked
5. Full chain: measure → correlate → respond → all three verdicts in store with correct lineage

---

## A8. Metric Name Alignment (OTel)

### Problem

nthlayer-generate produces PromQL expressions. nthlayer-measure queries Prometheus. The metric names must match, and they should follow OTel semantic conventions.

### Action Required

This is a documentation and verification task that must happen before A3 and A4.

1. Run `nthlayer generate` against a representative ai-gate spec and a traditional service spec
2. Extract every metric name referenced in the generated PromQL (inputs) and every recording rule output name
3. Compare to OTel GenAI semantic conventions (https://opentelemetry.io/docs/specs/semconv/gen-ai/)
4. Compare to OTel Collector Prometheus exporter naming convention (dots → underscores, unit suffixes)
5. Compare to OTel HTTP semantic conventions for traditional metrics (https://opentelemetry.io/docs/specs/semconv/http/)
6. Document the three-column table:

```
| OTel Convention | Prometheus Name (after export) | Generate Rule Reference |
|-----------------|-------------------------------|----------------------|
| gen_ai.decision event | gen_ai_decisions_total | ? |
| gen_ai.override event | gen_ai_overrides_total | ? |
| http.server.request.duration | http_server_request_duration_seconds | ? |
| ... | ... | ... |
```

7. Identify gaps between what generate currently produces and what OTel conventions specify
8. Propose a migration path: which template variables need renaming?

This table is a product artifact and should be committed to the NthLayer documentation.

---

## A9. Implementation Order

| Step | Section | Description |
|------|---------|-------------|
| 1 | A8 | Metric name alignment — run generate, document the metrics contract |
| 2 | A1 | Verdict types — audit existing schema, propose extensions |
| 3 | A3 | Measure `--evaluate-once` — core new feature |
| 4 | A4 | Correlate live data — wire Prometheus + verdict store |
| 5 | A5 | Respond verdict integration |
| 6 | A6 | Learn verdict chain consumption |
| 7 | A7 | Trigger chain — direct subprocess invocation |

After step 7, the core integration is complete. The product works as a system.

---

# PART B: TEST & DEMO INFRASTRUCTURE

These are NOT product features. They validate Part A and enable the real demo. They are built after Part A is functionally complete. They live in a `test/` or `demo/` directory.

---

## B1. Fake Service

A single Python script acting as a Prometheus exporter with controllable metrics.

### Requirements

- Exports metrics matching the "Prometheus Name" column of the A8 metrics contract (OTel-convention names)
- Parameterised via CLI flags: `--name`, `--type` (api or ai-gate), `--port`, `--rps`, `--error-rate`, etc.
- `/control` endpoint to change rates at runtime
- `/reset` endpoint to return to baseline
- Smooth transitions (2-3 scrape intervals)
- Single file, `prometheus_client` as the only dependency

---

## B2. Docker Compose Stack

- **Prometheus** (5s scrape interval, lifecycle API enabled)
- **Grafana** (anonymous viewer access, Prometheus data source auto-provisioned)
- **AlertManager** (for traditional human notification testing, NOT in the NthLayer machine chain)
- **Webhook receiver** (logs payloads, for verifying respond's notifications)
- **8 fake services** (fraud-detect as ai-gate, 7 traditional)

No Gitea, ArgoCD, Slack. NthLayer runs on the host, not in Docker.

---

## B3. End-to-End Integration Test

The acceptance test for Part A. A script that:

1. Verifies baseline (no alerts, no breach verdicts in store)
2. Runs `nthlayer generate`, loads rules into Prometheus
3. Degrades fraud-detect via `/control`
4. Runs `nthlayer measure --evaluate-once` (multiple times for hysteresis), verifies evaluation verdict in store
5. Runs `nthlayer correlate --trigger-verdict <id>`, verifies correlation verdict with correct root cause
6. Runs `nthlayer respond --trigger-verdict <id>`, verifies incident verdict
7. Restores service, closes incident
8. Runs `nthlayer learn --incident-verdict <id>`, verifies retrospective verdict with complete lineage chain
9. Degrades again, runs `nthlayer check-deploy`, verifies deploy blocked

When this passes, the product works end-to-end. ~4-5 minutes runtime.

---

## B4. Scenario Runner

Drives fake services through a scripted incident for demos. Only manipulates fake services via `/control`. Does NOT invoke NthLayer commands. NthLayer detects and responds on its own via the trigger chain.

---

## B5. Live Topology Connection

Connect the topology visualisation to real Prometheus data and the verdict store. Display verdicts in the event feed as they're written. Last thing to build.

---

## Implementation Order (Both Parts)

| Step | Section | Type | Description |
|------|---------|------|-------------|
| 1 | A8 | Core | Metric name alignment (prerequisite) |
| 2 | A1 | Core | Verdict types (audit existing schema, propose extensions) |
| 3 | A3 | Core | Measure `--evaluate-once` mode |
| 4 | A4 | Core | Correlate live data + verdict store |
| 5 | A5 | Core | Respond verdict integration |
| 6 | A6 | Core | Learn verdict chain consumption |
| 7 | A7 | Core | Trigger chain |
| 8 | B1 | Test | Fake service |
| 9 | B2 | Test | Docker Compose stack |
| 10 | B3 | Test | End-to-end integration test |
| 11 | B4 | Demo | Scenario runner |
| 12 | B5 | Demo | Live topology connection |

Steps 1-7 are the product. Steps 8-12 prove it works.

---

## Notes for Claude Code

**Read before you write.** Every section has an "Audit First" block. Complete the audit and document findings before writing any implementation code. The proposals in this spec are informed guesses. The existing codebase is the authority.

**The verdict store is the integration layer.** Components do not pass files to each other. They read from and write to the shared verdict store. The trigger chain (subprocess invocation) is the control flow. The verdict store is the data flow.

**Verdict lineage is the audit trail.** Every verdict must correctly populate `lineage.context` to reference the upstream verdict that triggered it. Walking the lineage from a retrospective verdict back to the original evaluation verdict must produce the complete incident story.

**OTel conventions are the metric contract.** Metric names in generate templates, measure queries, and fake services must all align with OTel semantic conventions as exported to Prometheus. The A8 alignment table is the contract.

**Replay scenarios must continue working.** The live data path is additive. Every component must still work with its existing fixture-based tests. The `--prometheus-url` and `--verdict-store` flags enable the live path; their absence falls back to the existing behaviour.

**`--evaluate-once` before `--watch`.** Testability first. The single-evaluation mode is essential for scripting, CI, and the integration test.

**The trigger chain uses direct subprocess invocation.** Do not introduce message queues, file watchers, or event buses. Keep it simple.

**Part B lives in `test/` or `demo/`.** Not in the core package. Not shipped to users.
