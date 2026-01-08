"""
CLI command for blast radius analysis.

Calculates the deployment risk for a service based on downstream dependents.

Commands:
    nthlayer blast-radius <service.yaml>           - Calculate deployment risk
    nthlayer blast-radius <service.yaml> --depth 3 - Limit transitive depth
    nthlayer blast-radius <service.yaml> --json    - Output as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header
from nthlayer.dependencies import (
    BlastRadiusResult,
    DependencyDiscovery,
    create_demo_discovery,
)
from nthlayer.dependencies.providers.prometheus import PrometheusDepProvider
from nthlayer.specs.parser import parse_service_file


def blast_radius_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    environment: Optional[str] = None,
    depth: int = 10,
    output_format: str = "table",
    demo: bool = False,
) -> int:
    """
    Calculate deployment blast radius for a service.

    Analyzes downstream dependents to assess deployment risk.

    Exit codes:
        0 - Low risk (0-2 dependents, no critical services)
        1 - Medium risk (3-5 dependents, or 1 critical service)
        2 - High/Critical risk (6+ dependents, or 2+ critical services)

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus server URL (or use env var)
        environment: Optional environment name
        depth: Maximum depth for transitive analysis
        output_format: Output format ("table" or "json")
        demo: If True, show demo output with sample data

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_blast_radius_output(service_file, depth, output_format)

    # Resolve Prometheus URL
    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    if not prom_url:
        error("No Prometheus URL provided")
        console.print()
        console.print(
            "[muted]Provide via --prometheus-url or NTHLAYER_PROMETHEUS_URL env var[/muted]"
        )
        return 2

    # Parse service file
    try:
        context, _resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    service_name = context.name or "unknown"
    tier = getattr(context, "tier", "standard") or "standard"

    # Create discovery with Prometheus provider
    username = os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

    provider = PrometheusDepProvider(
        url=prom_url,
        username=username,
        password=password,
    )

    discovery = DependencyDiscovery()
    discovery.add_provider(provider)
    discovery.set_tier(service_name, tier)

    # Build dependency graph
    try:
        graph = asyncio.run(discovery.build_graph([service_name]))
    except Exception as e:
        error(f"Failed to build dependency graph: {e}")
        return 2

    # Calculate blast radius
    result = discovery.calculate_blast_radius(
        service=service_name,
        graph=graph,
        max_depth=depth,
    )

    # Output results
    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        _print_blast_radius_table(result)

    # Return exit code based on risk
    return _risk_to_exit_code(result.risk_level)


def _risk_to_exit_code(risk_level: str) -> int:
    """Convert risk level to exit code."""
    if risk_level == "low":
        return 0
    if risk_level == "medium":
        return 1
    return 2  # high or critical


def _print_blast_radius_table(result: BlastRadiusResult) -> None:
    """Print blast radius as formatted output."""
    console.print()
    header(f"Blast Radius: {result.service}")
    console.print()

    # Risk assessment banner
    risk_colors = {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "red bold",
    }
    risk_icons = {
        "low": "✓",
        "medium": "⚠",
        "high": "✗",
        "critical": "✗✗",
    }
    color = risk_colors.get(result.risk_level, "white")
    icon = risk_icons.get(result.risk_level, "?")

    console.print(f"Risk Assessment: [{color}]{icon} {result.risk_level.upper()}[/]")
    console.print()

    # Impact summary
    console.print("[bold]Impact Summary:[/bold]")
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Label", style="muted")
    summary_table.add_column("Value")

    summary_table.add_row("Direct dependents:", f"{len(result.direct_downstream)} services")
    summary_table.add_row("Transitive dependents:", f"{len(result.transitive_downstream)} services")

    if result.critical_services_affected > 0:
        summary_table.add_row(
            "Critical services:",
            f"[red]{result.critical_services_affected} affected[/]",
        )
    else:
        summary_table.add_row("Critical services:", "[green]0 affected[/]")

    summary_table.add_row("Total services:", str(result.total_services_affected))

    console.print(summary_table)
    console.print()

    # Affected services table
    if result.direct_downstream or result.transitive_downstream:
        console.print("[bold]Affected Services (by depth):[/bold]")
        services_table = Table(show_header=True, header_style="bold")
        services_table.add_column("Service", style="cyan")
        services_table.add_column("Depth", justify="right")
        services_table.add_column("Tier")
        services_table.add_column("Impact", style="muted")

        # Direct dependencies (depth 1)
        for dep in result.direct_downstream:
            tier = "critical" if "critical" in str(dep.metadata) else "standard"
            tier_style = "red" if tier == "critical" else "white"
            services_table.add_row(
                dep.source.canonical_name,
                "1",
                f"[{tier_style}]{tier}[/]",
                "Direct dependency",
            )

        # Transitive dependencies
        for dep, dep_depth in result.transitive_downstream:
            # Skip if already shown as direct
            if dep_depth == 1:
                continue
            tier = "critical" if "critical" in str(dep.metadata) else "standard"
            tier_style = "red" if tier == "critical" else "white"
            via = f"Via {dep.target.canonical_name}"
            services_table.add_row(
                dep.source.canonical_name,
                str(dep_depth),
                f"[{tier_style}]{tier}[/]",
                via,
            )

        console.print(services_table)
        console.print()

    # Recommendation
    if result.recommendation:
        console.print(f"[bold]Recommendation:[/bold] {result.recommendation}")
        console.print()


def _demo_blast_radius_output(service_file: str, depth: int, output_format: str) -> int:
    """Show demo blast radius output."""
    discovery, graph = create_demo_discovery()

    # Calculate blast radius for payment-api
    result = discovery.calculate_blast_radius(
        service="payment-api",
        graph=graph,
        max_depth=depth,
    )

    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        _print_blast_radius_table(result)

    return _risk_to_exit_code(result.risk_level)


def register_blast_radius_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register blast-radius subcommand parser."""
    parser = subparsers.add_parser(
        "blast-radius",
        help="Calculate deployment blast radius",
    )
    parser.add_argument("service_file", help="Path to service YAML file")
    parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus server URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        help="Environment name (dev, staging, prod)",
    )
    parser.add_argument(
        "--depth",
        "-d",
        type=int,
        default=10,
        help="Maximum depth for transitive analysis (default: 10)",
    )
    parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_blast_radius_command(args: argparse.Namespace) -> int:
    """Handle blast-radius command from CLI args."""
    return blast_radius_command(
        service_file=args.service_file,
        prometheus_url=getattr(args, "prometheus_url", None),
        environment=getattr(args, "environment", None),
        depth=getattr(args, "depth", 10),
        output_format=getattr(args, "output_format", "table"),
        demo=getattr(args, "demo", False),
    )
