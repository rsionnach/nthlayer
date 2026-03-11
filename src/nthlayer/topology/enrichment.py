"""
Topology enrichment: converts DependencyGraph to TopologyGraph.

Matches manifest dependency entries to graph edges, attaching
SLO contracts and service metadata for export.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from nthlayer.topology.models import (
    SLOContract,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
)

if TYPE_CHECKING:
    from nthlayer.dependencies.models import DependencyGraph
    from nthlayer.specs.manifest import ReliabilityManifest


def build_topology(
    graph: DependencyGraph,
    manifests: list[ReliabilityManifest] | None = None,
    max_depth: int | None = None,
    root_service: str | None = None,
) -> TopologyGraph:
    """
    Convert a DependencyGraph to an enriched TopologyGraph.

    Args:
        graph: Source dependency graph from discovery
        manifests: Optional reliability manifests for SLO contract enrichment
        max_depth: If set with root_service, limit edges to N hops from root
        root_service: Root service for depth filtering

    Returns:
        TopologyGraph ready for serialization
    """
    manifests = manifests or []

    # Index manifests by service name for fast lookup
    manifest_by_name: dict[str, ReliabilityManifest] = {}
    for m in manifests:
        manifest_by_name[m.name] = m

    # Build nodes from graph services
    nodes: list[TopologyNode] = []
    for name, identity in graph.services.items():
        manifest = manifest_by_name.get(name)
        node = TopologyNode(
            name=name,
            tier=manifest.tier if manifest else None,
            type=manifest.type if manifest else None,
            team=manifest.team if manifest else None,
        )
        # Copy identity attributes as metadata
        if identity.attributes:
            node.metadata = dict(identity.attributes)
        nodes.append(node)

    # Build edges from graph, enriching with manifest dependency data
    edges: list[TopologyEdge] = []
    for resolved in graph.edges:
        source_name = resolved.source.canonical_name
        target_name = resolved.target.canonical_name

        # Look up SLO contract from source manifest's dependencies
        slo_contract = None
        critical = False
        source_manifest = manifest_by_name.get(source_name)
        if source_manifest:
            for dep in source_manifest.dependencies:
                if dep.name == target_name:
                    critical = dep.critical
                    if dep.slo:
                        slo_contract = SLOContract(
                            availability=dep.slo.availability,
                            latency_p99=dep.slo.latency_p99,
                        )
                    break

        edges.append(
            TopologyEdge(
                source=source_name,
                target=target_name,
                dep_type=resolved.dep_type.value,
                confidence=resolved.confidence,
                providers=list(resolved.providers),
                slo_contract=slo_contract,
                critical=critical,
                metadata=dict(resolved.metadata),
            )
        )

    # Apply depth filtering if requested
    if max_depth is not None and root_service is not None:
        edges = _filter_by_depth(edges, root_service, max_depth)
        # Keep only nodes that appear in filtered edges
        edge_names = set()
        for e in edges:
            edge_names.add(e.source)
            edge_names.add(e.target)
        edge_names.add(root_service)
        nodes = [n for n in nodes if n.name in edge_names]

    topology = TopologyGraph(
        nodes=nodes,
        edges=edges,
        metadata={
            "providers_used": list(graph.providers_used),
        },
    )

    return topology


def _filter_by_depth(
    edges: list[TopologyEdge],
    root: str,
    max_depth: int,
) -> list[TopologyEdge]:
    """Limit edges to N hops from root service via BFS."""
    # Build adjacency list (both directions since edges are directional)
    neighbors: dict[str, list[str]] = {}
    for e in edges:
        neighbors.setdefault(e.source, []).append(e.target)
        neighbors.setdefault(e.target, []).append(e.source)

    # BFS to find reachable nodes within max_depth
    reachable: set[str] = {root}
    queue: deque[tuple[str, int]] = deque([(root, 0)])

    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in neighbors.get(node, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append((neighbor, depth + 1))

    # Keep only edges where both endpoints are reachable
    return [e for e in edges if e.source in reachable and e.target in reachable]
