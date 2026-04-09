"""
Re-export shim — canonical source is nthlayer_common.providers.mimir.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.mimir import (  # noqa: F401
    DEFAULT_USER_AGENT,
    MimirRulerError,
    MimirRulerProvider,
    RulerPushResult,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "MimirRulerError",
    "RulerPushResult",
    "MimirRulerProvider",
]
