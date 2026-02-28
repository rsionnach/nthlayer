"""
Topology-specific models for dependency graph export.

Wraps dependency graph data with SLO contract enrichment
for Sitrep agent consumption and visualization output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SLOContract:
    """SLO expectations on a dependency edge."""

    availability: float | None = None  # e.g., 0.999
    latency_p99: str | None = None  # e.g., "200ms"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result: dict[str, Any] = {}
        if self.availability is not None:
            result["availability"] = self.availability
        if self.latency_p99 is not None:
            result["latency_p99"] = self.latency_p99
        return result


@dataclass
class TopologyNode:
    """Enriched graph node for topology export."""

    name: str
    tier: str | None = None
    type: str | None = None
    team: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result: dict[str, Any] = {"name": self.name}
        if self.tier is not None:
            result["tier"] = self.tier
        if self.type is not None:
            result["type"] = self.type
        if self.team is not None:
            result["team"] = self.team
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class TopologyEdge:
    """Enriched edge with SLO contract for topology export."""

    source: str
    target: str
    dep_type: str  # service, datastore, queue, external, infra
    confidence: float = 0.5
    providers: list[str] = field(default_factory=list)
    slo_contract: SLOContract | None = None
    critical: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "dep_type": self.dep_type,
            "confidence": self.confidence,
            "providers": self.providers,
            "critical": self.critical,
        }
        if self.slo_contract:
            result["slo_contract"] = self.slo_contract.to_dict()
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class TopologyGraph:
    """Complete topology export model."""

    nodes: list[TopologyNode] = field(default_factory=list)
    edges: list[TopologyEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    exported_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "version": self.version,
            "exported_at": self.exported_at.isoformat(),
            "metadata": self.metadata,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            },
        }
