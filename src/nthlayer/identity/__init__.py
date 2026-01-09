"""
Identity resolution for service name normalization.

Normalizes service names from different providers to canonical forms,
enabling cross-provider service identity matching.
"""

from nthlayer.identity.models import IdentityMatch, ServiceIdentity
from nthlayer.identity.normalizer import (
    DEFAULT_RULES,
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
