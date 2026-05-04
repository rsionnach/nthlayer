# BRIEF.md — OpenSRM Ecosystem Scaffolding

Read this entire document before doing anything. It contains the architectural vision, component descriptions, integration model, and specific instructions for what to create.


## What You're Building

A set of independent GitHub repos that together form the OpenSRM ecosystem. Each repo is a standalone project that solves a complete problem on its own. The repos integrate through a shared specification (OpenSRM manifests) and shared telemetry conventions (OpenTelemetry), not through code dependencies.

The repos to create as subdirectories here:

1. `opensrm` — The specification (repo already exists at github.com/rsionnach/opensrm and should be restructured in place, not recreated from scratch)
2. `arbiter` — AI agent output quality measurement engine
3. `nthlayer` — Reliability-as-code generator (already exists at github.com/rsionnach/nthlayer, needs updated README)
4. `sitrep` — Situational awareness through signal correlation
5. `mayday` — Multi-agent incident response

Each subdirectory should be treated as if it will become its own GitHub repo with its own README, LICENSE (Apache 2.0), and CONTRIBUTING.md.


## Author

Rob — Senior SRE based in Dublin, creator of OpenSRM and NthLayer. GitHub: @rsionnach. Building observability and reliability tooling for AI systems.


## Architectural Principles

### The Spec Is the Integration Layer

OpenSRM defines the shared language. Every component reads OpenSRM manifests as its input contract. A manifest declares what a service needs: SLO targets, judgment SLO thresholds for AI decision quality, dependency topology, alerting preferences. Components don't import each other's code. They all read the same manifest format and emit telemetry following the same OTel semantic conventions.

This is the OTel model: the spec repo defines what a span is and what attributes it carries. The collector, SDKs, Jaeger, Prometheus, and Grafana all speak the same language without knowing about each other directly.

### Zero Framework Cognition (ZFC)

Core tenet: **Transport is code. Judgment is model.**

Code handles deterministic transformation: receiving inputs, routing them, persisting results, generating config, sending alerts. Code never decides whether something is good, bad, important, or risky.

The model handles judgment: scoring quality, evaluating whether an agent's output is correct, deciding if a quality trend constitutes a real problem, recommending actions. Thresholds in configuration become guidance to the model rather than hardcoded comparisons.

This principle governs every architectural decision. Include the full ZFC document (provided below in the ZFC REFERENCE section) in each repo that has judgment responsibilities (Arbiter, SitRep, Mayday). Reference it from the others.

### Independence Is the Feature

Unlike monolithic platforms where you must adopt everything to get value from anything, each OpenSRM ecosystem component solves a complete problem alone:

- Someone running AI agents who needs quality measurement adopts the Arbiter. They don't need NthLayer, SitRep, or Mayday.
- Someone who already has monitoring but needs reliability-as-code adopts NthLayer. They don't need the Arbiter.
- Someone who has both but no incident response adopts Mayday.

The components compose when used together (the Arbiter's quality scores flow into NthLayer's dashboards, SitRep's correlations inform Mayday's incident response) but never require each other.

### Component Taxonomy

Every component falls into one of three categories based on its execution model. This distinction is architectural: it determines how the component is built, deployed, tested, and monitored.

**Data Sources** (static, queryable, no reasoning): OpenSRM manifests (YAML in Git, source of truth), Prometheus/OTel metrics (time-series, queryable), change event logs (deployment, config, flag history). These are queryable state that other things read.

**Tools** (deterministic, invocable, no reasoning): NthLayer compiler (manifest in, artifacts out), schema validator (YAML in, pass/fail out), dependency math engine (targets in, ceiling out). Given the same input, they produce the same output every time.

**Agents** (reasoning, adaptive, judgment required): the Arbiter (quality measurement and governance), SitRep (continuous correlation), Mayday's sub-agents (triage, investigation, communication, remediation). These interpret ambiguous inputs and make judgment calls.

**The test:** Does this component need to reason about ambiguous inputs to produce its output? If yes, it's an agent. If it does the same thing every time given the same input, it's a tool. If it's queryable state that other things read, it's a data source.

**Why this matters:** The data and tool layers work without any AI. Teams can adopt OpenSRM manifests and NthLayer today with zero agents and still get validated manifests, generated monitoring, and dependency math. The agent layer is additive, not foundational. This maps directly to ZFC: data sources and tools are transport, agents are judgment.

Note: the architecture's "Reasoning Boundary" principle (Design Principle #5 in the existing ARCHITECTURE.md) is the precursor to ZFC. The taxonomy formalises what the Reasoning Boundary described informally: "If a component doesn't need to reason, it isn't an agent."


## Component Descriptions

### OpenSRM (the spec)

**Repo: `opensrm`** (already exists at github.com/rsionnach/opensrm, needs restructuring to be spec-only)

**One-liner:** Open specification for declaring service reliability requirements as code, including judgment SLOs for AI systems.

**What it is:** A YAML/JSON schema for service reliability manifests. Defines SLO targets, AI decision quality thresholds (judgment SLOs), service dependency topology, cost budgets, and alerting preferences. The manifest is the shared contract that every other component in the ecosystem reads.

**What it is not:** An implementation. No CLI, no runtime, no agents. Pure specification with schema, examples, governance, and semantic conventions.

**Key concepts to cover in the README:**
- The manifest format (service.reliability.yaml) with a concrete example
- The `type: ai-gate` extension for AI decision services (judgment SLOs)
- Judgment SLO metrics: reversal rate, high-confidence failure rate, calibration score
- Semantic conventions for AI decision telemetry (OTel attributes). The spec MUST define the exact OTel metric names that the Arbiter emits and that NthLayer queries. These are the bridge between measurement and enforcement. The metric names are:
  - `gen_ai_decision_total` (counter): total evaluations, labels: service, agent, dimension, environment
  - `gen_ai_decision_score` (gauge): quality score 0.0-1.0, labels: service, agent, dimension, environment
  - `gen_ai_override_reversal_total` (counter): human full reversals of agent decisions, labels: service, agent, environment
  - `gen_ai_override_correction_total` (counter): human partial corrections, labels: service, agent, environment
  - `gen_ai_decision_confidence` (gauge): evaluator confidence 0.0-1.0, labels: service, agent, environment
  - `gen_ai_decision_cost_tokens` (counter): tokens consumed per evaluation, labels: service, agent, environment
  - `gen_ai_decision_cost_currency` (gauge): estimated cost in currency, labels: service, agent, environment
  These metric names must be documented in the spec alongside the existing `gen_ai.decision.*` event attributes. The distinction matters: events carry rich context (the full evaluation payload), metrics carry numeric values for aggregation and alerting. NthLayer generates Prometheus recording rules FROM these metrics (computing reversal rates, error budget burn, etc.). Without standardised metric names, each team invents their own naming scheme and NthLayer can't generate rules reliably.
- Change event schema: a standardised format for change events that all sources emit and consumers (SitRep, Arbiter, Mayday) ingest. This is critical because changes are the single most common cause of incidents and quality degradation. The schema must cover both traditional changes (deploys, config updates, feature flag toggles, schema migrations) and AI-specific changes that existing change tracking misses entirely (prompt changes, system instruction updates, model version swaps, LoRA adapter deployments, context window configuration changes, formula revisions, agent role reassignments). Every change source (GitHub, ArgoCD, LaunchDarkly, model registries, prompt management systems) normalises into this schema so that SitRep doesn't need per-source integrations. Include a concrete example in the README:
  ```yaml
  change_event:
    id: chg-2026-03-06-001
    timestamp: "2026-03-06T14:11:00Z"
    type: model_version  # deploy | config | feature_flag | model_version | prompt | adapter | formula | schema
    scope:
      service: webapp
      environment: production
      rig: rig-webapp  # optional, for agentic systems
    source: model-registry
    actor: deploy-pipeline
    detail:
      from_version: "claude-sonnet-4-20250514"
      to_version: "claude-sonnet-4-20250715"
    risk: low | medium | high  # optional, source-assessed
    rollback_available: true
  ```
- How implementations reference the spec (NthLayer, Arbiter, etc. listed as implementations)
- Relationship to existing standards: extends OpenSLO concepts, aligns with OTel semantic conventions, complements CDEvents (the change event schema specifically complements CDEvents by covering AI-specific change types that CDEvents doesn't address)

**README structure:**
1. What is OpenSRM (2-3 sentences)
2. Quick example manifest
3. Specification overview (manifest types, key fields)
4. Judgment SLOs for AI systems (the differentiator)
5. Change event schema (standardised change format covering traditional and AI-specific changes)
6. Semantic conventions
7. Implementations (list the ecosystem components with links)
8. Relationship to other standards
9. Contributing


### Arbiter

**Repo: `arbiter`**

**One-liner:** Universal quality measurement engine for AI agent output.

**What it is:** A standalone agent that evaluates AI agent output quality, tracks per-agent quality trends over rolling windows, detects quality degradation, measures its own accuracy through self-calibration, and governs agent autonomy based on measured performance. It answers the question every team running multiple AI agents is asking: "which of my agents is producing good work and which is silently producing garbage?"

The Arbiter also subsumes the role of a Reliability Governor (described in the existing ARCHITECTURE.md as a separate agent). Rather than having two things that watch agent quality, the Arbiter both measures quality and acts on those measurements: adjusting agent autonomy when judgment SLO error budgets are exhausted, reducing agents to advisory-only mode when quality degrades, and proposing autonomy increases (with human approval) when performance is sustained. This is a one-way safety ratchet: the Arbiter can reduce agent autonomy (safe direction) but cannot increase it without human approval.

**What it is not:** A GasTown plugin (the Guardian is the GasTown-specific implementation, the Arbiter is the universal version). Not a training pipeline (but training pipelines like lora-forge consume its output). Not an alerting system (but it produces signals that alerting systems consume).

**Origin:** The concept was proven inside GasTown as the Guardian (PR #2263, merged by Steve Yegge), a Deacon plugin that scores per-worker output quality in the merge pipeline. The Arbiter extracts this pattern into something any multi-agent system can use.

**Key concepts to cover in the README:**
- The core problem (at scale, you can't eyeball every agent's output)
- How it works: receive agent output, route to model for evaluation, persist scores, track trends, detect degradation
- ZFC architecture: the code is transport (plumbing), the model provides judgment (quality evaluation)
- Self-calibration: when the Arbiter scores output as good and a human later corrects it, that's a measurable signal. Judgment SLOs on the Arbiter itself (false accept rate, precision, recall)
- Governance: the Arbiter watches judgment SLO error budgets for all agents and makes autonomy decisions. When an agent's reversal rate exceeds its SLO target, the Arbiter increases human review requirements. When the error budget is exhausted, the agent drops to advisory-only mode. Sustained good performance can lead to autonomy increases (with human approval only). This is the one-way safety ratchet: automation can always be constrained, never self-expanded
- Governance actions: increase human review threshold, reduce to advisory-only, propose autonomy increase (requires human approval), flag for retraining or prompt adjustment, escalate to human operators when multiple agents degrade simultaneously
- Cost as a reliability dimension: the Arbiter tracks cost per agent per task alongside quality scores. Token spend, API calls, and compute cost are measured and correlated with quality. An agent that's expensive and low-quality gets constrained faster than one that's cheap and low-quality. Cost-per-quality-unit (how much does it cost to produce good output from this agent?) becomes a first-class metric alongside reversal rate and calibration. This matters for enterprise adoption because reliability decisions have cost implications (deeper review costs more tokens, frontier models cost more than local models) and cost pressures affect reliability (teams cut review depth to save tokens, which degrades quality, which causes incidents). Cost budgets can be declared in OpenSRM manifests alongside SLO targets, giving operators a unified view of quality and efficiency
- Model-agnostic: swap Claude for Gemini or a local model, the transport doesn't change, the judgment quality changes (and is measurable)
- **OTel metric emission (critical for NthLayer integration):** The Arbiter MUST emit raw OTel metrics for every evaluation, not just events. These are the metrics that flow through the OTel Collector to Prometheus and that NthLayer queries for deploy gating. The specific metrics are: `gen_ai_decision_total` (counter of evaluations), `gen_ai_decision_score` (quality score gauge), `gen_ai_override_reversal_total` (counter of human reversals), `gen_ai_override_correction_total` (counter of human corrections), `gen_ai_decision_confidence` (confidence gauge), `gen_ai_decision_cost_tokens` (token counter), `gen_ai_decision_cost_currency` (cost gauge). All metrics carry labels for service, agent, dimension, and environment. Without these metrics in Prometheus, NthLayer cannot generate judgment SLO recording rules or block deploys when judgment error budgets are exhausted. This is the bridge between Arbiter (measures quality) and NthLayer (enforces quality at the deployment boundary).
- OpenSRM integration: reads judgment SLO thresholds from the manifest, but also works with simple config for teams that don't use OpenSRM
- Adapters for different agent systems (GasTown, Devin, generic webhook)

**README structure:**
1. What is the Arbiter (the pitch: "point this at your agents, it tells you which ones are good")
2. How it works (simple diagram: agent output → Arbiter → quality scores + trends + alerts)
3. Quick start (simplest possible setup)
4. Architecture (ZFC: transport vs judgment)
5. Self-calibration (judgment SLOs on the Arbiter itself)
6. Governance (autonomy management, one-way safety ratchet)
7. Cost tracking (cost per agent, cost-per-quality-unit, cost budgets)
8. OTel metrics reference (the exact metric names emitted, their types, labels, and how they flow to Prometheus for NthLayer to query)
9. Integration with OpenSRM (optional, for teams that want SLO contracts)
10. Adapters (how to connect to different agent systems)
11. OpenSRM Ecosystem (how the Arbiter relates to NthLayer, SitRep, Mayday, with integration diagram)
12. Prior art (Guardian in GasTown, link to PR #2263)
13. Contributing


### NthLayer

**Repo: `nthlayer`**

**One-liner:** Generate reliability infrastructure from declarative service manifests.

**What it is:** A CLI that reads OpenSRM manifests and generates Prometheus alerting rules, recording rules, Grafana dashboards, PagerDuty configurations, and OpenSLO definitions. Deterministic transformation: manifest in, monitoring infrastructure out.

**What it already does (existing repo at github.com/rsionnach/nthlayer):**
- `nthlayer apply` — generates Prometheus alerts, recording rules, Grafana dashboards, OpenSLO from service.yaml
- `nthlayer verify` — validates declared metrics exist in Prometheus
- `nthlayer check-deploy` — deployment gate based on error budget
- `nthlayer validate-spec` — policy enforcement via OPA/Rego
- `nthlayer portfolio` — org-wide SLO health view
- `nthlayer slo collect` — queries Prometheus for current budget
- `nthlayer init` — interactive service.yaml creation
- 18 technology templates (PostgreSQL, Redis, Kafka, etc.)
- PagerDuty integration, Grafana push, Mimir/Cortex ruler push

**Judgment SLO support (new, integrates with the Arbiter):**

NthLayer already generates Prometheus recording rules for traditional SLOs (latency error budget burn rate, availability error budget, etc.). The same mechanism must be extended for judgment SLOs when a manifest declares `type: ai-gate`.

The flow:

1. The Arbiter emits raw OTel metrics for every evaluation it performs. These are counters and gauges, not pre-aggregated rates:
   - `gen_ai_decision_total{service, agent, dimension, environment}` — counter of evaluations
   - `gen_ai_decision_score{service, agent, dimension, environment}` — gauge of latest quality score (0.0-1.0)
   - `gen_ai_override_reversal_total{service, agent, environment}` — counter incremented when a human fully reverses an Arbiter approval
   - `gen_ai_override_correction_total{service, agent, environment}` — counter incremented when a human modifies (but doesn't fully reverse) Arbiter-approved output
   - `gen_ai_decision_confidence{service, agent, environment}` — gauge of the Arbiter's confidence in its own evaluation
   - `gen_ai_decision_cost_tokens{service, agent, environment}` — counter of tokens consumed per evaluation
   - `gen_ai_decision_cost_currency{service, agent, environment}` — gauge of estimated cost in currency

2. These raw metrics flow through the standard OTel Collector → Prometheus pipeline (the same pipeline every OTel deployment already has).

3. NthLayer reads the manifest's judgment SLO section and generates Prometheus recording rules that compute the aggregated judgment SLO metrics from the raw counters. For example, a manifest declaring `reversal.rate.target: 0.05` with a `window: 30d` causes NthLayer to generate:
   ```yaml
   - record: gen_ai:judgment:reversal_rate:30d
     expr: |
       rate(gen_ai_override_reversal_total{service="code-reviewer"}[30d])
       / rate(gen_ai_decision_total{service="code-reviewer"}[30d])
   - record: gen_ai:judgment:error_budget_remaining:reversal
     expr: |
       1 - (gen_ai:judgment:reversal_rate:30d / 0.05)
   ```

4. NthLayer's `check-deploy` queries these recording rules alongside traditional error budget rules. If the judgment SLO error budget is exhausted (`gen_ai:judgment:error_budget_remaining:reversal <= 0`), the deploy is blocked. This is the same gating mechanism NthLayer already uses for traditional SLOs, extended to judgment quality metrics.

5. NthLayer's `apply` generates Grafana dashboard panels for judgment SLO metrics alongside traditional SLO panels, giving operators a unified view of service health that includes both "is this service fast and available?" and "is this service making good decisions?"

This is critical because it closes the loop between the Arbiter (produces quality measurements) and NthLayer (enforces quality gates). Without this connection, judgment SLOs are measured but never enforced at the deployment boundary. With it, a team can declare "this agent must maintain a reversal rate below 5%" in their manifest and NthLayer will block deploys when the error budget is exhausted, exactly as it would for a traditional latency SLO.

**Planned agentic extension (follows ZFC):**
- `nthlayer infer` — model analyses a codebase and proposes an OpenSRM manifest (judgment). NthLayer then generates artifacts from that manifest (transport). Clean ZFC boundary.

**README structure:**
1. What is NthLayer (reliability-as-code, one manifest, all your monitoring)
2. Quick start (install, init, apply)
3. What it generates (Prometheus, Grafana, PagerDuty, OpenSLO)
4. Commands reference
5. Technology templates
6. Judgment SLO support (how NthLayer generates recording rules for AI decision quality metrics from `type: ai-gate` manifests, how `check-deploy` gates on judgment error budgets alongside traditional error budgets, with a concrete example showing the manifest → recording rule → deploy gate flow)
7. Agentic inference (planned: model proposes manifest, NthLayer generates from it)
8. OpenSRM ecosystem (how it relates to Arbiter, SitRep, Mayday)
9. Contributing


### SitRep

**Repo: `sitrep`**

**One-liner:** Situational awareness through automated signal correlation during incidents.

**What it is:** Correlates signals from multiple sources (metrics, logs, traces, change events, quality scores) to build a coherent picture of what's happening during an incident or degradation. Produces situational snapshots that combine what changed, what broke, and what the likely cause is.

**What it is not:** A monitoring system (it consumes monitoring data, doesn't produce it). Not an incident management tool (that's Mayday). Not a root cause analysis engine (it correlates, the model interprets).

**Key concepts to cover in the README:**

- **The core problem (event volume at enterprise scale):** This is critical and should be prominent in the README. Enterprise-scale distributed systems (think thousands of services at companies like Workday, Stripe, Twilio) produce an enormous volume of observability signals: metrics at 15-second intervals across thousands of services, structured logs on every request, distributed traces, alerts from multiple monitoring systems, change events from CI/CD pipelines, feature flag changes, and infrastructure scaling events. This is millions of events per minute. No human can correlate across all of these signals during an incident by reading dashboards. No existing tool pre-processes these signals into a form that AI agents (or humans) can consume efficiently. Prometheus handles metrics, Loki handles logs, Jaeger handles traces, but correlating across all three plus change events plus quality scores at enterprise scale is an unsolved problem that most teams handle manually during incidents. Agentic systems (like GasTown or Devin fleets) add additional volume on top of this enterprise baseline. SitRep exists because raw observability data at enterprise scale is unusable without a pre-correlation layer.

- **Pre-correlation:** The key architectural concept. Rather than storing raw events and querying them at incident time (which is too slow and too noisy), SitRep continuously pre-correlates signals in the background. It groups related signals, computes temporal proximity, identifies co-occurring changes, and maintains a rolling window of pre-correlated state. When an incident happens, the pre-correlated data is already available, so generating a situational snapshot takes seconds rather than minutes of ad-hoc querying. Pre-correlation is transport (deterministic grouping, windowing, counting). Interpreting what the correlations mean is judgment (model decides).

- **Event ingestion architecture:** At enterprise scale, SitRep needs a streaming/queuing layer between event producers and the correlation engine. Raw events from OTel collectors, monitoring systems, CI/CD pipelines, change event sources, and quality score producers should flow through a message queue (Kafka at enterprise scale, NATS for smaller deployments) that handles backpressure, replay, and fan-out. SitRep consumes from the queue, pre-correlates, and stores the results. This decouples event production rate from correlation processing rate, which is essential when thousands of services are each producing metrics, logs, and traces continuously. The README should be explicit that this streaming layer is a core architectural requirement for production use, not an optimization.

- **Situational snapshots:** Point-in-time snapshots that answer "what's happening right now" with evidence links. A snapshot is a structured document with a defined schema:

  Snapshot schema (cover in README with a concrete example):
  ```yaml
  snapshot:
    id: sitrep-2026-03-06T14:23:00Z
    triggered_by: alert | schedule | manual
    window: 15m
    severity: info | warning | critical
    summary: "model-generated natural language summary"
    signals:
      - source: arbiter
        type: quality_degradation
        detail: "worker ace-mjxwfy7e rejection rate 0.33 (threshold 0.20)"
        timestamp: 2026-03-06T14:18:00Z
      - source: otel
        type: deploy
        detail: "model version updated on rig-webapp 12m ago"
        timestamp: 2026-03-06T14:11:00Z
    correlations:
      - signals: [0, 1]
        confidence: 0.82
        interpretation: "quality degradation started within 7m of model version change"
    topology:
      affected_services: [webapp, api-gateway]
      dependency_chain: [webapp -> api-gateway -> database]
    recommended_actions:
      - "investigate model version change on rig-webapp"
      - "check if other workers on same rig are affected"
  ```

  The schema captures what happened (signals), what's related (correlations with confidence), what's affected (topology from OpenSRM manifests), and what to do (recommended actions). The signals and topology sections are transport (structured data from known sources). The summary, correlation interpretation, and recommended actions are judgment (model-generated).

- **Hybrid generation modes:** SitRep generates snapshots in three modes: batch (periodic, every N minutes, for continuous situational awareness), incident-triggered (on alert firing, for immediate incident context), and refresh (on-demand, when a human or agent requests an updated picture). Each mode produces the same snapshot schema but with different urgency and depth. Batch snapshots are lightweight summaries. Incident-triggered snapshots pull in more context and deeper correlation. Refresh snapshots can incorporate new information that arrived since the last snapshot.

- **Agent states:** SitRep operates in distinct states that affect its behaviour: WATCHING (normal operations, background correlation, 5-minute snapshot cycle), ALERT (elevated signal detected, increased correlation frequency, broader signal ingestion), INCIDENT (incident declared, continuous reassessment, 1-minute snapshots, pushes context to Mayday), DEGRADED (own judgment SLO metrics below threshold, conservative mode, reduced confidence in correlations, flags for human review). The DEGRADED state is important: SitRep monitors its own quality and reduces confidence when it detects its correlations are less reliable.

- **Change attribution:** A specific correlation pattern that deserves its own section. When quality degrades (Arbiter signals), SitRep looks for recent changes that temporally correlate. It consumes changes via the standardised change event schema defined in the OpenSRM spec, which means all change sources (deploys, config updates, model version swaps, prompt changes, adapter deployments, formula revisions) arrive in a uniform format. SitRep doesn't need per-source integrations because the change event schema normalises everything. The pre-correlation layer continuously maintains a rolling window of changes, so when a quality signal fires, the candidate causes are already indexed. Change attribution is judgment (the model evaluates whether the temporal correlation is causal), but the candidate set is pre-computed by transport.

- **OpenSRM integration:** reads service topology from manifests to understand dependency relationships when correlating. A quality drop in service A that depends on service B (as declared in the manifest) triggers SitRep to check service B's signals automatically.

- **Judgment SLOs for SitRep itself:** SitRep has its own judgment SLOs measured through the Arbiter's governance. Correlation accuracy: what percentage of SitRep's "related change" assessments do humans agree with? False positive rate: how often does SitRep flag a change as incident-related when it isn't? Every correlation assessment emits a `gen_ai.decision.*` OTel event, and human disagreements emit `gen_ai.override.*` events that feed SitRep's own quality measurement.

**README structure:**
1. What is SitRep (automated situational awareness for agentic systems at scale)
2. The problem it solves (event volume at enterprise scale overwhelms both humans and existing tools)
3. Pre-correlation (the core architectural concept)
4. Situational snapshots (schema, example, what a snapshot contains)
5. Event ingestion (streaming/queuing architecture for scale)
6. Generation modes (batch, incident-triggered, refresh)
7. Agent states (WATCHING, ALERT, INCIDENT, DEGRADED)
8. Change attribution (correlating quality changes with system changes)
9. Signal sources (OTel, change events, Arbiter scores, deploy records)
10. OpenSRM integration (topology from manifests)
11. Self-measurement (judgment SLOs for SitRep itself)
12. OpenSRM Ecosystem (how SitRep relates to Arbiter, NthLayer, Mayday, with integration diagram)
13. Architecture (ZFC: ingestion and pre-correlation are transport, interpretation is judgment)
14. Contributing


### Mayday

**Repo: `mayday`**

**One-liner:** Multi-agent incident response coordinated by AI.

**What it is:** An incident response system where specialised AI agents collaborate to triage, investigate, communicate, and remediate under human supervision. Each agent has a clear domain, defined decision authority, and its own judgment SLO. Mayday is the primary incident response platform in the ecosystem, not a supplement to PagerDuty or Opsgenie.

**What it is not:** An alerting system (it receives alerts from the Arbiter, SitRep, Prometheus, or any webhook source). Not a monitoring tool. Not an on-call scheduler. Not a notification service (but it uses PagerDuty, Slack, email, etc. as notification channels when it needs to reach humans).

**Alert flow (critical architectural decision):** Alerts flow into the ecosystem first. The flow is: alert source (Arbiter quality breach, Prometheus alert, any webhook) → SitRep provides correlated context → Mayday coordinates the response → PagerDuty/Slack/email are notification channels Mayday uses to reach humans when it needs approval or escalation. PagerDuty is downstream of Mayday, not upstream. Mayday owns the incident lifecycle.

**Orchestration model:** Pipeline with parallel branches. Mayday uses a purpose-built orchestrator (not a general-purpose agent framework) that sequences agents based on the incident lifecycle. The orchestrator itself is not an agent. It's a deterministic state machine that sequences agent execution (transport). Agents reason within their step (judgment).

```
Alert Source (Arbiter / Prometheus / webhook)
       │
       ▼
   SitRep Snapshot (correlated context)
       │
       ▼
   Mayday Orchestrator (creates incident context)
       │
       ▼
┌──────────────┐
│    Triage    │  severity, blast radius, initial assignment
└──────┬───────┘
       │
       ├───────────────────────┐
       ▼                       ▼
┌──────────────┐       ┌──────────────┐
│Investigation │       │Communication │  initial stakeholder notification
└──────┬───────┘       └──────┬───────┘
       │                       │
       │ root cause found      │
       ├───────────────────────┤
       ▼                       ▼
┌──────────────┐       ┌──────────────┐
│ Remediation  │       │Communication │  update with root cause + fix
└──────────────┘       └──────────────┘
```

**Shared incident context:** All Mayday agents read from and write to a shared incident context object that accumulates findings throughout the incident. Include this schema in the README:

```yaml
incident_context:
  id: INC-2026-0142
  declared_at: "2026-02-23T14:32:00Z"
  source: arbiter_quality_breach

  triage:
    severity: P1
    blast_radius: [checkout-service, payment-gateway]
    affected_slos: [checkout-availability, payment-latency-p99]
    assigned_teams: [platform-checkout, platform-payments]

  investigation:
    hypotheses:
      - id: H1
        description: "model version update at 14:28 introduced quality regression"
        confidence: 0.82
        evidence: [sitrep-correlation-id-847, arbiter-quality-drop]
      - id: H2
        description: "database connection pool exhaustion"
        confidence: 0.34
        evidence: [log-pattern-conn-timeout]
    root_cause: H1

  communication:
    updates_sent:
      - channel: "#platform-incidents"
        timestamp: "2026-02-23T14:33:12Z"
        type: initial_notification
      - channel: status_page
        timestamp: "2026-02-23T14:35:00Z"
        type: investigating

  remediation:
    proposed_action: rollback_model_version
    target: rig-webapp
    risk_assessment: low
    requires_human_approval: false
    executed_at: null
```

**Agent roles and decision authority:**

Triage Agent: classifies severity based on blast radius and SLO impact from OpenSRM manifests. Can set severity, notify teams (via PagerDuty/Slack as notification channels), assign ownership. Cannot remediate. Cannot override existing classification without human approval. Judgment SLO: reversal rate on severity classifications (target less than 10%).

Investigation Agent: generates hypotheses from SitRep snapshots, gathers evidence from metrics/logs/change history, ranks root causes by confidence. Can form and rank hypotheses, declare root cause when confidence exceeds threshold. Cannot execute any remediation. Judgment SLO: root cause agreement with post-incident review (target 70% at maturity).

Communication Agent: audience-appropriate messaging via appropriate channels. Can draft and send updates within pre-approved templates, choose channels and timing. Cannot contradict investigation findings, cannot communicate resolution until confirmed. Judgment SLO: human edit rate on outgoing communications (target less than 15%).

Remediation Agent: selects and executes fixes. Can suggest fixes to humans, execute pre-approved safe actions (rollback, scale up, disable feature flag) without human approval. Cannot execute novel remediation not pre-approved in the OpenSRM manifest. Cannot change services outside the blast radius. Judgment SLO: fix success rate (target 80%).

**Human-in-the-loop design:** Agents never take destructive action without human approval unless the action is pre-approved as safe in the OpenSRM manifest. Humans make severity calls, approve novel remediations, and override agent decisions. Every agent decision emits OTel telemetry, and every human override feeds back into the agent's judgment SLO.

**Key concepts to cover in the README:**
- The problem (incident response involves repetitive work that AI agents can handle, freeing humans for judgment calls)
- Alert flow (alerts → SitRep → Mayday → notification channels, not PagerDuty → Mayday)
- Orchestration model (pipeline with parallel branches, deterministic sequencing, agents reason within steps)
- Incident context (shared accumulating record, schema with example)
- Agent roles (triage, investigation, communication, remediation) with decision authority and judgment SLOs for each
- Human-in-the-loop (pre-approved safe actions, one-way safety ratchet via the Arbiter's governance)
- OpenSRM integration (severity tiers, safe action definitions, dependency topology, escalation paths from manifests)
- SitRep integration (consumes snapshots for correlated incident context)
- Arbiter integration (quality scores inform whether AI agents in the response are producing reliable diagnostics, governance layer adjusts autonomy)
- Notification channels (PagerDuty, Slack, email, status pages are outputs of Mayday, not inputs)
- Post-incident learning: after resolution, Mayday produces structured findings that flow back into the ecosystem. Findings map to specific manifest updates (tighter SLO targets, new dependency declarations, new safe action definitions), NthLayer rule refinements (alerts that should have fired earlier), and Arbiter threshold revisions. This closes the learning loop so the system improves after every incident rather than just documenting what happened

**README structure:**
1. What is Mayday (AI-coordinated incident response)
2. The problem it solves
3. Alert flow (how incidents enter the ecosystem)
4. Orchestration model (pipeline diagram, agent sequencing)
5. Incident context (schema, example)
6. Agent roles (triage, investigation, communication, remediation with decision authority)
7. Human-in-the-loop design
8. Post-incident learning (how findings flow back to manifests, rules, and thresholds)
9. OpenSRM integration (manifests define severity, safe actions, topology)
10. Ecosystem integration (SitRep for context, Arbiter for governance)
11. Architecture (ZFC: orchestrator is transport, agent decisions are judgment)
12. Status (architecture phase, not yet implemented)
13. Contributing


## How the Components Integrate

### The Event Volume Problem (Cross-Cutting Concern)

This should be documented prominently in the ecosystem overview and referenced from SitRep's README. The OpenSRM ecosystem must handle the volume of observability events produced by enterprise-scale distributed systems. A company running thousands of services (think SaaS platforms like Workday, Stripe, Twilio) produces an enormous volume of signals: metrics emitted at 15-second intervals across thousands of services, structured logs on every request, distributed traces across service boundaries, alerts from multiple monitoring systems, change events from CI/CD pipelines, feature flag changes, and infrastructure scaling events. This is millions of events per minute flowing into the ecosystem from external sources.

This is the primary scale concern. Agentic systems (like GasTown at 20-50 agents) add additional event volume on top of this, but the enterprise observability firehose is the harder problem by orders of magnitude. SitRep needs to correlate across all of these signals in near-real-time. You cannot query raw events at incident time across millions of signals. Pre-correlation must happen continuously in the background so that when an incident fires, the correlated view is already built.

Existing observability infrastructure was not designed for this level of cross-signal correlation. Prometheus handles metrics well. Loki handles logs. Jaeger handles traces. But correlating across all three plus change events plus quality scores plus custom signals at enterprise scale is an unsolved problem that most teams handle manually during incidents (or don't handle at all).

The ecosystem needs a streaming/queuing layer (Kafka recommended at enterprise scale, NATS acceptable for smaller deployments) as foundational infrastructure that sits between event producers (OTel collectors, monitoring systems, CI/CD pipelines, the Arbiter) and event consumers (SitRep for correlation, NthLayer for dashboard updates, Mayday for incident detection, training pipelines like lora-forge for training data). This is transport, not a product. It's plumbing that enables the ecosystem to function at scale.

Kafka is the default recommendation at enterprise scale because its partitioning, compaction, and replay capabilities are designed for exactly this volume. The topic/partition design maps naturally to OpenSRM's service topology: partition by service, topic by signal type, consumer groups per ecosystem component.

This streaming layer should be documented as an architectural requirement in the ecosystem overview, with guidance on: minimum viable setup (single NATS instance for a solo developer or small team), production setup (Kafka cluster for enterprise deployments), and the topic/partition design that maps to OpenSRM's service topology.

### Integration Diagram

Include a version of this in each README's ecosystem section, adapted to highlight that component's role:

```
                        ┌─────────────────────────┐
                        │     OpenSRM Manifest     │
                        │  (the shared contract)   │
                        └────────────┬────────────┘
                                     │
                    reads            │           reads
               ┌─────────────┬──────┴──────┬─────────────┐
               ▼             ▼             ▼             ▼
         ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
         │ Arbiter  │ │ NthLayer │ │  SitRep  │ │  Mayday  │
         │          │ │          │ │          │ │          │
         │ quality  │ │ generate │ │correlate │ │ incident │
         │+govern   │ │ monitoring│ │ signals  │ │ response │
         │+cost     │ │          │ │          │ │          │
         └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
              │             │             │             │
              └──────┬──────┴──────┬──────┘             │
                     ▼             ▼                    ▼
              ┌────────────────────────────┐  ┌──────────────┐
              │  Streaming / Queue Layer   │  │  Consumes    │
              │  (Kafka / NATS / etc)      │  │  all three   │
              └──────────┬─────────────────┘  └──────┬───────┘
                         ▼                           │
              ┌────────────────────────┐             │
              │   OTel Collector /     │             │
              │   Prometheus / etc     │             │
              └────────────────────────┘             │
                                                     │
              ┌──────────────────────────────────────┘
              │  Learning loop (post-incident):
              │  Mayday findings → manifest updates
              │  → NthLayer regenerates → Arbiter
              │  refines → SitRep improves
              └──────────────────────────────────────▶ OpenSRM
```

Data flows:
- **Forward path:** Alert sources (Arbiter quality breach, Prometheus alert, any webhook) → SitRep correlates with context → Mayday coordinates incident response → PagerDuty/Slack/email as notification channels to reach humans
- **Quality path:** Arbiter produces quality scores as OTel metrics → NthLayer generates dashboards for them → SitRep correlates them with other signals → Mayday uses them during incident response
- **Deploy gate path:** Arbiter emits raw OTel metrics (decision counts, reversal counts, scores) → OTel Collector exports to Prometheus → NthLayer generates recording rules that compute judgment SLO aggregations (reversal rate, error budget remaining) from the manifest's `type: ai-gate` section → NthLayer's `check-deploy` queries these recording rules alongside traditional error budget rules → deploy blocked if judgment error budget exhausted. This is the enforcement loop that turns judgment SLOs from passive measurement into active deployment gates.
- **Change path:** Change events from all sources (normalised via OpenSRM change event schema) → streaming layer → consumed by SitRep (correlation), Arbiter (quality context), Mayday (investigation)
- **Learning loop:** Mayday post-incident findings → OpenSRM manifest updates → NthLayer regenerates improved artifacts → Arbiter refines thresholds → SitRep improves correlations. The system gets better after every incident.
- Each arrow is optional. Any component works alone. Together they form a complete reliability lifecycle for AI systems.
- PagerDuty and similar tools are notification channels that Mayday uses, not incident management platforms that sit upstream of the ecosystem.

The integration point for a user is: one `service.reliability.yaml` manifest, a shared OTel backend, and whichever components they need.


## What Each README Must Communicate

Every README follows the same principle: **standalone value first, ecosystem context second.**

1. The first three paragraphs must make the component's value clear to someone who has never heard of OpenSRM. They should understand what the tool does and why they need it without reading about any other component.

2. Every README must include an "OpenSRM Ecosystem" section that explains how this component relates to the others, includes the integration diagram (adapted to highlight this component's role), and links to the other repos. This section is additive context, not a prerequisite for understanding the tool, but it must be present in every README so that someone discovering any single component can find the rest of the ecosystem.

3. No README should require reading another repo's README to make sense.


## Writing Style

- No emdashes (use commas, parentheses, or separate sentences instead)
- Use parentheses for clarifications
- Prefer longer compound sentences with connective phrases over short choppy ones
- Use single quotes for emphasis rather than bold (in prose, not headers)
- Keep a warm but direct tone, not corporate
- Technical but accessible, assume the reader is an engineer but not necessarily an SRE


## Files to Create Per Repo

Each subdirectory needs:
- `README.md` — as described above
- `LICENSE` — Apache 2.0
- `CONTRIBUTING.md` — brief, points to OpenSRM spec for shared conventions, explains how to contribute to this specific component
- `ZFC.md` — the full Zero Framework Cognition document (for Arbiter, SitRep, Mayday). For OpenSRM and NthLayer, reference it rather than including it.
- `.github/ISSUE_TEMPLATE/bug_report.md` — basic bug report template
- `.github/ISSUE_TEMPLATE/feature_request.md` — basic feature request template

For `opensrm` specifically, also create:
- `spec/v1/specification.md` — placeholder noting the spec is being migrated from the existing repo
- `spec/v1/schema.json` — placeholder
- `examples/` directory with a placeholder example manifest
- `ECOSYSTEM.md` — the full ecosystem overview document describing all components and how they integrate. This should include: the component taxonomy (data sources, tools, agents), the integration diagram, the event volume problem and streaming layer guidance, the alert flow (alerts → SitRep → Mayday → notification channels), deployment tiers (Tier 1: static only with manifests + NthLayer, Tier 2: add SitRep correlation, Tier 3: full autonomous with Mayday + Arbiter governance), and the security model (data classification, access control, agent authority boundaries with the one-way safety ratchet). The existing ARCHITECTURE.md has detailed content on deployment tiers and security that should be carried into ECOSYSTEM.md.

  ECOSYSTEM.md must also document these two cross-cutting concerns:

  **The Post-Incident Learning Loop:** The ecosystem has a complete forward path (Define → Generate → Measure → Correlate → Respond) but the backward path is equally important. After Mayday resolves an incident, findings must flow back into every component: incident findings update OpenSRM manifests (tighten SLO targets that were too loose, add missing dependency declarations, define new safe actions for remediation). Quality patterns from the Arbiter refine NthLayer's generated alerting rules (alerts that fired too late or didn't fire at all). SitRep's correlation accuracy on past incidents improves its future correlations. This is the difference between a system that responds to incidents and one that learns from them. Every mature SRE practice has post-incident review, but almost none systematically feed findings back into tooling. ECOSYSTEM.md should document the learning loop as a defined data flow: what Mayday's post-incident output looks like, how it maps to manifest updates, how the Arbiter's historical data informs threshold revisions, how SitRep's past correlations calibrate future ones. The learning loop is what turns five independent tools into a system that improves over time.

  ```
  Forward path:
  OpenSRM → NthLayer → Arbiter → SitRep → Mayday
  (define)   (generate)  (measure)  (correlate) (respond)

  Learning loop (backward path):
  Mayday findings → OpenSRM manifest updates (tighter targets, new dependencies)
  Mayday findings → NthLayer rule refinements (better alerts)
  Arbiter history → NthLayer threshold revisions (data-driven targets)
  SitRep accuracy → SitRep correlation improvements (self-calibration)
  Arbiter governance → all agents (autonomy adjustments)
  ```

  **The Change Event Ecosystem:** The change event schema defined in the OpenSRM spec is consumed by multiple components. SitRep uses it for change attribution (correlating quality drops with recent changes). Mayday uses it during investigation (what changed before the incident?). The Arbiter uses it to contextualise quality shifts (was a quality drop caused by a model version change or genuine agent degradation?). ECOSYSTEM.md should show how change events flow from sources through the streaming layer to all consumers, and emphasise that AI-specific changes (prompt updates, model swaps, adapter deployments, formula revisions) are first-class change types alongside traditional deploys.


## ZFC REFERENCE

Include this as ZFC.md in repos that have judgment responsibilities (Arbiter, SitRep, Mayday):

---

# Zero Framework Cognition (ZFC)

## Core Tenet of the OpenSRM Ecosystem

**Transport is code. Judgment is model.**

Code handles movement: receiving inputs, routing them, persisting results, exposing APIs, sending alerts. Code never decides whether something is good, bad, important, risky, or correct. That is judgment, and judgment belongs to the model.

This principle governs every architectural decision across the OpenSRM ecosystem.


## Origin

ZFC was articulated by Steve Yegge as a foundational design principle for GasTown: "Go code should never make judgment calls. Go is transport, not intelligence. Claude makes the decisions."

The principle emerged from a practical observation. When you encode judgment into compiled code (scoring functions, threshold comparisons, classification logic), you get decisions that can't adapt, can't reason about edge cases, and can't improve without a code change. A hardcoded `if score < 0.8 { status = "WARN" }` treats a 0.79 on a documentation typo the same as a 0.79 on broken authentication logic. A model understands the difference. Code never will.


## The Distinction

Transport is deterministic transformation with no ambiguity about what the right answer is:

- Receiving a diff from a webhook and passing it to a review function
- Persisting a quality score to a database or state file
- Generating a Prometheus recording rule from a declared SLO target of `p99: 200ms`
- Sending an alert when the model says to alert
- Routing a message between agents via a mail queue
- Rendering a dashboard from stored metrics
- Validating that a YAML manifest conforms to a JSON schema

Judgment involves interpretation, evaluation, or any decision where context changes the right answer:

- Reading a diff and deciding whether the code is correct
- Scoring quality across dimensions (correctness, clarity, risk)
- Deciding whether a pattern of declining scores constitutes a real problem or normal variance
- Determining which services in a codebase are critical and what SLO targets they need
- Evaluating whether an incident is resolved or still degraded
- Correlating a quality drop with a recent change and deciding if the change caused it
- Recommending an action (nudge, escalate, park) based on agent behaviour patterns


## Practical Implications

### Config is guidance, not logic

Traditional approach: config defines thresholds, code compares values against thresholds, code decides the outcome.

ZFC approach: config defines context and preferences, the model receives that context alongside the data, the model decides the outcome. A rejection rate threshold of 0.20 in config means "the operator considers 20% rejection concerning" not "trigger WARN at exactly 0.20."

### Fail open on model unavailability

If the model is unavailable, transport continues. Data is received, persisted, and routed. Judgment pauses. The system degrades to "no quality opinion" rather than "wrong quality opinion."

### Self-calibration is native

Because judgment comes from the model, every judgment is inherently auditable. The model said "this is good" and a human later corrected it. That's a measurable signal. Under ZFC, self-calibration (judgment SLOs on the judging agent itself) is a natural consequence of the architecture rather than an afterthought bolted on.

### Model-agnostic by design

Transport code doesn't care which model provides the judgment. Swap Claude for Gemini, GPT, or a local model and the transport layer is unchanged. The quality of judgment changes, which is itself measurable through the self-calibration loop. This makes every tool in the ecosystem model-portable without code changes.


## What ZFC Is Not

ZFC is not "put an LLM in every code path." Most code in the ecosystem is and should remain pure transport. ZFC applies specifically to the decision points where context matters and the right answer depends on interpretation.

ZFC is also not "models are always right." The self-calibration loop exists precisely because models make bad judgments. The point is that bad model judgments are improvable (through better prompts, better context, better models) while bad hardcoded judgments require code changes and redeployment.


## Summary

Every component in the OpenSRM ecosystem asks two questions about each function it performs:

1. Is there exactly one right answer given the inputs? That's transport. Write it in code.
2. Does the right answer depend on context, interpretation, or evaluation? That's judgment. Send it to the model.

Transport is code. Judgment is model. No exceptions.

---


## Instructions for Claude Code

1. Read this entire document first.
2. The existing ARCHITECTURE.md at github.com/rsionnach/opensrm/blob/main/ARCHITECTURE.md contains detailed content that should inform ECOSYSTEM.md. Key elements to carry forward: deployment tiers (Tier 1/2/3), security model (data classification, access control, agent authority boundaries), agent communication protocols, and data flow diagrams. However, note these changes from the existing architecture: "IncidentTown" is now "Mayday", the "Reliability Governor" is now folded into the Arbiter, and the alert flow is corrected (alerts flow into the ecosystem first, PagerDuty is a notification channel downstream of Mayday, not an upstream trigger).
3. Create each subdirectory with all specified files.
4. Write each README so it stands alone. A reader landing on any single repo should understand what it does and why they need it without visiting any other repo.
5. Use the integration diagram (adapted per component) in each README's ecosystem section.
6. Follow the writing style guidelines strictly (no emdashes, parentheses for clarifications, warm but direct tone).
7. The Arbiter README should lead with the universal problem ("which of my agents is producing good work?") not with the GasTown origin story. The GasTown connection goes in a Prior Art section.
8. NthLayer already exists as a working CLI. Its README should reflect what it already does, with planned features clearly marked.
9. SitRep and Mayday are in design phase. Their READMEs should be honest about this (architecture designed, implementation not started) while still communicating the vision clearly.
10. OpenSRM's README should lead with the manifest format and a concrete example. The ecosystem overview goes in ECOSYSTEM.md, not the README.
11. Every CONTRIBUTING.md should mention the Wasteland Wanted Board (https://wasteland.gastownhall.ai/) as a place where tasks for the component may be posted.
