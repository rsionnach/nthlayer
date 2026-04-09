"""
Re-export shim — canonical source is nthlayer_common.identity.ownership_providers.base.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.ownership_providers.base import (  # noqa: F401
    BaseOwnershipProvider,
    OwnershipProviderHealth,
)

__all__ = [
    "OwnershipProviderHealth",
    "BaseOwnershipProvider",
]
