"""
CLI command for dependency discovery.

Shows service dependencies discovered from Prometheus metrics.

Commands:
    nthlayer deps <service.yaml>              - Show all dependencies
    nthlayer deps <service.yaml> --upstream   - Show what this service calls
    nthlayer deps <service.yaml> --downstream - Show what calls this service
    nthlayer deps <service.yaml> --json       - Output as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any, Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header
from nthlayer.dependencies import (
    DependencyDiscovery,
    DependencyType,
    DiscoveryResult,
    ResolvedDependency,
    create_demo_discovery,
)
from nthlayer.dependencies.providers.prometheus import PrometheusDepProvider
from nthlayer.specs.parser import parse_service_file


def deps_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    environment: Optional[str] = None,
    direction: str = "both",
    output_format: str = "table",
    demo: bool = False,
) -> int:
    """
    Show dependencies for a service.

    Discovers upstream and downstream dependencies from Prometheus metrics.

    Exit codes:
        0 - Success
        1 - Partial success (some providers failed)
        2 - Error

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus server URL (or use env var)
        environment: Optional environment name
        direction: "upstream", "downstream", or "both"
        output_format: Output format ("table" or "json")
        demo: If True, show demo output with sample data

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_deps_output(service_file, direction, output_format)

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

    # Run discovery
    try:
        result = asyncio.run(discovery.discover(service_name))
    except Exception as e:
        error(f"Dependency discovery failed: {e}")
        return 2

    # Output results
    if output_format == "json":
        console.print_json(data=_result_to_dict(result, direction))
    else:
        _print_deps_table(result, direction)

    # Return code based on errors
    if result.errors:
        return 1
    return 0


def _result_to_dict(result: DiscoveryResult, direction: str) -> dict[str, Any]:
    """Convert discovery result to dict for JSON output."""
    data: dict[str, Any] = {
        "service": result.service,
        "providers_queried": result.providers_queried,
    }

    if direction in ("upstream", "both"):
        data["upstream"] = [_dep_to_dict(d) for d in result.upstream]

    if direction in ("downstream", "both"):
        data["downstream"] = [_dep_to_dict(d) for d in result.downstream]

    if result.errors:
        data["errors"] = result.errors

    return data


def _dep_to_dict(dep: ResolvedDependency) -> dict[str, Any]:
    """Convert dependency to dict."""
    return {
        "source": dep.source.canonical_name,
        "target": dep.target.canonical_name,
        "type": dep.dep_type.value,
        "confidence": dep.confidence,
        "providers": dep.providers,
    }


def _print_deps_table(result: DiscoveryResult, direction: str) -> None:
    """Print dependencies as formatted tables."""
    console.print()
    header(f"Dependencies: {result.service}")
    console.print()

    # Upstream dependencies (what this service calls)
    if direction in ("upstream", "both"):
        console.print("[bold]Upstream[/bold] [muted](services this calls):[/muted]")
        if result.upstream:
            _print_dep_table(result.upstream, show_target=True)
        else:
            console.print("[muted]  No upstream dependencies discovered[/muted]")
        console.print()

    # Downstream dependencies (what calls this service)
    if direction in ("downstream", "both"):
        console.print("[bold]Downstream[/bold] [muted](services that call this):[/muted]")
        if result.downstream:
            _print_dep_table(result.downstream, show_target=False)
        else:
            console.print("[muted]  No downstream dependencies discovered[/muted]")
        console.print()

    # Provider info
    console.print(f"[muted]Providers queried: {', '.join(result.providers_queried)}[/muted]")

    # Errors
    if result.errors:
        console.print()
        for provider, err in result.errors.items():
            console.print(f"[yellow]Warning:[/yellow] {provider}: {err}")


def _print_dep_table(deps: list[ResolvedDependency], show_target: bool = True) -> None:
    """Print a dependency table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Service", style="cyan")
    table.add_column("Type")
    table.add_column("Confidence", justify="right")
    table.add_column("Provider", style="muted")

    # Type styling
    type_styles = {
        DependencyType.SERVICE: "blue",
        DependencyType.DATASTORE: "green",
        DependencyType.QUEUE: "magenta",
        DependencyType.EXTERNAL: "yellow",
        DependencyType.INFRASTRUCTURE: "cyan",
    }

    for dep in sorted(deps, key=lambda d: d.confidence, reverse=True):
        service = dep.target.canonical_name if show_target else dep.source.canonical_name
        type_style = type_styles.get(dep.dep_type, "white")
        confidence_pct = f"{dep.confidence * 100:.0f}%"

        # Color confidence based on value
        if dep.confidence >= 0.9:
            conf_style = "green"
        elif dep.confidence >= 0.7:
            conf_style = "yellow"
        else:
            conf_style = "red"

        table.add_row(
            service,
            f"[{type_style}]{dep.dep_type.value}[/]",
            f"[{conf_style}]{confidence_pct}[/]",
            ", ".join(dep.providers),
        )

    console.print(table)


def _demo_deps_output(service_file: str, direction: str, output_format: str) -> int:
    """Show demo dependencies output."""
    discovery, graph = create_demo_discovery()

    # Create demo result
    result = DiscoveryResult(
        service="payment-api",
        providers_queried=["prometheus"],
    )

    # Get dependencies from graph
    result.upstream = graph.get_upstream("payment-api")
    result.downstream = graph.get_downstream("payment-api")

    if output_format == "json":
        console.print_json(data=_result_to_dict(result, direction))
    else:
        _print_deps_table(result, direction)

    return 0


def register_deps_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register deps subcommand parser."""
    deps_parser = subparsers.add_parser(
        "deps",
        help="Show service dependencies",
    )
    deps_parser.add_argument("service_file", help="Path to service YAML file")
    deps_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus server URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    deps_parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        help="Environment name (dev, staging, prod)",
    )

    # Direction group
    direction_group = deps_parser.add_mutually_exclusive_group()
    direction_group.add_argument(
        "--upstream",
        "-u",
        action="store_const",
        const="upstream",
        dest="direction",
        help="Show only upstream dependencies (what this service calls)",
    )
    direction_group.add_argument(
        "--downstream",
        "-d",
        action="store_const",
        const="downstream",
        dest="direction",
        help="Show only downstream dependencies (what calls this service)",
    )
    deps_parser.set_defaults(direction="both")

    deps_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    deps_parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_deps_command(args: argparse.Namespace) -> int:
    """Handle deps command from CLI args."""
    return deps_command(
        service_file=args.service_file,
        prometheus_url=getattr(args, "prometheus_url", None),
        environment=getattr(args, "environment", None),
        direction=getattr(args, "direction", "both"),
        output_format=getattr(args, "output_format", "table"),
        demo=getattr(args, "demo", False),
    )
