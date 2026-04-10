"""
Re-export shim — canonical source is nthlayer_common.tiers.

This shim maintains backward compatibility during the ecosystem migration.
All consumers within nthlayer can continue to import from nthlayer.core.tiers.
"""

from nthlayer_common.tiers import (  # noqa: F401
    TIER_CONFIGS,
    TIER_NAMES,
    VALID_TIERS,
    Tier,
    TierConfig,
    get_slo_targets,
    get_tier_config,
    get_tier_thresholds,
    is_valid_tier,
    normalize_tier,
)

__all__ = [
    "Tier",
    "TierConfig",
    "TIER_CONFIGS",
    "TIER_NAMES",
    "VALID_TIERS",
    "normalize_tier",
    "get_tier_config",
    "is_valid_tier",
    "get_tier_thresholds",
    "get_slo_targets",
]
