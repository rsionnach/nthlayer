"""
Re-export shim — canonical source is nthlayer_common.clients.cortex.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.clients.cortex import CortexClient  # noqa: F401

__all__ = ["CortexClient"]
