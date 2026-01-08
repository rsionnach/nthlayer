"""
Dependency graph models.

Data models for discovered dependencies, resolved dependencies,
and the dependency graph used for blast radius analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nthlayer.identity import ServiceIdentity


class DependencyType(Enum):
    """Classification of dependency relationships."""

    SERVICE = "service"  # Service-to-service call
    DATASTORE = "datastore"  # Database, cache, storage
    QUEUE = "queue"  # Message queue, event stream
    EXTERNAL = "external"  # Third-party API
    INFRASTRUCTURE = "infra"  # Internal infra (config, secrets)


class DependencyDirection(Enum):
    """Direction of dependency relationship."""

    UPSTREAM = "upstream"  # Services this service calls
    DOWNSTREAM = "downstream"  # Services that call this service


@dataclass
class DiscoveredDependency:
    """A dependency discovered from a provider."""

    source_service: str  # Service that has the dependency
    target_service: str  # Service being depended on
    provider: str  # Provider that discovered this

    dep_type: DependencyType = DependencyType.SERVICE
    confidence: float = 0.5  # 0.0 - 1.0

    # Provider-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Discovery timestamp
    discovered_at: datetime = field(default_factory=datetime.utcnow)

    # Raw identifiers before resolution
    raw_source: str | None = None
    raw_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_service": self.source_service,
            "target_service": self.target_service,
            "provider": self.provider,
            "dep_type": self.dep_type.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "discovered_at": self.discovered_at.isoformat(),
            "raw_source": self.raw_source,
            "raw_target": self.raw_target,
        }


@dataclass
class ResolvedDependency:
    """A dependency with resolved canonical identities."""

    source: ServiceIdentity
    target: ServiceIdentity
    dep_type: DependencyType

    # Aggregated confidence from all providers
    confidence: float

    # All providers that reported this dependency
    providers: list[str] = field(default_factory=list)

    # Combined metadata from all providers
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source": self.source.canonical_name,
            "target": self.target.canonical_name,
            "dep_type": self.dep_type.value,
            "confidence": self.confidence,
            "providers": self.providers,
            "metadata": self.metadata,
        }


@dataclass
class DependencyGraph:
    """Complete dependency graph for analysis."""

    services: dict[str, ServiceIdentity] = field(default_factory=dict)
    edges: list[ResolvedDependency] = field(default_factory=list)

    # Graph metadata
    built_at: datetime = field(default_factory=datetime.utcnow)
    providers_used: list[str] = field(default_factory=list)

    def add_service(self, identity: ServiceIdentity) -> None:
        """Add a service to the graph."""
        self.services[identity.canonical_name] = identity

    def add_edge(self, dependency: ResolvedDependency) -> None:
        """Add a dependency edge to the graph."""
        # Ensure both services are in the graph
        if dependency.source.canonical_name not in self.services:
            self.services[dependency.source.canonical_name] = dependency.source
        if dependency.target.canonical_name not in self.services:
            self.services[dependency.target.canonical_name] = dependency.target

        # Check for duplicate edges
        for existing in self.edges:
            if (
                existing.source.canonical_name == dependency.source.canonical_name
                and existing.target.canonical_name == dependency.target.canonical_name
                and existing.dep_type == dependency.dep_type
            ):
                # Merge providers and update confidence
                existing.providers = list(set(existing.providers + dependency.providers))
                existing.confidence = max(existing.confidence, dependency.confidence)
                existing.metadata.update(dependency.metadata)
                return

        self.edges.append(dependency)

    def get_upstream(self, service: str) -> list[ResolvedDependency]:
        """Get all services this service depends on (calls)."""
        return [e for e in self.edges if e.source.canonical_name == service]

    def get_downstream(self, service: str) -> list[ResolvedDependency]:
        """Get all services that depend on (call) this service."""
        return [e for e in self.edges if e.target.canonical_name == service]

    def get_transitive_upstream(
        self,
        service: str,
        max_depth: int = 10,
    ) -> list[tuple[ResolvedDependency, int]]:
        """
        Get all transitive dependencies (what this service depends on) with depth.

        Args:
            service: Service canonical name
            max_depth: Maximum traversal depth

        Returns:
            List of (dependency, depth) tuples
        """
        result: list[tuple[ResolvedDependency, int]] = []
        visited: set[str] = set()

        def traverse(svc: str, depth: int) -> None:
            if depth > max_depth or svc in visited:
                return
            visited.add(svc)

            for dep in self.get_upstream(svc):
                result.append((dep, depth))
                traverse(dep.target.canonical_name, depth + 1)

        traverse(service, 1)
        return result

    def get_transitive_downstream(
        self,
        service: str,
        max_depth: int = 10,
    ) -> list[tuple[ResolvedDependency, int]]:
        """
        Get all services transitively depending on this service with depth.

        Args:
            service: Service canonical name
            max_depth: Maximum traversal depth

        Returns:
            List of (dependency, depth) tuples
        """
        result: list[tuple[ResolvedDependency, int]] = []
        visited: set[str] = set()

        def traverse(svc: str, depth: int) -> None:
            if depth > max_depth or svc in visited:
                return
            visited.add(svc)

            for dep in self.get_downstream(svc):
                result.append((dep, depth))
                traverse(dep.source.canonical_name, depth + 1)

        traverse(service, 1)
        return result

    def get_service_count(self) -> int:
        """Get total number of services in the graph."""
        return len(self.services)

    def get_edge_count(self) -> int:
        """Get total number of dependency edges."""
        return len(self.edges)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "services": [s.to_dict() for s in self.services.values()],
            "edges": [e.to_dict() for e in self.edges],
            "built_at": self.built_at.isoformat(),
            "providers_used": self.providers_used,
            "stats": {
                "service_count": self.get_service_count(),
                "edge_count": self.get_edge_count(),
            },
        }


@dataclass
class BlastRadiusResult:
    """Result of blast radius analysis for a service."""

    service: str
    tier: str | None = None

    # Direct and transitive impact
    direct_downstream: list[ResolvedDependency] = field(default_factory=list)
    transitive_downstream: list[tuple[ResolvedDependency, int]] = field(default_factory=list)

    # Risk assessment
    risk_level: str = "low"  # low, medium, high, critical
    critical_services_affected: int = 0
    total_services_affected: int = 0

    # Recommendation
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "service": self.service,
            "tier": self.tier,
            "risk_level": self.risk_level,
            "direct_downstream_count": len(self.direct_downstream),
            "transitive_downstream_count": len(self.transitive_downstream),
            "critical_services_affected": self.critical_services_affected,
            "total_services_affected": self.total_services_affected,
            "recommendation": self.recommendation,
            "direct_downstream": [d.to_dict() for d in self.direct_downstream],
            "transitive_downstream": [
                {"dependency": d.to_dict(), "depth": depth}
                for d, depth in self.transitive_downstream
            ],
        }
