"""
Deployment gate checks for error budget validation.

Provides advisory and blocking gates based on error budget health.
Supports custom thresholds via DeploymentGate resources and condition-based policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Any

import structlog

from nthlayer.core.tiers import TIER_CONFIGS

if TYPE_CHECKING:
    from nthlayer.policies.recorder import PolicyAuditRecorder
    from nthlayer.policies.repository import PolicyAuditRepository

logger = structlog.get_logger()


class GateResult(IntEnum):
    """
    Deployment gate exit codes.

    Following common CI/CD conventions:
    - 0 = Success/Approved
    - 1 = Warning (advisory, doesn't block)
    - 2 = Error (blocked)
    """

    APPROVED = 0
    WARNING = 1
    BLOCKED = 2


@dataclass
class GatePolicy:
    """
    Custom gate policy from DeploymentGate resource.

    Allows overriding default tier-based thresholds and adding conditions.
    """

    # Custom thresholds (override defaults)
    warning: float | None = None  # Warn when budget remaining < this %
    blocking: float | None = None  # Block when budget remaining < this %

    # Conditional policies
    conditions: list[dict[str, Any]] = field(default_factory=list)

    # Exceptions (teams that can bypass)
    exceptions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "GatePolicy":
        """Create GatePolicy from DeploymentGate resource spec."""
        thresholds = spec.get("thresholds", {})
        return cls(
            warning=thresholds.get("warning"),
            blocking=thresholds.get("blocking"),
            conditions=spec.get("conditions", []),
            exceptions=spec.get("exceptions", []),
        )


@dataclass
class DeploymentGateCheck:
    """Result of deployment gate check."""

    service: str
    tier: str
    result: GateResult

    # Error budget status
    budget_total_minutes: int
    budget_consumed_minutes: int
    budget_remaining_minutes: int
    budget_remaining_percentage: float

    # Thresholds
    warning_threshold: float
    blocking_threshold: float | None

    # Blast radius
    downstream_services: list[str]
    high_criticality_downstream: list[str]

    # Messages
    message: str
    recommendations: list[str]

    @property
    def is_approved(self) -> bool:
        """Check if deployment is approved."""
        return self.result == GateResult.APPROVED

    @property
    def is_warning(self) -> bool:
        """Check if deployment has warnings."""
        return self.result == GateResult.WARNING

    @property
    def is_blocked(self) -> bool:
        """Check if deployment is blocked."""
        return self.result == GateResult.BLOCKED


class DeploymentGate:
    """
    Checks if deployment should be allowed based on error budget.

    Supports:
    - Tier-based default thresholds
    - Custom thresholds via GatePolicy
    - Condition-based dynamic thresholds

    Default tier thresholds:
    - Critical: Block <10%, Warn <20%
    - Standard: Warn <20%, Advisory <30%
    - Low: Advisory only
    """

    # Default thresholds derived from centralized tier config
    THRESHOLDS: dict[str, dict[str, float | None]] = {
        tier: {
            "warning": config.error_budget_warning_pct,
            "blocking": config.error_budget_blocking_pct,
        }
        for tier, config in TIER_CONFIGS.items()
    }

    def __init__(
        self,
        policy: GatePolicy | None = None,
        audit_recorder: PolicyAuditRecorder | None = None,
        override_repository: PolicyAuditRepository | None = None,
    ):
        """
        Initialize gate with optional custom policy and audit recorder.

        Args:
            policy: Custom GatePolicy to override defaults
            audit_recorder: Optional recorder for policy audit logging
            override_repository: Optional repository for checking active overrides
        """
        self.policy = policy
        self.audit_recorder = audit_recorder
        self.override_repository = override_repository

    def check_deployment(
        self,
        service: str,
        tier: str,
        budget_total_minutes: int,
        budget_consumed_minutes: int,
        downstream_services: list[dict[str, Any]] | None = None,
        environment: str = "prod",
        team: str | None = None,
        now: datetime | None = None,
    ) -> DeploymentGateCheck:
        """
        Check if deployment should be allowed.

        Args:
            service: Service name
            tier: Service tier (critical, standard, low)
            budget_total_minutes: Total error budget
            budget_consumed_minutes: Consumed error budget
            downstream_services: List of downstream dependencies with criticality
            environment: Deployment environment (dev, staging, prod)
            team: Deploying team (for exception checks)
            now: Current datetime (for condition evaluation)

        Returns:
            DeploymentGateCheck with result and details
        """
        # Calculate remaining budget
        budget_remaining_minutes = budget_total_minutes - budget_consumed_minutes
        budget_remaining_pct = (
            (budget_remaining_minutes / budget_total_minutes * 100)
            if budget_total_minutes > 0
            else 100.0
        )

        # Calculate blast radius info
        downstream = downstream_services or []
        all_downstream = [d["name"] for d in downstream]
        high_crit_downstream = [
            d["name"] for d in downstream if d.get("criticality") in ["critical", "high"]
        ]

        # Get thresholds (custom policy > tier defaults)
        warning_threshold, blocking_threshold = self._get_thresholds(
            tier=tier,
            budget_remaining=budget_remaining_pct,
            environment=environment,
            downstream_count=len(all_downstream),
            high_criticality_downstream=len(high_crit_downstream),
            now=now,
        )

        # Check for team exceptions
        if self._is_excepted(team):
            # Team can bypass gate
            return DeploymentGateCheck(
                service=service,
                tier=tier,
                result=GateResult.APPROVED,
                budget_total_minutes=budget_total_minutes,
                budget_consumed_minutes=budget_consumed_minutes,
                budget_remaining_minutes=budget_remaining_minutes,
                budget_remaining_percentage=budget_remaining_pct,
                warning_threshold=warning_threshold,
                blocking_threshold=blocking_threshold,
                downstream_services=all_downstream,
                high_criticality_downstream=high_crit_downstream,
                message=f"✅ Deployment APPROVED: Team '{team}' has gate bypass",
                recommendations=["Team has exception - gate bypassed"],
            )

        # Determine gate result
        result = GateResult.APPROVED
        message = ""
        recommendations: list[str] = []

        if blocking_threshold and budget_remaining_pct < blocking_threshold:
            # BLOCKED
            result = GateResult.BLOCKED
            message = (
                f"⛔ Deployment BLOCKED: Error budget critically low "
                f"({budget_remaining_pct:.1f}% remaining, threshold: {blocking_threshold}%)"
            )
            recommendations.extend(
                [
                    "Wait for error budget to recover before deploying",
                    f"Current budget: {budget_remaining_minutes:.0f} minutes remaining",
                    "Consider if this deploy is absolutely necessary",
                    "Review recent incidents and their causes",
                ]
            )

        elif budget_remaining_pct < warning_threshold:
            # WARNING
            result = GateResult.WARNING
            message = (
                f"⚠️  Deployment WARNING: Error budget low "
                f"({budget_remaining_pct:.1f}% remaining, threshold: {warning_threshold}%)"
            )
            recommendations.extend(
                [
                    "Proceed with caution - error budget is low",
                    f"Budget remaining: {budget_remaining_minutes:.0f} minutes",
                    "Have rollback plan ready",
                    "Monitor closely after deployment",
                ]
            )

        else:
            # APPROVED
            result = GateResult.APPROVED
            message = (
                f"✅ Deployment APPROVED: Error budget healthy "
                f"({budget_remaining_pct:.1f}% remaining)"
            )
            recommendations.extend(
                [
                    f"Budget: {budget_remaining_minutes:.0f}/{budget_total_minutes:.0f} minutes",
                    "Continue monitoring post-deployment",
                ]
            )

        # Add blast radius to recommendations if significant
        if high_crit_downstream:
            recommendations.append(
                f"⚡ Blast radius: {len(high_crit_downstream)} high-criticality service(s) "
                f"potentially affected: {', '.join(high_crit_downstream)}"
            )
        elif all_downstream:
            recommendations.append(
                f"📊 {len(all_downstream)} downstream service(s) potentially affected"
            )

        return DeploymentGateCheck(
            service=service,
            tier=tier,
            result=result,
            budget_total_minutes=budget_total_minutes,
            budget_consumed_minutes=budget_consumed_minutes,
            budget_remaining_minutes=budget_remaining_minutes,
            budget_remaining_percentage=budget_remaining_pct,
            warning_threshold=warning_threshold,
            blocking_threshold=blocking_threshold,
            downstream_services=all_downstream,
            high_criticality_downstream=high_crit_downstream,
            message=message,
            recommendations=recommendations,
        )

    def _get_thresholds(
        self,
        tier: str,
        budget_remaining: float,
        environment: str,
        downstream_count: int,
        high_criticality_downstream: int,
        now: datetime | None = None,
    ) -> tuple[float, float | None]:
        """
        Get warning and blocking thresholds.

        Priority: condition match > custom policy > tier defaults

        Returns:
            Tuple of (warning_threshold, blocking_threshold)
        """
        # Start with tier defaults
        defaults = self.THRESHOLDS.get(tier, self.THRESHOLDS["standard"])
        warning = defaults.get("warning") or 20.0  # Fallback to standard threshold
        blocking = defaults.get("blocking")

        if not self.policy:
            return warning, blocking

        # Apply custom policy thresholds
        if self.policy.warning is not None:
            warning = self.policy.warning
        if self.policy.blocking is not None:
            blocking = self.policy.blocking

        # Check conditions for dynamic thresholds
        if self.policy.conditions:
            from nthlayer.policies.evaluator import ConditionEvaluator, PolicyContext

            context = PolicyContext(
                budget_remaining=budget_remaining,
                budget_consumed=100 - budget_remaining,
                tier=tier,
                environment=environment,
                downstream_count=downstream_count,
                high_criticality_downstream=high_criticality_downstream,
                now=now,
            )

            evaluator = ConditionEvaluator(context)
            matched, condition = evaluator.evaluate_all(self.policy.conditions)

            if matched and condition:
                # Condition matched - use its thresholds
                if "warning" in condition:
                    warning = condition["warning"]
                if "blocking" in condition:
                    blocking = condition["blocking"]

        return warning, blocking

    def _is_excepted(self, team: str | None) -> bool:
        """Check if team has an exception to bypass the gate."""
        if not team or not self.policy or not self.policy.exceptions:
            return False

        for exc in self.policy.exceptions:
            exc_team = exc.get("team")
            allow = exc.get("allow", "")

            if exc_team == team and allow == "always":
                return True

        return False

    async def check_deployment_with_audit(
        self,
        service: str,
        tier: str,
        budget_total_minutes: int,
        budget_consumed_minutes: int,
        downstream_services: list[dict[str, Any]] | None = None,
        environment: str = "prod",
        team: str | None = None,
        now: datetime | None = None,
        actor: str | None = None,
        deployment_id: str | None = None,
    ) -> DeploymentGateCheck:
        """
        Check deployment with audit recording and override checking.

        Wraps check_deployment() with:
        1. Override checking — downgrades BLOCKED → APPROVED if active override exists
        2. Audit recording — logs evaluation to PolicyAuditRecorder

        Both operations are fail-open: errors are logged but never block deployments.

        Args:
            service: Service name
            tier: Service tier (critical, standard, low)
            budget_total_minutes: Total error budget
            budget_consumed_minutes: Consumed error budget
            downstream_services: List of downstream dependencies with criticality
            environment: Deployment environment
            team: Deploying team
            now: Current datetime
            actor: Actor performing the deployment (for audit trail)
            deployment_id: Deployment identifier (for audit trail)

        Returns:
            DeploymentGateCheck with result and details
        """
        # Run the core gate check (sync)
        result = self.check_deployment(
            service=service,
            tier=tier,
            budget_total_minutes=budget_total_minutes,
            budget_consumed_minutes=budget_consumed_minutes,
            downstream_services=downstream_services,
            environment=environment,
            team=team,
            now=now,
        )

        # Check for active override before blocking
        if result.is_blocked and self.override_repository:
            result = await self._check_override(result, service)

        # Record audit trail
        if self.audit_recorder:
            await self._record_audit(result, environment, team, actor, deployment_id, now)

        return result

    async def _check_override(
        self, result: DeploymentGateCheck, service: str
    ) -> DeploymentGateCheck:
        """Check for active override and downgrade BLOCKED if found.

        Fail-open: override check errors are logged, original result returned.
        """
        try:
            override = await self.override_repository.get_active_override(  # type: ignore[union-attr]
                service, "deployment-gate"
            )
            if override:
                logger.info(
                    "override_applied",
                    service=service,
                    override_id=override.id,
                    approved_by=override.approved_by,
                )
                return DeploymentGateCheck(
                    service=result.service,
                    tier=result.tier,
                    result=GateResult.APPROVED,
                    budget_total_minutes=result.budget_total_minutes,
                    budget_consumed_minutes=result.budget_consumed_minutes,
                    budget_remaining_minutes=result.budget_remaining_minutes,
                    budget_remaining_percentage=result.budget_remaining_percentage,
                    warning_threshold=result.warning_threshold,
                    blocking_threshold=result.blocking_threshold,
                    downstream_services=result.downstream_services,
                    high_criticality_downstream=result.high_criticality_downstream,
                    message=(
                        f"✅ Deployment APPROVED: Active override by {override.approved_by}"
                        f" (reason: {override.reason})"
                    ),
                    recommendations=[
                        f"Override approved by: {override.approved_by}",
                        f"Reason: {override.reason}",
                        "Original result was BLOCKED — proceed with caution",
                    ],
                )
        except Exception:
            logger.warning(
                "override_check_failed",
                service=service,
                exc_info=True,
            )
        return result

    async def _record_audit(
        self,
        result: DeploymentGateCheck,
        environment: str,
        team: str | None,
        actor: str | None,
        deployment_id: str | None,
        now: datetime | None,
    ) -> None:
        """Record gate check to audit trail. Fail-open."""
        try:
            from nthlayer.policies.evaluator import PolicyContext as _PolicyContext

            context = _PolicyContext(
                budget_remaining=result.budget_remaining_percentage,
                budget_consumed=100 - result.budget_remaining_percentage,
                tier=result.tier,
                environment=environment,
                service=result.service,
                team=team or "",
                downstream_count=len(result.downstream_services),
                high_criticality_downstream=len(result.high_criticality_downstream),
                now=now,
            )
            await self.audit_recorder.record_gate_check(  # type: ignore[union-attr]
                gate_check=result,
                context=context,
                actor=actor,
                deployment_id=deployment_id,
            )
        except Exception:
            logger.warning(
                "audit_record_failed",
                service=result.service,
                exc_info=True,
            )

    def get_threshold_for_tier(self, tier: str) -> dict[str, float | None]:
        """Get default thresholds for a service tier."""
        return self.THRESHOLDS.get(tier, self.THRESHOLDS["standard"])
