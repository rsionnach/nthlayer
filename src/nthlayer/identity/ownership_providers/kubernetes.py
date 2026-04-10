"""
Re-export shim — canonical source is nthlayer_common.identity.ownership_providers.kubernetes.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.ownership_providers.kubernetes import (  # noqa: F401
    KubernetesOwnershipProvider,
)

__all__ = ["KubernetesOwnershipProvider"]
