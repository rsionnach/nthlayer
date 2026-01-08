"""
Data models for drift detection.

These models represent the results of drift analysis, including:
- Severity classifications
- Pattern types (gradual decline, step change, etc.)
- Metrics and projections
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class DriftSeverity(Enum):
    """Severity level of detected drift."""

    NONE = "none"  # No significant drift
    INFO = "info"  # Minor drift, informational
    WARN = "warn"  # Actionable drift, investigate
    CRITICAL = "critical"  # Severe drift, immediate action needed


class DriftPattern(Enum):
    """Classification of drift pattern type."""

    STABLE = "stable"  # No significant trend
    GRADUAL_DECLINE = "gradual_decline"  # Slow, steady degradation
    GRADUAL_IMPROVEMENT = "gradual_improvement"  # Slow recovery
    STEP_CHANGE_DOWN = "step_change_down"  # Sudden drop
    STEP_CHANGE_UP = "step_change_up"  # Sudden improvement
    SEASONAL = "seasonal"  # Recurring pattern
    VOLATILE = "volatile"  # High variance, no clear trend


@dataclass
class DriftMetrics:
    """Raw metrics from drift analysis."""

    slope_per_day: float  # Budget change per day (e.g., -0.001 = -0.1%/day)
    slope_per_week: float  # Budget change per week
    r_squared: float  # Goodness of fit (0-1, higher = more linear)
    current_budget: float  # Current error budget remaining (0-1)
    budget_at_window_start: float  # Budget at start of analysis window
    variance: float  # Variance in budget over window
    data_points: int  # Number of data points analyzed


@dataclass
class DriftProjection:
    """Future budget projection."""

    days_until_exhaustion: int | None  # None if not trending toward exhaustion
    projected_budget_30d: float  # Projected budget in 30 days
    projected_budget_60d: float  # Projected budget in 60 days
    projected_budget_90d: float  # Projected budget in 90 days
    confidence: float  # Confidence in projection (based on r_squared)


@dataclass
class DriftResult:
    """Complete drift analysis result for a service."""

    service_name: str
    tier: str
    slo_name: str  # e.g., "availability", "latency_p99"

    # Analysis metadata
    window: str  # e.g., "30d"
    analyzed_at: datetime
    data_start: datetime
    data_end: datetime

    # Core results
    metrics: DriftMetrics
    projection: DriftProjection
    pattern: DriftPattern
    severity: DriftSeverity

    # Actionable output
    summary: str  # Human-readable summary
    recommendation: str  # Suggested action

    # For CI/CD
    exit_code: int  # 0=ok, 1=warn, 2=critical

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "service": self.service_name,
            "tier": self.tier,
            "slo": self.slo_name,
            "window": self.window,
            "analyzed_at": self.analyzed_at.isoformat(),
            "data_start": self.data_start.isoformat(),
            "data_end": self.data_end.isoformat(),
            "severity": self.severity.value,
            "pattern": self.pattern.value,
            "metrics": {
                "slope_per_day": f"{self.metrics.slope_per_day:.6f}",
                "slope_per_week": f"{self.metrics.slope_per_week:.4f}",
                "slope_per_week_pct": f"{self.metrics.slope_per_week * 100:.2f}%",
                "current_budget": f"{self.metrics.current_budget:.4f}",
                "current_budget_pct": f"{self.metrics.current_budget * 100:.2f}%",
                "r_squared": f"{self.metrics.r_squared:.3f}",
                "variance": f"{self.metrics.variance:.6f}",
                "data_points": self.metrics.data_points,
            },
            "projection": {
                "days_until_exhaustion": self.projection.days_until_exhaustion,
                "budget_30d": f"{self.projection.projected_budget_30d:.4f}",
                "budget_60d": f"{self.projection.projected_budget_60d:.4f}",
                "budget_90d": f"{self.projection.projected_budget_90d:.4f}",
                "confidence": f"{self.projection.confidence:.2f}",
            },
            "summary": self.summary,
            "recommendation": self.recommendation,
            "exit_code": self.exit_code,
        }


# Tier-based default configurations for drift detection
DRIFT_DEFAULTS: dict[str, dict[str, Any]] = {
    "critical": {
        "enabled": True,
        "window": "30d",
        "thresholds": {"warn": "-0.2%/week", "critical": "-0.5%/week"},
        "projection": {
            "horizon": "90d",
            "exhaustion_warn": "30d",
            "exhaustion_critical": "14d",
        },
        "patterns": {
            "detect_step_change": True,
            "detect_seasonal": False,
            "step_change_threshold": 0.05,
        },
    },
    "standard": {
        "enabled": True,
        "window": "30d",
        "thresholds": {"warn": "-0.5%/week", "critical": "-1.0%/week"},
        "projection": {
            "horizon": "60d",
            "exhaustion_warn": "14d",
            "exhaustion_critical": "7d",
        },
        "patterns": {
            "detect_step_change": True,
            "detect_seasonal": False,
            "step_change_threshold": 0.05,
        },
    },
    "low": {
        "enabled": False,  # Opt-in for low-tier services
        "window": "14d",
        "thresholds": {"warn": "-1.0%/week", "critical": "-2.0%/week"},
        "projection": {
            "horizon": "30d",
            "exhaustion_warn": "7d",
            "exhaustion_critical": "3d",
        },
        "patterns": {
            "detect_step_change": True,
            "detect_seasonal": False,
            "step_change_threshold": 0.10,
        },
    },
}


def get_drift_defaults(tier: str) -> dict[str, Any]:
    """Get drift detection defaults for a given tier.

    Args:
        tier: Service tier (critical, standard, low)

    Returns:
        Default drift configuration for the tier
    """
    # Normalize tier name
    tier_lower = tier.lower()
    if tier_lower in DRIFT_DEFAULTS:
        return DRIFT_DEFAULTS[tier_lower]

    # Default to standard for unknown tiers
    return DRIFT_DEFAULTS["standard"]
