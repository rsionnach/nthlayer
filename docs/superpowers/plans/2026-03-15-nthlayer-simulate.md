# NthLayer Simulate — Monte Carlo SLO Simulation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `nthlayer simulate` — a Monte Carlo reliability simulator that predicts the probability of meeting SLAs from OpenSRM manifests and dependency graphs.

**Architecture:** New `simulate/` package under `src/nthlayer/` with models, engine, graph, what-if, and output modules. CLI command registered in `demo.py` following the `drift` command pattern. Pure transport (no model calls) — arithmetic sampling from probability distributions using numpy/scipy (already dependencies).

**Tech Stack:** Python dataclasses, numpy (already installed), random stdlib module, Rich (already installed) for terminal output.

**Spec:** `/Users/robfox/Documents/GitHub/opensrm-ecosystem/NTHLAYER-SIMULATE.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/nthlayer/simulate/__init__.py` | Public API exports |
| `src/nthlayer/simulate/models.py` | All dataclasses: `ServiceFailureModel`, `DependencyModel`, `FailureEvent`, `PercentileResult`, `ServiceSimulationResult`, `WhatIfResult`, `SimulationResult` |
| `src/nthlayer/simulate/engine.py` | Core simulation: `generate_failure_timeline()`, `simulate_run()`, `run_simulation()`, `_topological_sort()`, `_aggregate_results()` |
| `src/nthlayer/simulate/graph.py` | `build_failure_models()`, `build_dependency_models()` — manifest → simulation model conversion |
| `src/nthlayer/simulate/what_if.py` | `parse_what_if()`, `apply_scenario()`, `run_what_if()` — what-if scenario modification layer |
| `src/nthlayer/simulate/output.py` | `print_simulation_table()` — Rich terminal output with box-drawn formatting |
| `src/nthlayer/cli/simulate.py` | `register_simulate_parser()`, `handle_simulate_command()`, `simulate_command()` — CLI entry point |
| `tests/test_simulate_models.py` | Unit tests for models |
| `tests/test_simulate_engine.py` | Unit tests for engine (analytical verification) |
| `tests/test_simulate_graph.py` | Unit tests for graph building and topological sort |
| `tests/test_simulate_what_if.py` | Unit tests for what-if scenarios |
| `tests/test_simulate_cli.py` | CLI handler tests |
| `tests/smoke/test_simulate_commands.py` | End-to-end CLI smoke tests |

### Modified Files

| File | Change |
|------|--------|
| `src/nthlayer/demo.py` | Import and register `simulate` command (~4 lines) |

---

## Chunk 1: Foundation — Models, Engine, Graph

### Task 1: Simulation Data Models

**Files:**
- Create: `src/nthlayer/simulate/__init__.py`
- Create: `src/nthlayer/simulate/models.py`
- Test: `tests/test_simulate_models.py`

- [ ] **Step 1: Write failing tests for `ServiceFailureModel` and `derive_failure_model()`**

```python
# tests/test_simulate_models.py
"""Tests for simulation data models."""
from __future__ import annotations

import pytest

from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    ServiceFailureModel,
    derive_failure_model,
)


class TestServiceFailureModel:
    def test_create_with_explicit_values(self):
        model = ServiceFailureModel(
            name="payment-api",
            availability_target=0.999,
            mtbf_hours=999.0,
            mttr_hours=1.0,
        )
        assert model.name == "payment-api"
        assert model.availability_target == 0.999
        assert model.mtbf_hours == 999.0
        assert model.mttr_hours == 1.0
        assert model.mtbf_distribution == "exponential"
        assert model.mttr_distribution == "lognormal"

    def test_default_distribution_params(self):
        model = ServiceFailureModel(
            name="test",
            availability_target=0.99,
            mtbf_hours=100.0,
            mttr_hours=1.0,
        )
        assert model.mtbf_shape == 1.0
        assert model.mttr_shape == 0.5


class TestDeriveFailureModel:
    def test_derive_from_three_nines(self):
        model = derive_failure_model("svc", availability_target=0.999)
        assert model.name == "svc"
        assert model.availability_target == 0.999
        # MTBF = MTTR * avail / (1 - avail) = 1.0 * 0.999 / 0.001 = 999
        assert model.mtbf_hours == pytest.approx(999.0, rel=0.01)
        assert model.mttr_hours == 1.0

    def test_derive_from_two_nines(self):
        model = derive_failure_model("svc", availability_target=0.99, mttr_hours=0.5)
        # MTBF = 0.5 * 0.99 / 0.01 = 49.5
        assert model.mtbf_hours == pytest.approx(49.5, rel=0.01)
        assert model.mttr_hours == 0.5

    def test_derive_with_custom_mttr(self):
        model = derive_failure_model("svc", availability_target=0.999, mttr_hours=2.0)
        # MTBF = 2.0 * 0.999 / 0.001 = 1998
        assert model.mtbf_hours == pytest.approx(1998.0, rel=0.01)


class TestFailureEvent:
    def test_create(self):
        event = FailureEvent(start_hour=10.0, duration=0.5)
        assert event.start_hour == 10.0
        assert event.duration == 0.5

    def test_end_hour(self):
        event = FailureEvent(start_hour=10.0, duration=0.5)
        assert event.end_hour == pytest.approx(10.5)


class TestDependencyModel:
    def test_critical_dependency(self):
        dep = DependencyModel(
            from_service="checkout",
            to_service="payment-api",
            critical=True,
        )
        assert dep.critical is True
        assert dep.degradation_factor == 0.99

    def test_non_critical_with_custom_degradation(self):
        dep = DependencyModel(
            from_service="checkout",
            to_service="cache",
            critical=False,
            degradation_factor=0.95,
        )
        assert dep.degradation_factor == 0.95
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nthlayer.simulate'`

- [ ] **Step 3: Create the package and implement models**

```python
# src/nthlayer/simulate/__init__.py
"""
Monte Carlo SLO simulation engine.

Predicts the probability of meeting SLAs from OpenSRM manifests
and dependency graphs. Pure transport — no model calls.
"""

from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    PercentileResult,
    ServiceFailureModel,
    ServiceSimulationResult,
    SimulationResult,
    WhatIfResult,
    derive_failure_model,
)

__all__ = [
    "DependencyModel",
    "FailureEvent",
    "PercentileResult",
    "ServiceFailureModel",
    "ServiceSimulationResult",
    "SimulationResult",
    "WhatIfResult",
    "derive_failure_model",
]
```

```python
# src/nthlayer/simulate/models.py
"""Data models for Monte Carlo SLO simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceFailureModel:
    """Stochastic failure model for a single service."""

    name: str
    availability_target: float  # e.g., 0.999
    mtbf_hours: float  # mean time between failures
    mttr_hours: float  # mean time to recovery
    mtbf_distribution: str = "exponential"
    mttr_distribution: str = "lognormal"
    mtbf_shape: float = 1.0  # shape for weibull (1.0 = exponential)
    mttr_shape: float = 0.5  # shape for lognormal


@dataclass
class FailureEvent:
    """A single failure event in a simulated timeline."""

    start_hour: float
    duration: float  # hours

    @property
    def end_hour(self) -> float:
        return self.start_hour + self.duration


@dataclass
class DependencyModel:
    """How one service depends on another."""

    from_service: str
    to_service: str
    critical: bool
    degradation_factor: float = 0.99  # for non-critical: availability during dep failure


@dataclass
class PercentileResult:
    """Percentile values for a distribution."""

    p50: float | None = None
    p75: float | None = None
    p95: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"p50": self.p50, "p75": self.p75, "p95": self.p95}


@dataclass
class ServiceSimulationResult:
    """Simulation result for a single service."""

    name: str
    target: float | None  # declared SLO target
    p_meeting_sla: float | None  # probability of meeting SLA
    availability_p50: float
    availability_p95: float
    availability_p99: float
    downtime_contribution: float  # fraction of total system downtime
    is_weakest_link: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "p_meeting_sla": self.p_meeting_sla,
            "availability_p50": round(self.availability_p50, 6),
            "availability_p95": round(self.availability_p95, 6),
            "availability_p99": round(self.availability_p99, 6),
            "downtime_contribution": round(self.downtime_contribution, 4),
            "is_weakest_link": self.is_weakest_link,
        }


@dataclass
class WhatIfResult:
    """Result of a what-if scenario comparison."""

    scenario: str  # e.g., "redundant:payment-api"
    base_p_meeting_sla: float
    modified_p_meeting_sla: float
    delta: float
    base_weakest_link: str
    modified_weakest_link: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "base_p_meeting_sla": round(self.base_p_meeting_sla, 4),
            "modified_p_meeting_sla": round(self.modified_p_meeting_sla, 4),
            "delta": round(self.delta, 4),
            "base_weakest_link": self.base_weakest_link,
            "modified_weakest_link": self.modified_weakest_link,
        }


@dataclass
class SimulationResult:
    """Complete Monte Carlo simulation result."""

    target_service: str
    target_sla: float
    horizon_days: int
    num_runs: int
    p_meeting_sla: float
    services: dict[str, ServiceSimulationResult]
    weakest_link: str
    weakest_link_contribution: float
    error_budget_forecast: PercentileResult
    what_if_results: list[WhatIfResult] = field(default_factory=list)
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_service": self.target_service,
            "target_sla": self.target_sla,
            "horizon_days": self.horizon_days,
            "num_runs": self.num_runs,
            "p_meeting_sla": round(self.p_meeting_sla, 4),
            "weakest_link": {
                "service": self.weakest_link,
                "downtime_contribution": round(self.weakest_link_contribution, 4),
            },
            "error_budget_forecast": self.error_budget_forecast.to_dict(),
            "services": {
                name: svc.to_dict() for name, svc in self.services.items()
            },
            "what_if": [w.to_dict() for w in self.what_if_results],
            "exit_code": self.exit_code,
        }


def derive_failure_model(
    name: str,
    availability_target: float,
    mttr_hours: float = 1.0,
) -> ServiceFailureModel:
    """
    Derive MTBF from availability target and MTTR.

    Availability = MTBF / (MTBF + MTTR)
    Therefore: MTBF = MTTR * availability / (1 - availability)
    """
    mtbf = mttr_hours * availability_target / (1.0 - availability_target)
    return ServiceFailureModel(
        name=name,
        availability_target=availability_target,
        mtbf_hours=mtbf,
        mttr_hours=mttr_hours,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_models.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/simulate/__init__.py src/nthlayer/simulate/models.py tests/test_simulate_models.py
git commit -m "feat: add simulation data models and derive_failure_model"
```

---

### Task 2: Failure Timeline Generation

**Files:**
- Create: `src/nthlayer/simulate/engine.py`
- Test: `tests/test_simulate_engine.py`

- [ ] **Step 1: Write failing tests for `generate_failure_timeline()` and statistical convergence**

```python
# tests/test_simulate_engine.py
"""Tests for Monte Carlo simulation engine."""
from __future__ import annotations

import random

import pytest

from nthlayer.simulate.engine import (
    generate_failure_timeline,
    simulate_run,
    run_simulation,
    _topological_sort,
)
from nthlayer.simulate.models import (
    DependencyModel,
    ServiceFailureModel,
    derive_failure_model,
)


class TestGenerateFailureTimeline:
    def test_returns_list_of_failure_events(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        events = generate_failure_timeline(model, horizon_hours=720.0)
        assert isinstance(events, list)
        assert len(events) > 0

    def test_events_within_horizon(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        horizon = 720.0
        events = generate_failure_timeline(model, horizon_hours=horizon)
        for event in events:
            assert event.start_hour < horizon
            assert event.start_hour + event.duration <= horizon + 0.001

    def test_events_non_overlapping(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        events = generate_failure_timeline(model, horizon_hours=720.0)
        for i in range(len(events) - 1):
            assert events[i].end_hour <= events[i + 1].start_hour + 0.001

    def test_high_availability_fewer_failures(self):
        low_avail = derive_failure_model("low", availability_target=0.95)
        high_avail = derive_failure_model("high", availability_target=0.9999)
        random.seed(42)
        low_events = generate_failure_timeline(low_avail, horizon_hours=2160.0)
        random.seed(42)
        high_events = generate_failure_timeline(high_avail, horizon_hours=2160.0)
        assert len(high_events) < len(low_events)


class TestTopologicalSort:
    def test_cycle_detection_raises(self):
        """Cycles in the dependency graph should raise ValueError."""
        a = derive_failure_model("a", availability_target=0.999)
        b = derive_failure_model("b", availability_target=0.999)
        deps = [
            DependencyModel(from_service="a", to_service="b", critical=True),
            DependencyModel(from_service="b", to_service="a", critical=True),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort([a, b], deps)

    def test_standalone_service_converges_to_target(self):
        """A standalone service should converge to its availability target."""
        model = derive_failure_model("svc", availability_target=0.999)
        random.seed(42)
        horizon = 2160.0  # 90 days
        availabilities = []
        for _ in range(1000):
            result = simulate_run([model], [], horizon)
            availabilities.append(result["svc"])
        mean_avail = sum(availabilities) / len(availabilities)
        # Should converge to ~0.999 within ±0.005
        assert mean_avail == pytest.approx(0.999, abs=0.005)


class TestSimulateRun:
    def test_two_independent_services(self):
        """Two independent services should each have their own availability."""
        svc_a = derive_failure_model("a", availability_target=0.999)
        svc_b = derive_failure_model("b", availability_target=0.995)
        random.seed(42)
        result = simulate_run([svc_a, svc_b], [], 2160.0)
        assert "a" in result
        assert "b" in result
        assert 0.0 <= result["a"] <= 1.0
        assert 0.0 <= result["b"] <= 1.0

    def test_critical_dependency_reduces_availability(self):
        """A service with a critical dependency should be less available."""
        parent = derive_failure_model("parent", availability_target=0.999)
        child = derive_failure_model("child", availability_target=0.999)
        dep = DependencyModel(
            from_service="child", to_service="parent", critical=True
        )
        random.seed(42)
        # Run many times and average
        child_avails = []
        for _ in range(500):
            result = simulate_run([parent, child], [dep], 2160.0)
            child_avails.append(result["child"])
        mean_child = sum(child_avails) / len(child_avails)
        # Child should be less available than its own target due to parent failures
        assert mean_child < 0.999


class TestRunSimulation:
    def test_returns_simulation_result(self):
        models = [derive_failure_model("svc", availability_target=0.999)]
        result = run_simulation(models, [], num_runs=100, horizon_days=90, seed=42)
        assert result.target_service == "svc"
        assert result.num_runs == 100
        assert 0.0 <= result.p_meeting_sla <= 1.0

    def test_analytical_two_services_in_series(self):
        """
        Analytical verification: two critical deps in series.
        A at 99.9%, B at 99.5% → composite ~99.4%
        """
        svc_a = derive_failure_model("a", availability_target=0.999)
        svc_b = derive_failure_model("b", availability_target=0.995)
        svc_c = derive_failure_model("c", availability_target=0.9999)
        deps = [
            DependencyModel(from_service="c", to_service="a", critical=True),
            DependencyModel(from_service="c", to_service="b", critical=True),
        ]
        result = run_simulation(
            [svc_a, svc_b, svc_c], deps,
            num_runs=5000, horizon_days=90, seed=42,
        )
        # C's effective availability should be around 0.999 * 0.995 = 0.994
        c_result = result.services["c"]
        assert c_result.availability_p50 == pytest.approx(0.994, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nthlayer.simulate.engine'`

- [ ] **Step 3: Implement `engine.py`**

```python
# src/nthlayer/simulate/engine.py
"""Monte Carlo SLO simulation engine."""
from __future__ import annotations

import math
import random
from collections import defaultdict

from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    PercentileResult,
    ServiceFailureModel,
    ServiceSimulationResult,
    SimulationResult,
)


def generate_failure_timeline(
    service: ServiceFailureModel, horizon_hours: float
) -> list[FailureEvent]:
    """Generate a sequence of failure events over the horizon."""
    events: list[FailureEvent] = []
    current_hour = 0.0

    while current_hour < horizon_hours:
        # Time until next failure
        if service.mtbf_distribution == "weibull":
            time_to_failure = random.weibullvariate(
                service.mtbf_hours, service.mtbf_shape
            )
        else:  # exponential (default)
            time_to_failure = random.expovariate(1.0 / service.mtbf_hours)

        current_hour += time_to_failure
        if current_hour >= horizon_hours:
            break

        # Duration of failure
        if service.mttr_distribution == "lognormal":
            duration = random.lognormvariate(
                math.log(service.mttr_hours), service.mttr_shape
            )
        else:  # exponential
            duration = random.expovariate(1.0 / service.mttr_hours)

        # Cap duration at remaining horizon
        duration = min(duration, horizon_hours - current_hour)

        events.append(FailureEvent(start_hour=current_hour, duration=duration))
        current_hour += duration

    return events


def _merge_and_sum(events: list[FailureEvent], horizon_hours: float) -> float:
    """Merge overlapping failure intervals and return total downtime."""
    if not events:
        return 0.0

    sorted_events = sorted(events, key=lambda e: e.start_hour)
    merged: list[tuple[float, float]] = []
    current_start = sorted_events[0].start_hour
    current_end = sorted_events[0].end_hour

    for event in sorted_events[1:]:
        if event.start_hour <= current_end:
            current_end = max(current_end, event.end_hour)
        else:
            merged.append((current_start, current_end))
            current_start = event.start_hour
            current_end = event.end_hour
    merged.append((current_start, current_end))

    return sum(end - start for start, end in merged)


def _topological_sort(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
) -> list[ServiceFailureModel]:
    """Sort services so dependencies are simulated before dependents."""
    name_to_service = {s.name: s for s in services}
    # Build adjacency: dep.to_service must come before dep.from_service
    in_degree: dict[str, int] = {s.name: 0 for s in services}
    adj: dict[str, list[str]] = {s.name: [] for s in services}

    for dep in dependencies:
        if dep.to_service in name_to_service and dep.from_service in name_to_service:
            adj[dep.to_service].append(dep.from_service)
            in_degree[dep.from_service] += 1

    queue = [name for name, degree in in_degree.items() if degree == 0]
    result: list[ServiceFailureModel] = []

    while queue:
        node = queue.pop(0)
        result.append(name_to_service[node])
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(services):
        raise ValueError(
            "Dependency cycle detected — cannot simulate circular dependencies"
        )

    return result


def simulate_run(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    horizon_hours: float,
) -> dict[str, float]:
    """One complete simulation run across all services."""
    ordered = _topological_sort(services, dependencies)
    timelines: dict[str, list[FailureEvent]] = {}
    results: dict[str, float] = {}

    for service in ordered:
        service_deps = [d for d in dependencies if d.from_service == service.name]
        # Generate timeline first (for downstream consumers)
        timeline = generate_failure_timeline(service, horizon_hours)
        timelines[service.name] = timeline

        # Compute availability including dependency effects
        own_downtime = _compute_downtime_from_events(timeline, horizon_hours)
        all_down_intervals: list[FailureEvent] = list(timeline)

        for dep in service_deps:
            if dep.critical and dep.to_service in timelines:
                all_down_intervals.extend(timelines[dep.to_service])

        total_downtime = _merge_and_sum(all_down_intervals, horizon_hours)

        # Non-critical degradation
        for dep in service_deps:
            if not dep.critical and dep.to_service in timelines:
                for e in timelines[dep.to_service]:
                    total_downtime += e.duration * (1.0 - dep.degradation_factor)

        total_downtime = min(total_downtime, horizon_hours)
        results[service.name] = 1.0 - (total_downtime / horizon_hours)

    return results


def run_simulation(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    num_runs: int = 10000,
    horizon_days: int = 90,
    seed: int | None = None,
) -> SimulationResult:
    """Run the full Monte Carlo simulation."""
    if seed is not None:
        random.seed(seed)

    horizon_hours = horizon_days * 24.0
    target_service = services[0]
    target_name = target_service.name
    target_sla = target_service.availability_target

    results_per_run: list[dict[str, float]] = []
    for _ in range(num_runs):
        run_result = simulate_run(services, dependencies, horizon_hours)
        results_per_run.append(run_result)

    return _aggregate_results(
        services, dependencies, results_per_run,
        target_name, target_sla, horizon_days, num_runs,
    )


def _aggregate_results(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    results_per_run: list[dict[str, float]],
    target_name: str,
    target_sla: float,
    horizon_days: int,
    num_runs: int,
) -> SimulationResult:
    """Aggregate N simulation runs into probability distributions."""
    # Collect per-service availability distributions
    service_avails: dict[str, list[float]] = defaultdict(list)
    for run in results_per_run:
        for name, avail in run.items():
            service_avails[name].append(avail)

    # P(meeting SLA) for target service
    target_avails = service_avails[target_name]
    p_meeting = sum(1 for a in target_avails if a >= target_sla) / len(target_avails)

    # Downtime contributions (how much of target's downtime each dep causes)
    downtime_contributions = _compute_downtime_contributions(
        services, dependencies, results_per_run, target_name
    )

    # Error budget exhaustion forecast
    budget_forecast = _compute_budget_forecast(
        target_avails, target_sla, horizon_days
    )

    # Build per-service results
    svc_results: dict[str, ServiceSimulationResult] = {}
    weakest = max(downtime_contributions, key=downtime_contributions.get) if downtime_contributions else target_name

    for svc in services:
        avails = sorted(service_avails[svc.name])
        n = len(avails)
        target = svc.availability_target

        svc_results[svc.name] = ServiceSimulationResult(
            name=svc.name,
            target=target,
            p_meeting_sla=sum(1 for a in avails if a >= target) / n,
            availability_p50=avails[n // 2],
            availability_p95=avails[int(n * 0.95)],
            availability_p99=avails[int(n * 0.99)],
            downtime_contribution=downtime_contributions.get(svc.name, 0.0),
            is_weakest_link=(svc.name == weakest),
        )

    weakest_contribution = downtime_contributions.get(weakest, 0.0)

    # Exit code based on P(meeting SLA)
    if p_meeting >= 0.80:
        exit_code = 0
    elif p_meeting >= 0.50:
        exit_code = 1
    else:
        exit_code = 2

    return SimulationResult(
        target_service=target_name,
        target_sla=target_sla,
        horizon_days=horizon_days,
        num_runs=num_runs,
        p_meeting_sla=p_meeting,
        services=svc_results,
        weakest_link=weakest,
        weakest_link_contribution=weakest_contribution,
        error_budget_forecast=budget_forecast,
        exit_code=exit_code,
    )


def _compute_downtime_contributions(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    results_per_run: list[dict[str, float]],
    target_name: str,
) -> dict[str, float]:
    """Estimate each service's contribution to target's downtime."""
    # Use correlation: when a dependency has low availability in a run,
    # does the target also have low availability?
    contributions: dict[str, float] = {}
    target_avails = [r[target_name] for r in results_per_run]
    target_downtimes = [1.0 - a for a in target_avails]
    total_target_downtime = sum(target_downtimes)

    if total_target_downtime == 0:
        return {s.name: 0.0 for s in services}

    for svc in services:
        if svc.name == target_name:
            # Self-contribution: runs where target is down but no dep is down
            contributions[svc.name] = 0.0  # will be remainder
            continue
        svc_downtimes = [1.0 - r.get(svc.name, 1.0) for r in results_per_run]
        # Correlation-weighted contribution
        correlated = sum(
            td * sd for td, sd in zip(target_downtimes, svc_downtimes)
        )
        contributions[svc.name] = correlated / total_target_downtime if total_target_downtime > 0 else 0.0

    # Normalize
    total_contrib = sum(contributions.values())
    if total_contrib > 0:
        for name in contributions:
            contributions[name] /= total_contrib

    return contributions


def _compute_budget_forecast(
    target_avails: list[float],
    target_sla: float,
    horizon_days: int,
) -> PercentileResult:
    """Compute when error budget would exhaust based on simulated availabilities."""
    error_budget = 1.0 - target_sla  # e.g., 0.001 for 99.9%
    exhaustion_days: list[float] = []

    for avail in target_avails:
        downtime_fraction = 1.0 - avail
        if downtime_fraction >= error_budget:
            # Budget would exhaust; estimate when
            if downtime_fraction > 0:
                day = horizon_days * (error_budget / downtime_fraction)
                exhaustion_days.append(day)
            else:
                exhaustion_days.append(float(horizon_days))
        # If budget not exhausted, don't add to exhaustion list

    if not exhaustion_days:
        return PercentileResult(p50=None, p75=None, p95=None)

    sorted_days = sorted(exhaustion_days)
    n = len(sorted_days)
    return PercentileResult(
        p50=sorted_days[n // 2],
        p75=sorted_days[int(n * 0.75)] if n > 1 else sorted_days[0],
        p95=sorted_days[int(n * 0.95)] if n > 1 else sorted_days[0],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/simulate/engine.py tests/test_simulate_engine.py
git commit -m "feat: add Monte Carlo simulation engine with failure timelines and dependency cascading"
```

---

### Task 3: Graph Building from Manifests

**Files:**
- Create: `src/nthlayer/simulate/graph.py`
- Test: `tests/test_simulate_graph.py`

- [ ] **Step 1: Write failing tests for manifest-to-model conversion**

```python
# tests/test_simulate_graph.py
"""Tests for building simulation models from manifests."""
from __future__ import annotations

import pytest

from nthlayer.simulate.graph import (
    build_failure_models,
    build_dependency_models,
)
from nthlayer.specs.manifest import (
    Dependency,
    DependencySLO,
    ReliabilityManifest,
    SLODefinition,
)


def _make_manifest(
    name: str,
    avail_target: float = 99.9,
    deps: list[Dependency] | None = None,
) -> ReliabilityManifest:
    return ReliabilityManifest(
        name=name,
        team="test",
        tier="standard",
        type="api",
        slos=[SLODefinition(name="availability", target=avail_target, window="30d")],
        dependencies=deps or [],
    )


class TestBuildFailureModels:
    def test_single_manifest(self):
        manifest = _make_manifest("svc-a", avail_target=99.9)
        models = build_failure_models([manifest])
        assert len(models) == 1
        assert models[0].name == "svc-a"
        assert models[0].availability_target == pytest.approx(0.999)

    def test_availability_as_percentage_vs_ratio(self):
        """Targets > 1 are treated as percentages (99.9 → 0.999)."""
        manifest = _make_manifest("svc", avail_target=99.95)
        models = build_failure_models([manifest])
        assert models[0].availability_target == pytest.approx(0.9995)

    def test_availability_as_ratio(self):
        """Targets <= 1 are treated as ratios."""
        manifest = _make_manifest("svc", avail_target=0.999)
        models = build_failure_models([manifest])
        assert models[0].availability_target == pytest.approx(0.999)

    def test_no_availability_slo_raises(self):
        manifest = ReliabilityManifest(
            name="svc", team="t", tier="standard", type="api", slos=[]
        )
        with pytest.raises(ValueError, match="availability"):
            build_failure_models([manifest])


class TestBuildDependencyModels:
    def test_critical_dependency(self):
        deps = [Dependency(name="db", type="database", critical=True)]
        manifest = _make_manifest("svc", deps=deps)
        dep_models = build_dependency_models([manifest])
        assert len(dep_models) == 1
        assert dep_models[0].from_service == "svc"
        assert dep_models[0].to_service == "db"
        assert dep_models[0].critical is True

    def test_non_critical_dependency(self):
        deps = [Dependency(name="cache", type="cache", critical=False)]
        manifest = _make_manifest("svc", deps=deps)
        dep_models = build_dependency_models([manifest])
        assert dep_models[0].critical is False

    def test_multiple_manifests(self):
        m1 = _make_manifest("a", deps=[Dependency(name="b", type="api", critical=True)])
        m2 = _make_manifest("b")
        dep_models = build_dependency_models([m1, m2])
        assert len(dep_models) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_graph.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `graph.py`**

```python
# src/nthlayer/simulate/graph.py
"""Build simulation models from OpenSRM manifests."""
from __future__ import annotations

from nthlayer.simulate.models import (
    DependencyModel,
    ServiceFailureModel,
    derive_failure_model,
)
from nthlayer.specs.manifest import ReliabilityManifest


def _normalize_availability(target: float) -> float:
    """Normalize availability target to a 0-1 ratio.

    Values > 1 are treated as percentages (e.g., 99.9 → 0.999).
    Values <= 1 are treated as ratios (e.g., 0.999).
    """
    if target > 1.0:
        return target / 100.0
    return target


def _get_availability_target(manifest: ReliabilityManifest) -> float:
    """Extract and normalize availability target from manifest."""
    for slo in manifest.slos:
        if slo.name == "availability":
            return _normalize_availability(slo.target)
    raise ValueError(
        f"Service '{manifest.name}' has no availability SLO — "
        f"required for simulation"
    )


def build_failure_models(
    manifests: list[ReliabilityManifest],
    default_mttr_hours: float = 1.0,
) -> list[ServiceFailureModel]:
    """Build failure models from manifests."""
    models: list[ServiceFailureModel] = []
    for manifest in manifests:
        avail = _get_availability_target(manifest)
        model = derive_failure_model(
            name=manifest.name,
            availability_target=avail,
            mttr_hours=default_mttr_hours,
        )
        models.append(model)
    return models


def build_dependency_models(
    manifests: list[ReliabilityManifest],
) -> list[DependencyModel]:
    """Build dependency models from manifests."""
    dep_models: list[DependencyModel] = []
    for manifest in manifests:
        for dep in manifest.dependencies:
            dep_models.append(
                DependencyModel(
                    from_service=manifest.name,
                    to_service=dep.name,
                    critical=dep.critical,
                )
            )
    return dep_models
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_graph.py -v`
Expected: All tests PASS

- [ ] **Step 5: Update `__init__.py` exports and commit**

Add `build_failure_models`, `build_dependency_models` to `src/nthlayer/simulate/__init__.py`.

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/simulate/graph.py src/nthlayer/simulate/__init__.py tests/test_simulate_graph.py
git commit -m "feat: add manifest-to-simulation-model conversion"
```

---

## Chunk 2: CLI, Output, What-If, Demo

### Task 4: Terminal Output Formatting

**Files:**
- Create: `src/nthlayer/simulate/output.py`
- Test: (tested via CLI integration — visual output is validated by smoke tests)

- [ ] **Step 1: Implement `output.py`**

```python
# src/nthlayer/simulate/output.py
"""Rich terminal output for simulation results."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from nthlayer.cli.ux import console
from nthlayer.simulate.models import SimulationResult


def print_simulation_table(result: SimulationResult) -> None:
    """Print simulation results as a formatted Rich table."""
    # Header panel
    console.print()
    p_pct = result.p_meeting_sla * 100
    sla_pct = result.target_sla * 100

    if p_pct >= 80:
        p_color = "green"
    elif p_pct >= 50:
        p_color = "yellow"
    else:
        p_color = "red"

    header_text = (
        f"[bold]SLA Simulation: {result.target_service}[/bold]\n"
        f"[muted]{result.num_runs:,} runs, {result.horizon_days}-day horizon[/muted]"
    )
    console.print(Panel(header_text, border_style="cyan"))
    console.print()

    # Headline numbers
    console.print(f"  [cyan]Target SLA:[/cyan]     {sla_pct:.1f}% availability")
    console.print(
        f"  [cyan]P(meeting SLA):[/cyan] [{p_color} bold]{p_pct:.1f}%[/]"
    )
    console.print()

    # Weakest link
    wl = result.weakest_link
    wl_pct = result.weakest_link_contribution * 100
    console.print(
        f"  [cyan]Weakest link:[/cyan]   {wl} "
        f"([muted]contributes {wl_pct:.0f}% of downtime[/muted])"
    )
    console.print()

    # Error budget forecast
    forecast = result.error_budget_forecast
    if forecast.p50 is not None:
        console.print("  [bold]Error budget forecast:[/bold]")
        console.print(f"    Median exhaustion:      day {forecast.p50:.0f} of {result.horizon_days}")
        if forecast.p95 is not None:
            console.print(f"    Worst case (p95):       day {forecast.p95:.0f} of {result.horizon_days}")
        console.print()

    # Per-service table
    table = Table(title="Per-Service Results", show_header=True, header_style="bold")
    table.add_column("Service", style="cyan")
    table.add_column("Target", justify="right")
    table.add_column("P(SLA)", justify="right")
    table.add_column("Avail p50", justify="right")
    table.add_column("Avail p99", justify="right")
    table.add_column("Downtime %", justify="right")

    for name, svc in sorted(result.services.items()):
        target_str = f"{svc.target * 100:.2f}%" if svc.target else "—"
        p_sla_str = f"{svc.p_meeting_sla * 100:.1f}%" if svc.p_meeting_sla is not None else "—"
        p50_str = f"{svc.availability_p50 * 100:.3f}%"
        p99_str = f"{svc.availability_p99 * 100:.3f}%"
        dt_str = f"{svc.downtime_contribution * 100:.1f}%"

        if svc.is_weakest_link:
            name = f"[bold red]{name}[/bold red]"

        table.add_row(name, target_str, p_sla_str, p50_str, p99_str, dt_str)

    console.print(table)
    console.print()

    # What-if results
    if result.what_if_results:
        console.print("[bold]What-if scenarios:[/bold]")
        for wif in result.what_if_results:
            delta_pct = wif.delta * 100
            if delta_pct > 0:
                delta_str = f"[green]+{delta_pct:.1f}%[/green]"
            else:
                delta_str = f"[red]{delta_pct:.1f}%[/red]  [warning]← reduces reliability[/warning]"

            base_pct = wif.base_p_meeting_sla * 100
            mod_pct = wif.modified_p_meeting_sla * 100
            console.print(
                f"  {wif.scenario:<35s}  P(SLA) {base_pct:.1f}% → {mod_pct:.1f}%  ({delta_str})"
            )
        console.print()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/simulate/output.py
git commit -m "feat: add Rich terminal output for simulation results"
```

---

### Task 5: What-If Scenarios

**Files:**
- Create: `src/nthlayer/simulate/what_if.py`
- Test: `tests/test_simulate_what_if.py`

- [ ] **Step 1: Write failing tests for what-if scenario parsing and execution**

```python
# tests/test_simulate_what_if.py
"""Tests for what-if scenario parsing and execution."""
from __future__ import annotations

import pytest

from nthlayer.simulate.models import ServiceFailureModel, DependencyModel, derive_failure_model
from nthlayer.simulate.what_if import parse_what_if, apply_scenario


class TestParseWhatIf:
    def test_redundant(self):
        scenario = parse_what_if("redundant:payment-api")
        assert scenario["type"] == "redundant"
        assert scenario["service"] == "payment-api"

    def test_improve(self):
        scenario = parse_what_if("improve:db:availability:0.9999")
        assert scenario["type"] == "improve"
        assert scenario["service"] == "db"
        assert scenario["value"] == pytest.approx(0.9999)

    def test_remove(self):
        scenario = parse_what_if("remove:cache")
        assert scenario["type"] == "remove"
        assert scenario["service"] == "cache"

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unknown"):
            parse_what_if("unknown:foo")


class TestApplyScenario:
    def test_redundant_squares_failure_probability(self):
        services = [derive_failure_model("a", 0.99)]
        deps: list[DependencyModel] = []
        scenario = parse_what_if("redundant:a")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        # Redundant should give much higher MTBF
        a_model = next(s for s in new_services if s.name == "a")
        assert a_model.availability_target > 0.99

    def test_remove_dependency(self):
        services = [
            derive_failure_model("parent", 0.999),
            derive_failure_model("child", 0.999),
        ]
        deps = [DependencyModel(from_service="child", to_service="parent", critical=True)]
        scenario = parse_what_if("remove:parent")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        assert len(new_deps) == 0

    def test_improve_availability(self):
        services = [derive_failure_model("svc", 0.99)]
        deps: list[DependencyModel] = []
        scenario = parse_what_if("improve:svc:availability:0.9999")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        svc = next(s for s in new_services if s.name == "svc")
        assert svc.availability_target == pytest.approx(0.9999)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_what_if.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `what_if.py`**

```python
# src/nthlayer/simulate/what_if.py
"""What-if scenario parsing and application."""
from __future__ import annotations

import copy
from typing import Any

from nthlayer.simulate.models import (
    DependencyModel,
    ServiceFailureModel,
    derive_failure_model,
)


def parse_what_if(scenario_str: str) -> dict[str, Any]:
    """Parse a what-if scenario string into a structured dict."""
    parts = scenario_str.split(":")

    if parts[0] == "redundant" and len(parts) == 2:
        return {"type": "redundant", "service": parts[1]}
    elif parts[0] == "improve" and len(parts) == 4:
        return {
            "type": "improve",
            "service": parts[1],
            "metric": parts[2],
            "value": float(parts[3]),
        }
    elif parts[0] == "remove" and len(parts) == 2:
        return {"type": "remove", "service": parts[1]}
    elif parts[0] == "degrade" and len(parts) == 3:
        return {
            "type": "degrade",
            "service": parts[1],
            "factor": float(parts[2]),
        }
    else:
        raise ValueError(
            f"Unknown what-if scenario: '{scenario_str}'. "
            f"Valid formats: redundant:<svc>, improve:<svc>:availability:<val>, "
            f"remove:<svc>, degrade:<svc>:<factor>"
        )


def apply_scenario(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    scenario: dict[str, Any],
) -> tuple[list[ServiceFailureModel], list[DependencyModel]]:
    """Apply a what-if scenario, returning modified copies."""
    new_services = copy.deepcopy(services)
    new_deps = copy.deepcopy(dependencies)

    stype = scenario["type"]
    svc_name = scenario["service"]

    if stype == "redundant":
        # Active-active: effective availability = 1 - (1 - A)^2
        for i, s in enumerate(new_services):
            if s.name == svc_name:
                p_fail = 1.0 - s.availability_target
                new_avail = 1.0 - (p_fail * p_fail)
                new_services[i] = derive_failure_model(
                    s.name, new_avail, s.mttr_hours
                )
                break

    elif stype == "improve":
        value = scenario["value"]
        for i, s in enumerate(new_services):
            if s.name == svc_name:
                new_services[i] = derive_failure_model(
                    s.name, value, s.mttr_hours
                )
                break

    elif stype == "remove":
        new_deps = [d for d in new_deps if d.to_service != svc_name]

    elif stype == "degrade":
        factor = scenario["factor"]
        for i, d in enumerate(new_deps):
            if d.to_service == svc_name and d.critical:
                new_deps[i] = DependencyModel(
                    from_service=d.from_service,
                    to_service=d.to_service,
                    critical=False,
                    degradation_factor=factor,
                )

    return new_services, new_deps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_what_if.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/simulate/what_if.py tests/test_simulate_what_if.py
git commit -m "feat: add what-if scenario parsing and application for simulation"
```

---

### Task 6: CLI Command + Demo Mode

**Files:**
- Create: `src/nthlayer/cli/simulate.py`
- Modify: `src/nthlayer/demo.py` (add import and registration at ~line 872)
- Test: `tests/test_simulate_cli.py`
- Test: `tests/smoke/test_simulate_commands.py`

- [ ] **Step 1: Write failing tests for CLI handler**

```python
# tests/test_simulate_cli.py
"""Tests for simulate CLI command."""
from __future__ import annotations

import os

import pytest

from nthlayer.cli.simulate import simulate_command


class TestSimulateCommand:
    def test_demo_mode_returns_zero(self):
        result = simulate_command(
            manifest_file="dummy.yaml",
            demo=True,
            output_format="json",
        )
        assert result == 0

    def test_demo_mode_table_returns_zero(self):
        result = simulate_command(
            manifest_file="dummy.yaml",
            demo=True,
            output_format="table",
        )
        assert result == 0

    def test_missing_manifest_returns_error(self):
        result = simulate_command(
            manifest_file="/nonexistent/path.yaml",
            demo=False,
            output_format="table",
        )
        assert result == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `cli/simulate.py`**

```python
# src/nthlayer/cli/simulate.py
"""
CLI command for Monte Carlo SLO simulation.

Predicts the probability of meeting SLAs from OpenSRM manifests
and dependency graphs.

Commands:
    nthlayer simulate <manifest>             - Run simulation
    nthlayer simulate <manifest> --demo      - Demo with sample data
    nthlayer simulate <manifest> --json      - JSON output
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from nthlayer.cli.ux import console, error, info
from nthlayer.simulate.engine import run_simulation
from nthlayer.simulate.graph import build_dependency_models, build_failure_models
from nthlayer.simulate.models import (
    DependencyModel,
    PercentileResult,
    ServiceSimulationResult,
    SimulationResult,
    WhatIfResult,
    derive_failure_model,
)
from nthlayer.simulate.output import print_simulation_table
from nthlayer.simulate.what_if import apply_scenario, parse_what_if


def simulate_command(
    manifest_file: str,
    manifests_dir: Optional[str] = None,
    num_runs: int = 10000,
    horizon_days: int = 90,
    seed: Optional[int] = None,
    what_if: Optional[list[str]] = None,
    output_format: str = "table",
    min_p_sla: Optional[float] = None,
    demo: bool = False,
) -> int:
    """
    Run Monte Carlo SLO simulation.

    Exit codes:
        0 - P(SLA) >= 80% (or >= min_p_sla if set)
        1 - P(SLA) between 50% and 80%
        2 - P(SLA) < 50% or error

    Returns:
        Exit code (0, 1, or 2)
    """
    if demo:
        return _demo_simulate_output(output_format)

    # Load manifests
    try:
        from nthlayer.specs.loader import load_manifest

        manifests = [load_manifest(manifest_file)]
    except Exception as e:
        error(f"Error loading manifest: {e}")
        return 2

    # Load additional manifests from directory
    if manifests_dir:
        try:
            manifests.extend(_load_manifests_from_dir(manifests_dir, exclude=manifest_file))
        except Exception as e:
            error(f"Error loading manifests from directory: {e}")
            return 2

    # Build simulation models
    try:
        services = build_failure_models(manifests)
        dependencies = build_dependency_models(manifests)
    except ValueError as e:
        error(str(e))
        return 2

    # Run base simulation
    result = run_simulation(
        services, dependencies,
        num_runs=num_runs,
        horizon_days=horizon_days,
        seed=seed,
    )

    # Run what-if scenarios
    if what_if:
        for scenario_str in what_if:
            try:
                scenario = parse_what_if(scenario_str)
                mod_services, mod_deps = apply_scenario(services, dependencies, scenario)
                mod_result = run_simulation(
                    mod_services, mod_deps,
                    num_runs=num_runs,
                    horizon_days=horizon_days,
                    seed=seed,
                )
                result.what_if_results.append(
                    WhatIfResult(
                        scenario=scenario_str,
                        base_p_meeting_sla=result.p_meeting_sla,
                        modified_p_meeting_sla=mod_result.p_meeting_sla,
                        delta=mod_result.p_meeting_sla - result.p_meeting_sla,
                        base_weakest_link=result.weakest_link,
                        modified_weakest_link=mod_result.weakest_link,
                    )
                )
            except ValueError as e:
                error(f"Invalid what-if scenario '{scenario_str}': {e}")

    # Override exit code if min_p_sla is set
    if min_p_sla is not None:
        result.exit_code = 0 if result.p_meeting_sla >= min_p_sla else 1

    # Output
    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        print_simulation_table(result)

    return result.exit_code


def _load_manifests_from_dir(directory: str, exclude: str = "") -> list:
    """Load all manifests from a directory."""
    from nthlayer.specs.loader import load_manifest

    manifests = []
    exclude_abs = os.path.abspath(exclude) if exclude else ""

    for filename in sorted(os.listdir(directory)):
        if not filename.endswith((".yaml", ".yml")):
            continue
        filepath = os.path.join(directory, filename)
        if os.path.abspath(filepath) == exclude_abs:
            continue
        try:
            manifests.append(load_manifest(filepath))
        except Exception:
            pass  # intentionally ignored: skip non-manifest YAML files

    return manifests


def _demo_simulate_output(output_format: str) -> int:
    """Show demo simulation output with sample data."""
    result = SimulationResult(
        target_service="checkout-service",
        target_sla=0.999,
        horizon_days=90,
        num_runs=10000,
        p_meeting_sla=0.732,
        services={
            "checkout-service": ServiceSimulationResult(
                name="checkout-service",
                target=0.999,
                p_meeting_sla=0.732,
                availability_p50=0.9987,
                availability_p95=0.9951,
                availability_p99=0.9923,
                downtime_contribution=0.10,
                is_weakest_link=False,
            ),
            "payment-api": ServiceSimulationResult(
                name="payment-api",
                target=0.999,
                p_meeting_sla=0.812,
                availability_p50=0.9992,
                availability_p95=0.9971,
                availability_p99=0.9948,
                downtime_contribution=0.68,
                is_weakest_link=True,
            ),
            "database-primary": ServiceSimulationResult(
                name="database-primary",
                target=0.9999,
                p_meeting_sla=0.951,
                availability_p50=0.99997,
                availability_p95=0.99981,
                availability_p99=0.99962,
                downtime_contribution=0.22,
                is_weakest_link=False,
            ),
        },
        weakest_link="payment-api",
        weakest_link_contribution=0.68,
        error_budget_forecast=PercentileResult(p50=71, p75=58, p95=34),
        what_if_results=[
            WhatIfResult(
                scenario="redundant:payment-api",
                base_p_meeting_sla=0.732,
                modified_p_meeting_sla=0.946,
                delta=0.214,
                base_weakest_link="payment-api",
                modified_weakest_link="database-primary",
            ),
            WhatIfResult(
                scenario="improve:database-primary:availability:0.9999",
                base_p_meeting_sla=0.732,
                modified_p_meeting_sla=0.821,
                delta=0.089,
                base_weakest_link="payment-api",
                modified_weakest_link="payment-api",
            ),
        ],
        exit_code=1,
    )

    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        print_simulation_table(result)

    return 0


def register_simulate_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register simulate subcommand parser."""
    parser = subparsers.add_parser(
        "simulate",
        help="Monte Carlo SLO simulation — predict P(meeting SLA)",
    )
    parser.add_argument("manifest_file", help="Path to primary service manifest")
    parser.add_argument(
        "--manifests-dir",
        help="Directory containing dependency manifests",
    )
    parser.add_argument(
        "--runs", "-n",
        type=int, default=10000,
        help="Number of simulation runs (default: 10000)",
    )
    parser.add_argument(
        "--horizon",
        type=int, default=90,
        help="Simulation horizon in days (default: 90)",
    )
    parser.add_argument(
        "--seed",
        type=int, default=None,
        help="Random seed for reproducible results",
    )
    parser.add_argument(
        "--what-if",
        action="append", default=None,
        help="What-if scenario (e.g., redundant:payment-api, improve:db:availability:0.9999, remove:cache)",
    )
    parser.add_argument(
        "--format", "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--min-p-sla",
        type=float, default=None,
        help="Minimum P(SLA) for CI gate (exit 1 if below)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_simulate_command(args: argparse.Namespace) -> int:
    """Handle simulate command from CLI args."""
    return simulate_command(
        manifest_file=args.manifest_file,
        manifests_dir=getattr(args, "manifests_dir", None),
        num_runs=getattr(args, "runs", 10000),
        horizon_days=getattr(args, "horizon", 90),
        seed=getattr(args, "seed", None),
        what_if=getattr(args, "what_if", None),
        output_format=getattr(args, "output_format", "table"),
        min_p_sla=getattr(args, "min_p_sla", None),
        demo=getattr(args, "demo", False),
    )
```

- [ ] **Step 4: Register the command in `demo.py`**

Two changes needed in `demo.py`:

**4a. Add import** at the top (around line 37, with the other CLI imports):

```python
from nthlayer.cli.simulate import handle_simulate_command, register_simulate_parser
```

**4b. Add parser registration** in `build_parser()` after `register_migrate_parser(subparsers)` (line 898):

```python
    # Monte Carlo SLO simulation
    register_simulate_parser(subparsers)
```

**4c. Add dispatch** in `main()` after the `migrate` handler (line 1347), before `parser.print_help()`:

```python
    if args.command == "simulate":
        sys.exit(handle_simulate_command(args))
```

This follows the exact pattern used by all other registered commands (e.g., `drift` at line 1316-1317).

- [ ] **Step 5: Run CLI tests to verify they pass**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_simulate_cli.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Write and run smoke test**

```python
# tests/smoke/test_simulate_commands.py
"""Smoke tests for nthlayer simulate CLI command."""
from __future__ import annotations

import pytest

from tests.smoke._helpers import run_nthlayer

pytestmark = pytest.mark.smoke


class TestSimulateDemo:
    def test_simulate_demo_table(self):
        result = run_nthlayer("simulate", "dummy.yaml", "--demo")
        assert result.exit_code == 0
        assert "checkout-service" in result.stdout

    def test_simulate_demo_json(self):
        result = run_nthlayer("simulate", "dummy.yaml", "--demo", "--format", "json")
        assert result.exit_code == 0
        assert '"target_service"' in result.stdout
        assert '"p_meeting_sla"' in result.stdout
```

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/smoke/test_simulate_commands.py -v`
Expected: All 2 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
git add src/nthlayer/cli/simulate.py src/nthlayer/demo.py src/nthlayer/simulate/output.py tests/test_simulate_cli.py tests/smoke/test_simulate_commands.py
git commit -m "feat: add nthlayer simulate CLI command with demo mode and what-if scenarios"
```

---

### Task 7: Run Existing Tests to Verify No Regressions

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/ -x --ignore=tests/smoke --ignore=tests/integration -q`
Expected: All existing tests still pass

- [ ] **Step 2: Run smoke tests**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/smoke/ -x -q`
Expected: All smoke tests pass (including new simulate tests)

- [ ] **Step 3: Run linting**

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && make lint`
Expected: No new lint errors

---

## Task Summary

| Task | Description | New Tests | Files Created | Files Modified |
|------|-------------|-----------|---------------|----------------|
| 1 | Data models + `derive_failure_model()` | 8 | `simulate/__init__.py`, `simulate/models.py`, `test_simulate_models.py` | — |
| 2 | Simulation engine (timeline, run, aggregation, topo sort) | 9 | `simulate/engine.py`, `test_simulate_engine.py` | — |
| 3 | Manifest → simulation model conversion | 7 | `simulate/graph.py`, `test_simulate_graph.py` | `simulate/__init__.py` |
| 4 | Rich terminal output | — | `simulate/output.py` | — |
| 5 | What-if scenario parsing + application | 7 | `simulate/what_if.py`, `test_simulate_what_if.py` | — |
| 6 | CLI command + demo mode + smoke tests | 5 | `cli/simulate.py`, `test_simulate_cli.py`, `smoke/test_simulate_commands.py` | `demo.py` |
| 7 | Regression check | 0 | — | — |
| **Total** | | **~36** | **11 new files** | **2 modified** |

## Future Work (Not in This Plan)

These items from the spec are deferred to follow-up work:

- **Prometheus historical calibration** (spec items 9): Requires live Prometheus — add after core is stable
- **Judgment SLO simulation for ai-gate** (spec item 10): Bernoulli process model for reversal rates
- **Grafana dashboard output** (spec item 11): `--grafana-output` flag generating dashboard JSON
- **Markdown report output** (spec item 8, partial): `--format markdown`
- **CI/CD gate GitHub Action** integration: Wrapping `--min-p-sla --exit-code` in an action
- **`failure_model` manifest field**: Adding MTBF/MTTR to the OpenSRM schema and parser
