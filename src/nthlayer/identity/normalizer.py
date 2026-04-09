"""
Re-export shim — canonical source is nthlayer_common.identity.normalizer.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.normalizer import (  # noqa: F401
    DEFAULT_RULES,
    PROVIDER_PATTERNS,
    NormalizationRule,
    extract_from_pattern,
    extract_service_name,
    normalize_service_name,
)

__all__ = [
    "NormalizationRule",
    "DEFAULT_RULES",
    "normalize_service_name",
    "extract_from_pattern",
    "PROVIDER_PATTERNS",
    "extract_service_name",
]
