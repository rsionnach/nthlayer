"""
Dependency discovery providers.

Providers discover service dependencies from various sources
like Prometheus metrics, Kubernetes, Backstage, etc.
"""

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth

__all__ = [
    "BaseDepProvider",
    "ProviderHealth",
]
