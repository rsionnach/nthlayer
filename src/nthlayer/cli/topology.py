"""
CLI command for topology export.

Exports dependency graph in JSON, Mermaid, or DOT format
enriched with SLO contract data from reliability manifests.

Commands:
    nthlayer topology export <manifest>                  - Export as JSON
    nthlayer topology export <manifest> --format mermaid - Export as Mermaid
    nthlayer topology export <manifest> --format dot     - Export as DOT
    nthlayer topology export --demo                      - Demo with sample data
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

from nthlayer.cli.ux import console, error
from nthlayer.dependencies import DependencyDiscovery, create_demo_discovery
from nthlayer.dependencies.providers.prometheus import PrometheusDepProvider
from nthlayer.specs.loader import load_manifest
from nthlayer.topology.enrichment import build_topology
from nthlayer.topology.serializers import (
    serialize_dot,
    serialize_json,
    serialize_mermaid,
)


def topology_export_command(
    manifest_file: str | None = None,
    output_format: str = "json",
    output_file: Optional[str] = None,
    depth: Optional[int] = None,
    demo: bool = False,
    prometheus_url: Optional[str] = None,
) -> int:
    """
    Export service dependency topology.

    Args:
        manifest_file: Path to reliability manifest YAML
        output_format: Output format (json, mermaid, dot)
        output_file: Optional file path for output
        depth: Maximum depth from root service
        demo: If True, use demo data
        prometheus_url: Prometheus server URL

    Returns:
        Exit code (0 on success)
    """
    if demo:
        return _demo_topology_export(output_format, output_file, depth)

    if manifest_file is None:
        error("Manifest file is required (or use --demo)")
        return 2

    # Load manifest
    try:
        manifest = load_manifest(manifest_file)
    except Exception as e:
        error(f"Error loading manifest: {e}")
        return 2

    # Create discovery and add providers
    discovery = DependencyDiscovery()
    providers_added = 0

    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    if prom_url:
        username = os.environ.get("NTHLAYER_METRICS_USER")
        password = os.environ.get("NTHLAYER_METRICS_PASSWORD")
        prom_provider = PrometheusDepProvider(
            url=prom_url,
            username=username,
            password=password,
        )
        discovery.add_provider(prom_provider)
        providers_added += 1

    if providers_added == 0:
        error("No providers available")
        console.print()
        console.print(
            "[muted]Provide Prometheus URL via --prometheus-url"
            " or NTHLAYER_PROMETHEUS_URL[/muted]"
        )
        return 2

    # Build dependency graph
    try:
        graph = asyncio.run(discovery.build_graph([manifest.name]))
    except Exception as e:
        error(f"Failed to build dependency graph: {e}")
        return 2

    # Build enriched topology
    topology = build_topology(
        graph=graph,
        manifests=[manifest],
        max_depth=depth,
        root_service=manifest.name if depth is not None else None,
    )

    return _output_topology(topology, output_format, output_file)


def _demo_topology_export(
    output_format: str,
    output_file: Optional[str],
    depth: Optional[int],
) -> int:
    """Export topology using demo data."""
    _discovery, graph = create_demo_discovery()

    topology = build_topology(
        graph=graph,
        manifests=[],
        max_depth=depth,
        root_service="payment-api" if depth is not None else None,
    )

    return _output_topology(topology, output_format, output_file)


def _output_topology(
    topology: object,
    output_format: str,
    output_file: Optional[str],
) -> int:
    """Serialize and output topology."""
    from nthlayer.topology.models import TopologyGraph

    assert isinstance(topology, TopologyGraph)

    serializers = {
        "json": serialize_json,
        "mermaid": serialize_mermaid,
        "dot": serialize_dot,
    }

    serializer = serializers.get(output_format)
    if serializer is None:
        error(f"Unknown format: {output_format}")
        return 2

    output = serializer(topology)

    if output_file:
        with open(output_file, "w") as f:
            f.write(output)
            f.write("\n")
        console.print(f"[green]Wrote {output_format} output to {output_file}[/green]")
    else:
        # Use print() not console.print() — output is machine-readable
        # and may contain brackets that rich would interpret as markup
        print(output)

    return 0


def register_topology_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register topology subcommand parser with export sub-subcommand."""
    topology_parser = subparsers.add_parser(
        "topology",
        help="Dependency graph topology commands",
    )
    topology_subparsers = topology_parser.add_subparsers(
        dest="topology_command",
        metavar="subcommand",
    )

    export_parser = topology_subparsers.add_parser(
        "export",
        help="Export dependency topology",
    )
    export_parser.add_argument(
        "manifest_file",
        nargs="?",
        help="Path to reliability manifest YAML",
    )
    export_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["json", "mermaid", "dot"],
        default="json",
        help="Output format (default: json)",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        help="Write output to file instead of stdout",
    )
    export_parser.add_argument(
        "--depth",
        "-d",
        type=int,
        default=None,
        help="Maximum depth from root service",
    )
    export_parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo data for sample output",
    )
    export_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus server URL (or set NTHLAYER_PROMETHEUS_URL)",
    )


def handle_topology_command(args: argparse.Namespace) -> int:
    """Handle topology command from CLI args."""
    if getattr(args, "topology_command", None) != "export":
        error("Usage: nthlayer topology export [options]")
        return 2

    return topology_export_command(
        manifest_file=getattr(args, "manifest_file", None),
        output_format=getattr(args, "output_format", "json"),
        output_file=getattr(args, "output_file", None),
        depth=getattr(args, "depth", None),
        demo=getattr(args, "demo", False),
        prometheus_url=getattr(args, "prometheus_url", None),
    )
