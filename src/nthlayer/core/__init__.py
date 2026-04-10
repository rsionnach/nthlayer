"""Core modules for NthLayer - centralized definitions and utilities."""

from nthlayer.core.errors import (
    BlockedError,
    ConfigurationError,
    ExitCode,
    NthLayerError,
    PolicyAuditError,
    ProviderError,
    ValidationError,
    WarningResult,
    exit_with_error,
    format_error_message,
    main_with_error_handling,
)

# Subset only — full tier API at nthlayer.core.tiers or nthlayer_common.tiers
from nthlayer.core.tiers import (
    TIER_NAMES,
    VALID_TIERS,
    Tier,
    TierConfig,
    get_tier_config,
)

__all__ = [
    # Errors
    "ExitCode",
    "NthLayerError",
    "ConfigurationError",
    "ProviderError",
    "ValidationError",
    "BlockedError",
    "PolicyAuditError",
    "WarningResult",
    "main_with_error_handling",
    "format_error_message",
    "exit_with_error",
    # Tiers
    "Tier",
    "TierConfig",
    "TIER_NAMES",
    "VALID_TIERS",
    "get_tier_config",
]
