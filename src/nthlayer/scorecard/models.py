"""
Scorecard data models.

Models for reliability scoring across services and teams.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ScoreBand(str, Enum):
    """Score classification bands."""

    EXCELLENT = "excellent"  # 90-100
    GOOD = "good"  # 75-89
    FAIR = "fair"  # 50-74
    POOR = "poor"  # 25-49
    CRITICAL = "critical"  # 0-24


@dataclass
class ScoreComponents:
    """Individual score components (0-100 each)."""

    slo_compliance: float  # 40% weight
    incident_score: float  # 30% weight
    deploy_success_rate: float  # 20% weight
    error_budget_remaining: float  # 10% weight

    # Raw data for transparency
    slos_met: int = 0
    slos_total: int = 0
    incident_count: int = 0
    deploys_successful: int = 0
    deploys_total: int = 0
    budget_percent_remaining: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slo_compliance": self.slo_compliance,
            "incident_score": self.incident_score,
            "deploy_success_rate": self.deploy_success_rate,
            "error_budget_remaining": self.error_budget_remaining,
            "raw": {
                "slos_met": self.slos_met,
                "slos_total": self.slos_total,
                "incident_count": self.incident_count,
                "deploys_successful": self.deploys_successful,
                "deploys_total": self.deploys_total,
                "budget_percent_remaining": self.budget_percent_remaining,
            },
        }


@dataclass
class ServiceScore:
    """Reliability score for a single service."""

    service: str
    tier: int
    team: str
    service_type: str

    score: float  # Weighted score 0-100
    band: ScoreBand  # Classification
    components: ScoreComponents  # Breakdown

    # Trend data
    score_30d_ago: float | None = None
    score_90d_ago: float | None = None
    trend_direction: str = "stable"  # improving, degrading, stable

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "service": self.service,
            "tier": self.tier,
            "team": self.team,
            "type": self.service_type,
            "score": self.score,
            "band": self.band.value,
            "components": self.components.to_dict(),
            "trend": {
                "score_30d_ago": self.score_30d_ago,
                "score_90d_ago": self.score_90d_ago,
                "direction": self.trend_direction,
            },
        }


@dataclass
class TeamScore:
    """Aggregated reliability score for a team."""

    team: str
    score: float  # Average weighted by tier
    band: ScoreBand
    service_count: int

    # Tier breakdown
    tier1_score: float | None = None
    tier2_score: float | None = None
    tier3_score: float | None = None

    # Trend
    score_30d_ago: float | None = None
    trend_direction: str = "stable"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "team": self.team,
            "score": self.score,
            "band": self.band.value,
            "service_count": self.service_count,
            "by_tier": {
                "tier1": self.tier1_score,
                "tier2": self.tier2_score,
                "tier3": self.tier3_score,
            },
            "trend": {
                "score_30d_ago": self.score_30d_ago,
                "direction": self.trend_direction,
            },
        }


@dataclass
class ScorecardReport:
    """Complete scorecard report."""

    timestamp: datetime
    period: str  # "30d" or "90d"

    # Organization level
    org_score: float
    org_band: ScoreBand

    # Aggregations
    services: list[ServiceScore] = field(default_factory=list)
    teams: list[TeamScore] = field(default_factory=list)

    # Rankings
    top_services: list[ServiceScore] = field(default_factory=list)
    bottom_services: list[ServiceScore] = field(default_factory=list)
    most_improved: list[ServiceScore] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "period": self.period,
            "summary": {
                "org_score": self.org_score,
                "org_band": self.org_band.value,
                "total_services": len(self.services),
                "total_teams": len(self.teams),
            },
            "services": [svc.to_dict() for svc in self.services],
            "teams": [team.to_dict() for team in self.teams],
            "rankings": {
                "top_services": [svc.to_dict() for svc in self.top_services],
                "bottom_services": [svc.to_dict() for svc in self.bottom_services],
                "most_improved": [svc.to_dict() for svc in self.most_improved],
            },
        }

    def to_csv_rows(self) -> list[dict[str, Any]]:
        """Convert to flat rows for CSV export."""
        rows = []
        for svc in self.services:
            c = svc.components
            rows.append(
                {
                    "service": svc.service,
                    "tier": svc.tier,
                    "team": svc.team,
                    "type": svc.service_type,
                    "score": svc.score,
                    "band": svc.band.value,
                    "slo_compliance": c.slo_compliance,
                    "incident_score": c.incident_score,
                    "deploy_success_rate": c.deploy_success_rate,
                    "error_budget_remaining": c.error_budget_remaining,
                    "slos_met": c.slos_met,
                    "slos_total": c.slos_total,
                    "incident_count": c.incident_count,
                    "deploys_successful": c.deploys_successful,
                    "deploys_total": c.deploys_total,
                    "budget_percent_remaining": c.budget_percent_remaining,
                    "trend_direction": svc.trend_direction,
                }
            )
        return rows
