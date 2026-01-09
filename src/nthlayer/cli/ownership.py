"""
CLI command for ownership resolution.

Shows service ownership from multiple sources with confidence scoring.

Commands:
    nthlayer ownership <service.yaml>           - Show ownership attribution
    nthlayer ownership <service.yaml> --json    - Output as JSON
    nthlayer ownership <service.yaml> --demo    - Show demo output
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header
from nthlayer.identity.ownership import (
    OwnershipAttribution,
    OwnershipResolver,
    OwnershipSource,
    create_demo_attribution,
)
from nthlayer.specs.parser import parse_service_file


def ownership_command(
    service_file: str,
    environment: Optional[str] = None,
    output_format: str = "table",
    demo: bool = False,
    backstage_url: Optional[str] = None,
    pagerduty_token: Optional[str] = None,
    k8s_namespace: Optional[str] = None,
    codeowners_root: Optional[str] = None,
) -> int:
    """
    Show ownership attribution for a service.

    Aggregates ownership signals from multiple sources and shows
    the resolved owner with confidence scoring.

    Exit codes:
        0 - Success (owner found)
        1 - Partial success (no owner found, but signals available)
        2 - Error

    Args:
        service_file: Path to service YAML file
        environment: Optional environment name
        output_format: Output format ("table" or "json")
        demo: If True, show demo output with sample data
        backstage_url: Backstage catalog URL (or use env var)
        pagerduty_token: PagerDuty API token (or use env var)
        k8s_namespace: Kubernetes namespace to search
        codeowners_root: Root directory for CODEOWNERS file

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_ownership_output(output_format)

    # Parse service file
    try:
        context, _resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    service_name = context.name or "unknown"
    declared_team = getattr(context, "team", None)
    declared_owner = getattr(context, "owner", None)

    # Create resolver and add providers
    resolver = OwnershipResolver()

    # Add Backstage provider
    bs_url = backstage_url or os.environ.get("NTHLAYER_BACKSTAGE_URL")
    if bs_url:
        from nthlayer.identity.ownership_providers.backstage import (
            BackstageOwnershipProvider,
        )

        resolver.add_provider(
            BackstageOwnershipProvider(
                url=bs_url,
                token=os.environ.get("NTHLAYER_BACKSTAGE_TOKEN"),
            )
        )

    # Add PagerDuty provider
    pd_token = pagerduty_token or os.environ.get("PAGERDUTY_API_KEY")
    if pd_token:
        from nthlayer.identity.ownership_providers.pagerduty import (
            PagerDutyOwnershipProvider,
        )

        resolver.add_provider(
            PagerDutyOwnershipProvider(
                api_token=pd_token,
            )
        )

    # Add Kubernetes provider (if available)
    try:
        from nthlayer.identity.ownership_providers.kubernetes import (
            KubernetesOwnershipProvider,
        )

        resolver.add_provider(
            KubernetesOwnershipProvider(
                namespace=k8s_namespace or os.environ.get("NTHLAYER_K8S_NAMESPACE"),
            )
        )
    except ImportError:
        pass  # Kubernetes not available

    # Add CODEOWNERS provider
    from nthlayer.identity.ownership_providers.codeowners import CODEOWNERSProvider

    resolver.add_provider(
        CODEOWNERSProvider(
            repo_root=codeowners_root or ".",
        )
    )

    # Resolve ownership
    try:
        attribution = asyncio.run(
            resolver.resolve(
                service=service_name,
                declared_owner=declared_owner,
                declared_team=declared_team,
            )
        )
    except Exception as e:
        error(f"Ownership resolution failed: {e}")
        return 2

    # Output results
    if output_format == "json":
        console.print_json(data=attribution.to_dict())
    else:
        _print_ownership_table(attribution)

    # Return code based on resolution
    if attribution.owner:
        return 0
    elif attribution.signals:
        return 1
    return 2


def _confidence_bar(confidence: float) -> str:
    """Create a visual confidence bar."""
    filled = int(confidence * 10)
    empty = 10 - filled
    return "[green]" + "█" * filled + "[/][dim]" + "░" * empty + "[/]"


def _print_ownership_table(attribution: OwnershipAttribution) -> None:
    """Print ownership as formatted output."""
    console.print()
    header(f"Ownership: {attribution.service}")
    console.print()

    if not attribution.signals:
        console.print("[muted]No ownership signals found[/muted]")
        console.print()
        return

    # Signals table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Owner", style="cyan")
    table.add_column("Confidence")
    table.add_column("Details", style="muted")

    for signal in attribution.signals:
        # Source styling
        source_name = signal.source.value

        # Details from metadata
        details = ""
        if signal.source == OwnershipSource.DECLARED:
            details = f"service.yaml ({signal.metadata.get('field', 'team')})"
        elif signal.source == OwnershipSource.PAGERDUTY:
            policy = signal.metadata.get("escalation_policy", "")
            details = f"via {policy}" if policy else "escalation policy"
        elif signal.source == OwnershipSource.BACKSTAGE:
            details = "catalog owner"
        elif signal.source == OwnershipSource.CODEOWNERS:
            file = signal.metadata.get("file", "CODEOWNERS")
            details = file
        elif signal.source == OwnershipSource.KUBERNETES:
            label = signal.metadata.get("label") or signal.metadata.get("annotation", "")
            details = f"label: {label}" if label else "labels"

        table.add_row(
            source_name,
            signal.owner,
            _confidence_bar(signal.confidence),
            details,
        )

    console.print(table)
    console.print()

    # Resolved owner
    if attribution.owner:
        pct = int(attribution.confidence * 100)
        source = attribution.source.value if attribution.source else "unknown"
        console.print(f"[bold]Resolved:[/bold] {attribution.owner} ({source}, confidence: {pct}%)")
    else:
        console.print("[yellow]No owner could be resolved[/yellow]")

    # Contact info
    if attribution.pagerduty_escalation or attribution.slack_channel or attribution.email:
        console.print()
        console.print("[bold]Contact:[/bold]")
        if attribution.pagerduty_escalation:
            console.print(f"  PagerDuty: {attribution.pagerduty_escalation}")
        if attribution.slack_channel:
            console.print(f"  Slack: {attribution.slack_channel}")
        if attribution.email:
            console.print(f"  Email: {attribution.email}")

    console.print()


def _demo_ownership_output(output_format: str) -> int:
    """Show demo ownership output."""
    attribution = create_demo_attribution()

    if output_format == "json":
        console.print_json(data=attribution.to_dict())
    else:
        _print_ownership_table(attribution)

    return 0


def register_ownership_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ownership subcommand parser."""
    parser = subparsers.add_parser(
        "ownership",
        help="Show service ownership attribution",
    )
    parser.add_argument("service_file", help="Path to service YAML file")
    parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        help="Environment name (dev, staging, prod)",
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
        "--backstage-url",
        help="Backstage catalog URL (or set NTHLAYER_BACKSTAGE_URL)",
    )
    parser.add_argument(
        "--pagerduty-token",
        help="PagerDuty API token (or set PAGERDUTY_API_KEY)",
    )
    parser.add_argument(
        "--k8s-namespace",
        "--namespace",
        dest="k8s_namespace",
        help="Kubernetes namespace to search",
    )
    parser.add_argument(
        "--codeowners-root",
        help="Root directory for CODEOWNERS file (default: current dir)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_ownership_command(args: argparse.Namespace) -> int:
    """Handle ownership command from CLI args."""
    return ownership_command(
        service_file=args.service_file,
        environment=getattr(args, "environment", None),
        output_format=getattr(args, "output_format", "table"),
        demo=getattr(args, "demo", False),
        backstage_url=getattr(args, "backstage_url", None),
        pagerduty_token=getattr(args, "pagerduty_token", None),
        k8s_namespace=getattr(args, "k8s_namespace", None),
        codeowners_root=getattr(args, "codeowners_root", None),
    )
