"""
Topology serializers: JSON, Mermaid, and DOT output formats.

Pure functions that convert TopologyGraph to string output.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nthlayer.topology.models import TopologyGraph


def serialize_json(topology: TopologyGraph) -> str:
    """Serialize topology as Sitrep-compatible JSON."""
    return json.dumps(topology.to_dict(), indent=2)


def serialize_mermaid(topology: TopologyGraph) -> str:
    """
    Serialize topology as Mermaid flowchart.

    Uses graph LR layout with SLO labels on edges,
    Nord-themed classDef styles for tiers, and cylinder
    shape for datastores.
    """
    lines: list[str] = ["graph LR"]

    # Emit node definitions with shapes
    for node in topology.nodes:
        node_id = _mermaid_id(node.name)
        label = node.name
        if node.type in ("database",):
            # Cylinder shape for datastores
            lines.append(f"    {node_id}[({label})]")
        else:
            lines.append(f"    {node_id}[{label}]")

    lines.append("")

    # Emit edges with SLO labels
    for edge in topology.edges:
        src = _mermaid_id(edge.source)
        tgt = _mermaid_id(edge.target)
        label_parts: list[str] = []
        if edge.slo_contract:
            if edge.slo_contract.availability is not None:
                label_parts.append(f"avail: {edge.slo_contract.availability}")
            if edge.slo_contract.latency_p99 is not None:
                label_parts.append(f"p99: {edge.slo_contract.latency_p99}")
        if edge.critical:
            label_parts.append("CRITICAL")

        if label_parts:
            label = " | ".join(label_parts)
            lines.append(f"    {src} -->|{label}| {tgt}")
        else:
            lines.append(f"    {src} --> {tgt}")

    lines.append("")

    # Nord-themed classDef styles for tiers
    lines.append("    classDef critical fill:#BF616A,stroke:#2E3440,color:#ECEFF4")
    lines.append("    classDef high fill:#D08770,stroke:#2E3440,color:#ECEFF4")
    lines.append("    classDef standard fill:#5E81AC,stroke:#2E3440,color:#ECEFF4")
    lines.append("    classDef low fill:#A3BE8C,stroke:#2E3440,color:#ECEFF4")

    # Apply tier classes to nodes
    for node in topology.nodes:
        if node.tier:
            node_id = _mermaid_id(node.name)
            lines.append(f"    class {node_id} {node.tier}")

    return "\n".join(lines)


def serialize_dot(topology: TopologyGraph) -> str:
    """
    Serialize topology as Graphviz DOT digraph.

    Uses Nord palette for tier-colored nodes, shaped nodes
    (cylinder for database, hexagon for worker), and critical
    edges highlighted in red with penwidth=2.
    """
    # Nord palette mapped to tiers
    tier_colors = {
        "critical": "#BF616A",
        "high": "#D08770",
        "standard": "#5E81AC",
        "low": "#A3BE8C",
    }

    type_shapes = {
        "database": "cylinder",
        "worker": "hexagon",
        "batch": "hexagon",
        "queue": "parallelogram",
    }

    lines: list[str] = [
        "digraph topology {",
        "    rankdir=LR;",
        '    node [style=filled, fontname="sans-serif", fontcolor="#ECEFF4"];',
        '    edge [fontname="sans-serif", fontsize=10];',
        "",
    ]

    # Emit nodes
    for node in topology.nodes:
        node_id = _dot_id(node.name)
        attrs: list[str] = [f'label="{node.name}"']

        color = tier_colors.get(node.tier or "", "#4C566A")
        attrs.append(f'fillcolor="{color}"')

        shape = type_shapes.get(node.type or "", "box")
        attrs.append(f"shape={shape}")

        lines.append(f"    {node_id} [{', '.join(attrs)}];")

    lines.append("")

    # Emit edges
    for edge in topology.edges:
        src = _dot_id(edge.source)
        tgt = _dot_id(edge.target)
        edge_attrs: list[str] = []

        # Edge label with SLO contract
        label_parts: list[str] = []
        if edge.slo_contract:
            if edge.slo_contract.availability is not None:
                label_parts.append(f"avail: {edge.slo_contract.availability}")
            if edge.slo_contract.latency_p99 is not None:
                label_parts.append(f"p99: {edge.slo_contract.latency_p99}")
        if label_parts:
            edge_attrs.append(f'label="{", ".join(label_parts)}"')

        # Critical edges in red with thicker line
        if edge.critical:
            edge_attrs.append('color="#BF616A"')
            edge_attrs.append("penwidth=2")

        attr_str = f" [{', '.join(edge_attrs)}]" if edge_attrs else ""
        lines.append(f"    {src} -> {tgt}{attr_str};")

    lines.append("}")

    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    """Convert service name to valid Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name)


def _dot_id(name: str) -> str:
    """Convert service name to valid DOT node ID."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name)
