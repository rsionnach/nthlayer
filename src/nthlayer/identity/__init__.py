"""
Re-export shim — canonical source is nthlayer_common.identity.

This shim maintains backward compatibility during the ecosystem migration.
All identity and ownership symbols are now in nthlayer-common.
"""

from nthlayer.identity.models import IdentityMatch, ServiceIdentity
from nthlayer.identity.normalizer import (
    DEFAULT_RULES,
    PROVIDER_PATTERNS,
    NormalizationRule,
    extract_from_pattern,
    extract_service_name,
    normalize_service_name,
)
from nthlayer.identity.ownership import (
    DEFAULT_CONFIDENCE,
    OwnershipAttribution,
    OwnershipResolver,
    OwnershipSignal,
    OwnershipSource,
    create_demo_attribution,
)
from nthlayer.identity.resolver import IdentityResolver

__all__ = [
    # Models
    "ServiceIdentity",
    "IdentityMatch",
    # Normalizer
    "normalize_service_name",
    "extract_from_pattern",
    "extract_service_name",
    "NormalizationRule",
    "DEFAULT_RULES",
    "PROVIDER_PATTERNS",
    # Resolver
    "IdentityResolver",
    # Ownership
    "OwnershipSource",
    "OwnershipSignal",
    "OwnershipAttribution",
    "OwnershipResolver",
    "DEFAULT_CONFIDENCE",
    "create_demo_attribution",
]
