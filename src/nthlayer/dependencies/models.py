"""
Re-export shim — canonical source is nthlayer_common.dependency_models.

This shim maintains backward compatibility during the ecosystem migration.
All consumers within nthlayer can continue to import from nthlayer.dependencies.models.
"""

from nthlayer_common.dependency_models import (  # noqa: F401
    BlastRadiusResult,
    DependencyDirection,
    DependencyGraph,
    DependencyType,
    DiscoveredDependency,
    ResolvedDependency,
)

__all__ = [
    "DependencyType",
    "DependencyDirection",
    "DiscoveredDependency",
    "ResolvedDependency",
    "DependencyGraph",
    "BlastRadiusResult",
]
