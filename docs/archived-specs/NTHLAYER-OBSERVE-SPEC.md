# NthLayer: nthlayer-observe Component Spec & Migration Guide

**Status:** Approved for implementation  
**Date:** 2026-04-06  
**Author:** Rob  
**Context:** The nthlayer-generate capability audit found that 41% of generate's codebase is runtime infrastructure that doesn't belong in a compiler. This spec defines where that code goes and how it relates to the agentic components.

---

## The Core Architecture Principle

NthLayer has two kinds of runtime work. They must not be mixed.

**Deterministic infrastructure work** — reading live system state, querying Prometheus, discovering dependencies, checking if metrics exist, evaluating deployment gates. Same inputs always produce the same outputs. No LLM, no reasoning, no judgment. This is **observation**.

**Agentic reasoning work** — evaluating AI decision quality, correlating signals into root causes, triaging incidents, reasoning about remediation. These require LLM calls, produce different outputs for different runs, and have decision quality measured by judgment SLOs. This is **judgment**.

The architecture after migration:

```
generate (specs → artifacts, pure compiler, stateless)
    ↓ produces artifacts consumed by
observe (live state → deterministic assessments, runtime, stateful)
    ↓ produces assessments consumed by
measure (AI decision quality evaluation — AGENTIC, emits verdicts)
correlate (causal reasoning — AGENTIC, emits verdicts)
respond (incident response — AGENTIC, emits verdicts)
learn (retrospective analysis — AGENTIC, emits verdicts)
```

**The test for every capability:**
- Does it need an LLM? → Agentic component (measure/correlate/respond/learn)
- Does it query live infrastructure? → observe
- Is it deterministic given the same manifest? → generate
- Does it make a judgment call? → Agentic component, emits a verdict

---

## What nthlayer-observe Is

nthlayer-observe is the **deterministic runtime infrastructure layer**. It reads live system state and produces structured assessments. It is NOT agentic. It does NOT emit verdicts. It does NOT call LLMs.

### What It Does

1. **Collects SLO state** — queries Prometheus for SLI metrics, computes error budget remaining, burn rates, and budget projections. Currently: `slos/collector.py`, `slos/storage.py`.

2. **Detects drift** — tracks SLO budget trends over time, identifies degradation patterns. Currently: `drift/analyzer.py`, `drift/models.py`, `drift/patterns.py`.

3. **Verifies metric existence** — checks that metrics declared in manifests actually exist in Prometheus. Currently: `verification/verifier.py`, `verification/models.py`.

4. **Discovers metrics** — queries Prometheus for available metrics, classifies them by type. Currently: `discovery/client.py`, `discovery/classifier.py`.

5. **Discovers dependencies** — queries Kubernetes, Prometheus, Consul, etcd, Zookeeper, and Backstage for live service dependencies. Currently: `dependencies/discovery.py`, `dependencies/providers/`.

6. **Evaluates deployment gates** — makes go/no-go deployment decisions based on error budget state, freeze periods, business hours. Currently: `slos/gates.py`, `cli/deploy.py`, `policies/evaluator.py`.

7. **Correlates deployments** — 5-factor weighted scoring to associate deployments with incidents. Currently: `slos/correlator.py`. (Note: this is deterministic correlation using heuristics, not the LLM-powered causal reasoning in nthlayer-correlate.)

8. **Aggregates portfolio health** — computes org-wide reliability posture from live SLO data. Currently: live portions of `portfolio/aggregator.py`, `scorecard/calculator.py`.

9. **Hosts the runtime API server** — the FastAPI server that receives deployment webhooks, serves policy overrides, and provides health endpoints. Currently: `api/`.

### What It Produces: Assessments (NOT Verdicts)

Observe produces **assessments** — structured, deterministic descriptions of system state. An assessment is evidence. A verdict is a judgment drawn from evidence. Only agentic components emit verdicts.

```python
@dataclass
class Assessment:
    """
    A deterministic observation of system state.
    NOT a verdict. No judgment, no confidence score,
    no LLM reasoning. Same inputs always produce
    the same assessment.
    """
    id: str                         # unique assessment ID
    timestamp: datetime             # when the observation was made
    assessment_type: str            # "slo_state" | "drift" | "verification" | "gate" | "dependency"
    service: str                    # which service this assessment concerns
    producer: str                   # "nthlayer-observe"
    
    # The observation data — type-specific
    data: dict                      # structured payload, schema varies by type
    
    # NOT present (these belong on verdicts, not assessments):
    # - confidence (deterministic, no confidence needed)
    # - judgment / reasoning (no LLM involved)
    # - lineage.children (assessments don't chain to verdicts automatically)
```

Assessment type examples:

```yaml
# SLO state assessment
assessment_type: slo_state
data:
  slo_name: availability
  target: 0.999
  current: 0.9987
  error_budget_remaining: 0.43
  burn_rate_1h: 2.1
  burn_rate_6h: 1.4
  breaching: false

# Drift assessment
assessment_type: drift
data:
  slo_name: latency_p99
  trend: degrading
  rate: -0.02_per_day     # budget depleting 2% faster per day
  projected_breach: "2026-04-09T00:00:00Z"

# Verification assessment
assessment_type: verification
data:
  declared_metrics: 5
  found_metrics: 4
  missing: ["custom_payment_errors_total"]

# Gate assessment
assessment_type: gate
data:
  action: deploy
  decision: blocked        # "allowed" | "blocked" | "warning"
  reasons:
    - "Error budget below 20% (14.3% remaining)"
    - "Active incident INC-4821 affects downstream service"

# Dependency assessment
assessment_type: dependency
data:
  service: payment-api
  dependencies_declared: 3
  dependencies_discovered: 4
  undeclared: ["auth-cache"]
  missing: []
```

### How Agentic Components Consume Assessments

The agentic components (measure, correlate, respond) read assessments as input:

- **nthlayer-measure** reads SLO state assessments, then runs the LLM evaluation to produce an evaluation verdict. The assessment says "reversal rate is 2.7%, target is 1.5%." The verdict says "AI decision quality is degrading with 0.85 confidence."

- **nthlayer-correlate** reads alerts, assessments, and verdicts, then runs the LLM reasoning layer to produce a correlation verdict. The assessment says "deployment v2.3 occurred at 14:26, error budget dropped from 43% to 12%." The verdict says "model deploy v2.3 is the root cause with 0.91 confidence."

- **nthlayer-respond** reads correlation verdicts and gate assessments, then runs the agent pipeline. The gate assessment says "rollback is allowed, error budget is exhausted." The agent pipeline decides severity, proposes remediation, and manages approval.

**Key point for Claude Code:** Do NOT move code into measure, correlate, or respond if it doesn't involve LLM calls or judgment. If it's a Prometheus query, a threshold check, or a dependency lookup, it goes in observe. The agentic components should be thin wrappers around LLM reasoning that consume pre-gathered evidence.

---

## What nthlayer-observe Is NOT

- **Not agentic.** No LLM calls. No prompts. No reasoning layer. No judgment SLOs on its own outputs.
- **Not a verdict emitter.** Assessments are not verdicts. They don't have confidence scores, reasoning fields, or lineage chains. They're structured data.
- **Not nthlayer-generate.** Generate is a compiler that runs at build time. Observe runs continuously or on-demand at runtime.
- **Not a replacement for the agentic components.** Observe gathers evidence. Agents reason about it.

---

## What nthlayer-generate Is NOT (Post-Migration)

After the migration, generate should have NO:
- Prometheus queries (live state)
- Database connections (runtime state)
- Long-running servers (FastAPI)
- Notification dispatch (Slack, PagerDuty)
- Deployment event handling (webhooks)
- Live dependency discovery (Kubernetes, Consul)
- Policy audit trails (runtime logging)

Generate should ONLY:
- Parse manifests
- Validate schemas
- Resolve templates
- Generate artifacts (Prometheus rules, Grafana dashboards, AlertManager config, PagerDuty config, Backstage entities, documentation, OpenSLO specs, recording rules)
- Run simulations (Monte Carlo, deterministic given seed)
- Enforce build-time policies (same input, same violations)

**Generate does NOT emit verdicts or assessments.** A validation error is an error, not a verdict. A generated artifact is an artifact, not an assessment. Generate's outputs are files, not runtime data structures.

---

## Migration Plan

### Phase 0: Create nthlayer-observe Package Structure

```
nthlayer-observe/
├── pyproject.toml
├── src/
│   └── nthlayer_observe/
│       ├── __init__.py
│       ├── cli.py                    # CLI entry point
│       ├── config.py                 # ObserveConfig
│       ├── assessment.py             # Assessment dataclass + store
│       │
│       ├── slo/                      # SLO state collection
│       │   ├── collector.py          # ← from slos/collector.py
│       │   ├── storage.py            # ← from slos/storage.py
│       │   └── models.py             # ← SLO runtime models from slos/models.py
│       │
│       ├── drift/                    # Drift detection
│       │   ├── analyzer.py           # ← from drift/analyzer.py
│       │   ├── models.py             # ← from drift/models.py
│       │   └── patterns.py           # ← from drift/patterns.py
│       │
│       ├── verification/             # Metric verification
│       │   ├── verifier.py           # ← from verification/verifier.py
│       │   ├── models.py             # ← from verification/models.py
│       │   └── extractor.py          # ← from verification/extractor.py
│       │
│       ├── discovery/                # Metric + dependency discovery
│       │   ├── metrics.py            # ← from discovery/client.py + classifier.py
│       │   └── dependencies.py       # ← from dependencies/discovery.py
│       │
│       ├── dependencies/             # Dependency providers
│       │   ├── kubernetes.py         # ← from dependencies/providers/kubernetes.py
│       │   ├── prometheus.py         # ← from dependencies/providers/prometheus.py
│       │   ├── consul.py             # ← from dependencies/providers/consul.py
│       │   └── backstage.py          # ← from dependencies/providers/backstage.py
│       │
│       ├── gate/                     # Deployment gates
│       │   ├── evaluator.py          # ← from slos/gates.py
│       │   ├── policies.py           # ← from policies/evaluator.py + conditions.py
│       │   ├── audit.py              # ← from policies/audit.py + recorder.py
│       │   └── correlator.py         # ← from slos/correlator.py
│       │
│       ├── portfolio/                # Portfolio health
│       │   ├── aggregator.py         # ← live portions of portfolio/aggregator.py
│       │   └── scorecard.py          # ← live portions of scorecard/calculator.py
│       │
│       ├── api/                      # Runtime HTTP API
│       │   ├── main.py              # ← from api/main.py (FastAPI server)
│       │   ├── routes/              # ← from api/routes/
│       │   └── auth.py              # ← from api/auth.py
│       │
│       ├── deployments/              # Deployment event handling
│       │   ├── registry.py           # ← from deployments/registry.py
│       │   └── providers/            # ← from deployments/providers/
│       │
│       └── db/                       # Runtime database
│           ├── models.py             # ← from db/models.py
│           ├── session.py            # ← from db/session.py
│           └── repositories.py       # ← from db/repositories.py
```

### Phase 0.5: Extract Shared Utilities to nthlayer-common

Before moving anything, extract shared code that multiple components need:

| Module | Source | Used By |
|---|---|---|
| `tiers.py` | `core/tiers.py` | generate, observe, measure |
| `errors.py` | `core/errors.py` | all components |
| `slo_models.py` | `slos/models.py` (data structures only) | observe, measure, generate |
| `dependency_models.py` | `dependencies/models.py` | observe, correlate, generate |
| `identity/` | `identity/normalizer.py`, `resolver.py`, `models.py` | observe, correlate, generate |
| `prometheus.py` | `providers/prometheus.py` + `clients/prometheus.py` | observe, measure (fallback), correlate (fallback) |
| `http_client.py` | `clients/base.py` | all components |

### Phase 1: Quick Wins (from audit, no changes)

These move to their already-identified destinations:
- `slos/notifiers.py` → nthlayer-respond (notification dispatch)
- `slos/explanations.py` → nthlayer-respond (alert context for humans)
- Remove deprecated methods, `demo.py`, `workflows/team_reconcile.py`

### Phase 2: Create nthlayer-observe with SLO Collection

The first real capability in observe:
- Move `slos/collector.py` → `observe/slo/collector.py`
- Move `slos/storage.py` → `observe/slo/storage.py`
- Create `Assessment` dataclass
- Create CLI: `nthlayer-observe collect --specs-dir ./specs/ --prometheus-url http://localhost:9090`
- Wire into nthlayer-measure: measure reads assessments from observe instead of querying Prometheus directly

### Phase 3: Move Drift, Verification, Discovery to Observe

- `drift/` → `observe/drift/`
- `verification/` → `observe/verification/`
- `discovery/` → `observe/discovery/`
- `dependencies/discovery.py` + `dependencies/providers/` → `observe/dependencies/`
- Create CLI commands: `nthlayer-observe verify`, `nthlayer-observe discover`, `nthlayer-observe drift`

### Phase 4: Move Gate to Observe

The largest move:
- `slos/gates.py` → `observe/gate/evaluator.py`
- `cli/deploy.py` → `observe/cli.py` (as `nthlayer-observe check-deploy`)
- `policies/evaluator.py`, `policies/conditions.py` → `observe/gate/policies.py`
- `policies/audit.py`, `policies/recorder.py` → `observe/gate/audit.py`
- `slos/correlator.py` → `observe/gate/correlator.py` (deterministic deployment correlation)
- `api/` → `observe/api/`
- `deployments/` → `observe/deployments/`
- `db/` → `observe/db/`

### Phase 5: Cleanup Generate

- Remove all moved files from generate
- Update import paths
- Remove runtime dependencies from generate's pyproject.toml (FastAPI, SQLAlchemy, etc.)
- Run full test suite
- Verify generate is now stateless: no Prometheus queries, no database, no long-running server

---

## Critical Rules for Claude Code

### 1. Never Add Infrastructure Code to Agentic Components

If the code doesn't call an LLM or make a judgment, it does NOT go in measure, correlate, respond, or learn. If you're about to add a Prometheus query to measure, stop — it goes in observe. Measure reads the result.

### 2. Assessments Are Not Verdicts

Do not give assessments confidence scores, reasoning fields, or lineage chains. An assessment is a fact: "error budget is at 14%." A verdict is a judgment: "this service is degrading with 0.85 confidence." If you're tempted to add `confidence` to an assessment, you're building a verdict and it belongs in an agentic component.

### 3. Generate Stays Pure

Do not add runtime capabilities to generate. If it needs live data, it's not a generate concern. Generate's only inputs are manifest files and templates. Generate's only outputs are artifact files. No network calls to production systems.

### 4. Observe Has No LLM Dependency

nthlayer-observe must not import `nthlayer_common.llm` or any LLM library. If you find yourself wanting to add an LLM call to observe, you're building an agentic capability that belongs in measure, correlate, or respond.

### 5. Backward Compatibility During Migration

Each phase should leave the system working. When moving `slos/collector.py` to observe, the existing generate CLI commands that use it should still work — either by importing from the new location or by leaving a thin re-export in the old location until all consumers are migrated. The test suite must pass after every phase.

### 6. Assessment Storage

Assessments are stored in the same SQLite verdict store (it becomes the "evidence store" conceptually) or in a separate lightweight store. The key requirement: agentic components can query recent assessments for a service without re-running the observation. This enables the pattern where observe runs on a schedule (or on trigger) and measure/correlate consume the latest assessments.

### 7. One Prometheus Client, Many Consumers

The Prometheus HTTP client lives in nthlayer-common. Observe is the primary consumer. Measure and correlate may also query Prometheus directly for now (they already do), but new Prometheus query code should go in observe. Over time, the agentic components should consume assessments rather than querying Prometheus directly.

---

## Component Summary (Post-Migration)

| Component | Role | Runtime? | LLM? | Emits |
|---|---|---|---|---|
| **generate** | Compile specs → artifacts | No (build-time) | No | Artifact files |
| **observe** | Read live state → assessments | Yes | No | Assessments |
| **measure** | Evaluate AI decision quality | Yes | Yes | Evaluation verdicts |
| **correlate** | Reason about causality | Yes | Yes | Correlation verdicts |
| **respond** | Incident response pipeline | Yes | Yes | Incident verdicts |
| **learn** | Retrospective analysis | Yes | Yes | Retrospective verdicts |
