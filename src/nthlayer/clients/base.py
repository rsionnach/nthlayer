"""
Re-export shim — canonical source is nthlayer_common.clients.base.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.clients.base import (  # noqa: F401
    BaseHTTPClient,
    PermanentHTTPError,
    RetryableHTTPError,
    is_retryable_status,
)

__all__ = [
    "RetryableHTTPError",
    "PermanentHTTPError",
    "is_retryable_status",
    "BaseHTTPClient",
]
