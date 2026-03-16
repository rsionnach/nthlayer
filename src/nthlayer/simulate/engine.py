"""
Monte Carlo simulation engine for SLO reliability prediction.

Implements failure timeline generation, dependency cascading, and
aggregation of simulation runs into a SimulationResult.

Pure stdlib — no numpy, no external sampling libraries.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Sequence

from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    PercentileResult,
    ServiceFailureModel,
    ServiceSimulationResult,
    SimulationResult,
)


# ---------------------------------------------------------------------------
# Internal sampling helpers
# ---------------------------------------------------------------------------


def _sample_exponential(mean: float) -> float:
    """Sample from an exponential distribution with the given mean.

    Uses the inverse-CDF method: -mean * ln(U) where U ~ Uniform(0, 1].
    """
    u = random.random()
    # Clamp to avoid log(0)
    if u <= 0.0:
        u = 1e-300
    return -mean * math.log(u)


def _sample_weibull(scale: float, shape: float) -> float:
    """Sample from a Weibull distribution.

    scale = lambda (characteristic life), shape = k (shape parameter).
    Uses inverse-CDF: scale * (-ln(U))^(1/shape).
    """
    u = random.random()
    if u <= 0.0:
        u = 1e-300
    return scale * (-math.log(u)) ** (1.0 / shape)


def _sample_lognormal(mean: float, sigma: float) -> float:
    """Sample from a lognormal distribution.

    mean is the *arithmetic* mean of the lognormal.
    sigma is the shape parameter (std of the underlying normal).

    Convert arithmetic mean to mu (log-space mean):
        mu = ln(mean) - sigma^2 / 2
    """
    mu = math.log(mean) - (sigma**2) / 2.0
    return math.exp(random.gauss(mu, sigma))


def _sample_ttf(service: ServiceFailureModel) -> float:
    """Sample a time-to-failure from the service's MTBF distribution."""
    if service.mtbf_distribution == "weibull":
        # For Weibull, mtbf_hours is the scale; mtbf_shape is the shape k
        return _sample_weibull(service.mtbf_hours, service.mtbf_shape)
    # Default: exponential
    return _sample_exponential(service.mtbf_hours)


def _sample_duration(service: ServiceFailureModel) -> float:
    """Sample a failure duration from the service's MTTR distribution."""
    if service.mttr_distribution == "exponential":
        return _sample_exponential(service.mttr_hours)
    # Default: lognormal
    return _sample_lognormal(service.mttr_hours, service.mttr_shape)


# ---------------------------------------------------------------------------
# Public: generate_failure_timeline
# ---------------------------------------------------------------------------


def generate_failure_timeline(
    service: ServiceFailureModel,
    horizon_hours: float,
) -> list[FailureEvent]:
    """Walk forward through time generating non-overlapping failure events.

    Samples time-to-failure (from exponential or Weibull) and recovery
    duration (from lognormal or exponential) until the horizon is exceeded.

    Args:
        service: Failure characteristics for the service.
        horizon_hours: Simulation window in hours.

    Returns:
        Chronologically ordered list of non-overlapping FailureEvent objects.
        Each event is fully contained within [0, horizon_hours].
    """
    events: list[FailureEvent] = []
    current_time = 0.0

    while True:
        # Time until next failure
        ttf = _sample_ttf(service)
        current_time += ttf
        if current_time >= horizon_hours:
            break

        # Duration of this failure
        duration = _sample_duration(service)
        # Cap at remaining horizon
        max_duration = horizon_hours - current_time
        if duration > max_duration:
            duration = max_duration

        if duration > 0.0:
            events.append(FailureEvent(start_hour=current_time, duration=duration))

        # Advance time past the recovery
        current_time += duration

    return events


# ---------------------------------------------------------------------------
# Internal: _merge_and_sum
# ---------------------------------------------------------------------------


def _merge_and_sum(events: list[FailureEvent], horizon_hours: float) -> float:
    """Merge overlapping failure intervals and return total downtime hours.

    Args:
        events: List of FailureEvent objects (may be unsorted or overlapping).
        horizon_hours: Simulation horizon; result is capped to this value.

    Returns:
        Total downtime in hours after merging all overlapping intervals.
    """
    if not events:
        return 0.0

    # Sort by start time
    sorted_events = sorted(events, key=lambda e: e.start_hour)

    total_downtime = 0.0
    merge_start = sorted_events[0].start_hour
    merge_end = sorted_events[0].end_hour

    for event in sorted_events[1:]:
        if event.start_hour <= merge_end:
            # Overlapping — extend the merged interval
            merge_end = max(merge_end, event.end_hour)
        else:
            # Gap — close the current interval and start a new one
            total_downtime += min(merge_end, horizon_hours) - min(merge_start, horizon_hours)
            merge_start = event.start_hour
            merge_end = event.end_hour

    # Close the last interval
    total_downtime += min(merge_end, horizon_hours) - min(merge_start, horizon_hours)

    return max(0.0, total_downtime)


# ---------------------------------------------------------------------------
# Internal: _topological_sort
# ---------------------------------------------------------------------------


def _topological_sort(
    services: Sequence[ServiceFailureModel],
    dependencies: Sequence[DependencyModel],
) -> list[ServiceFailureModel]:
    """Return services in topological order (dependencies before dependents).

    Uses Kahn's algorithm. A service that depends on another (from_service
    depends on to_service) must be processed *after* to_service.

    Args:
        services: All service models to sort.
        dependencies: Directed dependency edges.

    Returns:
        Services in an order such that all dependencies are processed first.

    Raises:
        ValueError: If a cycle is detected in the dependency graph.
    """
    service_map = {s.name: s for s in services}
    all_names = set(service_map.keys())

    # Build adjacency: to_service → [from_service, ...]
    # (to_service must come before from_service)
    successors: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)

    for name in all_names:
        in_degree[name]  # Ensure every node exists in in_degree

    for dep in dependencies:
        frm = dep.from_service
        to = dep.to_service
        if frm not in all_names or to not in all_names:
            continue
        successors[to].append(frm)
        in_degree[frm] += 1

    # Start with nodes that have no dependencies
    queue: list[str] = [name for name in all_names if in_degree[name] == 0]
    result: list[ServiceFailureModel] = []

    while queue:
        # Use a deterministic ordering for reproducibility
        queue.sort()
        name = queue.pop(0)
        result.append(service_map[name])
        for successor in successors[name]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    if len(result) != len(all_names):
        raise ValueError(
            "Dependency cycle detected among services: "
            f"{sorted(all_names - {s.name for s in result})}"
        )

    return result


# ---------------------------------------------------------------------------
# Internal: simulate_run helpers
# ---------------------------------------------------------------------------


def _overlay_critical_failures(
    base_events: list[FailureEvent],
    dep_events: list[FailureEvent],
) -> list[FailureEvent]:
    """Combine service failures with critical dependency failures.

    Returns a merged list suitable for downtime calculation.
    """
    return base_events + dep_events


# ---------------------------------------------------------------------------
# Public: simulate_run
# ---------------------------------------------------------------------------


def simulate_run(
    services: Sequence[ServiceFailureModel],
    dependencies: Sequence[DependencyModel],
    horizon_hours: float,
) -> dict[str, float]:
    """Run a single Monte Carlo simulation and return per-service availability.

    Steps:
    1. Topologically sort services so dependencies are processed first.
    2. For each service, generate its own failure timeline.
    3. Overlay critical dependency failures (full outage propagation).
    4. Apply non-critical degradation as a multiplier on resulting uptime.
    5. Compute availability = (horizon - downtime) / horizon.

    Args:
        services: Service failure models.
        dependencies: Directed dependency edges.
        horizon_hours: Simulation window in hours.

    Returns:
        Dict mapping service name → availability fraction [0, 1].
    """
    sorted_services = _topological_sort(services, dependencies)

    # Group dependencies by from_service for fast lookup
    critical_deps: dict[str, list[str]] = defaultdict(list)
    non_critical_deps: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for dep in dependencies:
        if dep.critical:
            critical_deps[dep.from_service].append(dep.to_service)
        else:
            non_critical_deps[dep.from_service].append((dep.to_service, dep.degradation_factor))

    # Timeline store: service name → list of FailureEvent
    timelines: dict[str, list[FailureEvent]] = {}

    for service in sorted_services:
        own_events = generate_failure_timeline(service, horizon_hours)

        # Accumulate critical dependency outage events
        all_events: list[FailureEvent] = list(own_events)
        for dep_name in critical_deps[service.name]:
            dep_timeline = timelines.get(dep_name, [])
            all_events.extend(dep_timeline)

        timelines[service.name] = all_events

    # Compute availability per service
    result: dict[str, float] = {}
    for service in sorted_services:
        all_events = timelines[service.name]
        downtime = _merge_and_sum(all_events, horizon_hours)
        availability = (horizon_hours - downtime) / horizon_hours

        # Apply non-critical degradation: when a non-critical dependency fails,
        # the service degrades by (1 - degradation_factor) of the dep's downtime.
        for dep_name, degradation_factor in non_critical_deps[service.name]:
            dep_downtime = _merge_and_sum(timelines.get(dep_name, []), horizon_hours)
            # Degradation: proportion of dep downtime applies a partial availability hit
            # The effective downtime added = dep_downtime * (1 - degradation_factor)
            extra_downtime = dep_downtime * (1.0 - degradation_factor)
            availability -= extra_downtime / horizon_hours

        availability = max(0.0, min(1.0, availability))
        result[service.name] = availability

    return result


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile of a sorted list (0 <= p <= 1)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = p * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _compute_downtime_contributions(
    per_run_downtimes: dict[str, list[float]],
    horizon_hours: float,
    num_runs: int,
) -> dict[str, float]:
    """Compute each service's fractional contribution to total system downtime.

    Args:
        per_run_downtimes: service name → list of per-run downtime hours.
        horizon_hours: Simulation window.
        num_runs: Number of runs performed.

    Returns:
        Dict mapping service name → fraction of total downtime (sums to ≤ 1).
    """
    mean_downtimes = {
        name: sum(vals) / max(len(vals), 1) for name, vals in per_run_downtimes.items()
    }
    total = sum(mean_downtimes.values())
    if total <= 0.0:
        # All services were fully available — distribute equally
        n = len(mean_downtimes)
        return {name: 1.0 / n if n > 0 else 0.0 for name in mean_downtimes}
    return {name: dt / total for name, dt in mean_downtimes.items()}


def _compute_budget_forecast(
    per_run_availabilities: list[float],
    target_sla: float,
    horizon_hours: float,
) -> PercentileResult:
    """Estimate when the error budget would be exhausted.

    Maps availability distributions to remaining error budget fractions,
    expressed as percentile distribution of "days until budget exhaustion".

    Args:
        per_run_availabilities: Per-run availability fractions for the target svc.
        target_sla: Target availability fraction.
        horizon_hours: Simulation window in hours.

    Returns:
        PercentileResult with p50/p75/p95 of remaining budget fraction (0-1).
    """
    if not per_run_availabilities:
        return PercentileResult(p50=1.0, p75=1.0, p95=1.0)

    error_budget_hours = (1.0 - target_sla) * horizon_hours
    if error_budget_hours <= 0.0:
        return PercentileResult(p50=0.0, p75=0.0, p95=0.0)

    # Remaining budget fraction per run
    remaining_fractions = []
    for avail in per_run_availabilities:
        actual_downtime = (1.0 - avail) * horizon_hours
        remaining = (error_budget_hours - actual_downtime) / error_budget_hours
        remaining_fractions.append(max(-1.0, min(1.0, remaining)))

    remaining_fractions.sort()

    return PercentileResult(
        p50=_percentile(remaining_fractions, 0.50),
        p75=_percentile(remaining_fractions, 0.75),
        p95=_percentile(remaining_fractions, 0.95),
    )


def _aggregate_results(
    services: Sequence[ServiceFailureModel],
    all_run_results: list[dict[str, float]],
    target_sla: float,
    horizon_hours: float,
    num_runs: int,
    horizon_days: int,
) -> SimulationResult:
    """Build a SimulationResult from all Monte Carlo run data.

    Args:
        services: Service models.
        all_run_results: List of per-run availability dicts.
        target_sla: Target availability fraction for the primary service.
        horizon_hours: Simulation window in hours.
        num_runs: Number of runs.
        horizon_days: Simulation window in days.

    Returns:
        Fully populated SimulationResult.
    """
    service_names = [s.name for s in services]

    # Collect per-service availability across all runs
    per_service_avails: dict[str, list[float]] = defaultdict(list)
    for run in all_run_results:
        for name in service_names:
            per_service_avails[name].append(run.get(name, 1.0))

    # Collect per-service downtime (hours) across all runs
    per_run_downtimes: dict[str, list[float]] = {
        name: [(1.0 - avail) * horizon_hours for avail in per_service_avails[name]]
        for name in service_names
    }

    # Identify the target service (last in topological order = most dependent)
    # Use the first service with the lowest mean availability, or first service.
    target_service = services[0].name if services else ""
    if len(services) > 1:
        # Prefer the service explicitly listed last (most downstream)
        target_service = services[-1].name

    target_service_avails = per_service_avails.get(target_service, [1.0])
    target_sla_val = target_sla

    # P(meeting SLA) for the target service
    p_meeting = sum(1 for a in target_service_avails if a >= target_sla_val) / max(
        len(target_service_avails), 1
    )

    # Compute contributions
    contributions = _compute_downtime_contributions(per_run_downtimes, horizon_hours, num_runs)

    # Build per-service results
    service_results: dict[str, ServiceSimulationResult] = {}
    for svc in services:
        name = svc.name
        avails = sorted(per_service_avails[name])
        p_svc = sum(1 for a in avails if a >= svc.availability_target) / max(len(avails), 1)

        service_results[name] = ServiceSimulationResult(
            name=name,
            target=svc.availability_target,
            p_meeting_sla=round(p_svc, 6),
            availability_p50=_percentile(avails, 0.50),
            availability_p95=_percentile(avails, 0.95),
            availability_p99=_percentile(avails, 0.99),
            downtime_contribution=contributions.get(name, 0.0),
            is_weakest_link=False,  # Set below
        )

    # Identify weakest link (lowest p_meeting_sla)
    weakest_name = min(service_results, key=lambda n: service_results[n].p_meeting_sla)
    service_results[weakest_name] = ServiceSimulationResult(
        **{**vars(service_results[weakest_name]), "is_weakest_link": True}  # type: ignore[arg-type]
    )

    # Error budget forecast for target service
    error_budget_forecast = _compute_budget_forecast(
        target_service_avails, target_sla_val, horizon_hours
    )

    # Determine exit code
    if p_meeting >= 0.80:
        exit_code = 0
    elif p_meeting >= 0.50:
        exit_code = 1
    else:
        exit_code = 2

    return SimulationResult(
        target_service=target_service,
        target_sla=target_sla_val,
        horizon_days=horizon_days,
        num_runs=num_runs,
        p_meeting_sla=round(p_meeting, 6),
        services=service_results,
        weakest_link=weakest_name,
        weakest_link_contribution=contributions.get(weakest_name, 0.0),
        error_budget_forecast=error_budget_forecast,
        what_if_results=[],
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# Public: run_simulation
# ---------------------------------------------------------------------------


def run_simulation(
    services: Sequence[ServiceFailureModel],
    dependencies: Sequence[DependencyModel],
    num_runs: int = 10000,
    horizon_days: int = 90,
    seed: int | None = None,
) -> SimulationResult:
    """Run N Monte Carlo iterations and return aggregated simulation results.

    Args:
        services: Service failure models to simulate.
        dependencies: Directed dependency edges between services.
        num_runs: Number of Monte Carlo iterations to perform (default 10000).
        horizon_days: Simulation time window in days (default 90).
        seed: Optional random seed for reproducibility.

    Returns:
        SimulationResult with per-service statistics, weakest link, and
        error budget forecast.

    Exit code logic (stored on result):
        0 — P(meeting SLA) >= 0.80 (SLA likely met)
        1 — P(meeting SLA) >= 0.50 (marginal)
        2 — P(meeting SLA) < 0.50 (SLA likely missed)
    """
    if seed is not None:
        random.seed(seed)

    horizon_hours = horizon_days * 24.0

    # Determine target SLA from the last (most downstream) service
    if not services:
        raise ValueError("At least one service is required for simulation.")

    # Use topological sort to identify a reasonable target service
    sorted_svcs = _topological_sort(list(services), list(dependencies))
    target_sla = sorted_svcs[-1].availability_target

    all_run_results: list[dict[str, float]] = []
    for _ in range(num_runs):
        run_result = simulate_run(services, dependencies, horizon_hours)
        all_run_results.append(run_result)

    return _aggregate_results(
        sorted_svcs,
        all_run_results,
        target_sla,
        horizon_hours,
        num_runs,
        horizon_days,
    )
