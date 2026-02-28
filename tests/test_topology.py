"""Tests for topology export: models, serializers, enrichment, and CLI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nthlayer.dependencies.models import (
    DependencyGraph,
    DependencyType,
    ResolvedDependency,
)
from nthlayer.identity import ServiceIdentity
from nthlayer.specs.manifest import Dependency, DependencySLO, ReliabilityManifest
from nthlayer.topology.enrichment import build_topology
from nthlayer.topology.models import (
    SLOContract,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
)
from nthlayer.topology.serializers import (
    serialize_dot,
    serialize_json,
    serialize_mermaid,
)

# ===========================================================================
# Model tests
# ===========================================================================


class TestSLOContract:
    def test_to_dict_full(self):
        contract = SLOContract(availability=0.999, latency_p99="200ms")
        d = contract.to_dict()
        assert d == {"availability": 0.999, "latency_p99": "200ms"}

    def test_to_dict_partial(self):
        contract = SLOContract(availability=0.99)
        d = contract.to_dict()
        assert d == {"availability": 0.99}
        assert "latency_p99" not in d

    def test_to_dict_empty(self):
        contract = SLOContract()
        assert contract.to_dict() == {}


class TestTopologyNode:
    def test_to_dict_minimal(self):
        node = TopologyNode(name="payment-api")
        d = node.to_dict()
        assert d == {"name": "payment-api"}

    def test_to_dict_full(self):
        node = TopologyNode(
            name="payment-api",
            tier="critical",
            type="api",
            team="payments",
            metadata={"region": "us-east-1"},
        )
        d = node.to_dict()
        assert d["name"] == "payment-api"
        assert d["tier"] == "critical"
        assert d["type"] == "api"
        assert d["team"] == "payments"
        assert d["metadata"] == {"region": "us-east-1"}


class TestTopologyEdge:
    def test_to_dict_minimal(self):
        edge = TopologyEdge(source="a", target="b", dep_type="service")
        d = edge.to_dict()
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["critical"] is False
        assert "slo_contract" not in d

    def test_to_dict_with_contract(self):
        edge = TopologyEdge(
            source="a",
            target="b",
            dep_type="service",
            slo_contract=SLOContract(availability=0.999),
            critical=True,
        )
        d = edge.to_dict()
        assert d["critical"] is True
        assert d["slo_contract"] == {"availability": 0.999}


class TestTopologyGraph:
    def test_to_dict_structure(self):
        graph = TopologyGraph(
            nodes=[TopologyNode(name="a")],
            edges=[TopologyEdge(source="a", target="b", dep_type="service")],
        )
        d = graph.to_dict()
        assert d["version"] == "1.0"
        assert d["stats"]["node_count"] == 1
        assert d["stats"]["edge_count"] == 1
        assert len(d["nodes"]) == 1
        assert len(d["edges"]) == 1
        assert "exported_at" in d


# ===========================================================================
# Serializer tests
# ===========================================================================


def _sample_topology() -> TopologyGraph:
    """Create a sample topology for serializer tests."""
    return TopologyGraph(
        nodes=[
            TopologyNode(name="payment-api", tier="critical", type="api"),
            TopologyNode(name="postgresql", tier="standard", type="database"),
            TopologyNode(name="order-worker", tier="standard", type="worker"),
        ],
        edges=[
            TopologyEdge(
                source="payment-api",
                target="postgresql",
                dep_type="datastore",
                slo_contract=SLOContract(availability=0.999, latency_p99="50ms"),
                critical=True,
            ),
            TopologyEdge(
                source="payment-api",
                target="order-worker",
                dep_type="service",
            ),
        ],
        exported_at=datetime(2026, 1, 1, 0, 0, 0),
    )


class TestSerializeJSON:
    def test_valid_json(self):
        output = serialize_json(_sample_topology())
        parsed = json.loads(output)
        assert parsed["version"] == "1.0"

    def test_contains_nodes_and_edges(self):
        output = serialize_json(_sample_topology())
        parsed = json.loads(output)
        assert len(parsed["nodes"]) == 3
        assert len(parsed["edges"]) == 2

    def test_slo_contract_in_edge(self):
        output = serialize_json(_sample_topology())
        parsed = json.loads(output)
        critical_edge = next(e for e in parsed["edges"] if e["critical"])
        assert critical_edge["slo_contract"]["availability"] == 0.999


class TestSerializeMermaid:
    def test_has_graph_lr(self):
        output = serialize_mermaid(_sample_topology())
        assert "graph LR" in output

    def test_has_nodes(self):
        output = serialize_mermaid(_sample_topology())
        assert "payment_api" in output
        assert "postgresql" in output

    def test_cylinder_shape_for_database(self):
        output = serialize_mermaid(_sample_topology())
        # Database nodes use cylinder shape: [(label)]
        assert "postgresql[(postgresql)]" in output

    def test_slo_labels_on_edges(self):
        output = serialize_mermaid(_sample_topology())
        assert "avail: 0.999" in output
        assert "p99: 50ms" in output

    def test_critical_label(self):
        output = serialize_mermaid(_sample_topology())
        assert "CRITICAL" in output

    def test_tier_classdef(self):
        output = serialize_mermaid(_sample_topology())
        assert "classDef critical" in output
        assert "classDef standard" in output

    def test_class_assignments(self):
        output = serialize_mermaid(_sample_topology())
        assert "class payment_api critical" in output


class TestSerializeDOT:
    def test_has_digraph(self):
        output = serialize_dot(_sample_topology())
        assert "digraph topology" in output

    def test_has_nodes(self):
        output = serialize_dot(_sample_topology())
        assert 'label="payment-api"' in output
        assert 'label="postgresql"' in output

    def test_cylinder_shape_for_database(self):
        output = serialize_dot(_sample_topology())
        assert "shape=cylinder" in output

    def test_hexagon_shape_for_worker(self):
        output = serialize_dot(_sample_topology())
        assert "shape=hexagon" in output

    def test_critical_edge_style(self):
        output = serialize_dot(_sample_topology())
        assert "#BF616A" in output
        assert "penwidth=2" in output

    def test_slo_label_on_edge(self):
        output = serialize_dot(_sample_topology())
        assert "avail: 0.999" in output

    def test_nord_colors(self):
        output = serialize_dot(_sample_topology())
        # Critical tier color
        assert "#BF616A" in output
        # Standard tier color
        assert "#5E81AC" in output


# ===========================================================================
# Enrichment tests
# ===========================================================================


def _build_test_graph() -> DependencyGraph:
    """Build a small DependencyGraph for enrichment tests."""
    graph = DependencyGraph()
    api = ServiceIdentity(canonical_name="payment-api")
    db = ServiceIdentity(canonical_name="postgresql")
    cache = ServiceIdentity(canonical_name="redis")

    graph.add_service(api)
    graph.add_service(db)
    graph.add_service(cache)

    graph.add_edge(
        ResolvedDependency(
            source=api,
            target=db,
            dep_type=DependencyType.DATASTORE,
            confidence=0.9,
            providers=["prometheus"],
        )
    )
    graph.add_edge(
        ResolvedDependency(
            source=api,
            target=cache,
            dep_type=DependencyType.DATASTORE,
            confidence=0.8,
            providers=["prometheus"],
        )
    )
    return graph


def _build_test_manifest() -> ReliabilityManifest:
    """Build a manifest with dependency SLO contracts."""
    return ReliabilityManifest(
        name="payment-api",
        team="payments",
        tier="critical",
        type="api",
        dependencies=[
            Dependency(
                name="postgresql",
                type="database",
                critical=True,
                slo=DependencySLO(availability=0.9999, latency_p99="50ms"),
            ),
            Dependency(
                name="redis",
                type="cache",
                critical=False,
            ),
        ],
    )


class TestBuildTopology:
    def test_basic_conversion(self):
        graph = _build_test_graph()
        topology = build_topology(graph)
        assert len(topology.nodes) == 3
        assert len(topology.edges) == 2
        assert topology.version == "1.0"

    def test_slo_contract_enrichment(self):
        graph = _build_test_graph()
        manifest = _build_test_manifest()
        topology = build_topology(graph, manifests=[manifest])

        # Find the postgresql edge
        pg_edge = next(e for e in topology.edges if e.target == "postgresql")
        assert pg_edge.critical is True
        assert pg_edge.slo_contract is not None
        assert pg_edge.slo_contract.availability == 0.9999
        assert pg_edge.slo_contract.latency_p99 == "50ms"

    def test_no_contract_for_unmatched_dep(self):
        graph = _build_test_graph()
        manifest = _build_test_manifest()
        topology = build_topology(graph, manifests=[manifest])

        redis_edge = next(e for e in topology.edges if e.target == "redis")
        assert redis_edge.slo_contract is None
        assert redis_edge.critical is False

    def test_node_metadata_from_manifest(self):
        graph = _build_test_graph()
        manifest = _build_test_manifest()
        topology = build_topology(graph, manifests=[manifest])

        api_node = next(n for n in topology.nodes if n.name == "payment-api")
        assert api_node.tier == "critical"
        assert api_node.type == "api"
        assert api_node.team == "payments"

    def test_depth_filtering(self):
        """Depth filtering limits edges to N hops from root."""
        graph = DependencyGraph()
        a = ServiceIdentity(canonical_name="a")
        b = ServiceIdentity(canonical_name="b")
        c = ServiceIdentity(canonical_name="c")
        d = ServiceIdentity(canonical_name="d")

        for svc in [a, b, c, d]:
            graph.add_service(svc)

        # Chain: a -> b -> c -> d
        for src, tgt in [(a, b), (b, c), (c, d)]:
            graph.add_edge(
                ResolvedDependency(
                    source=src,
                    target=tgt,
                    dep_type=DependencyType.SERVICE,
                    confidence=0.9,
                    providers=["test"],
                )
            )

        # Depth 1 from 'a': only a -> b reachable
        topology = build_topology(graph, max_depth=1, root_service="a")
        assert len(topology.edges) == 1
        assert topology.edges[0].source == "a"
        assert topology.edges[0].target == "b"

        # Depth 2 from 'a': a -> b -> c reachable
        topology = build_topology(graph, max_depth=2, root_service="a")
        assert len(topology.edges) == 2

    def test_without_manifests(self):
        graph = _build_test_graph()
        topology = build_topology(graph)

        # Nodes should have no tier/type/team without manifests
        for node in topology.nodes:
            assert node.tier is None
            assert node.type is None


# ===========================================================================
# CLI integration tests
# ===========================================================================


class TestTopologyCLI:
    def test_demo_json(self):
        from nthlayer.cli.topology import topology_export_command

        exit_code = topology_export_command(demo=True, output_format="json")
        assert exit_code == 0

    def test_demo_mermaid(self):
        from nthlayer.cli.topology import topology_export_command

        exit_code = topology_export_command(demo=True, output_format="mermaid")
        assert exit_code == 0

    def test_demo_dot(self):
        from nthlayer.cli.topology import topology_export_command

        exit_code = topology_export_command(demo=True, output_format="dot")
        assert exit_code == 0

    def test_demo_file_output(self, tmp_path):
        from nthlayer.cli.topology import topology_export_command

        output_file = str(tmp_path / "topology.dot")
        exit_code = topology_export_command(
            demo=True,
            output_format="dot",
            output_file=output_file,
        )
        assert exit_code == 0
        content = Path(output_file).read_text()
        assert "digraph topology" in content

    def test_no_manifest_no_demo_errors(self):
        from nthlayer.cli.topology import topology_export_command

        exit_code = topology_export_command(manifest_file=None, demo=False)
        assert exit_code == 2

    def test_handle_topology_command_no_subcommand(self):
        import argparse

        from nthlayer.cli.topology import handle_topology_command

        args = argparse.Namespace(topology_command=None)
        assert handle_topology_command(args) == 2

    def test_demo_depth_filtering(self):
        from nthlayer.cli.topology import topology_export_command

        exit_code = topology_export_command(
            demo=True,
            output_format="json",
            depth=1,
        )
        assert exit_code == 0
