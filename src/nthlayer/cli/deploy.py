"""
Deployment gate check command.

Queries Prometheus for SLO metrics, calculates error budget,
then evaluates deployment gate thresholds.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.slos.gates import DeploymentGate, GateResult
from nthlayer.specs.parser import parse_service_file


def check_deploy_command(
    service_file: str,
    prometheus_url: str | None = None,
    environment: str | None = None,
    demo: bool = False,
    demo_blocked: bool = False,
) -> int:
    """
    Check if deployment should be allowed based on error budget.

    Queries Prometheus for actual SLI metrics, calculates budget,
    then evaluates deployment gate thresholds.

    Exit codes:
    - 0 = Approved (proceed with deploy)
    - 1 = Warning (advisory, proceed with caution)
    - 2 = Blocked (do not deploy)

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus server URL (or use PROMETHEUS_URL env var)
        environment: Optional environment name (dev, staging, prod)
        demo: Show demo output with sample data (for VHS recordings)
        demo_blocked: Show demo output with BLOCKED scenario (for VHS recordings)

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode for VHS recordings
    if demo:
        return _run_demo_mode(service_file, environment, blocked=False)
    if demo_blocked:
        return _run_demo_mode(service_file, environment, blocked=True)
    # Resolve Prometheus URL
    prom_url = prometheus_url or os.environ.get("PROMETHEUS_URL")

    # Parse service file
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    # Print header
    header(f"Deployment Gate Check: {service_context.name}")
    console.print()

    if prom_url:
        console.print(f"[cyan]Prometheus:[/cyan] {prom_url}")
    console.print(f"[cyan]Service:[/cyan] {service_context.name}")
    console.print(f"[cyan]Team:[/cyan] {service_context.team}")
    console.print(f"[cyan]Tier:[/cyan] {service_context.tier}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    console.print()

    # Get SLO resources
    slo_resources = [r for r in resources if r.kind == "SLO"]

    if not slo_resources:
        warning("No SLOs defined in service.yaml")
        console.print("[muted]Cannot check error budget without SLO definitions[/muted]")
        console.print()
        console.print("[muted]Add SLOs to enable deployment gating:[/muted]")
        console.print("  resources:")
        console.print("    - kind: SLO")
        console.print("      name: availability")
        console.print("      spec:")
        console.print("        objective: 99.95")
        console.print("        window: 30d")
        return 0

    # Get dependencies for blast radius
    dep_resources = [r for r in resources if r.kind == "Dependencies"]
    downstream_services = []

    if dep_resources:
        deps_spec = dep_resources[0].spec
        for svc in deps_spec.get("services", []):
            downstream_services.append(
                {
                    "name": svc["name"],
                    "criticality": svc.get("criticality", "medium"),
                }
            )

    # If no Prometheus URL, show example scenarios
    if not prom_url:
        info("No Prometheus URL provided")
        console.print("[muted]Provide via --prometheus-url or PROMETHEUS_URL env var[/muted]")
        console.print()
        _show_example_scenarios(service_context, slo_resources, downstream_services)
        return 0

    # Query Prometheus for SLO metrics
    console.print("[bold]Querying Prometheus for SLO metrics...[/bold]")
    console.print()

    try:
        slo_results = asyncio.run(
            _collect_slo_metrics(slo_resources, prom_url, service_context.name)
        )
    except Exception as e:
        error(f"Failed to query Prometheus: {e}")
        console.print()
        console.print(f"[muted]Check Prometheus is reachable at: {prom_url}[/muted]")
        return 2

    # Display SLO status table
    _print_slo_table(slo_results)

    # Calculate aggregate budget
    valid_results = [r for r in slo_results if r["burned_minutes"] is not None]

    if not valid_results:
        warning("No SLO data available from Prometheus")
        console.print("[muted]Ensure metrics are being collected[/muted]")
        return 0

    total_budget = sum(r["total_budget_minutes"] for r in valid_results)
    burned_budget = sum(r["burned_minutes"] for r in valid_results)
    if total_budget > 0:
        remaining_pct = (total_budget - burned_budget) / total_budget * 100
    else:
        remaining_pct = 100

    consumed_pct = 100 - remaining_pct
    console.print(
        f"[bold]Aggregate Budget:[/bold] {burned_budget:.1f}/{total_budget:.1f} "
        f"minutes consumed ({consumed_pct:.1f}%)"
    )
    console.print()

    # Run deployment gate
    gate = DeploymentGate()
    result = gate.check_deployment(
        service=service_context.name,
        tier=service_context.tier,
        budget_total_minutes=int(total_budget),
        budget_consumed_minutes=int(burned_budget),
        downstream_services=downstream_services,
    )

    # Display thresholds
    console.print(f"[bold]Thresholds ({service_context.tier} tier):[/bold]")
    console.print(f"  [muted]Warning:[/muted] <{result.warning_threshold}% remaining")
    if result.blocking_threshold:
        console.print(f"  [muted]Blocking:[/muted] <{result.blocking_threshold}% remaining")
    else:
        console.print("  [muted]Blocking:[/muted] None (advisory only)")
    console.print()

    # Blast radius
    if result.high_criticality_downstream:
        console.print("[bold]Blast Radius:[/bold]")
        console.print(
            f"  [warning]⚡[/warning] {len(result.high_criticality_downstream)} "
            "high-criticality downstream service(s)"
        )
        for svc in result.high_criticality_downstream:
            console.print(f"    [muted]•[/muted] {svc}")
        console.print()

    # Final verdict
    if result.result == GateResult.BLOCKED:
        error("Deployment BLOCKED")
        console.print(
            f"[muted]Error budget critically low ({remaining_pct:.1f}% remaining)[/muted]"
        )
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for rec in result.recommendations[:3]:
            console.print(f"  [muted]•[/muted] {rec}")
        console.print()
        console.print("[error]Exit code: 2[/error]")
        return 2

    elif result.result == GateResult.WARNING:
        warning("Deployment allowed with WARNING")
        console.print(f"[muted]Error budget low ({remaining_pct:.1f}% remaining)[/muted]")
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for rec in result.recommendations[:3]:
            console.print(f"  [muted]•[/muted] {rec}")
        console.print()
        console.print("[warning]Exit code: 1[/warning]")
        return 1

    else:
        success("Deployment APPROVED")
        console.print(f"[muted]Error budget healthy ({remaining_pct:.1f}% remaining)[/muted]")
        console.print()
        console.print("[success]Exit code: 0[/success]")
        return 0


def _show_example_scenarios(
    service_context: Any,
    slo_resources: list[Any],
    downstream_services: list[dict[str, Any]],
) -> None:
    """Show example scenarios when no Prometheus URL provided."""
    console.print(f"[bold]Example scenarios for {service_context.tier} tier:[/bold]")
    console.print()

    gate = DeploymentGate()

    # Calculate example budget from first SLO
    if slo_resources:
        spec = slo_resources[0].spec or {}
        window = spec.get("window", "30d")
        objective = spec.get("objective", 99.9)
        window_minutes = _parse_window_minutes(window)
        total_budget = window_minutes * ((100 - objective) / 100)
    else:
        total_budget = 43.2  # Default: 30 days at 99.9%

    scenarios = [
        ("Healthy (5% consumed)", int(total_budget * 0.05)),
        ("Warning (85% consumed)", int(total_budget * 0.85)),
        ("Blocked (95% consumed)", int(total_budget * 0.95)),
    ]

    for scenario_name, consumed in scenarios:
        result = gate.check_deployment(
            service_context.name,
            service_context.tier,
            int(total_budget),
            consumed,
            downstream_services,
        )

        status_icon = {
            GateResult.APPROVED: "[success]✓[/success]",
            GateResult.WARNING: "[warning]⚠[/warning]",
            GateResult.BLOCKED: "[error]✗[/error]",
        }[result.result]

        console.print(f"  {status_icon} {scenario_name} → Exit code: {result.result}")

    console.print()
    console.print("[muted]To check with real data:[/muted]")
    console.print(
        f"  [cyan]nthlayer deploy check {Path(service_context.name).name}.yaml "
        "--prometheus-url http://prometheus:9090[/cyan]"
    )
    console.print()


def _print_slo_table(results: list[dict[str, Any]]) -> None:
    """Print SLO status as a table."""
    console.print("[bold]SLO Budget Status:[/bold]")

    for result in results:
        status_icon = {
            "HEALTHY": "[success]✓[/success]",
            "WARNING": "[warning]⚠[/warning]",
            "CRITICAL": "[error]!![/error]",
            "EXHAUSTED": "[error]✗[/error]",
            "NO_DATA": "[muted]?[/muted]",
            "ERROR": "[error]E[/error]",
        }.get(result["status"], "[muted]?[/muted]")

        name = result["name"]
        objective = result["objective"]

        if result["current_sli"] is not None:
            sli = f"{result['current_sli']:.2f}%"
            burned_pct = result["percent_consumed"]
            budget_str = f"{burned_pct:.0f}% burned"
        else:
            sli = "N/A"
            budget_str = result.get("error", "No data")

        console.print(
            f"  {status_icon} {name:<20} "
            f"[muted]target:[/muted] {objective}% "
            f"[muted]current:[/muted] {sli:<8} "
            f"[muted]budget:[/muted] {budget_str}"
        )

    console.print()


async def _collect_slo_metrics(
    slo_resources: list[Any],
    prometheus_url: str,
    service_name: str,
) -> list[dict[str, Any]]:
    """Query Prometheus for SLO metrics."""
    from nthlayer.providers.prometheus import PrometheusProvider, PrometheusProviderError

    # Get auth credentials from environment
    username = os.environ.get("PROMETHEUS_USERNAME") or os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("PROMETHEUS_PASSWORD") or os.environ.get("NTHLAYER_METRICS_PASSWORD")

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
        # Support both simple indicator.query format and indicators[].success_ratio format
        query = indicator.get("query")

        # Fallback: check for indicators[] format used in service.yaml examples
        if not query:
            indicators = spec.get("indicators", [])
            if indicators:
                ind = indicators[0]
                if ind.get("success_ratio"):
                    sr = ind["success_ratio"]
                    total_query = sr.get("total_query")
                    good_query = sr.get("good_query")
                    if total_query and good_query:
                        query = f"({good_query}) / ({total_query})"

        if query:
            # Substitute service name in query
            query = query.replace("${service}", service_name)
            query = query.replace("$service", service_name)

            try:
                sli_value = await provider.get_sli_value(query)

                if sli_value > 0:
                    result["current_sli"] = sli_value * 100

                    # Calculate burn
                    error_rate = 1.0 - sli_value
                    burned_minutes = window_minutes * error_rate
                    result["burned_minutes"] = burned_minutes
                    result["percent_consumed"] = (
                        (burned_minutes / total_budget_minutes) * 100
                        if total_budget_minutes > 0
                        else 0
                    )

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
                    result["error"] = "No data returned"
                    result["status"] = "NO_DATA"

            except PrometheusProviderError as e:
                result["error"] = str(e)
                result["status"] = "ERROR"
        else:
            result["error"] = "No query defined"
            result["status"] = "NO_DATA"

        results.append(result)

    return results


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


def _run_demo_mode(service_file: str, environment: str | None = None, blocked: bool = False) -> int:
    """Run demo mode with sample data for VHS recordings.

    Args:
        service_file: Path to service YAML file
        environment: Optional environment name
        blocked: If True, show BLOCKED scenario; if False, show WARNING scenario
    """
    from nthlayer.specs.parser import parse_service_file

    # Parse service file to get real names
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
        service_name = service_context.name
        tier = service_context.tier
        team = service_context.team
    except Exception:
        service_name = "payment-api"
        tier = "critical"
        team = "payments"

    # Print header
    header(f"Deployment Gate Check: {service_name}")
    console.print()

    console.print("[cyan]Prometheus:[/cyan] https://prometheus.internal:9090")
    console.print(f"[cyan]Service:[/cyan] {service_name}")
    console.print(f"[cyan]Team:[/cyan] {team}")
    console.print(f"[cyan]Tier:[/cyan] {tier}")
    console.print()

    console.print("[bold]Querying Prometheus for SLO metrics...[/bold]")
    console.print()

    if blocked:
        # Demo SLO data - shows a BLOCKED scenario (error budget exhausted)
        console.print("[bold]SLO Budget Status:[/bold]")
        console.print(
            "  [error]!![/error] availability          "
            "[muted]target:[/muted] 99.95% "
            "[muted]current:[/muted] 99.68%   "
            "[muted]budget:[/muted] 93% burned"
        )
        console.print(
            "  [warning]⚠[/warning] latency_p99           "
            "[muted]target:[/muted] 200ms  "
            "[muted]current:[/muted] 312ms    "
            "[muted]budget:[/muted] 78% burned"
        )
        console.print()

        console.print("[bold]Aggregate Budget:[/bold] 39.8/43.2 minutes consumed (92.1%)")
        console.print()

        console.print(f"[bold]Thresholds ({tier} tier):[/bold]")
        console.print("  [muted]Warning:[/muted] <50% remaining")
        console.print("  [muted]Blocking:[/muted] <10% remaining")
        console.print()

        # Show blocked result
        error("Deployment BLOCKED")
        console.print("[muted]Error budget critically low (7.9% remaining)[/muted]")
        console.print()

        console.print("[bold]Recommendations:[/bold]")
        console.print("  [muted]•[/muted] Investigate current reliability issues before deploying")
        console.print("  [muted]•[/muted] Consider rolling back recent changes")
        console.print("  [muted]•[/muted] Wait for error budget to recover (estimated: 4 hours)")
        console.print()

        console.print("[error]Exit code: 2[/error]")
        return 2
    else:
        # Demo SLO data - shows a warning scenario
        console.print("[bold]SLO Budget Status:[/bold]")
        console.print(
            "  [warning]⚠[/warning] availability          "
            "[muted]target:[/muted] 99.95% "
            "[muted]current:[/muted] 99.87%   "
            "[muted]budget:[/muted] 58% burned"
        )
        console.print(
            "  [success]✓[/success] latency_p99           "
            "[muted]target:[/muted] 200ms  "
            "[muted]current:[/muted] 187ms    "
            "[muted]budget:[/muted] 22% burned"
        )
        console.print()

        console.print("[bold]Aggregate Budget:[/bold] 18.7/43.2 minutes consumed (43.3%)")
        console.print()

        console.print(f"[bold]Thresholds ({tier} tier):[/bold]")
        console.print("  [muted]Warning:[/muted] <50% remaining")
        console.print("  [muted]Blocking:[/muted] <10% remaining")
        console.print()

        # Show warning result
        warning("Deployment allowed with WARNING")
        console.print("[muted]Error budget low (56.7% remaining)[/muted]")
        console.print()

        console.print("[bold]Recommendations:[/bold]")
        console.print("  [muted]•[/muted] Review recent changes for reliability impact")
        console.print("  [muted]•[/muted] Consider smaller deployment batch size")
        console.print("  [muted]•[/muted] Ensure rollback plan is ready")
        console.print()

        console.print("[warning]Exit code: 1[/warning]")
        return 1
