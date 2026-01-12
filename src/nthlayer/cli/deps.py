"""
CLI command for dependency discovery.

Shows service dependencies discovered from Prometheus, Kubernetes, and Backstage.

Commands:
    nthlayer deps <service.yaml>              - Show all dependencies
    nthlayer deps <service.yaml> --upstream   - Show what this service calls
    nthlayer deps <service.yaml> --downstream - Show what calls this service
    nthlayer deps <service.yaml> --json       - Output as JSON
    nthlayer deps <service.yaml> --provider kubernetes - Use only Kubernetes
    nthlayer deps <service.yaml> --provider backstage  - Use only Backstage
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any, Literal, Optional

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

# Provider type
ProviderChoice = Literal["prometheus", "kubernetes", "backstage", "all"]


def deps_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    environment: Optional[str] = None,
    direction: str = "both",
    output_format: str = "table",
    demo: bool = False,
    provider: ProviderChoice = "all",
    k8s_namespace: Optional[str] = None,
    backstage_url: Optional[str] = None,
) -> int:
    """
    Show dependencies for a service.

    Discovers upstream and downstream dependencies from Prometheus metrics,
    Kubernetes resources, and/or Backstage catalog.

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
        provider: Provider to use ("prometheus", "kubernetes", "backstage", or "all")
        k8s_namespace: Kubernetes namespace to search (None = all)
        backstage_url: Backstage catalog URL (or use env var)

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_deps_output(service_file, direction, output_format, provider)

    # Parse service file
    try:
        context, _resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    service_name = context.name or "unknown"

    # Create discovery and add providers
    discovery = DependencyDiscovery()
    providers_added = 0

    # Add Prometheus provider
    if provider in ("prometheus", "all"):
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
        elif provider == "prometheus":
            error("No Prometheus URL provided")
            console.print()
            console.print(
                "[muted]Provide via --prometheus-url or NTHLAYER_PROMETHEUS_URL env var[/muted]"
            )
            return 2

    # Add Kubernetes provider
    if provider in ("kubernetes", "all"):
        try:
            from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

            k8s_provider = KubernetesDepProvider(
                namespace=k8s_namespace or os.environ.get("NTHLAYER_K8S_NAMESPACE"),
            )
            discovery.add_provider(k8s_provider)
            providers_added += 1
        except ImportError:
            if provider == "kubernetes":
                error("Kubernetes provider not available")
                console.print()
                console.print("[muted]Install with: pip install nthlayer[kubernetes][/muted]")
                return 2
            # Skip silently if "all" and not installed

    # Add Backstage provider
    if provider in ("backstage", "all"):
        bs_url = backstage_url or os.environ.get("NTHLAYER_BACKSTAGE_URL")
        if bs_url:
            from nthlayer.dependencies.providers.backstage import BackstageDepProvider

            bs_provider = BackstageDepProvider(
                url=bs_url,
                token=os.environ.get("NTHLAYER_BACKSTAGE_TOKEN"),
            )
            discovery.add_provider(bs_provider)
            providers_added += 1
        elif provider == "backstage":
            error("No Backstage URL provided")
            console.print()
            console.print(
                "[muted]Provide via --backstage-url or NTHLAYER_BACKSTAGE_URL env var[/muted]"
            )
            return 2

    if providers_added == 0:
        error("No providers available")
        console.print()
        console.print("[muted]Provide Prometheus URL or install kubernetes extra[/muted]")
        return 2

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


def _demo_deps_output(
    service_file: str,
    direction: str,
    output_format: str,
    provider: ProviderChoice = "all",
) -> int:
    """Show demo dependencies output."""
    discovery, graph = create_demo_discovery()

    # Determine providers to show based on selection
    providers_queried: list[str] = []
    if provider in ("prometheus", "all"):
        providers_queried.append("prometheus")
    if provider in ("kubernetes", "all"):
        providers_queried.append("kubernetes")
    if provider in ("backstage", "all"):
        providers_queried.append("backstage")

    # Create demo result
    result = DiscoveryResult(
        service="payment-api",
        providers_queried=providers_queried,
    )

    # Get dependencies from graph (prometheus-discovered)
    if provider in ("prometheus", "all"):
        result.upstream = graph.get_upstream("payment-api")
        result.downstream = graph.get_downstream("payment-api")
    else:
        result.upstream = []
        result.downstream = []

    from nthlayer.identity import ServiceIdentity

    # Add kubernetes-specific demo dependencies
    if provider in ("kubernetes", "all"):
        # Add demo K8s-discovered dependencies to upstream
        k8s_deps = [
            ResolvedDependency(
                source=ServiceIdentity(canonical_name="payment-api"),
                target=ServiceIdentity(canonical_name="config-service"),
                dep_type=DependencyType.INFRASTRUCTURE,
                confidence=0.85,
                providers=["kubernetes"],
                metadata={"source": "network_policy_egress", "namespace": "default"},
            ),
        ]
        result.upstream.extend(k8s_deps)

        # Add ingress as downstream
        k8s_downstream = [
            ResolvedDependency(
                source=ServiceIdentity(canonical_name="ingress/payment-ingress"),
                target=ServiceIdentity(canonical_name="payment-api"),
                dep_type=DependencyType.INFRASTRUCTURE,
                confidence=0.95,
                providers=["kubernetes"],
                metadata={"source": "ingress", "namespace": "default", "host": "api.example.com"},
            ),
        ]
        result.downstream.extend(k8s_downstream)

    # Add backstage-specific demo dependencies
    if provider in ("backstage", "all"):
        backstage_deps = [
            ResolvedDependency(
                source=ServiceIdentity(canonical_name="payment-api"),
                target=ServiceIdentity(canonical_name="audit-service"),
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                providers=["backstage"],
                metadata={"source": "spec.dependsOn", "namespace": "default"},
            ),
            ResolvedDependency(
                source=ServiceIdentity(canonical_name="payment-api"),
                target=ServiceIdentity(canonical_name="notification-api"),
                dep_type=DependencyType.SERVICE,
                confidence=0.90,
                providers=["backstage"],
                metadata={"source": "spec.consumesApis", "namespace": "default"},
            ),
        ]
        result.upstream.extend(backstage_deps)

        # Add downstream from backstage
        backstage_downstream = [
            ResolvedDependency(
                source=ServiceIdentity(canonical_name="refund-service"),
                target=ServiceIdentity(canonical_name="payment-api"),
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                providers=["backstage"],
                metadata={"source": "spec.dependsOn", "namespace": "default"},
            ),
        ]
        result.downstream.extend(backstage_downstream)

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

    # Provider selection
    deps_parser.add_argument(
        "--provider",
        choices=["prometheus", "kubernetes", "backstage", "all"],
        default="all",
        help="Dependency provider to use (default: all)",
    )
    deps_parser.add_argument(
        "--k8s-namespace",
        "--namespace",
        dest="k8s_namespace",
        help="Kubernetes namespace to search (default: all namespaces)",
    )
    deps_parser.add_argument(
        "--backstage-url",
        help="Backstage catalog URL (or set NTHLAYER_BACKSTAGE_URL)",
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
        provider=getattr(args, "provider", "all"),
        k8s_namespace=getattr(args, "k8s_namespace", None),
        backstage_url=getattr(args, "backstage_url", None),
    )
