"""
Portfolio data models.

Models for aggregating SLO health across all services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    """Overall health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


class InsightType(str, Enum):
    """Type of portfolio insight."""

    PROMOTION = "promotion"  # Service exceeds SLO, consider tier upgrade
    UNREALISTIC = "unrealistic"  # SLO never met, target too aggressive
    EXHAUSTION = "exhaustion"  # Approaching budget exhaustion
    NO_SLO = "no_slo"  # Service has no SLOs defined


@dataclass
class SLOHealth:
    """Health status of a single SLO."""

    name: str
    objective: float  # Target percentage (e.g., 99.95)
    window: str  # e.g., "30d"
    status: HealthStatus = HealthStatus.UNKNOWN
    current_value: float | None = None  # Actual SLI value if available
    budget_consumed_percent: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "objective": self.objective,
            "window": self.window,
            "status": self.status.value,
            "current_value": self.current_value,
            "budget_consumed_percent": self.budget_consumed_percent,
        }


@dataclass
class ServiceHealth:
    """Health status of a service's SLOs."""

    service: str
    tier: int
    team: str
    service_type: str
    slos: list[SLOHealth] = field(default_factory=list)
    overall_status: HealthStatus = HealthStatus.UNKNOWN

    def __post_init__(self) -> None:
        """Calculate overall status from SLOs."""
        if not self.slos:
            self.overall_status = HealthStatus.UNKNOWN
            return

        # Overall status is the worst of all SLOs
        status_priority = {
            HealthStatus.EXHAUSTED: 4,
            HealthStatus.CRITICAL: 3,
            HealthStatus.WARNING: 2,
            HealthStatus.UNKNOWN: 1,
            HealthStatus.HEALTHY: 0,
        }

        worst_status = HealthStatus.HEALTHY
        for slo in self.slos:
            if status_priority.get(slo.status, 0) > status_priority.get(worst_status, 0):
                worst_status = slo.status

        self.overall_status = worst_status

    @property
    def is_healthy(self) -> bool:
        """Check if service is meeting all SLOs."""
        return self.overall_status in (HealthStatus.HEALTHY, HealthStatus.UNKNOWN)

    @property
    def needs_attention(self) -> bool:
        """Check if service needs attention."""
        attention_statuses = (
            HealthStatus.WARNING,
            HealthStatus.CRITICAL,
            HealthStatus.EXHAUSTED,
        )
        return self.overall_status in attention_statuses

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "service": self.service,
            "tier": self.tier,
            "team": self.team,
            "type": self.service_type,
            "overall_status": self.overall_status.value,
            "slos": [slo.to_dict() for slo in self.slos],
        }


@dataclass
class TierHealth:
    """Health aggregation for a tier."""

    tier: int
    tier_name: str  # e.g., "Critical", "Standard", "Low"
    total_services: int
    healthy_services: int

    @property
    def health_percent(self) -> float:
        """Percentage of services meeting SLOs."""
        if self.total_services == 0:
            return 100.0
        return (self.healthy_services / self.total_services) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tier": self.tier,
            "tier_name": self.tier_name,
            "total_services": self.total_services,
            "healthy_services": self.healthy_services,
            "health_percent": round(self.health_percent, 1),
        }


@dataclass
class Insight:
    """Actionable insight about portfolio health."""

    type: InsightType
    service: str
    message: str
    severity: str = "info"  # info, warning, critical

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "service": self.service,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class PortfolioHealth:
    """Overall portfolio health aggregation."""

    timestamp: datetime
    total_services: int
    services_with_slos: int
    healthy_services: int
    by_tier: list[TierHealth] = field(default_factory=list)
    services: list[ServiceHealth] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    @property
    def org_health_percent(self) -> float:
        """Overall organization health percentage."""
        if self.services_with_slos == 0:
            return 100.0
        return (self.healthy_services / self.services_with_slos) * 100

    @property
    def total_slos(self) -> int:
        """Total number of SLOs across all services."""
        return sum(len(svc.slos) for svc in self.services)

    @property
    def services_needing_attention(self) -> list[ServiceHealth]:
        """Services that need attention (warning/critical/exhausted)."""
        return [svc for svc in self.services if svc.needs_attention]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "total_services": self.total_services,
                "services_with_slos": self.services_with_slos,
                "healthy_services": self.healthy_services,
                "org_health_percent": round(self.org_health_percent, 1),
                "total_slos": self.total_slos,
            },
            "by_tier": [tier.to_dict() for tier in self.by_tier],
            "services": [svc.to_dict() for svc in self.services],
            "insights": [insight.to_dict() for insight in self.insights],
        }

    def to_csv_rows(self) -> list[dict[str, Any]]:
        """Convert to flat rows for CSV export."""
        rows = []
        for svc in self.services:
            for slo in svc.slos:
                rows.append(
                    {
                        "service": svc.service,
                        "tier": svc.tier,
                        "team": svc.team,
                        "type": svc.service_type,
                        "slo_name": slo.name,
                        "objective": slo.objective,
                        "window": slo.window,
                        "status": slo.status.value,
                        "current_value": slo.current_value,
                        "budget_consumed_percent": slo.budget_consumed_percent,
                    }
                )
        return rows


# Tier name mapping
TIER_NAMES = {
    1: "Critical",
    2: "Standard",
    3: "Low",
}


def get_tier_name(tier: int) -> str:
    """Get human-readable tier name."""
    return TIER_NAMES.get(tier, f"Tier {tier}")
