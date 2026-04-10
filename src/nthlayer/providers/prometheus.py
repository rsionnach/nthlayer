"""
Re-export shim — canonical source is nthlayer_common.providers.prometheus.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.prometheus import (  # noqa: F401
    DEFAULT_USER_AGENT,
    PrometheusProvider,
    PrometheusProviderError,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "PrometheusProviderError",
    "PrometheusProvider",
]
