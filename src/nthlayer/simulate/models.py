"""
Data models for Monte Carlo SLO simulation.

These models represent service failure characteristics, simulation results,
and what-if scenario comparisons derived from OpenSRM manifests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceFailureModel:
    """Failure characteristics for a single service.

    Attributes:
        name: Service identifier (matches manifest service name).
        availability_target: Target availability as a fraction (e.g. 0.999).
        mtbf_hours: Mean Time Between Failures in hours.
        mttr_hours: Mean Time To Recovery in hours.
        mtbf_distribution: Probability distribution for inter-failure times.
        mttr_distribution: Probability distribution for recovery times.
        mtbf_shape: Shape parameter for the MTBF distribution.
        mttr_shape: Shape parameter (sigma) for the MTTR distribution.
    """

    name: str
    availability_target: float
    mtbf_hours: float
    mttr_hours: float
    mtbf_distribution: str = "exponential"
    mttr_distribution: str = "lognormal"
    mtbf_shape: float = 1.0
    mttr_shape: float = 0.5


@dataclass
class FailureEvent:
    """A single failure event on a service's timeline.

    Attributes:
        start_hour: Hour offset from simulation start when failure begins.
        duration: Duration of the failure in hours.
    """

    start_hour: float
    duration: float

    @property
    def end_hour(self) -> float:
        """Computed end time of the failure event in hours."""
        return self.start_hour + self.duration


@dataclass
class DependencyModel:
    """Directed dependency relationship between two services.

    Attributes:
        from_service: Upstream service (the one that depends on to_service).
        to_service: Downstream service (the dependency).
        critical: If True, failure of to_service causes full outage of from_service.
        degradation_factor: Availability multiplier applied when a non-critical
            dependency fails (default 0.99 — 1% degradation).
    """

    from_service: str
    to_service: str
    critical: bool
    degradation_factor: float = 0.99


@dataclass
class PercentileResult:
    """Percentile distribution of a simulated metric.

    Attributes:
        p50: 50th percentile value (median), or None if not computed.
        p75: 75th percentile value, or None if not computed.
        p95: 95th percentile value, or None if not computed.
    """

    p50: float | None = None
    p75: float | None = None
    p95: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict with rounded floats."""

        def _fmt(v: float | None) -> float | None:
            return round(v, 6) if v is not None else None

        return {
            "p50": _fmt(self.p50),
            "p75": _fmt(self.p75),
            "p95": _fmt(self.p95),
        }


@dataclass
class ServiceSimulationResult:
    """Simulation result for a single service.

    Attributes:
        name: Service identifier.
        target: Availability target as a fraction.
        p_meeting_sla: Probability (0–1) of meeting SLA over the horizon.
        availability_p50: Median simulated availability.
        availability_p95: 95th-percentile simulated availability.
        availability_p99: 99th-percentile simulated availability.
        downtime_contribution: Fraction of total system downtime attributable
            to this service.
        is_weakest_link: True if this service has the lowest p_meeting_sla.
    """

    name: str
    target: float
    p_meeting_sla: float
    availability_p50: float
    availability_p95: float
    availability_p99: float
    downtime_contribution: float
    is_weakest_link: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict with rounded floats."""
        return {
            "name": self.name,
            "target": round(self.target, 6),
            "p_meeting_sla": round(self.p_meeting_sla, 4),
            "availability_p50": round(self.availability_p50, 6),
            "availability_p95": round(self.availability_p95, 6),
            "availability_p99": round(self.availability_p99, 6),
            "downtime_contribution": round(self.downtime_contribution, 4),
            "is_weakest_link": self.is_weakest_link,
        }


@dataclass
class WhatIfResult:
    """Result of a what-if scenario comparison.

    Attributes:
        scenario: Human-readable description of the scenario change.
        base_p_meeting_sla: Baseline probability of meeting SLA.
        modified_p_meeting_sla: Modified (post-scenario) probability of meeting SLA.
        delta: Difference (modified − base).
        base_weakest_link: Service name of the weakest link in the baseline.
        modified_weakest_link: Service name of the weakest link after the change.
    """

    scenario: str
    base_p_meeting_sla: float
    modified_p_meeting_sla: float
    delta: float
    base_weakest_link: str
    modified_weakest_link: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict with rounded floats."""
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
    """Top-level result from a Monte Carlo SLO simulation run.

    Attributes:
        target_service: Name of the primary service being simulated.
        target_sla: SLA target as a fraction (e.g. 0.999).
        horizon_days: Simulation horizon in days.
        num_runs: Number of Monte Carlo iterations performed.
        p_meeting_sla: Fraction of runs where the SLA was met.
        services: Per-service results keyed by service name.
        weakest_link: Service with the lowest p_meeting_sla.
        weakest_link_contribution: Downtime contribution of the weakest link.
        error_budget_forecast: Percentile distribution of remaining error budget.
        what_if_results: List of what-if scenario comparison results.
        exit_code: 0 = SLA likely met, 1 = marginal, 2 = SLA likely missed.
    """

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
        """Serialize to JSON-safe dict with rounded floats."""
        return {
            "target_service": self.target_service,
            "target_sla": round(self.target_sla, 6),
            "horizon_days": self.horizon_days,
            "num_runs": self.num_runs,
            "p_meeting_sla": round(self.p_meeting_sla, 4),
            "services": {k: v.to_dict() for k, v in self.services.items()},
            "weakest_link": self.weakest_link,
            "weakest_link_contribution": round(self.weakest_link_contribution, 4),
            "error_budget_forecast": self.error_budget_forecast.to_dict(),
            "what_if_results": [r.to_dict() for r in self.what_if_results],
            "exit_code": self.exit_code,
        }


def derive_failure_model(
    name: str,
    availability_target: float,
    mttr_hours: float = 1.0,
) -> ServiceFailureModel:
    """Derive a ServiceFailureModel from an availability target and MTTR.

    Uses the steady-state availability equation:
        availability = MTBF / (MTBF + MTTR)

    Rearranging to solve for MTBF:
        MTBF = MTTR * availability / (1 - availability)

    Args:
        name: Service identifier.
        availability_target: Target availability as a fraction (e.g. 0.999).
        mttr_hours: Mean Time To Recovery in hours (default 1.0).

    Returns:
        A ServiceFailureModel with derived MTBF and default distribution params.
    """
    mtbf_hours = mttr_hours * availability_target / (1.0 - availability_target)
    return ServiceFailureModel(
        name=name,
        availability_target=availability_target,
        mtbf_hours=mtbf_hours,
        mttr_hours=mttr_hours,
    )
