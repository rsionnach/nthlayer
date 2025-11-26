"""
Deployment gate checks for error budget validation.

Provides advisory and blocking gates based on error budget health.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


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
    
    Tier-based thresholds:
    - Critical: Block <10%, Warn <20%
    - Standard: Warn <20%, Advisory <30%
    - Low: Advisory only
    """
    
    # Default thresholds (percentage)
    THRESHOLDS = {
        "critical": {"warning": 20.0, "blocking": 10.0},
        "standard": {"warning": 20.0, "blocking": None},
        "low": {"warning": 30.0, "blocking": None},
    }
    
    def check_deployment(
        self,
        service: str,
        tier: str,
        budget_total_minutes: int,
        budget_consumed_minutes: int,
        downstream_services: list[dict[str, Any]] | None = None,
    ) -> DeploymentGateCheck:
        """
        Check if deployment should be allowed.
        
        Args:
            service: Service name
            tier: Service tier (critical, standard, low)
            budget_total_minutes: Total error budget
            budget_consumed_minutes: Consumed error budget
            downstream_services: List of downstream dependencies with criticality
        
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
        
        # Get thresholds for tier
        thresholds = self.THRESHOLDS.get(tier, self.THRESHOLDS["standard"])
        warning_threshold = thresholds["warning"]
        blocking_threshold = thresholds["blocking"]
        
        # Determine gate result
        result = GateResult.APPROVED
        message = ""
        recommendations = []
        
        if blocking_threshold and budget_remaining_pct < blocking_threshold:
            # BLOCKED
            result = GateResult.BLOCKED
            message = (
                f"⛔ Deployment BLOCKED: Error budget critically low "
                f"({budget_remaining_pct:.1f}% remaining, threshold: {blocking_threshold}%)"
            )
            recommendations.extend([
                "Wait for error budget to recover before deploying",
                f"Current budget will recover: {budget_remaining_minutes:.0f} minutes remaining",
                "Consider if this deploy is absolutely necessary",
                "Review recent incidents and their causes",
            ])
        
        elif budget_remaining_pct < warning_threshold:
            # WARNING
            result = GateResult.WARNING
            message = (
                f"⚠️  Deployment WARNING: Error budget low "
                f"({budget_remaining_pct:.1f}% remaining, threshold: {warning_threshold}%)"
            )
            recommendations.extend([
                "Proceed with caution - error budget is low",
                f"Budget remaining: {budget_remaining_minutes:.0f} minutes",
                "Have rollback plan ready",
                "Monitor closely after deployment",
            ])
        
        else:
            # APPROVED
            result = GateResult.APPROVED
            message = (
                f"✅ Deployment APPROVED: Error budget healthy "
                f"({budget_remaining_pct:.1f}% remaining)"
            )
            recommendations.extend([
                f"Budget remaining: {budget_remaining_minutes:.0f} minutes of {budget_total_minutes:.0f} minutes",
                "Continue monitoring post-deployment",
            ])
        
        # Calculate blast radius
        downstream = downstream_services or []
        all_downstream = [d["name"] for d in downstream]
        high_crit_downstream = [
            d["name"]
            for d in downstream
            if d.get("criticality") in ["critical", "high"]
        ]
        
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
    
    def get_threshold_for_tier(self, tier: str) -> dict[str, float | None]:
        """Get thresholds for a service tier."""
        return self.THRESHOLDS.get(tier, self.THRESHOLDS["standard"])
