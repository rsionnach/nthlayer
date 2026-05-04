# ECOSYSTEM-GAPS.md — Specification for Remaining Ecosystem Gaps

This document specifies solutions for six gaps in the OpenSRM ecosystem that the verdict primitive partially addresses but does not fully solve. Each solution follows the same design principle: one simple, well-defined thing rather than a complex framework. Each solution is transport (deterministic) unless explicitly noted otherwise.

Read VERDICT.md first. Verdicts are the data primitive that several of these solutions build on, but verdicts alone don't close these gaps.


## 1. Replay and Simulation

### The Problem

The ecosystem measures other people's agents but has no way to test, evaluate, and iterate on its own agentic components before real incidents happen. Every improvement to a model prompt, evaluation rubric, or correlation algorithm is a guess validated only by the next real event. This is the agentic equivalent of deploying code without tests.

### The Solution: Scenarios

A scenario is a recorded or synthetic event stream with a known timeline and known outcomes. It is to agentic components what a test fixture is to code. Scenarios live in each component's `scenarios/` directory, are versioned in Git, and are the regression suite for judgment quality.

#### Scenario Schema

```yaml
scenario:
  # Identity
  id: "scn-payment-api-deploy-regression"
  version: 1
  created: "2026-03-07"
  source: "real-incident"          # real-incident | synthetic | hybrid
  anonymised: true                 # whether service names and values have been anonymised

  # Description
  description: "Deploy v2.3.1 removed connection pooling config, causing p99 latency spike on payment-api and cascading error rate increase on checkout-service."
  tags: ["deploy", "latency", "cascading-failure", "connection-pooling"]
  difficulty: "medium"             # easy | medium | hard | adversarial
  duration: "45m"                  # total timeline of the scenario

  # Topology context (what the component should know about service relationships)
  topology:
    services:
      - name: payment-api
        tier: critical
        dependencies: [database-primary, cache-redis]
        dependents: [checkout-service, billing-service]
      - name: checkout-service
        tier: critical
        dependencies: [payment-api, inventory-service]
      - name: database-primary
        tier: critical
    slo_targets:
      payment-api:
        latency_p99: 200ms
        error_rate: 0.01
      checkout-service:
        latency_p99: 500ms
        error_rate: 0.01

  # The event stream (ordered by timestamp)
  events:
    - at: "T+0m"
      type: change
      payload:
        service: payment-api
        change_type: deploy
        detail:
          from_version: "2.3.0"
          to_version: "2.3.1"
          actor: deploy-pipeline
          rollback_available: true

    - at: "T+12m"
      type: alert
      payload:
        service: payment-api
        alert_name: latency_p99_breach
        metric: http_request_duration_seconds
        value: 0.52
        threshold: 0.20
        severity_source: 0.8

    - at: "T+13m"
      type: metric_breach
      payload:
        service: payment-api
        metric: database_connection_pool_active
        value: 0
        expected_range: [10, 50]

    - at: "T+14m"
      type: alert
      payload:
        service: checkout-service
        alert_name: error_rate_breach
        metric: http_requests_errors_total
        value: 0.08
        threshold: 0.01
        severity_source: 0.7

    - at: "T+15m"
      type: alert
      payload:
        service: checkout-service
        alert_name: latency_p99_breach
        metric: http_request_duration_seconds
        value: 1.2
        threshold: 0.50
        severity_source: 0.6

    - at: "T+20m"
      type: quality_score
      payload:
        service: payment-api
        agent: code-reviewer
        score: 0.45
        dimension_scores:
          correctness: 0.3
          completeness: 0.5
          safety: 0.6

    # ... additional events as the scenario progresses

  # What the correct interpretation is (ground truth)
  expected_outcomes:
    root_cause: "deploy v2.3.1 removed connection pooling configuration from payment-api, causing all database connections to be created on-demand without reuse"
    causal_chain:
      - "deploy v2.3.1 at T+0m removed connection pool config"
      - "connection pool exhaustion began at approximately T+10m"
      - "latency spike on payment-api at T+12m (direct effect)"
      - "checkout-service errors at T+14m (dependency failure, payment-api calls timing out)"
    severity: 2
    affected_services: [payment-api, checkout-service]
    unaffected_services: [billing-service, inventory-service]
    correct_remediation: "rollback payment-api to v2.3.0"
    false_signals:
      - "checkout-service alerts are symptoms, not independent issues"

  # Expected verdicts (what a correct component should produce)
  expected_verdicts:
    sitrep:
      - subject_type: correlation
        should_correlate: [payment-api-latency, checkout-service-errors]
        should_identify_cause: deploy-v2.3.1
        min_confidence: 0.6
      - subject_type: correlation
        should_NOT_correlate: [checkout-service-errors, inventory-service]

    mayday:
      triage:
        expected_severity: 2
        expected_blast_radius: [payment-api, checkout-service]
      investigation:
        expected_root_cause: "connection pooling removal in deploy v2.3.1"
        expected_evidence: [connection_pool_active_metric, deploy_temporal_proximity]
      remediation:
        expected_action: rollback
        expected_target: payment-api
        expected_version: "2.3.0"
```

#### Replay Operations

Each component implements a `replay` CLI command:

```bash
# SitRep: replay an event stream through pre-correlation and snapshot generation
nthlayer-correlate replay --scenario scenarios/payment-api-deploy.yaml
# Output:
#   Events ingested: 6
#   Correlation groups formed: 2
#   Expected correlations found: 1/1
#   False correlations: 0
#   Root cause identified: yes (confidence 0.74)
#   Time to root cause identification: T+14m (2 minutes after first cascading alert)
#   Verdict accuracy vs expected: 85%

# Arbiter: replay agent outputs with known quality labels
nthlayer-measure replay --scenario scenarios/subtle-auth-bug.yaml
# Output:
#   Outputs evaluated: 12
#   Score accuracy vs known labels: 0.83
#   False accepts: 1 (scored 0.71, should have been flagged)
#   False rejects: 0
#   Per-dimension accuracy: correctness 0.92, completeness 0.75, safety 0.88

# Mayday: replay a full incident scenario
nthlayer-respond replay --scenario scenarios/cascading-failure.yaml
# Output:
#   Triage accuracy: severity correct, blast radius correct
#   Investigation: root cause identified (confidence 0.68), matches expected
#   Remediation: suggested rollback (correct), target service correct
#   Time to remediation suggestion: T+22m
```

#### Replay Diffing

When you change a model prompt, evaluation rubric, or pre-correlation algorithm, replay all scenarios and diff:

```bash
nthlayer-correlate replay --scenario scenarios/ --diff baseline.json
# Compares current run against a stored baseline
# Output:
#   payment-api-deploy: IMPROVED (root cause confidence 0.74 → 0.81)
#   cascading-database: REGRESSED (false correlation introduced)
#   network-partition: UNCHANGED
#   Summary: 1 improved, 1 regressed, 1 unchanged
```

The baseline is a stored set of replay results (JSON). After a successful replay run, save it as the new baseline:

```bash
nthlayer-correlate replay --scenario scenarios/ --save-baseline baseline.json
```

This is the regression suite. Run it before merging any change to agentic components. Run it in CI.

#### Scenario Sources

Scenarios come from three sources:

1. **Real incidents (anonymised).** After an incident is resolved, the verdict chain (with confirmed/overridden outcomes) is exported as a scenario. Service names, metric values, and deployment details are anonymised. The causal chain and expected outcomes are filled from the post-incident review. This is the highest-value source because it captures real-world complexity.

2. **Synthetic scenarios.** Hand-crafted to test specific capabilities: simple causal chains, complex cascading failures, misleading correlations (two things happened at the same time but are unrelated), adversarial scenarios (signals designed to mislead the model). Synthetic scenarios are the unit tests of judgment quality.

3. **Hybrid scenarios.** Real event patterns with synthetic variations. Take a real incident and modify it: what if the deploy happened 30 minutes earlier? What if there were 3 candidate changes instead of 1? What if the cascading service was a lower tier? This tests how robust the component's judgment is to variations in context.

#### Scenario Storage

```
component-repo/
├── scenarios/
│   ├── README.md              # how to create, run, and contribute scenarios
│   ├── real/
│   │   ├── payment-api-deploy-regression.yaml
│   │   └── database-failover-weekend.yaml
│   ├── synthetic/
│   │   ├── simple-causal-chain.yaml
│   │   ├── misleading-temporal-correlation.yaml
│   │   └── adversarial-gaming-attempt.yaml
│   └── hybrid/
│       ├── deploy-timing-variation.yaml
│       └── multi-candidate-change.yaml
├── baselines/
│   └── baseline.json          # stored replay results for regression diffing
```

#### Converting Verdicts to Scenarios

The verdict library should include a scenario export command:

```bash
nthlayer-learn export-scenario \
  --producer sitrep \
  --time-range "2026-03-01T14:00:00Z/2026-03-01T15:00:00Z" \
  --include-events \
  --anonymise \
  --output scenarios/real/march-1-incident.yaml
```

This queries the verdict store for all verdicts in the time range, retrieves the events that produced them (via `subject.ref`), includes the resolved outcomes, anonymises service names and values, and outputs a complete scenario file. A human then reviews and optionally adds to `expected_outcomes` based on post-incident analysis.

**Automatic export from Mayday:** When Mayday resolves an incident, its post-incident processing automatically exports the incident's event stream and verdict chain as a scenario (see MAYDAY.md). This means real incidents become replay scenarios without manual effort. The exported scenario includes the full event timeline, all verdicts produced during the incident (with resolved outcomes), and the expected outcomes derived from the resolution. The `nthlayer-learn export-scenario` CLI command is the manual version of the same operation, useful for exporting scenarios from SitRep or Arbiter verdicts outside of Mayday's incident lifecycle.


## 2. Agent Interaction Contracts

### The Problem

When components exchange verdicts, the happy path is defined but the failure modes aren't. What happens when a producer is slow, unavailable, or returning stale data? These are transport decisions that must be deterministic and explicit, not left to model judgment.

### The Solution: Contract Manifests

Each component declares what it provides and what it expects. Contracts are YAML files alongside the component's config. The transport layer enforces them at runtime.

#### Contract Schema

```yaml
# sitrep.contracts.yaml
component: sitrep

provides:
  correlation_verdicts:
    description: "Correlation assessments linking signals to potential causes"
    verdict_types: [correlation]
    freshness:
      watching: 5m       # in WATCHING mode, new verdicts at least every 5 minutes
      alert: 1m          # in ALERT mode
      incident: 30s      # in INCIDENT mode
    availability:
      target: 0.99       # 99% of the time, verdicts are produced within freshness window
    degradation:
      on_model_unavailable: "produce template-based verdicts with confidence 0.0"
      on_store_unavailable: "buffer in memory up to 1000 events, drop oldest beyond that"

consumes: {}             # SitRep ingests raw events, not other components' verdicts
```

```yaml
# mayday.contracts.yaml
component: mayday

provides:
  triage_verdicts:
    description: "Severity and blast radius assessments"
    verdict_types: [triage]
    freshness:
      incident: 2m
    availability:
      target: 0.95

  investigation_verdicts:
    description: "Root cause hypotheses and evidence"
    verdict_types: [investigation]
    freshness:
      incident: 10m
    availability:
      target: 0.90

  remediation_verdicts:
    description: "Proposed fixes and rollback recommendations"
    verdict_types: [remediation]
    freshness:
      incident: 15m
    availability:
      target: 0.90

consumes:
  sitrep.correlation_verdicts:
    required: false                # Mayday works without SitRep (reduced quality, noted in verdicts)
    max_staleness: 10m             # ignore verdicts with timestamp older than 10 minutes
    on_unavailable: "operate without pre-correlated context, note in verdict reasoning, reduce confidence by 0.2"
    on_stale: "use stale verdicts with reduced confidence, note staleness and age in verdict reasoning"
    on_low_confidence: "include in context but weight lower in judgment, note in verdict reasoning"
    timeout: 5s                    # max wait for verdict query before falling back

  arbiter.quality_verdicts:
    required: false
    max_staleness: 1h
    on_unavailable: "ignore quality context, note absence in verdict reasoning"
    on_stale: "use with caveat, note staleness"
    timeout: 3s
```

```yaml
# arbiter.contracts.yaml
component: arbiter

provides:
  quality_verdicts:
    description: "Agent output quality evaluations"
    verdict_types: [agent_output]
    freshness:
      default: "within 60s of receiving agent output"
    availability:
      target: 0.99
    degradation:
      on_model_unavailable: "queue unscored output (max 1000), produce verdicts with confidence 0.0 and reasoning 'evaluation pending, model unavailable'"
      on_queue_full: "drop oldest unscored output, emit metric arbiter_dropped_evaluations_total"
      on_recovery: "evaluate queued output in FIFO order, mark verdicts with 'delayed_evaluation: true' in metadata"

consumes: {}              # Arbiter evaluates agent output directly, not via other component verdicts
```

#### Runtime Enforcement

The transport layer in each component enforces its consumption contracts:

```python
# Pseudocode for Mayday consuming SitRep verdicts
def get_sitrep_context(contracts, verdict_store):
    contract = contracts.consumes["sitrep.correlation_verdicts"]

    try:
        verdicts = verdict_store.query(
            producer_system="sitrep",
            subject_type="correlation",
            time_range=last(contract.max_staleness),
            timeout=contract.timeout
        )
    except TimeoutError:
        return FallbackContext(
            reason=contract.on_unavailable,
            confidence_reduction=0.2
        )

    if not verdicts:
        return FallbackContext(
            reason=contract.on_unavailable,
            confidence_reduction=0.2
        )

    freshest = max(verdicts, key=lambda v: v.timestamp)
    age = now() - freshest.timestamp

    if age > contract.max_staleness:
        return StaleContext(
            verdicts=verdicts,
            staleness=age,
            reason=contract.on_stale,
            confidence_reduction=0.1
        )

    return FreshContext(verdicts=verdicts)
```

This is deterministic transport. The model never decides how to handle unavailability or staleness. The contract tells the transport layer exactly what to do. The model receives the context with appropriate confidence adjustments and notes in the reasoning.

#### Contract Validation

A CLI command validates that all component contracts are compatible:

```bash
opensrm validate-contracts \
  --contracts sitrep.contracts.yaml arbiter.contracts.yaml mayday.contracts.yaml
# Output:
#   mayday consumes sitrep.correlation_verdicts: OK (SitRep provides it)
#   mayday consumes arbiter.quality_verdicts: OK (Arbiter provides it)
#   mayday timeout (5s) < sitrep freshness (30s in INCIDENT): OK
#   No orphaned providers (all provided verdicts are consumed by at least one component)
#   No unresolvable consumers (all consumed verdicts have a provider)
```


## 3. Cascading Degradation

### The Problem

Individual components have degradation modes, but the ecosystem doesn't have a cohesive story for what happens when infrastructure between components fails. OTel Collector down, Prometheus has stale data, model APIs unavailable while agents keep producing output. The cascading effects of these failures are unspecified.

### The Solution: The Staleness Policy

One ecosystem-wide principle with per-component overrides, configured in the OpenSRM manifest.

#### The Principle

**Fail safe on stale data. Fail open on missing data with explicit warning.**

"Fail safe" means: if we have data but it's old, assume the worst (block deploys, escalate, increase review). Old data saying "everything is fine" is dangerous because things may have changed.

"Fail open on missing data" means: if a component was never deployed (no data exists at all), don't block everything. Warn, but allow. A team that hasn't deployed the Arbiter yet shouldn't have all deploys blocked because NthLayer can't find judgment SLO metrics.

The distinction: stale data (was fresh, became old) is treated differently from absent data (was never there).

#### Staleness Configuration

```yaml
# In service.reliability.yaml (OpenSRM manifest)
spec:
  degradation:
    # How stale can judgment SLO metrics be before check-deploy blocks?
    metric_staleness_threshold: 1h

    # What happens when check-deploy finds stale metrics?
    on_stale_metrics: block           # block | warn | pass
    # block: deploy is blocked, reason: "judgment SLO data is stale"
    # warn: deploy is allowed, warning emitted, verdict produced with low confidence
    # pass: deploy is allowed silently (not recommended)

    # What happens when check-deploy finds no judgment metrics at all?
    on_missing_metrics: warn          # block | warn | pass
    # This covers the case where the Arbiter isn't deployed yet

    # How long does the Arbiter queue unscored output when the model is unavailable?
    arbiter:
      unscored_queue_max: 1000
      unscored_queue_action: drop_oldest    # drop_oldest | block_agent | evaluate_on_recovery
      # drop_oldest: when queue is full, discard the oldest unscored output
      # block_agent: stop accepting new agent output until model recovers (risky, backs up agents)
      # evaluate_on_recovery: when model comes back, evaluate everything in queue (expensive, may be outdated)

    # How long does SitRep buffer events when the store is unavailable?
    sitrep:
      event_buffer_max: 10000
      event_buffer_action: drop_oldest

    # What happens when the OTel Collector is unreachable?
    otel:
      local_buffer_max: 5000           # events buffered locally per component
      fallback_push: true              # attempt direct Prometheus remote_write as fallback
      fallback_endpoint: "http://prometheus:9090/api/v1/write"
      health_check_interval: 30s       # how often to check if the collector is back
```

#### Cascading Failure Matrix

The spec must document the specific cascading scenarios and their resolutions:

| Failure | Immediate Effect | Downstream Effect | Resolution |
|---------|-----------------|-------------------|------------|
| **OTel Collector down** | Components can't emit metrics | Prometheus has no new data, NthLayer queries return stale results | Components buffer locally. If buffer fills, drop oldest. When collector recovers, flush buffer. NthLayer's `check-deploy` sees stale metrics and applies `on_stale_metrics` policy. |
| **Prometheus down** | NthLayer can't query metrics | `check-deploy` can't evaluate error budgets, dashboards go blank | `check-deploy` applies `on_stale_metrics: block` (safest default). Components continue producing verdicts and emitting to OTel (buffered). When Prometheus recovers, recording rules catch up. |
| **Arbiter model API down** | Arbiter can't evaluate agent output | Unscored output accumulates. No new `gen_ai_decision_*` metrics emitted. Judgment SLO data becomes stale. | Arbiter queues unscored output per `unscored_queue_action`. Produces verdicts with `confidence: 0.0`. Emits `gen_ai_decision_total` with `degraded=true` label. After `metric_staleness_threshold`, NthLayer's `check-deploy` blocks deploys. |
| **SitRep model API down** | SitRep can't produce model-interpreted snapshots | Mayday operates without pre-correlated context (per interaction contract) | SitRep enters DEGRADED mode. Produces template-based correlation verdicts with `confidence: 0.0`. Pre-correlation engine continues running (transport, no model needed). Mayday receives low-confidence verdicts and adjusts its own confidence accordingly. |
| **SitRep store unavailable** | SitRep can't persist or query events | Pre-correlation engine has no state to work from | SitRep buffers events in memory per `event_buffer_max`. If buffer fills, drops oldest. Produces verdicts noting "operating from in-memory buffer, limited history". When store recovers, flushes buffer. |
| **Verdict store unavailable** | Components can't persist or query verdicts | Self-calibration has no data, lineage is broken, replay impossible | Components buffer verdicts in memory. Continue emitting OTel metrics (separate path). When store recovers, flush buffer. Accuracy queries return "insufficient data" during outage. |
| **Kafka/NATS down (Tier 2/3)** | SitRep ingestion stops | Pre-correlation state becomes stale, new events lost | Ingestion falls back to direct webhook if configured. Components producing events buffer locally. SitRep's snapshot cache continues serving the last known state with increasing staleness warnings. |
| **Multiple simultaneous failures** | Combination of above | | Each failure is handled independently per its policy. The Arbiter's governance detects "multiple components degrading simultaneously" and escalates to human operators (this is already in the governance spec). |

#### Health Dashboard

NthLayer should generate a degradation health dashboard (as part of `nthlayer apply`) that shows:

- Per-component: operational / degraded / unavailable
- Metric freshness: how old is the latest data point for each judgment SLO metric
- Verdict freshness: how old is the latest verdict from each producer
- Buffer status: how full are local buffers (percentage of max)
- Deploy gate status: currently passing / blocking / warning

This dashboard is the first thing an operator checks when something seems wrong with the ecosystem itself.


## 4. Adversarial Robustness

### The Problem

If an agent knows what the Arbiter evaluates, it can optimise for the evaluation rubric while being subtly wrong in ways the rubric doesn't catch. This is Goodhart's Law: "When a measure becomes a target, it ceases to be a good measure."

### The Solution: The Audit Protocol

A set of Arbiter behaviours designed to make gaming expensive and detectable.

#### Random Deep Evaluation

A configurable percentage of agent outputs that scored well (above a configurable threshold) receive a second, more thorough evaluation with an expanded rubric.

```yaml
# In arbiter.yaml
audit:
  deep_evaluation:
    enabled: true
    sample_rate: 0.05                # 5% of high-scoring outputs
    score_threshold: 0.8             # only sample outputs that scored above this
    model: frontier                  # always use frontier model for audits
    expanded_dimensions:             # dimensions not in the primary rubric
      - maintainability
      - performance_implications
      - dependency_hygiene
      - test_meaningfulness          # do the tests actually test behaviour, or just check syntax?
      - hidden_complexity            # does simple-looking code hide complex behaviour?
```

The deep evaluation produces a second verdict linked to the original via lineage (`parent: original_verdict_id`). If the deep evaluation finds issues the primary evaluation missed, that's a calibration signal: the primary rubric has a blind spot.

Over time, if deep evaluations consistently find issues on a specific dimension, that dimension should be added to the primary rubric. The audit protocol is self-improving: it discovers the rubric's weaknesses.

#### Downstream Outcome Tracking

For agent outputs with measurable downstream effects, the Arbiter tracks whether the outcome matched the predicted quality.

```yaml
audit:
  outcome_tracking:
    enabled: true
    sources:
      - type: deployment_metrics      # did the code cause a regression after deploy?
        signal: "error_rate increase > 2x within 1h of deploy"
        verdict_update: "ground_truth.signal: deployment_regression"
      - type: test_results             # did the code pass tests in CI?
        signal: "test failure within same PR"
        verdict_update: "ground_truth.signal: test_failure"
      - type: incident_correlation     # did the code get mentioned in an incident?
        signal: "SitRep correlation verdict linking this change to an incident"
        verdict_update: "ground_truth.signal: incident_related"
      - type: revert                   # was the code reverted?
        signal: "git revert of the commit within 7 days"
        verdict_update: "ground_truth.signal: reverted"
```

When a downstream outcome signal fires, the Arbiter automatically updates the original verdict's `outcome.ground_truth` field. This closes the loop without requiring human intervention for every verdict.

High score + bad outcome = potential gaming signal. The query:

```bash
nthlayer-learn gaming-check --producer arbiter --window 90d
# For each agent, computes:
#   score_mean: average judgment score
#   outcome_confirmation_rate: percentage of verdicts confirmed by downstream outcomes
#   divergence: score_mean - outcome_confirmation_rate
#   verdict: OK | WARNING | ALERT
#
# Example output:
#   code-reviewer: score 0.88, outcome confirmation 0.71, divergence 0.17 → ALERT
#   doc-writer: score 0.79, outcome confirmation 0.81, divergence -0.02 → OK
#   test-writer: score 0.82, outcome confirmation 0.80, divergence 0.02 → OK
```

A divergence above a configurable threshold (default 0.10) triggers a warning. Above 0.15 triggers an alert. The Arbiter can automatically increase the deep evaluation sample rate for flagged agents.

#### Criteria Rotation

The evaluation rubric is not static. Secondary dimensions rotate on a configurable schedule so agents can't permanently optimise for a fixed set of criteria.

```yaml
audit:
  criteria_rotation:
    fixed_dimensions:                 # always present in every evaluation
      - correctness
      - safety
    rotating_dimensions:              # drawn from this pool
      - clarity
      - efficiency
      - convention_adherence
      - documentation_accuracy
      - test_coverage
      - test_meaningfulness
      - error_message_quality
      - logging_adequacy
      - dependency_minimisation
      - backwards_compatibility
    active_rotating: 2                # how many rotating dimensions are active at any time
    rotation_period: 7d               # how often the active set changes
    rotation_strategy: random         # random | sequential | weighted_by_weakness
    # weighted_by_weakness: dimensions where the agent has lower scores rotate in more often
```

The model receives the current active dimensions as part of its evaluation prompt. The rotation is deterministic (based on date and a seed, so it's reproducible for replay) but unpredictable to the agent being evaluated.

#### Evaluation Prompt Diversity

Beyond rotating dimensions, the evaluation prompt itself should vary. Multiple phrasings of the same evaluation criteria reduce the chance that an agent can optimise for specific prompt patterns.

```yaml
audit:
  prompt_diversity:
    enabled: true
    variants_per_dimension: 3        # number of prompt variants per dimension
    selection: random_per_evaluation  # each evaluation randomly selects a variant
```

The variants are stored in the Arbiter's config:

```yaml
dimensions:
  correctness:
    variants:
      - "Is the logic sound? Are there bugs, type mismatches, or error handling gaps?"
      - "Would this code produce correct results for all valid inputs? What about edge cases?"
      - "Trace the execution path for the primary use case. Does it do what the spec says?"
```

Same intent, different phrasing. An agent that has learned to produce output that looks correct to one phrasing may fail against another.


## 5. Configuration Complexity

### The Problem

Six components (OpenSRM, Verdict, Arbiter, NthLayer, SitRep, Mayday), each with its own configuration, plus OTel Collector config, plus Prometheus, plus potentially Kafka/NATS. The configuration surface area grows with each component and creates friction for incremental adoption.

### The Solution: `opensrm init`

One interactive CLI command in the opensrm repo that generates the manifest and all component configs from a single guided session. The manifest is the single source of truth. Component configs reference it.

#### The Command

```bash
opensrm init
```

Walks through:

```
OpenSRM Ecosystem Setup
========================

Service name: payment-api
Service tier: [critical / standard / best-effort] critical
Environment: production

Service type:
  [1] Traditional service (latency, availability, error rate SLOs)
  [2] AI agent gate (judgment SLOs: reversal rate, calibration)
  [3] Both
  > 3

Traditional SLOs:
  Latency p99 target (ms): 200
  Error rate target: 0.01
  Availability target: 0.999

Judgment SLOs (for AI decision quality):
  Reversal rate target: 0.05
  Reversal rate window: 30d
  High-confidence failure target: 0.02
  Confidence threshold: 0.9

Which components will you use?
  [x] NthLayer (monitoring generation)
  [x] Arbiter (quality measurement)
  [ ] SitRep (signal correlation)
  [ ] Mayday (incident response)

Infrastructure:
  Prometheus endpoint: http://prometheus:9090
  Grafana endpoint: http://grafana:3000 (optional, press enter to skip)
  OTel Collector endpoint: http://otel-collector:4317 (optional)

Verdict store:
  Backend: [sqlite / postgres / clickhouse] sqlite
  Path: verdicts.db

Degradation policy:
  Use defaults? [y/n] y
  (metric_staleness_threshold: 1h, on_stale_metrics: block, on_missing_metrics: warn)

Generating configuration...
  ✓ service.reliability.yaml    (OpenSRM manifest)
  ✓ arbiter.yaml                (Arbiter config)
  ✓ verdict.yaml                (Verdict store config, shared)
  ✓ nthlayer.yaml               (NthLayer config)
  ✓ degradation.yaml            (Staleness policy)
  ✓ contracts/arbiter.contracts.yaml
  ✓ contracts/nthlayer.contracts.yaml

Done. Run 'nthlayer apply' to generate your monitoring stack.
```

#### Generated Files

All generated configs reference the manifest as the source of truth:

```yaml
# arbiter.yaml (generated)
manifest: ./service.reliability.yaml      # single source of truth
evaluator:
  model: claude-sonnet-4-20250514         # default, user can change
  max_tokens: 4096
otel:
  endpoint: http://otel-collector:4317
verdict:
  store:
    backend: sqlite
    path: verdicts.db
audit:
  deep_evaluation:
    enabled: true
    sample_rate: 0.05
  outcome_tracking:
    enabled: true
  criteria_rotation:
    enabled: true
    rotation_period: 7d
```

SLO targets, service tier, and degradation policy are all read from the manifest at runtime, not duplicated in the component config. If you change the reversal rate target in the manifest, the Arbiter picks it up without config changes.

#### Config Validation

```bash
opensrm validate
# Checks:
#   ✓ Manifest is valid OpenSRM schema
#   ✓ All referenced component configs exist
#   ✓ Component configs reference the manifest correctly
#   ✓ Prometheus endpoint is reachable
#   ✓ OTel Collector endpoint is reachable (if configured)
#   ✓ Verdict store is accessible
#   ✓ Interaction contracts are compatible
#   ✓ Degradation policy is consistent across components
```

#### Config Update

When a team adds a new component:

```bash
opensrm add-component sitrep
# Walks through SitRep-specific configuration
# Generates sitrep.yaml and contracts/sitrep.contracts.yaml
# Updates any existing component contracts that can now consume SitRep's verdicts
```


## 6. Human Interface

### The Problem

The specs define machine-readable schemas and agent-to-agent communication, but the human operator's experience is undefined. Humans provide the override signals that calibrate the entire system. If the human interface is bad (noisy notifications, unclear verdicts, no actionable context), humans ignore or dismiss verdicts without reading them, and the calibration loop degrades.

### The Solution: The Verdict Feed

Rather than a custom dashboard, the human interface is a filtered feed of verdicts that need attention, surfaced through channels operators already use (Slack, Grafana, CLI).

#### Notification Configuration

```yaml
# In service.reliability.yaml
spec:
  notifications:
    channels:
      - type: slack
        webhook: "https://hooks.slack.com/services/..."
        filter:
          events:
            - governance_action          # Arbiter reduced agent autonomy
            - state_transition           # SitRep changed state (WATCHING → ALERT)
            - incident_declared          # Mayday activated
            - pending_review_overdue     # verdict hasn't been reviewed within threshold
            - gaming_alert               # adversarial robustness check flagged an agent
            - degradation_warning        # component entered degraded mode
          min_severity: medium           # skip low-severity notifications
        format: structured               # include verdict summary, confidence, links

      - type: email
        address: "oncall@company.com"
        filter:
          events:
            - incident_declared
            - governance_action
          min_severity: high

    review_thresholds:
      governance_action: 24h             # must be reviewed within 24 hours
      incident_verdict: 72h             # post-incident verdicts must be resolved within 72 hours
      routine_verdict: 7d               # routine quality verdicts can wait up to 7 days
      overdue_reminder_interval: 12h    # remind again this often if still pending
```

#### What Notifications Look Like

A governance action notification:

```
🔒 Arbiter: Agent autonomy reduced

Agent: code-reviewer (payment-api)
Action: Increased human review threshold from 0.7 → 0.85
Reason: Reversal rate 0.08 exceeds SLO target 0.05 (30-day window)

Recent verdicts that triggered this:
  • vrd-0139: approved auth middleware change, human overrode (score 0.81, should have flagged missing rate limit)
  • vrd-0142: approved API endpoint change, human overrode (score 0.77, should have flagged missing input validation)
  • vrd-0155: approved config change, human overrode (score 0.85, missed environment variable reference)

📊 View full trend: [Grafana link]
✅ Confirm this action | ❌ Override (restore previous autonomy) | 📝 Review verdicts
```

A state transition notification:

```
⚠️ SitRep: State changed WATCHING → ALERT

Trigger: P0 correlation group detected
Services: payment-api, checkout-service
Correlation: latency spike on payment-api (T+12m) correlated with deploy v2.3.1 (T+0m), confidence 0.74
Cascading: checkout-service error rate increase (T+14m), likely dependency failure

Candidate change:
  Deploy v2.3.1 to payment-api at 14:10 UTC (12 minutes before first alert)
  Rollback available: yes

📊 View snapshot: [Grafana link]
🔍 View correlation verdicts: [verdict feed link]
```

#### Verdict Feed UI

NthLayer generates a Grafana dashboard panel for the verdict feed. The panel shows:

**Active feed (default view):**
- Verdicts needing review, sorted by priority (governance actions first, then overdue reviews, then routine)
- Each verdict shows: producer, subject summary, judgment action, confidence, age, and status (pending/confirmed/overridden)
- One-click confirm or override buttons
- Override requires a reason (free text, this becomes the verdict's `outcome.override.reasoning`)

**Accuracy view:**
- Per-component accuracy over time (line chart)
- Per-agent accuracy with drill-down
- Calibration gap (confidence vs actual accuracy)
- Gaming alerts

**Degradation view:**
- Component health status
- Metric freshness
- Buffer utilisation
- Recent degradation events

#### CLI Interface

For operators who prefer the terminal:

```bash
# See what needs attention
nthlayer-learn review --pending --overdue
# Lists verdicts sorted by priority, shows summary and confidence

# Confirm a verdict
nthlayer-learn confirm vrd-0142 --reason "reviewed the diff, judgment was correct"

# Override a verdict
nthlayer-learn override vrd-0139 --action reject --reason "missed rate limiting on new endpoint, should have been flagged"

# Check ecosystem health
opensrm status
# Shows: component health, metric freshness, pending review count, recent governance actions
```

#### The Key Design Principle

**Humans should only see verdicts that need their attention.** The notification filter defaults to: governance actions, state transitions, and overdue reviews. A flood of "everything is fine" notifications trains humans to ignore the feed. The system should be silent when everything is working and loud when something needs a human decision.

The review thresholds create a forcing function: if a governance action verdict hasn't been reviewed within 24 hours, the reminder fires again. This ensures the calibration loop stays closed. Unreviewed verdicts are dead data that can't improve the system.

#### Minimum Viable Human Interface

For a team just starting with the ecosystem, the minimum viable human interface is:

1. Slack notifications for governance actions and state transitions (configured in the manifest)
2. `nthlayer-learn review` CLI for confirming/overriding verdicts
3. A single Grafana panel showing per-component accuracy over time (generated by NthLayer)

This gives humans a way to receive alerts, provide feedback, and monitor overall quality without building any custom UI. The more sophisticated verdict feed dashboard is a later investment.


## Implementation Priority

Across all six gaps:

1. **Scenario schema and replay CLI** (highest impact, enables regression testing for judgment quality). Start with SitRep and Arbiter replay. Add Mayday when Mayday is implemented.

2. **Staleness policy in the OpenSRM manifest** (closes the most dangerous gap: what happens when data is stale). Add the `degradation` section to the manifest schema and implement staleness checks in NthLayer's `check-deploy`.

3. **Contract manifests** (defines failure behaviour between components). Write contracts for each component. Implement the runtime enforcement in the transport layer.

4. **Notification configuration** (enables the human feedback loop). Add the `notifications` section to the manifest schema. Implement Slack notifications for governance actions and state transitions.

5. **`opensrm init` CLI** (reduces configuration friction for new adopters). Build the interactive setup that generates manifest and component configs.

6. **Audit protocol** (adversarial robustness). Add deep evaluation sampling, outcome tracking, and criteria rotation to the Arbiter. This can wait until the Arbiter has enough verdict history to make gaming detection meaningful.

7. **Verdict feed Grafana dashboard** (human interface). NthLayer generates the panel. This can wait until there are enough verdicts flowing to make the dashboard useful.

8. **Scenario export from verdicts** (completing the replay loop). Build `nthlayer-learn export-scenario` once there's real verdict history to export from.

Items 1-4 are critical for a production-ready ecosystem. Items 5-8 improve developer experience and long-term quality.


## Relationship to Other Specs

| Spec | What This Document Adds |
|------|------------------------|
| **BRIEF.md** | Scenarios, contracts, staleness policy, audit protocol, opensrm init, and notification config should be referenced in each component's key concepts and README structure sections |
| **VERDICT.md** | Scenario export command, gaming-check query, and the connection between verdict outcome tracking and downstream outcome signals |
| **VERDICT-INTEGRATION.md** | Contract manifests per component, staleness policy implementation in NthLayer, notification configuration in each component |
| **SITREP-PRECORRELATION.md** | Contract declarations for SitRep's provided and consumed verdicts, degradation behaviour when store or model is unavailable, scenario replay for the pre-correlation engine |
| **MAYDAY.md** | Mayday's interaction contracts (consuming SitRep verdicts with staleness/fallback handling), post-incident scenario export (completing the replay loop from real incidents), safe action registry (the deterministic gate between agent proposal and system execution), degradation behaviour per agent and for the coordinator |
| **COSTOPTIMISATION.md** | Deep evaluation sampling cost (offline, controllable), replay cost (offline, sample-based), prompt diversity cost (marginal per-evaluation increase) |
