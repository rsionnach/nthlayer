"""
Dependency discovery and graph analysis.

Discovers service dependencies from various providers (Prometheus, etc.)
and builds a unified dependency graph for blast radius analysis.
"""

from nthlayer.dependencies.discovery import (
    DependencyDiscovery,
    DiscoveryError,
    DiscoveryResult,
    create_demo_discovery,
)
from nthlayer.dependencies.models import (
    BlastRadiusResult,
    DependencyDirection,
    DependencyGraph,
    DependencyType,
    DiscoveredDependency,
    ResolvedDependency,
)
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth

__all__ = [
    # Models
    "DependencyType",
    "DependencyDirection",
    "DiscoveredDependency",
    "ResolvedDependency",
    "DependencyGraph",
    "BlastRadiusResult",
    # Discovery
    "DependencyDiscovery",
    "DiscoveryResult",
    "DiscoveryError",
    "create_demo_discovery",
    # Providers
    "BaseDepProvider",
    "ProviderHealth",
]
