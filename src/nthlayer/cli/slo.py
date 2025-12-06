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

from nthlayer.specs.parser import parse_service_file


def slo_show_command(
    service: str,
    service_file: str | None = None,
) -> int:
    """Show SLOs and current error budget for a service."""
    print()
    print("=" * 60)
    print(f"  SLO Status: {service}")
    print("=" * 60)
    print()

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
            print(f"No service file found for: {service}")
            print()
            print("Specify file with: nthlayer slo show <service> --file <path>")
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
        print()
        print("Add SLOs to your service.yaml:")
        print("  resources:")
        print("    - kind: SLO")
        print("      name: availability")
        print("      spec:")
        print("        objective: 99.95")
        print("        window: 30d")
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

        print(f"SLO: {slo.name}")
        print(f"  Objective: {objective}%")
        print(f"  Window: {window}")
        print(f"  Error Budget: {error_budget_minutes:.1f} minutes ({error_budget_percent:.2f}%)")
        print()

        # Indicator details
        indicator = spec.get("indicator", {})
        indicator_type = indicator.get("type", "custom")
        print(f"  Indicator: {indicator_type}")

        if indicator.get("query"):
            query = indicator["query"].strip()
            if len(query) > 60:
                query = query[:57] + "..."
            print(f"  Query: {query}")

        print()

    print("-" * 60)
    print(f"Total: {len(slo_resources)} SLO(s) defined")
    print()
    print("To collect metrics and calculate actual budget:")
    print(f"  nthlayer slo collect {service}")
    print()

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

    for slo in sorted(all_slos, key=lambda x: (x["service"], x["name"])):
        print(
            f"{slo['service']:<25} {slo['name']:<20} " f"{slo['objective']:<12} {slo['window']:<10}"
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
    prom_url = prometheus_url or os.environ.get(
        "NTHLAYER_PROMETHEUS_URL", "http://localhost:9090"
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
        results = asyncio.run(_collect_slo_metrics(slo_resources, prom_url, context.name))
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

    provider = PrometheusProvider(prometheus_url)
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
    """Show which deployments burned error budget."""
    print()
    print("=" * 60)
    print(f"  Deployment Blame: {service}")
    print("=" * 60)
    print()

    print("Deployment correlation requires CI/CD integration.")
    print()
    print("Coming soon:")
    print("  - ArgoCD (Application CRD, webhook listener)")
    print("  - GitHub Actions (deployment events API)")
    print("  - Tekton (PipelineRun CRD)")
    print("  - GitLab CI (pipeline webhooks)")
    print()
    print("For now, use 'nthlayer slo collect' to see current budget status.")
    print()

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
