"""
Re-export shim — canonical source is nthlayer_common.identity.models.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.models import (  # noqa: F401
    IdentityMatch,
    ServiceIdentity,
)

__all__ = [
    "ServiceIdentity",
    "IdentityMatch",
]
