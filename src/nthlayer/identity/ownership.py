"""
Re-export shim — canonical source is nthlayer_common.identity.ownership.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.ownership import (  # noqa: F401
    DEFAULT_CONFIDENCE,
    OwnershipAttribution,
    OwnershipResolver,
    OwnershipSignal,
    OwnershipSource,
    create_demo_attribution,
)

__all__ = [
    "OwnershipSource",
    "DEFAULT_CONFIDENCE",
    "OwnershipSignal",
    "OwnershipAttribution",
    "OwnershipResolver",
    "create_demo_attribution",
]
