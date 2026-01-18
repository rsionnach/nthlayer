"""
Reliability score calculator.

Calculates weighted reliability scores for services and teams.
"""

from __future__ import annotations

from nthlayer.scorecard.models import (
    ScoreComponents,
    ServiceScore,
    TeamScore,
    ScoreBand,
)
from nthlayer.portfolio import ServiceHealth, HealthStatus

# Weights for score calculation (must sum to 1.0)
WEIGHTS = {
    "slo_compliance": 0.40,
    "incident_score": 0.30,
    "deploy_success_rate": 0.20,
    "error_budget_remaining": 0.10,
}

# Tier weights for team aggregation
TIER_WEIGHTS = {
    1: 3.0,  # Critical services weighted 3x
    2: 2.0,  # Standard services weighted 2x
    3: 1.0,  # Low priority weighted 1x
}


class ScoreCalculator:
    """Calculates reliability scores for services and teams."""

    def __init__(
        self,
        prometheus_url: str | None = None,
        incident_source: str | None = None,  # Future: PagerDuty, etc.
        deployment_source: str | None = None,  # Future: ArgoCD, etc.
    ):
        """
        Initialize calculator.

        Args:
            prometheus_url: Optional Prometheus URL for live data
            incident_source: Future: Incident management integration
            deployment_source: Future: Deployment tracking integration
        """
        self.prometheus_url = prometheus_url
        self.incident_source = incident_source
        self.deployment_source = deployment_source

    def calculate_service_score(
        self,
        service_health: ServiceHealth,
        incident_count: int = 0,
        deploys_successful: int = 0,
        deploys_total: int = 0,
        budget_remaining_percent: float = 100.0,
    ) -> ServiceScore:
        """
        Calculate weighted reliability score for a service.

        Args:
            service_health: ServiceHealth from portfolio aggregator
            incident_count: Number of incidents in period (0 = best)
            deploys_successful: Number of successful deployments
            deploys_total: Total deployments attempted
            budget_remaining_percent: Error budget remaining (100 = full budget)

        Returns:
            ServiceScore with weighted score and breakdown
        """
        # Component 1: SLO Compliance (40%)
        slos_met = sum(
            1
            for s in service_health.slos
            if s.status in (HealthStatus.HEALTHY, HealthStatus.UNKNOWN)
        )
        slos_total = len(service_health.slos) or 1
        slo_compliance = (slos_met / slos_total) * 100

        # Component 2: Incident Score (30%)
        # Score decreases with more incidents: 100 -> 0 as incidents 0 -> 10+
        incident_score = max(0, 100 - (incident_count * 10))

        # Component 3: Deploy Success Rate (20%)
        if deploys_total > 0:
            deploy_success_rate = (deploys_successful / deploys_total) * 100
        else:
            deploy_success_rate = 100  # No deploys = no failures

        # Component 4: Error Budget Remaining (10%)
        error_budget_remaining = min(100, max(0, budget_remaining_percent))

        # Calculate weighted score
        score = (
            slo_compliance * WEIGHTS["slo_compliance"]
            + incident_score * WEIGHTS["incident_score"]
            + deploy_success_rate * WEIGHTS["deploy_success_rate"]
            + error_budget_remaining * WEIGHTS["error_budget_remaining"]
        )

        components = ScoreComponents(
            slo_compliance=round(slo_compliance, 1),
            incident_score=round(incident_score, 1),
            deploy_success_rate=round(deploy_success_rate, 1),
            error_budget_remaining=round(error_budget_remaining, 1),
            slos_met=slos_met,
            slos_total=slos_total,
            incident_count=incident_count,
            deploys_successful=deploys_successful,
            deploys_total=deploys_total,
            budget_percent_remaining=round(budget_remaining_percent, 1),
        )

        return ServiceScore(
            service=service_health.service,
            tier=service_health.tier,
            team=service_health.team,
            service_type=service_health.service_type,
            score=round(score, 1),
            band=self._score_to_band(score),
            components=components,
        )

    def calculate_team_score(
        self,
        team: str,
        service_scores: list[ServiceScore],
    ) -> TeamScore:
        """
        Calculate tier-weighted team score.

        Args:
            team: Team name
            service_scores: List of ServiceScore for this team

        Returns:
            TeamScore with tier-weighted average
        """
        if not service_scores:
            return TeamScore(team=team, score=0, band=ScoreBand.CRITICAL, service_count=0)

        # Group by tier
        by_tier: dict[int, list[ServiceScore]] = {}
        for svc in service_scores:
            tier = svc.tier
            if tier not in by_tier:
                by_tier[tier] = []
            by_tier[tier].append(svc)

        # Calculate tier averages
        tier_scores: dict[int, float] = {}
        for tier, svcs in by_tier.items():
            tier_scores[tier] = sum(s.score for s in svcs) / len(svcs)

        # Weighted average across tiers
        total_weight = sum(TIER_WEIGHTS.get(t, 1.0) for t in tier_scores.keys())
        weighted_sum = sum(tier_scores[t] * TIER_WEIGHTS.get(t, 1.0) for t in tier_scores.keys())
        team_score = weighted_sum / total_weight if total_weight > 0 else 0

        return TeamScore(
            team=team,
            score=round(team_score, 1),
            band=self._score_to_band(team_score),
            service_count=len(service_scores),
            tier1_score=round(tier_scores[1], 1) if 1 in tier_scores else None,
            tier2_score=round(tier_scores[2], 1) if 2 in tier_scores else None,
            tier3_score=round(tier_scores[3], 1) if 3 in tier_scores else None,
        )

    def calculate_org_score(
        self,
        service_scores: list[ServiceScore],
    ) -> float:
        """
        Calculate organization-wide score (tier-weighted).

        Args:
            service_scores: All service scores

        Returns:
            Organization score (0-100)
        """
        if not service_scores:
            return 0.0

        total_weight = sum(TIER_WEIGHTS.get(s.tier, 1.0) for s in service_scores)
        weighted_sum = sum(s.score * TIER_WEIGHTS.get(s.tier, 1.0) for s in service_scores)

        return round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0

    def _score_to_band(self, score: float) -> ScoreBand:
        """Convert numeric score to band classification."""
        if score >= 90:
            return ScoreBand.EXCELLENT
        elif score >= 75:
            return ScoreBand.GOOD
        elif score >= 50:
            return ScoreBand.FAIR
        elif score >= 25:
            return ScoreBand.POOR
        else:
            return ScoreBand.CRITICAL

    def score_to_band(self, score: float) -> ScoreBand:
        """Public method to convert numeric score to band classification."""
        return self._score_to_band(score)
