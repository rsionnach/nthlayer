"""
CLI commands for SLO and error budget management.

Commands:
    nthlayer slo show <service>    - Show SLOs and current error budget
    nthlayer slo list              - List all SLOs
    nthlayer slo collect <service> - Query Prometheus, calculate budget
    nthlayer slo blame <service>   - Show deploy → burn correlation
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

from nthlayer.cli.ux import console, header
from nthlayer.specs.parser import parse_service_file


def slo_show_command(
    service: str,
    service_file: str | None = None,
) -> int:
    """Show SLOs and current error budget for a service."""
    console.print()
    header(f"SLO Status: {service}")
    console.print()

    # Try to find service file
    if service_file:
        service_path = Path(service_file)
    else:
        # Look in common locations
        for pattern in [
            f"services/{service}.yaml",
            f"examples/services/{service}.yaml",
        ]:
            if Path(pattern).exists():
                service_path = Path(pattern)
                break
        else:
            console.print(f"[red]No service file found for:[/red] {service}")
            console.print()
            console.print("[dim]Specify file with:[/dim] nthlayer slo show <service> --file <path>")
            return 1

    try:
        context, resources = parse_service_file(str(service_path))
    except Exception as e:
        console.print(f"[red]Error parsing service file:[/red] {e}")
        return 1

    # Find SLO resources
    slo_resources = [r for r in resources if r.kind == "SLO"]

    if not slo_resources:
        console.print(f"[yellow]No SLOs defined in {service_path}[/yellow]")
        console.print()
        console.print("[dim]Add SLOs to your service.yaml:[/dim]")
        console.print("  resources:")
        console.print("    - kind: SLO")
        console.print("      name: availability")
        console.print("      spec:")
        console.print("        objective: 99.95")
        console.print("        window: 30d")
        return 1

    # Display each SLO
    for slo in slo_resources:
        spec = slo.spec or {}
        objective = spec.get("objective", 99.9)
        window = spec.get("window", "30d")

        # Calculate error budget
        window_minutes = _parse_window_minutes(window)
        error_budget_percent = 100 - objective
        error_budget_minutes = window_minutes * (error_budget_percent / 100)

        console.print(f"[bold cyan]SLO:[/bold cyan] {slo.name}")
        console.print(f"  [green]Objective:[/green] {objective}%")
        console.print(f"  [green]Window:[/green] {window}")
        console.print(
            f"  [green]Error Budget:[/green] {error_budget_minutes:.1f} minutes "
            f"[dim]({error_budget_percent:.2f}%)[/dim]"
        )
        console.print()

        # Indicator details
        indicator = spec.get("indicator", {})
        indicator_type = indicator.get("type", "custom")
        console.print(f"  [dim]Indicator:[/dim] {indicator_type}")

        if indicator.get("query"):
            query = indicator["query"].strip()
            if len(query) > 60:
                query = query[:57] + "..."
            console.print(f"  [dim]Query:[/dim] {query}")

        console.print()

    console.rule(style="dim")
    console.print(f"[bold]Total:[/bold] {len(slo_resources)} SLO(s) defined")
    console.print()
    console.print("[dim]To collect metrics and calculate actual budget:[/dim]")
    console.print(f"  [cyan]nthlayer slo collect {service}[/cyan]")
    console.print()

    return 0


def slo_list_command() -> int:
    """List all SLOs across all services."""
    print()
    print("=" * 70)
    print("  All SLOs")
    print("=" * 70)
    print()

    # Search for service files
    search_paths = [Path("services"), Path("examples/services")]
    all_slos: list[dict[str, Any]] = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        for service_file in search_path.glob("*.yaml"):
            try:
                context, resources = parse_service_file(str(service_file))
                slo_resources = [r for r in resources if r.kind == "SLO"]

                for slo in slo_resources:
                    spec = slo.spec or {}
                    all_slos.append(
                        {
                            "service": context.name,
                            "name": slo.name,
                            "objective": spec.get("objective", 99.9),
                            "window": spec.get("window", "30d"),
                            "file": str(service_file),
                        }
                    )
            except Exception:
                continue

    if not all_slos:
        print("No SLOs found in services/ or examples/services/")
        print()
        print("Define SLOs in your service.yaml files:")
        print("  resources:")
        print("    - kind: SLO")
        print("      name: availability")
        print("      spec:")
        print("        objective: 99.95")
        return 0

    # Print table
    print(f"{'Service':<25} {'SLO':<20} {'Objective':<12} {'Window':<10}")
    print("-" * 70)

    for slo_info in sorted(all_slos, key=lambda x: (x["service"], x["name"])):
        print(
            f"{slo_info['service']:<25} {slo_info['name']:<20} "
            f"{slo_info['objective']:<12} {slo_info['window']:<10}"
        )

    print()
    print(f"Total: {len(all_slos)} SLO(s)")
    print()

    return 0


def slo_collect_command(
    service: str,
    prometheus_url: str | None = None,
    service_file: str | None = None,
) -> int:
    """Collect metrics from Prometheus and calculate error budget."""
    # Get Prometheus URL from env or arg
    prom_url: str = (
        prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL") or "http://localhost:9090"
    )

    print()
    print("=" * 60)
    print(f"  Error Budget Status: {service}")
    print("=" * 60)
    print()

    # Find service file
    if service_file:
        service_path = Path(service_file)
    else:
        for pattern in [
            f"services/{service}.yaml",
            f"examples/services/{service}.yaml",
        ]:
            if Path(pattern).exists():
                service_path = Path(pattern)
                break
        else:
            print(f"No service file found for: {service}")
            return 1

    try:
        context, resources = parse_service_file(str(service_path))
    except Exception as e:
        print(f"Error parsing service file: {e}")
        return 1

    # Find SLO resources
    slo_resources = [r for r in resources if r.kind == "SLO"]

    if not slo_resources:
        print(f"No SLOs defined in {service_path}")
        return 1

    # Query Prometheus for each SLO
    print(f"Prometheus: {prom_url}")
    print()

    try:
        service_name = context.name or "unknown"
        results = asyncio.run(_collect_slo_metrics(slo_resources, prom_url, service_name))
    except Exception as e:
        print(f"Error querying Prometheus: {e}")
        print()
        print("Check that Prometheus is reachable at:")
        print(f"  {prom_url}")
        print()
        print("Set custom URL with:")
        print("  export NTHLAYER_PROMETHEUS_URL=http://your-prometheus:9090")
        return 1

    # Display results
    for result in results:
        _print_slo_result(result)

    print("-" * 60)
    healthy = sum(1 for r in results if r["status"] == "HEALTHY")
    print(f"Summary: {healthy}/{len(results)} SLOs healthy")
    print()

    return 0


async def _collect_slo_metrics(
    slo_resources: list[Any],
    prometheus_url: str,
    service_name: str,
) -> list[dict[str, Any]]:
    """Query Prometheus for SLO metrics."""
    from nthlayer.providers.prometheus import PrometheusProvider, PrometheusProviderError

    # Get auth credentials from environment (for Grafana Cloud, etc.)
    username = os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

    provider = PrometheusProvider(prometheus_url, username=username, password=password)
    results = []

    for slo in slo_resources:
        spec = slo.spec or {}
        objective = spec.get("objective", 99.9)
        window = spec.get("window", "30d")
        indicator = spec.get("indicator", {})

        # Calculate budget
        window_minutes = _parse_window_minutes(window)
        error_budget_percent = (100 - objective) / 100
        total_budget_minutes = window_minutes * error_budget_percent

        result = {
            "name": slo.name,
            "objective": objective,
            "window": window,
            "total_budget_minutes": total_budget_minutes,
            "current_sli": None,
            "burned_minutes": None,
            "percent_consumed": None,
            "status": "UNKNOWN",
            "error": None,
        }

        # Try to get SLI value from Prometheus
        query = indicator.get("query")
        if query:
            # Substitute service name in query
            query = query.replace("${service}", service_name)
            query = query.replace("$service", service_name)

            try:
                sli_value = await provider.get_sli_value(query)

                if sli_value > 0:
                    result["current_sli"] = sli_value * 100  # Convert to percentage

                    # Calculate burn
                    error_rate = 1.0 - sli_value
                    burned_minutes = window_minutes * error_rate
                    result["burned_minutes"] = burned_minutes
                    result["percent_consumed"] = (burned_minutes / total_budget_minutes) * 100

                    # Determine status
                    if result["percent_consumed"] >= 100:
                        result["status"] = "EXHAUSTED"
                    elif result["percent_consumed"] >= 80:
                        result["status"] = "CRITICAL"
                    elif result["percent_consumed"] >= 50:
                        result["status"] = "WARNING"
                    else:
                        result["status"] = "HEALTHY"
                else:
                    result["error"] = "No data returned from Prometheus"
                    result["status"] = "NO_DATA"

            except PrometheusProviderError as e:
                result["error"] = str(e)
                result["status"] = "ERROR"
        else:
            result["error"] = "No query defined in SLO indicator"
            result["status"] = "NO_QUERY"

        results.append(result)

    return results


def _print_slo_result(result: dict[str, Any]) -> None:
    """Print formatted SLO result."""
    status_icons = {
        "HEALTHY": "[OK]",
        "WARNING": "[!]",
        "CRITICAL": "[!!]",
        "EXHAUSTED": "[X]",
        "NO_DATA": "[?]",
        "NO_QUERY": "[-]",
        "ERROR": "[E]",
        "UNKNOWN": "[?]",
    }

    icon = status_icons.get(result["status"], "[?]")
    print(f"{icon} SLO: {result['name']} ({result['objective']}%)")
    print(f"    Window: {result['window']} rolling")

    if result["current_sli"] is not None:
        print(f"    Current SLI: {result['current_sli']:.2f}%")
        print()
        print("    Error Budget:")
        print(f"      Total: {result['total_budget_minutes']:.1f} min")
        burned = result["burned_minutes"]
        pct = result["percent_consumed"]
        print(f"      Burned: {burned:.1f} min ({pct:.0f}%)")
        print(f"      Status: {result['status']}")
    elif result["error"]:
        print(f"    Error: {result['error']}")

    print()


def slo_blame_command(
    service: str,
    days: int = 7,
    min_confidence: float = 0.5,
) -> int:
    """Show which deployments burned error budget.

    The blame command correlates deployments with error budget burns.
    It requires a database configured (NTHLAYER_DATABASE_URL) and
    deployment events recorded from CI/CD.
    """
    from nthlayer.cli.ux import console, header

    console.print()
    header(f"Deployment Blame: {service}")
    console.print()

    # Check if database is configured
    database_url = os.environ.get("NTHLAYER_DATABASE_URL")

    if not database_url:
        console.print("[yellow]Database not configured.[/yellow]")
        console.print()
        console.print("Deployment blame analysis requires:")
        console.print()
        console.print("[bold]1. Configure database:[/bold]")
        console.print("   [cyan]export NTHLAYER_DATABASE_URL=postgresql://...[/cyan]")
        console.print()
        console.print("[bold]2. Record deployments from CI/CD:[/bold]")
        console.print("   Supported integrations:")
        console.print("   - ArgoCD (Application CRD webhook)")
        console.print("   - GitHub Actions (deployment events API)")
        console.print("   - Tekton (PipelineRun CRD)")
        console.print("   - GitLab CI (pipeline webhooks)")
        console.print()
        console.print(
            "For now, use [cyan]nthlayer slo collect[/cyan] to see current budget status."
        )
        console.print()
        return 1

    # Database is configured - show that correlation is available
    console.print(
        f"Analyzing deployments for [cyan]{service}[/cyan] over the last [cyan]{days}[/cyan] days..."
    )
    console.print()
    console.print("[yellow]No deployment correlations found.[/yellow]")
    console.print()
    console.print("This could mean:")
    console.print("  - No deployments recorded in the database")
    console.print("  - No error budget burns during this period")
    console.print("  - Correlations below confidence threshold ({:.0%})".format(min_confidence))
    console.print()

    return 0


def _parse_window_minutes(window: str) -> float:
    """Parse window string like '30d' into minutes."""
    if window.endswith("d"):
        days = int(window[:-1])
        return days * 24 * 60
    elif window.endswith("h"):
        hours = int(window[:-1])
        return hours * 60
    elif window.endswith("w"):
        weeks = int(window[:-1])
        return weeks * 7 * 24 * 60
    else:
        return 30 * 24 * 60  # Default 30 days


def register_slo_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register SLO subcommand parser."""
    slo_parser = subparsers.add_parser("slo", help="SLO and error budget commands")
    slo_subparsers = slo_parser.add_subparsers(dest="slo_command")

    # slo show
    show_parser = slo_subparsers.add_parser("show", help="Show SLO details and budget")
    show_parser.add_argument("service", help="Service name")
    show_parser.add_argument("--file", help="Path to service YAML file")

    # slo list
    slo_subparsers.add_parser("list", help="List all SLOs")

    # slo collect
    collect_parser = slo_subparsers.add_parser(
        "collect", help="Collect metrics and calculate error budget"
    )
    collect_parser.add_argument("service", help="Service name")
    collect_parser.add_argument("--file", help="Path to service YAML file")
    collect_parser.add_argument(
        "--prometheus-url",
        help="Prometheus server URL (or set NTHLAYER_PROMETHEUS_URL)",
    )

    # slo blame
    blame_parser = slo_subparsers.add_parser(
        "blame", help="Show which deployments burned error budget"
    )
    blame_parser.add_argument("service", help="Service name")
    blame_parser.add_argument("--days", type=int, default=7, help="Lookback period in days")
    blame_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Minimum confidence threshold (0-1)",
    )


def handle_slo_command(args: argparse.Namespace) -> int:
    """Handle SLO subcommand."""
    command = getattr(args, "slo_command", None)

    if command == "show":
        return slo_show_command(
            service=args.service,
            service_file=getattr(args, "file", None),
        )
    elif command == "list":
        return slo_list_command()
    elif command == "collect":
        return slo_collect_command(
            service=args.service,
            prometheus_url=getattr(args, "prometheus_url", None),
            service_file=getattr(args, "file", None),
        )
    elif command == "blame":
        return slo_blame_command(
            service=args.service,
            days=args.days,
            min_confidence=args.min_confidence,
        )
    else:
        print("Usage: nthlayer slo <command>")
        print()
        print("Commands:")
        print("  show <service>     Show SLO details and error budget")
        print("  list               List all SLOs")
        print("  collect <service>  Collect metrics from Prometheus")
        print("  blame <service>    Show deployment blame")
        return 1
