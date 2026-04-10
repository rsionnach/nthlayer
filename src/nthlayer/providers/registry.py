"""
Re-export shim — canonical source is nthlayer_common.providers.registry.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.registry import (  # noqa: F401
    ProviderFactory,
    ProviderRegistry,
    ProviderSpec,
    create_provider,
    list_providers,
    provider_registry,
    register_provider,
)

__all__ = [
    "ProviderFactory",
    "ProviderSpec",
    "ProviderRegistry",
    "provider_registry",
    "register_provider",
    "create_provider",
    "list_providers",
]
