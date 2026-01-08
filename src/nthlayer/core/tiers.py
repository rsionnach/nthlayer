"""
Centralized tier definitions for NthLayer.

This module is the single source of truth for all tier-related configuration.
Service tiers define reliability expectations, SLO targets, and deployment gates.

Tiers:
- critical (Tier 1): Business-critical services requiring highest reliability
- standard (Tier 2): Standard services with moderate reliability requirements
- low (Tier 3): Low-priority services with relaxed reliability targets
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Tier(StrEnum):
    """Service tier levels."""

    CRITICAL = "critical"
    STANDARD = "standard"
    LOW = "low"


# Valid tier names (including legacy aliases)
VALID_TIERS: frozenset[str] = frozenset(
    {"critical", "standard", "low", "tier-1", "tier-2", "tier-3"}
)

# Canonical tier names
TIER_NAMES: tuple[str, ...] = ("critical", "standard", "low")


@dataclass(frozen=True)
class TierConfig:
    """Configuration for a service tier.

    Attributes:
        name: Tier name (critical, standard, low)
        display_name: Human-readable name
        description: Description of the tier
        availability_target: Target availability percentage (e.g., 99.95)
        latency_p99_ms: Target p99 latency in milliseconds
        error_budget_warning_pct: Warning threshold (% remaining)
        error_budget_blocking_pct: Blocking threshold (% remaining), None = advisory only
        pagerduty_urgency: PagerDuty alert urgency (high or low)
    """

    name: str
    display_name: str
    description: str
    availability_target: float
    latency_p99_ms: int
    error_budget_warning_pct: float
    error_budget_blocking_pct: float | None
    pagerduty_urgency: Literal["high", "low"]


# Tier configurations - single source of truth
TIER_CONFIGS: dict[str, TierConfig] = {
    "critical": TierConfig(
        name="critical",
        display_name="Tier 1 - Critical",
        description="Business-critical services requiring highest reliability",
        availability_target=99.95,
        latency_p99_ms=200,
        error_budget_warning_pct=20.0,
        error_budget_blocking_pct=10.0,
        pagerduty_urgency="high",
    ),
    "standard": TierConfig(
        name="standard",
        display_name="Tier 2 - Standard",
        description="Standard services with moderate reliability requirements",
        availability_target=99.9,
        latency_p99_ms=500,
        error_budget_warning_pct=20.0,
        error_budget_blocking_pct=None,  # Advisory only
        pagerduty_urgency="low",
    ),
    "low": TierConfig(
        name="low",
        display_name="Tier 3 - Low Priority",
        description="Low-priority services with relaxed reliability targets",
        availability_target=99.5,
        latency_p99_ms=1000,
        error_budget_warning_pct=30.0,
        error_budget_blocking_pct=None,  # Advisory only
        pagerduty_urgency="low",
    ),
}

# Legacy tier name mappings
_TIER_ALIASES: dict[str, str] = {
    "tier-1": "critical",
    "tier-2": "standard",
    "tier-3": "low",
}


def normalize_tier(tier: str) -> str:
    """Normalize tier name to canonical form.

    Args:
        tier: Tier name (may be alias like 'tier-1')

    Returns:
        Canonical tier name ('critical', 'standard', or 'low')

    Raises:
        ValueError: If tier name is invalid
    """
    tier_lower = tier.lower()
    if tier_lower in _TIER_ALIASES:
        return _TIER_ALIASES[tier_lower]
    if tier_lower in TIER_CONFIGS:
        return tier_lower
    raise ValueError(f"Invalid tier: {tier}. Valid tiers: {', '.join(TIER_NAMES)}")


def get_tier_config(tier: str) -> TierConfig:
    """Get configuration for a tier.

    Args:
        tier: Tier name (supports aliases like 'tier-1')

    Returns:
        TierConfig for the tier

    Raises:
        ValueError: If tier name is invalid
    """
    canonical = normalize_tier(tier)
    return TIER_CONFIGS[canonical]


def is_valid_tier(tier: str) -> bool:
    """Check if a tier name is valid.

    Args:
        tier: Tier name to check

    Returns:
        True if tier is valid (including aliases)
    """
    return tier.lower() in VALID_TIERS


def get_tier_thresholds(tier: str) -> dict[str, float | None]:
    """Get deployment gate thresholds for a tier.

    Args:
        tier: Tier name

    Returns:
        Dict with 'warning' and 'blocking' thresholds
    """
    config = get_tier_config(tier)
    return {
        "warning": config.error_budget_warning_pct,
        "blocking": config.error_budget_blocking_pct,
    }


def get_slo_targets(tier: str) -> dict[str, float]:
    """Get SLO targets for a tier.

    Args:
        tier: Tier name

    Returns:
        Dict with 'availability' and 'latency_ms' targets
    """
    config = get_tier_config(tier)
    return {
        "availability": config.availability_target,
        "latency_ms": config.latency_p99_ms,
    }
