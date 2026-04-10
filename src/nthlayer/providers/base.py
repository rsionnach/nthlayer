"""
Re-export shim — canonical source is nthlayer_common.providers.base.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.base import (  # noqa: F401
    PlanChange,
    PlanResult,
    Provider,
    ProviderHealth,
    ProviderResource,
    ProviderResourceSchema,
)

__all__ = [
    "ProviderResourceSchema",
    "PlanChange",
    "PlanResult",
    "ProviderHealth",
    "ProviderResource",
    "Provider",
]
