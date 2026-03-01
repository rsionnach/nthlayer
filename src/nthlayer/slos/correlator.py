"""
Deployment correlation engine.

Correlates deployments with error budget burns to identify which deploys
caused reliability issues.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from nthlayer.slos.deployment import Deployment
from nthlayer.slos.models import SLO
from nthlayer.slos.storage import SLORepository

if TYPE_CHECKING:
    from nthlayer.dependencies.models import DependencyGraph

logger = structlog.get_logger()


# Confidence thresholds
HIGH_CONFIDENCE = 0.7
MEDIUM_CONFIDENCE = 0.5
LOW_CONFIDENCE = 0.3
BLOCKING_CONFIDENCE = 0.8


@dataclass
class CorrelationWindow:
    """Time window configuration for correlation analysis."""

    before_minutes: int = 30  # Look 30 min before deploy
    after_minutes: int = 120  # Look 2 hours after deploy
    history_lookback_hours: int = 168  # 7 days for history scoring


@dataclass
class CorrelationResult:
    """Result of correlation analysis."""

    deployment_id: str
    service: str
    burn_minutes: float
    confidence: float
    method: str
    details: dict[str, Any]

    @property
    def confidence_label(self) -> str:
        """Get human-readable confidence label."""
        if self.confidence >= HIGH_CONFIDENCE:
            return "HIGH"
        elif self.confidence >= MEDIUM_CONFIDENCE:
            return "MEDIUM"
        elif self.confidence >= LOW_CONFIDENCE:
            return "LOW"
        else:
            return "NONE"

    @property
    def confidence_emoji(self) -> str:
        """Get emoji for confidence level."""
        if self.confidence >= HIGH_CONFIDENCE:
            return "🔴"
        elif self.confidence >= MEDIUM_CONFIDENCE:
            return "🟡"
        else:
            return "✅"


class DeploymentCorrelator:
    """Correlates deployments with error budget burns."""

    def __init__(
        self,
        repository: SLORepository,
        window: CorrelationWindow | None = None,
    ) -> None:
        self.repository = repository
        self.window = window or CorrelationWindow()

    async def correlate_deployment(
        self,
        deployment: Deployment,
        slo: SLO,
        dependency_graph: DependencyGraph | None = None,
        downstream_services: list[str] | None = None,
    ) -> CorrelationResult:
        """
        Correlate a single deployment with error budget burns for an SLO.

        Uses 5-factor weighted scoring:
        - burn_rate_score (0.35): Spike in burn rate after deploy
        - proximity_score (0.25): Time proximity (exponential decay)
        - magnitude_score (0.15): Absolute burn amount
        - dependency_score (0.15): Relationship between deploying and affected service
        - history_score (0.10): Historical correlation pattern for service

        Args:
            deployment: Deployment to analyze
            slo: SLO to check against
            dependency_graph: Optional dependency graph for relationship scoring
            downstream_services: Optional list of downstream service names from YAML

        Returns:
            Correlation result with confidence score
        """
        logger.info(
            "correlating_deployment",
            deployment_id=deployment.id,
            service=deployment.service,
            slo_id=slo.id,
        )

        # Get burn rates before and after deployment
        before_start = deployment.deployed_at - timedelta(minutes=self.window.before_minutes)
        before_end = deployment.deployed_at
        after_start = deployment.deployed_at
        after_end = deployment.deployed_at + timedelta(minutes=self.window.after_minutes)

        # Query burn rates
        before_burn_rate = await self.repository.get_burn_rate_window(
            slo_id=slo.id,
            start_time=before_start,
            end_time=before_end,
        )

        after_burn_rate = await self.repository.get_burn_rate_window(
            slo_id=slo.id,
            start_time=after_start,
            end_time=after_end,
        )

        # Calculate total burn in after window
        burn_minutes = after_burn_rate * self.window.after_minutes

        # Factor 1: Burn rate spike
        burn_rate_score = self._calculate_burn_rate_score(
            before_burn_rate,
            after_burn_rate,
        )

        # Factor 2: Time proximity (exponential decay)
        proximity_score = self._calculate_proximity_score(
            deployment.deployed_at,
            deployment.deployed_at,  # No per-minute burn timestamps yet
        )

        # Factor 3: Magnitude
        magnitude_score = self._calculate_magnitude_score(burn_minutes)

        # Factor 4: Dependency relationship
        dependency_score = self._calculate_dependency_score(
            deploying_service=deployment.service,
            affected_service=slo.service,
            dependency_graph=dependency_graph,
            downstream_services=downstream_services,
        )

        # Factor 5: Historical pattern
        history_score = await self._calculate_history_score(deployment.service)

        # Overall confidence (5-factor weighted average)
        confidence = (
            0.35 * burn_rate_score
            + 0.25 * proximity_score
            + 0.15 * magnitude_score
            + 0.15 * dependency_score
            + 0.10 * history_score
        )

        result = CorrelationResult(
            deployment_id=deployment.id,
            service=deployment.service,
            burn_minutes=burn_minutes,
            confidence=confidence,
            method="time_window_analysis",
            details={
                "before_burn_rate": before_burn_rate,
                "after_burn_rate": after_burn_rate,
                "burn_rate_score": burn_rate_score,
                "proximity_score": proximity_score,
                "magnitude_score": magnitude_score,
                "dependency_score": dependency_score,
                "history_score": history_score,
                "window_before_minutes": self.window.before_minutes,
                "window_after_minutes": self.window.after_minutes,
            },
        )

        logger.info(
            "correlation_complete",
            deployment_id=deployment.id,
            confidence=confidence,
            confidence_label=result.confidence_label,
            burn_minutes=burn_minutes,
        )

        # Update deployment with correlation data
        if confidence >= LOW_CONFIDENCE:
            await self.repository.update_deployment_correlation(
                deployment_id=deployment.id,
                burn_minutes=burn_minutes,
                confidence=confidence,
            )

        return result

    async def correlate_service(
        self,
        service: str,
        lookback_hours: int = 24,
    ) -> list[CorrelationResult]:
        """
        Correlate all recent deployments for a service.

        Args:
            service: Service name
            lookback_hours: How far back to analyze

        Returns:
            List of correlation results sorted by confidence
        """
        logger.info(
            "correlating_service",
            service=service,
            lookback_hours=lookback_hours,
        )

        # Get recent deployments
        deployments = await self.repository.get_recent_deployments(
            service=service,
            hours=lookback_hours,
        )

        if not deployments:
            logger.warning("no_deployments_found", service=service)
            return []

        # Get SLOs for service
        slos = await self.repository.get_slos_by_service(service)

        if not slos:
            logger.warning("no_slos_found", service=service)
            return []

        # Correlate each deployment with each SLO
        results = []
        for deployment in deployments:
            for slo in slos:
                try:
                    result = await self.correlate_deployment(deployment, slo)
                    if result.confidence >= LOW_CONFIDENCE:
                        results.append(result)
                except Exception as exc:
                    logger.error(
                        "correlation_failed",
                        deployment_id=deployment.id,
                        slo_id=slo.id,
                        error=str(exc),
                    )

        # Sort by confidence (highest first)
        results.sort(key=lambda r: r.confidence, reverse=True)

        logger.info(
            "correlation_complete",
            service=service,
            total_results=len(results),
            high_confidence=sum(1 for r in results if r.confidence >= HIGH_CONFIDENCE),
        )

        return results

    def _calculate_proximity_score(
        self,
        deployed_at: datetime,
        burn_detected_at: datetime,
    ) -> float:
        """
        Calculate time proximity score using exponential decay.

        Half-life ~30 minutes: score = exp(-minutes_elapsed / 30).

        Args:
            deployed_at: When the deployment happened
            burn_detected_at: When the burn was detected

        Returns:
            Score from 0.0-1.0
        """
        elapsed = abs((burn_detected_at - deployed_at).total_seconds()) / 60.0
        return math.exp(-elapsed / 30.0)

    def _calculate_dependency_score(
        self,
        deploying_service: str,
        affected_service: str,
        dependency_graph: DependencyGraph | None = None,
        downstream_services: list[str] | None = None,
    ) -> float:
        """
        Calculate dependency relationship score.

        - Same service → 1.0
        - Direct upstream in graph (depth 1) → 1.0
        - Transitive upstream (depth 2+) → 0.4
        - Listed in YAML downstream_services (no graph) → 0.6
        - No relationship found → 0.0

        Args:
            deploying_service: Service being deployed
            affected_service: Service whose SLO is affected
            dependency_graph: Optional dependency graph
            downstream_services: Optional YAML-declared downstream services

        Returns:
            Score from 0.0-1.0
        """
        if deploying_service == affected_service:
            return 1.0

        if dependency_graph is not None:
            # Check if deploying_service is upstream of affected_service
            # (affected_service depends on deploying_service)
            upstream_deps = dependency_graph.get_upstream(affected_service)
            for dep in upstream_deps:
                if dep.target.canonical_name == deploying_service:
                    return 1.0  # Direct upstream

            # Check transitive upstream
            transitive = dependency_graph.get_transitive_upstream(affected_service)
            for dep, depth in transitive:
                if dep.target.canonical_name == deploying_service and depth >= 2:
                    return 0.4

        # Fallback to YAML downstream list
        if downstream_services and affected_service in downstream_services:
            return 0.6

        return 0.0

    async def _calculate_history_score(self, service: str) -> float:
        """
        Calculate historical correlation score.

        Queries recent deployments and checks how many had medium+ correlation.
        Repeat offenders score higher.

        Args:
            service: Service name

        Returns:
            Score from 0.0-1.0. Returns 0.0 on DB error (fail-open).
        """
        try:
            deployments = await self.repository.get_recent_deployments(
                service=service,
                hours=self.window.history_lookback_hours,
            )

            if not deployments:
                return 0.0

            correlated_count = sum(
                1
                for d in deployments
                if d.correlation_confidence is not None
                and d.correlation_confidence >= MEDIUM_CONFIDENCE
            )

            return min(correlated_count / len(deployments), 1.0)
        except Exception:
            logger.warning(
                "history_score_failed",
                service=service,
                exc_info=True,
            )
            return 0.0

    def _calculate_burn_rate_score(
        self,
        before_rate: float,
        after_rate: float,
    ) -> float:
        """
        Calculate burn rate change score.

        Higher spike = higher score.

        Args:
            before_rate: Burn rate per minute before deploy
            after_rate: Burn rate per minute after deploy

        Returns:
            Score from 0.0-1.0
        """
        if before_rate == 0:
            # No baseline, use absolute after rate
            # If after rate is significant, assume correlation
            return min(after_rate / 0.1, 1.0)  # 0.1 min/min = high burn

        # Calculate spike ratio
        spike_ratio = after_rate / before_rate

        # 5x spike or more = 1.0 score
        score = min(spike_ratio / 5.0, 1.0)

        return score

    def _calculate_magnitude_score(self, burn_minutes: float) -> float:
        """
        Calculate magnitude score based on absolute burn amount.

        Larger burns = higher confidence (rules out noise).

        Args:
            burn_minutes: Total minutes burned

        Returns:
            Score from 0.0-1.0
        """
        # 10+ minutes = 1.0 score
        score = min(burn_minutes / 10.0, 1.0)

        return score
