"""CLI command for validating dashboard metric resolution."""

from typing import Optional

import yaml

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.dashboards.intents import ALL_INTENTS, get_intents_for_technology, list_technologies
from nthlayer.dashboards.resolver import ResolutionStatus
from nthlayer.dashboards.validator import (
    DashboardValidator,
    IntentResult,
    ValidationResult,
    extract_custom_overrides,
    extract_technologies,
)
from nthlayer.specs.parser import parse_service_file


def validate_dashboard_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    technology: Optional[str] = None,
    show_all: bool = False,
) -> int:
    """Validate dashboard metric resolution for a service."""
    header("Dashboard Metric Validation")
    console.print()

    try:
        context, resources = parse_service_file(service_file)
        _display_service_info(service_file, context)

        # Determine technologies to validate
        technologies = extract_technologies(context, resources)
        if technology:
            technologies = {technology}

        _display_technologies(technologies)

        # Run validation
        custom_overrides = extract_custom_overrides(resources)
        validator = DashboardValidator(prometheus_url)

        if prometheus_url:
            _display_discovery_start(prometheus_url)

        result = validator.validate(
            service_name=context.name,
            technologies=technologies,
            custom_overrides=custom_overrides,
            validate_all=show_all,
        )

        # Display discovery result
        _display_discovery_result(result, prometheus_url)

        if result.total == 0:
            info("No intents to validate. Add --technology or --show-all")
            return 0

        # Display intent results
        _display_intent_results(result)
        _display_summary(result)

        return _display_final_verdict(result, prometheus_url)

    except FileNotFoundError:
        error(f"Service file not found: {service_file}")
        return 1
    except (yaml.YAMLError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"{e}")
        import traceback

        traceback.print_exc()
        return 1


def _display_service_info(service_file: str, context) -> None:
    """Display service information."""
    console.print(f"[cyan]Service:[/cyan] {service_file}")
    console.print(f"   [muted]Name:[/muted] {context.name}")
    console.print(f"   [muted]Team:[/muted] {context.team}")
    console.print()


def _display_technologies(technologies: set[str]) -> None:
    """Display technologies to validate."""
    tech_list = ", ".join(sorted(technologies)) or "none detected"
    console.print(f"[muted]Technologies to validate:[/muted] {tech_list}")
    console.print()


def _display_discovery_start(prometheus_url: str) -> None:
    """Display discovery start message."""
    console.print(f"[cyan]Discovering metrics from {prometheus_url}...[/cyan]")


def _display_discovery_result(result: ValidationResult, prometheus_url: Optional[str]) -> None:
    """Display metric discovery result."""
    if prometheus_url:
        if result.discovery_error:
            warning(f"Discovery failed: {result.discovery_error}")
            console.print("   [muted]Continuing without discovery (intents unresolved)[/muted]")
        else:
            console.print(f"   [success]✓[/success] Found {result.discovery_count} metrics")
        console.print()
    else:
        info("No Prometheus URL provided - showing intent structure only")
        console.print(
            "   [muted]Tip: Add --prometheus-url to validate against real metrics[/muted]"
        )
        console.print()


def _display_intent_results(result: ValidationResult) -> None:
    """Display individual intent resolution results."""
    console.print("[bold]Resolving intents:[/bold]")
    console.print("[muted]─[/muted]" * 60)

    all_intents = (
        result.resolved + result.synthesized + result.custom + result.fallback + result.unresolved
    )

    for intent in sorted(all_intents, key=lambda x: x.name):
        _display_single_intent(intent)


def _display_single_intent(intent: IntentResult) -> None:
    """Display a single intent result."""
    if intent.status == ResolutionStatus.RESOLVED:
        console.print(f"  [success]✓[/success] {intent.name}")
        console.print(f"     [muted]Resolved:[/muted] {intent.metric_name}")
    elif intent.status == ResolutionStatus.CUSTOM:
        console.print(f"  [highlight]⚙[/highlight] {intent.name}")
        console.print(f"     [muted]Custom:[/muted] {intent.metric_name}")
    elif intent.status == ResolutionStatus.FALLBACK:
        console.print(f"  [warning]⚠[/warning] {intent.name}")
        console.print(f"     [muted]Fallback:[/muted] {intent.metric_name}")
        console.print(f"     [muted]Note:[/muted] {intent.message}")
    elif intent.status == ResolutionStatus.SYNTHESIZED:
        console.print(f"  [cyan]↻[/cyan] {intent.name}")
        console.print(f"     [muted]Synthesized:[/muted] {intent.metric_name}")
        console.print(f"     [muted]Expression:[/muted] {intent.synthesis_expr}")
    else:
        console.print(f"  [error]✗[/error] {intent.name}")
        console.print(f"     [muted]{intent.message}[/muted]")
    console.print()


def _display_summary(result: ValidationResult) -> None:
    """Display validation summary."""
    console.print("[muted]─[/muted]" * 60)
    console.print("[bold]Summary:[/bold]")
    console.print(f"   [muted]Total intents:[/muted] {result.total}")
    console.print(f"   [success]✓[/success] Resolved: {result.resolved_count}")
    if result.custom:
        console.print(f"   [highlight]⚙[/highlight] Custom: {len(result.custom)}")
    if result.fallback:
        console.print(f"   [warning]⚠[/warning] Fallback: {len(result.fallback)}")
    console.print(f"   [error]✗[/error] Unresolved: {len(result.unresolved)}")
    console.print()


def _display_final_verdict(result: ValidationResult, prometheus_url: Optional[str]) -> int:
    """Display final verdict and return exit code."""
    if result.has_unresolved:
        if prometheus_url:
            warning("Some intents could not be resolved. Dashboard will include guidance panels.")
            console.print(
                "[muted]See exporter recommendations above to enable missing metrics.[/muted]"
            )
            return 2
        else:
            info("Run with --prometheus-url to validate against real metrics.")
            return 0
    else:
        success("All intents resolved successfully!")
        return 0


def list_intents_command(technology: Optional[str] = None) -> int:
    """List all available metric intents.

    Args:
        technology: Filter by technology (postgresql, redis, etc.)

    Returns:
        Exit code (0 for success)
    """
    header("Available Metric Intents")
    console.print()

    if technology:
        intents = get_intents_for_technology(technology)
        console.print(f"[bold]Intents for {technology}:[/bold]")
    else:
        intents = ALL_INTENTS
        console.print(f"[bold]All intents ({len(intents)} total):[/bold]")

    console.print()

    current_tech = None
    for name, intent in sorted(intents.items()):
        tech = name.split(".")[0]
        if tech != current_tech:
            current_tech = tech
            console.print(f"  [cyan][{tech.upper()}][/cyan]")

        console.print(f"    [bold]{name}[/bold]")
        console.print(f"      [muted]Type:[/muted] {intent.metric_type.value}")
        print(f"      Candidates: {', '.join(intent.candidates[:3])}", end="")
        if len(intent.candidates) > 3:
            print(f" (+{len(intent.candidates) - 3} more)")
        else:
            console.print()
        console.print()

    console.print(f"[muted]Supported technologies: {', '.join(list_technologies())}")
    return 0
