# NTHLAYER-SIMULATE.md — Monte Carlo SLO Simulation Specification

This document specifies `nthlayer simulate`, a probabilistic reliability simulator that answers: "Given our declared SLOs and dependency chain, what's the probability we meet our customer-facing SLA over the next quarter?"

This is a deterministic tool (Monte Carlo is arithmetic: sample from distributions, multiply probabilities, aggregate). No model calls. No agents. No judgment. Pure transport. It fits NthLayer's existing category: manifest in, analysis out.


## Core Principle

**Turn declared intent into quantified prediction.**

The SRE industry measures reliability after the fact (dashboards, error budgets, incident counts). This tool predicts it before, from the same manifests teams already version-control. It transforms OpenSRM from a documentation standard into a reliability planning language.


## What It Does

The simulator reads one or more OpenSRM manifests, builds the dependency graph, models each service's failure characteristics as probability distributions, and runs thousands of simulated time periods. The output is a probability distribution over the target SLA: what's the chance you meet it, when does the error budget likely exhaust, what's the weakest link, and what happens if you change something.

```bash
nthlayer simulate \
  --manifest service.reliability.yaml \
  --manifests-dir ./manifests/ \
  --runs 10000 \
  --horizon 90d
```


## Input: What the Simulator Reads

### From OpenSRM Manifests

The simulator reads fields that already exist (or should exist) in the manifest schema:

```yaml
apiVersion: opensrm/v1
kind: ServiceReliabilityManifest
metadata:
  name: checkout-service
  tier: critical
spec:
  slos:
    availability:
      target: 0.999           # 99.9%
      window: 30d
    latency:
      p99:
        target: 200            # ms
        window: 30d

  dependencies:
    - service: payment-api
      critical: true           # failure of this dependency fails checkout-service
      expects:
        availability: 0.999
        latency_p99: 150       # ms
    - service: inventory-service
      critical: false          # degraded experience, not full failure
      expects:
        availability: 0.995
    - service: cache-redis
      critical: false
      expects:
        availability: 0.999

  # NEW (optional): historical failure characteristics
  # If absent, the simulator derives distributions from the SLO targets
  failure_model:
    mtbf_hours: 720            # mean time between failures (optional)
    mttr_hours: 0.5            # mean time to recovery (optional)
    incident_rate_per_month: 2 # average incidents per month (optional)
```

**What the simulator needs from each service:**

| Field | Source | Fallback If Absent |
|-------|--------|-------------------|
| Availability target | `spec.slos.availability.target` | Required, no fallback |
| Dependency graph | `spec.dependencies` | Service modelled as standalone |
| Dependency criticality | `spec.dependencies[].critical` | Default: true (conservative) |
| Expected dependency availability | `spec.dependencies[].expects.availability` | Use the dependency's own SLO target |
| MTBF | `spec.failure_model.mtbf_hours` | Derived from availability target |
| MTTR | `spec.failure_model.mttr_hours` | Default: 1 hour |
| Incident rate | `spec.failure_model.incident_rate_per_month` | Derived from MTBF |

### From Prometheus (Optional, Improves Accuracy)

When a Prometheus endpoint is configured, the simulator can pull actual historical data instead of using declared targets:

```bash
nthlayer simulate \
  --manifest service.reliability.yaml \
  --manifests-dir ./manifests/ \
  --prometheus http://prometheus:9090 \
  --historical-window 90d \
  --runs 10000 \
  --horizon 90d
```

Historical data replaces the configured distributions:

| Metric | What It Provides |
|--------|-----------------|
| `up` or availability recording rule | Actual availability over the historical window |
| Error rate metrics | Actual failure frequency and duration |
| Latency histograms | Actual latency distributions (not just targets) |
| `gen_ai_override_reversal_total` / `gen_ai_decision_total` | Actual judgment SLO performance (for `type: ai-gate` services) |

The gap between declared targets and historical actuals is itself a valuable output: "your manifest says 99.9% but your measured availability over the last 90 days is 99.2%." That's a manifest accuracy signal.

### From Verdict Store (Optional, Future)

When connected to a verdict store, the simulator can incorporate judgment quality data for `type: ai-gate` services:

- Actual reversal rates (from resolved verdicts) replace declared judgment SLO targets
- Actual confidence distributions (from verdict confidence scores) model judgment reliability
- Score-outcome divergence (from gaming checks) models hidden quality risk

This is a Tier 2+ integration, not required for Tier 1. The simulator works with manifest data alone.


## Simulation Model

### Failure Modelling

Each service is modelled as a stochastic process with failures and recoveries. The simulator doesn't model the internal mechanics of each service. It models the observable behaviour: how often does it fail, and how long does it take to recover.

**Per-service failure model:**

```python
@dataclass
class ServiceFailureModel:
    name: str
    availability_target: float          # e.g., 0.999
    mtbf_hours: float                   # mean time between failures
    mttr_hours: float                   # mean time to recovery
    mtbf_distribution: str              # "exponential" (default) or "weibull"
    mttr_distribution: str              # "lognormal" (default) or "exponential"
    mtbf_shape: float                   # shape parameter for weibull (default 1.0 = exponential)
    mttr_shape: float                   # shape parameter for lognormal (default 0.5)
```

**Why these distributions:**

- **MTBF as exponential (default):** Failures are memoryless, which is a reasonable first approximation for most services. The exponential distribution models "failures happen at a constant rate." This is the standard assumption in availability modelling.

- **MTBF as Weibull (optional):** For services that degrade over time (memory leaks, connection pool exhaustion, log rotation failures), the Weibull distribution models increasing failure rate. The shape parameter controls how much the failure rate increases over time. Shape = 1.0 is exponential (constant rate). Shape > 1.0 is increasing rate (infant mortality or wear-out).

- **MTTR as lognormal (default):** Recovery times are typically right-skewed: most recoveries are fast (auto-restart, failover), but some are slow (manual intervention, data corruption). The lognormal distribution captures this skew. The shape parameter controls how heavy the right tail is.

**Deriving MTBF and MTTR from availability target when not explicitly declared:**

```python
def derive_failure_model(availability_target: float, mttr_hours: float = 1.0) -> ServiceFailureModel:
    """
    Availability = MTBF / (MTBF + MTTR)
    Therefore: MTBF = MTTR * availability / (1 - availability)

    For a service targeting 99.9% availability with 1-hour MTTR:
    MTBF = 1.0 * 0.999 / 0.001 = 999 hours ≈ 41.6 days between failures
    """
    mtbf = mttr_hours * availability_target / (1 - availability_target)
    return ServiceFailureModel(
        availability_target=availability_target,
        mtbf_hours=mtbf,
        mttr_hours=mttr_hours,
        mtbf_distribution="exponential",
        mttr_distribution="lognormal",
        mtbf_shape=1.0,
        mttr_shape=0.5
    )
```

### Dependency Modelling

The dependency graph determines how individual service failures cascade.

**Critical dependency:** If a critical dependency is down, the dependent service is down. This models hard dependencies (can't process payments if the payment API is unreachable).

**Non-critical dependency:** If a non-critical dependency is down, the dependent service is degraded but not down. The simulator models this as a reduced availability target during the dependency's downtime (configurable, default: dependent service's availability drops to 99% during non-critical dependency failure).

```python
@dataclass
class DependencyModel:
    from_service: str
    to_service: str
    critical: bool
    degradation_factor: float          # for non-critical: how much availability drops during dependency failure
                                       # default 0.99 (1% of requests fail during degradation)
```

**Availability calculation for a single simulation run:**

```python
def simulate_service_availability(
    service: ServiceFailureModel,
    dependencies: list[DependencyModel],
    dep_timelines: dict[str, list[FailureEvent]],
    horizon_hours: float
) -> float:
    """
    Simulate one run of a service's availability over the horizon.

    1. Generate the service's own failure timeline (when it fails, how long each failure lasts)
    2. Overlay critical dependency failures (service is down whenever a critical dep is down)
    3. Overlay non-critical dependency degradation
    4. Compute total uptime / horizon
    """
    # Service's own failures
    own_failures = generate_failure_timeline(service, horizon_hours)
    own_downtime = sum(f.duration for f in own_failures)

    # Critical dependency failures (additive downtime, but don't double-count overlaps)
    critical_downtime = 0
    for dep in dependencies:
        if dep.critical and dep.to_service in dep_timelines:
            dep_failures = dep_timelines[dep.to_service]
            critical_downtime += compute_non_overlapping_downtime(
                dep_failures, own_failures, horizon_hours
            )

    # Non-critical dependency degradation
    noncritical_downtime = 0
    for dep in dependencies:
        if not dep.critical and dep.to_service in dep_timelines:
            dep_failures = dep_timelines[dep.to_service]
            # During each dependency failure window, a fraction of requests fail
            for f in dep_failures:
                noncritical_downtime += f.duration * (1 - dep.degradation_factor)

    total_downtime = min(own_downtime + critical_downtime + noncritical_downtime, horizon_hours)
    availability = 1 - (total_downtime / horizon_hours)
    return availability
```

**Topological ordering:** Services are simulated in dependency order (leaf services first, then their dependents). This ensures that when simulating checkout-service, payment-api's failure timeline has already been generated for this run.

```python
def simulate_run(services: list[ServiceFailureModel], dependencies: list[DependencyModel], horizon_hours: float) -> dict[str, float]:
    """
    One complete simulation run across all services.
    Returns availability per service for this run.
    """
    # Topological sort: simulate dependencies before dependents
    order = topological_sort(services, dependencies)

    timelines = {}   # service_name -> [FailureEvent]
    results = {}     # service_name -> availability

    for service in order:
        # Generate this service's failure timeline
        timelines[service.name] = generate_failure_timeline(service, horizon_hours)

        # Compute availability including dependency effects
        service_deps = [d for d in dependencies if d.from_service == service.name]
        results[service.name] = simulate_service_availability(
            service, service_deps, timelines, horizon_hours
        )

    return results
```

### Failure Timeline Generation

```python
@dataclass
class FailureEvent:
    start_hour: float
    duration: float            # hours

def generate_failure_timeline(service: ServiceFailureModel, horizon_hours: float) -> list[FailureEvent]:
    """
    Generate a sequence of failure events for a service over the horizon.
    """
    events = []
    current_hour = 0

    while current_hour < horizon_hours:
        # Time until next failure
        if service.mtbf_distribution == "exponential":
            time_to_failure = random.expovariate(1.0 / service.mtbf_hours)
        elif service.mtbf_distribution == "weibull":
            time_to_failure = random.weibullvariate(service.mtbf_hours, service.mtbf_shape)

        current_hour += time_to_failure
        if current_hour >= horizon_hours:
            break

        # Duration of failure
        if service.mttr_distribution == "lognormal":
            duration = random.lognormvariate(
                math.log(service.mttr_hours), service.mttr_shape
            )
        elif service.mttr_distribution == "exponential":
            duration = random.expovariate(1.0 / service.mttr_hours)

        # Cap duration at remaining horizon
        duration = min(duration, horizon_hours - current_hour)

        events.append(FailureEvent(start_hour=current_hour, duration=duration))
        current_hour += duration

    return events
```

### Judgment SLO Simulation (for type: ai-gate)

For services declared as `type: ai-gate`, the simulator also models judgment quality:

```yaml
spec:
  type: ai-gate
  slos:
    judgment:
      reversal_rate:
        target: 0.05
        window: 30d
```

The simulator models judgment quality as a Bernoulli process: each decision has a probability of being reversed. The reversal probability is derived from the target (or from actual verdict data if available).

```python
def simulate_judgment_slo(
    reversal_rate_target: float,
    decisions_per_day: float,           # estimated from historical verdict rate or configured
    horizon_days: int,
    window_days: int                    # SLO window (e.g., 30d)
) -> dict:
    """
    Simulate judgment SLO compliance over the horizon.

    For each day, sample the number of reversals from a binomial distribution.
    Compute the rolling reversal rate over the SLO window.
    Track whether the error budget is exhausted at any point.
    """
    daily_decisions = int(decisions_per_day)
    daily_reversals = []

    for day in range(horizon_days):
        # Each decision has reversal_rate_target probability of being reversed
        # (or use actual rate from Prometheus/verdicts if available)
        reversals = sum(
            1 for _ in range(daily_decisions)
            if random.random() < reversal_rate_target
        )
        daily_reversals.append(reversals)

    # Compute rolling window compliance
    budget_exhausted_day = None
    for day in range(window_days, horizon_days):
        window_reversals = sum(daily_reversals[day - window_days:day])
        window_decisions = daily_decisions * window_days
        rolling_rate = window_reversals / window_decisions if window_decisions > 0 else 0

        if rolling_rate > reversal_rate_target:
            budget_exhausted_day = day
            break

    return {
        "budget_exhausted": budget_exhausted_day is not None,
        "budget_exhausted_day": budget_exhausted_day,
        "final_reversal_rate": sum(daily_reversals[-window_days:]) / (daily_decisions * window_days)
    }
```


## Monte Carlo Execution

The simulator runs N independent simulations (default 10,000) and aggregates the results into probability distributions.

```python
def run_simulation(
    manifests: list[Manifest],
    num_runs: int = 10000,
    horizon_days: int = 90,
    seed: int | None = None
) -> SimulationResult:
    """
    Run the full Monte Carlo simulation.
    """
    if seed is not None:
        random.seed(seed)                # reproducible for testing

    horizon_hours = horizon_days * 24

    # Build models from manifests
    services = [build_failure_model(m) for m in manifests]
    dependencies = build_dependency_graph(manifests)

    # Run simulations
    results_per_run = []
    for run in range(num_runs):
        run_result = simulate_run(services, dependencies, horizon_hours)
        results_per_run.append(run_result)

    # Aggregate
    return aggregate_results(manifests, results_per_run, horizon_days)
```

### Aggregation

```python
@dataclass
class ServiceSimulationResult:
    name: str
    target: float                       # declared SLO target
    p_meeting_sla: float                # probability of meeting SLA over horizon
    availability_distribution: list[float]  # all simulated availabilities (for percentiles)
    availability_p50: float
    availability_p95: float
    availability_p99: float
    downtime_contribution: float        # fraction of total system downtime caused by this service
    error_budget_exhaustion_day: PercentileResult  # when error budget runs out (median, p50, p95)
    is_weakest_link: bool

@dataclass
class PercentileResult:
    p50: float | None
    p75: float | None
    p95: float | None

@dataclass
class SimulationResult:
    target_service: str
    target_sla: float
    horizon_days: int
    num_runs: int
    p_meeting_sla: float                # headline number
    services: dict[str, ServiceSimulationResult]
    weakest_link: str                   # service contributing most downtime
    weakest_link_contribution: float    # percentage of total downtime
    error_budget_forecast: PercentileResult  # when does the target service's budget exhaust
    manifest_vs_actual: dict[str, float] | None  # gap between declared and measured (if Prometheus data)

def aggregate_results(manifests, results_per_run, horizon_days) -> SimulationResult:
    """
    Aggregate N simulation runs into probability distributions.
    """
    target_manifest = manifests[0]      # first manifest is the target service
    target_name = target_manifest.metadata.name
    target_sla = target_manifest.spec.slos.availability.target

    # Per-service availability distributions
    service_availabilities = defaultdict(list)
    for run in results_per_run:
        for service_name, availability in run.items():
            service_availabilities[service_name].append(availability)

    # P(meeting SLA) = fraction of runs where target service availability >= target
    target_avails = service_availabilities[target_name]
    p_meeting = sum(1 for a in target_avails if a >= target_sla) / len(target_avails)

    # Weakest link: which dependency contributes most downtime across all runs
    downtime_contributions = compute_downtime_contributions(results_per_run, target_name, manifests)

    # Error budget exhaustion forecast
    budget_exhaustion_days = compute_budget_exhaustion_days(target_avails, target_sla, horizon_days)

    # Build per-service results
    service_results = {}
    for name, avails in service_availabilities.items():
        manifest = find_manifest(manifests, name)
        target = manifest.spec.slos.availability.target if manifest else None
        sorted_avails = sorted(avails)
        n = len(sorted_avails)

        service_results[name] = ServiceSimulationResult(
            name=name,
            target=target,
            p_meeting_sla=sum(1 for a in avails if a >= target) / n if target else None,
            availability_distribution=sorted_avails,
            availability_p50=sorted_avails[n // 2],
            availability_p95=sorted_avails[int(n * 0.95)],
            availability_p99=sorted_avails[int(n * 0.99)],
            downtime_contribution=downtime_contributions.get(name, 0),
            error_budget_exhaustion_day=None,     # computed per-service if needed
            is_weakest_link=(name == max(downtime_contributions, key=downtime_contributions.get))
        )

    weakest = max(downtime_contributions, key=downtime_contributions.get)

    return SimulationResult(
        target_service=target_name,
        target_sla=target_sla,
        horizon_days=horizon_days,
        num_runs=len(results_per_run),
        p_meeting_sla=p_meeting,
        services=service_results,
        weakest_link=weakest,
        weakest_link_contribution=downtime_contributions[weakest],
        error_budget_forecast=budget_exhaustion_days,
        manifest_vs_actual=None            # populated if Prometheus data available
    )
```


## What-If Scenarios

The most powerful feature. The simulator runs the base case, then re-runs with modifications to answer "what if" questions.

### Built-In What-If Scenarios

```bash
nthlayer simulate \
  --manifest service.reliability.yaml \
  --manifests-dir ./manifests/ \
  --what-if redundant:payment-api \
  --what-if improve:database-primary:availability:0.9999 \
  --what-if remove:cache-redis \
  --what-if add-dep:checkout-service:new-fraud-service:critical:0.995
```

| Scenario Type | Syntax | What It Does |
|--------------|--------|-------------|
| `redundant:{service}` | Add a redundant instance of a dependency | Models active-active: both must fail for the dependency to be down. Squares the failure probability. |
| `improve:{service}:{metric}:{value}` | Improve a service's target | Reruns with the service's SLO target (or MTBF/MTTR) adjusted to the new value. |
| `remove:{service}` | Remove a dependency | Reruns without this dependency in the graph. Shows the impact of decoupling. |
| `add-dep:{from}:{to}:{critical}:{availability}` | Add a new dependency | Reruns with a new dependency added. Shows the cost of adding a dependency. |
| `circuit-breaker:{service}:{timeout_ms}` | Add a circuit breaker to a dependency | Models the dependency as non-critical with a fast failure threshold (instead of waiting for timeout). Reduces cascading failure duration. |
| `degrade:{service}:{factor}` | Change a critical dependency to non-critical | Models graceful degradation: the dependency failure causes partial degradation instead of full outage. |

### What-If Implementation

```python
def run_what_if(
    base_manifests: list[Manifest],
    scenario: WhatIfScenario,
    num_runs: int,
    horizon_days: int
) -> WhatIfResult:
    """
    Run a modified simulation and compare against the base case.
    """
    # Deep copy manifests and apply modification
    modified_manifests = deep_copy(base_manifests)
    apply_scenario(modified_manifests, scenario)

    # Run simulation with modified manifests
    modified_result = run_simulation(modified_manifests, num_runs, horizon_days)

    return WhatIfResult(
        scenario=scenario,
        base_p_meeting_sla=base_result.p_meeting_sla,
        modified_p_meeting_sla=modified_result.p_meeting_sla,
        delta=modified_result.p_meeting_sla - base_result.p_meeting_sla,
        base_weakest_link=base_result.weakest_link,
        modified_weakest_link=modified_result.weakest_link
    )
```

### What-If Output

```
What-if scenarios:
  +redundant payment-api:       P(SLA) 73.2% → 94.6%  (+21.4%)
  +improve database to 99.99%:  P(SLA) 73.2% → 82.1%  (+8.9%)
  -remove cache dependency:     P(SLA) 73.2% → 75.8%  (+2.6%)
  +circuit breaker on db:       P(SLA) 73.2% → 79.4%  (+6.2%)
  +add fraud-service dep:       P(SLA) 73.2% → 68.1%  (-5.1%)  ← WARNING: reduces reliability
```

What-if scenarios that reduce reliability are flagged with a warning. This is how teams discover the cost of adding a new dependency before they add it.


## Output Formats

### Terminal (Default)

The formatted table shown in Claude Code's original proposal. Human-readable, coloured, box-drawn.

### JSON (Machine-Readable)

```bash
nthlayer simulate --manifest service.yaml --format json
```

```json
{
  "target_service": "checkout-service",
  "target_sla": 0.999,
  "horizon_days": 90,
  "num_runs": 10000,
  "p_meeting_sla": 0.732,
  "weakest_link": {
    "service": "payment-api",
    "downtime_contribution": 0.68
  },
  "error_budget_forecast": {
    "median_exhaustion_day": 71,
    "p75_exhaustion_day": 58,
    "p95_exhaustion_day": 34,
    "p_exhausted_before_horizon": 0.421
  },
  "services": {
    "checkout-service": {
      "target": 0.999,
      "p_meeting_sla": 0.732,
      "availability_p50": 0.9987,
      "availability_p95": 0.9951,
      "availability_p99": 0.9923
    },
    "payment-api": { ... },
    "database-primary": { ... }
  },
  "what_if": [
    {
      "scenario": "redundant:payment-api",
      "p_meeting_sla": 0.946,
      "delta": 0.214
    }
  ],
  "manifest_vs_actual": null
}
```

### Grafana Dashboard (via NthLayer)

The simulation results can be stored and rendered as a Grafana dashboard:

```bash
nthlayer simulate --manifest service.yaml --grafana-output simulation-dashboard.json
```

This generates a Grafana dashboard with:
- SLA probability gauge (big number: "73.2% chance of meeting 99.9% SLA")
- Error budget exhaustion forecast (line chart: probability of exhaustion over time)
- Dependency contribution (pie chart: which dependencies cause the most downtime)
- What-if comparison (bar chart: base case vs each scenario)
- Historical trend (if simulation is run periodically, track P(SLA) over time)

### Markdown Report

```bash
nthlayer simulate --manifest service.yaml --format markdown --output report.md
```

Generates a markdown report suitable for architecture review documents, production readiness reviews, or post-incident analysis.


## Historical Calibration (Prometheus Integration)

When Prometheus is available, the simulator calibrates its models against actual historical data.

### What It Pulls

```python
def calibrate_from_prometheus(
    service: str,
    prometheus_url: str,
    window_days: int = 90
) -> CalibratedFailureModel:
    """
    Query Prometheus for actual failure characteristics.
    Returns a failure model calibrated to reality, not declared targets.
    """
    # Actual availability (from up metric or recording rule)
    actual_availability = prom_query(
        f'avg_over_time(up{{service="{service}"}}[{window_days}d])'
    )

    # Actual incident count (from alertmanager or recording rule)
    incident_count = prom_query(
        f'count_over_time(ALERTS{{service="{service}", alertstate="firing"}}[{window_days}d])'
    )

    # Actual MTTR (from alert duration)
    avg_alert_duration = prom_query(
        f'avg(alert_duration_seconds{{service="{service}"}}) / 3600'
    )

    # For ai-gate services: actual reversal rate from verdict metrics
    actual_reversal_rate = prom_query(
        f'rate(gen_ai_override_reversal_total{{service="{service}"}}[{window_days}d])'
        f' / rate(gen_ai_decision_total{{service="{service}"}}[{window_days}d])'
    )

    return CalibratedFailureModel(
        actual_availability=actual_availability,
        declared_availability=manifest_target,
        gap=manifest_target - actual_availability,  # positive = overestimating reliability
        calibrated_mtbf=compute_mtbf(actual_availability, avg_alert_duration),
        calibrated_mttr=avg_alert_duration,
        actual_reversal_rate=actual_reversal_rate
    )
```

### Manifest vs Actual Output

```
Manifest accuracy:
  checkout-service:  declared 99.9%,  actual 99.7%  (gap: -0.2%)
  payment-api:       declared 99.9%,  actual 99.2%  (gap: -0.7%)  ← SIGNIFICANT
  database-primary:  declared 99.99%, actual 99.95% (gap: -0.04%)
  cache-redis:       declared 99.9%,  actual 99.98% (gap: +0.08%)

Simulation using actual data:
  P(meeting SLA): 73.2% (from declared) → 54.1% (from actual)
  Your manifests are overestimating reliability by 19.1 percentage points.
```

This is the "your manifest is lying to you" signal. When the gap between declared and actual is significant, the simulator flags it. Teams can then either fix the underlying reliability problem or update the manifest to reflect reality.


## CI/CD Integration

### Production Readiness Gate

```bash
# In CI/CD pipeline
nthlayer simulate \
  --manifest service.yaml \
  --manifests-dir ./manifests/ \
  --min-p-sla 0.80 \
  --format json \
  --exit-code

# Exit code 0 if P(meeting SLA) >= 80%
# Exit code 1 if P(meeting SLA) < 80%
```

This gates service launches (not deploys of existing services, but launches of new services or major architecture changes) on a minimum SLA probability. "You can't launch if the simulator says you have less than 80% chance of meeting your SLA."

### Architecture Review Automation

```bash
# Before adding a new dependency
nthlayer simulate \
  --manifest service.yaml \
  --manifests-dir ./manifests/ \
  --what-if add-dep:checkout-service:new-fraud-service:critical:0.995 \
  --format json

# Parse the delta: if P(SLA) drops by more than 5%, flag for architecture review
```

This automates the question "should we add this dependency?" with quantified impact.


## Configuration

```yaml
# In nthlayer.yaml or as CLI flags
simulate:
  default_runs: 10000
  default_horizon_days: 90
  default_mttr_hours: 1.0            # when not declared in manifest
  default_mtbf_distribution: exponential
  default_mttr_distribution: lognormal
  default_degradation_factor: 0.99   # for non-critical dependencies
  seed: null                          # set for reproducible results
  prometheus:
    url: null                         # set to enable historical calibration
    historical_window_days: 90
  what_if_scenarios: []               # default what-if scenarios to always run
  ci:
    min_p_sla: 0.80                  # minimum P(SLA) for CI gate
    exit_code_on_fail: true
```


## Implementation Priority

1. **Failure model construction from manifests.** Parse manifests, build ServiceFailureModel for each service, derive MTBF/MTTR from availability targets. This is the foundation.

2. **Failure timeline generation.** Implement `generate_failure_timeline()` with exponential and lognormal distributions. Test that generated timelines produce availabilities close to the target over many runs.

3. **Dependency graph and topological sort.** Build the dependency graph from manifests, implement topological ordering. Test with cycles detection (cycles should error, not infinite loop).

4. **Single simulation run.** Implement `simulate_run()` with dependency cascading (critical and non-critical). Test with known dependency graphs where the analytical answer is computable.

5. **Monte Carlo aggregation.** Implement `run_simulation()` and `aggregate_results()`. Run 10,000 simulations, produce P(meeting SLA), percentiles, weakest link, error budget forecast.

6. **Terminal output.** The formatted box-drawn table. This is what makes the demo compelling.

7. **What-if scenarios.** Implement the scenario modification layer. Start with `redundant`, `improve`, and `remove`. Add `add-dep`, `circuit-breaker`, and `degrade` after.

8. **JSON and Markdown output.** Machine-readable and document-ready formats.

9. **Prometheus calibration.** Historical data ingestion, manifest-vs-actual comparison, calibrated simulation.

10. **Judgment SLO simulation.** For `type: ai-gate` services, model reversal rates as Bernoulli processes. Connect to verdict store for actual rates.

11. **Grafana dashboard output.** Generate a simulation results dashboard via NthLayer's existing dashboard generation.

12. **CI/CD gate.** `--min-p-sla` flag with exit code for pipeline integration.

Items 1-6 give you a working simulator that produces the headline output from manifests alone. Items 7-8 add the what-if scenarios and output formats. Items 9-12 connect to the broader ecosystem.


## Validation

### Analytical Verification

For simple dependency graphs, the analytical answer is known:

**Two independent services in series (both critical):**
- Service A: 99.9% availability
- Service B: 99.5% availability
- Composite: 99.9% × 99.5% = 99.4%
- The simulator should converge to ~99.4% over 10,000 runs

**Redundant service (active-active):**
- Service A: 99.9% availability, two instances
- Composite: 1 - (1 - 0.999)² = 99.9999%
- The simulator should converge to ~99.9999%

**Single service with known MTBF/MTTR:**
- MTBF: 1000 hours, MTTR: 1 hour
- Expected availability: 1000 / 1001 = 99.9%
- The simulator should converge to ~99.9%

These analytical cases are the test suite for the simulation model. If the simulator doesn't converge to the analytical answer within statistical tolerance (±0.5% at 10,000 runs), the model has a bug.

### Statistical Tolerance

With 10,000 runs, the standard error on a probability estimate is approximately `sqrt(p * (1-p) / N)`. For p = 0.73, that's `sqrt(0.73 * 0.27 / 10000) ≈ 0.004`, meaning the 95% confidence interval is ±0.8 percentage points. This is sufficient precision for planning purposes.

For higher precision, increase `--runs`. At 100,000 runs, the confidence interval narrows to ±0.25 percentage points. The trade-off is computation time (linear in number of runs, but each run is fast: a 90-day simulation of 20 services is microseconds).


## Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| **BRIEF.md** | NthLayer gains `nthlayer simulate` as a new command. Add to commands reference and README structure. |
| **VERDICT.md** | Verdict store provides actual reversal rates for judgment SLO simulation calibration. |
| **SITREP-PRECORRELATION.md** | SitRep's pre-correlation could feed incident data into simulation calibration (actual incident frequency and duration). |
| **COSTOPTIMISATION.md** | Simulation is pure compute (no model calls). Zero token cost. Can run in CI without API spend. |
| **ECOSYSTEM-GAPS.md** | Simulation results feed into the confidence dashboard (predicted vs actual SLA over time). |
| **SRE-EXPERIENCE.md** | Simulation output appears in architecture review documents and production readiness gates. The shift report could include "P(SLA) this quarter: 73%, weakest link: payment-api." |
| **ARBITER-INTEGRATIONS.md** | For ai-gate services, the Arbiter's verdict metrics provide actual reversal rates that calibrate the judgment SLO simulation. |
