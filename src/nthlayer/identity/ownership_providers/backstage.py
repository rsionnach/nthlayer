"""
Re-export shim — canonical source is nthlayer_common.identity.ownership_providers.backstage.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.ownership_providers.backstage import (  # noqa: F401
    BackstageOwnershipProvider,
)

__all__ = ["BackstageOwnershipProvider"]
