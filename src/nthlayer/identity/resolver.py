"""
Re-export shim — canonical source is nthlayer_common.identity.resolver.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.resolver import IdentityResolver  # noqa: F401

__all__ = [
    "IdentityResolver",
]
