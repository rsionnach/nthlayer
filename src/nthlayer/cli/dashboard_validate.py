"""CLI command for validating dashboard metric resolution."""

from typing import Optional

import yaml

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.dashboards.intents import (
    ALL_INTENTS,
    get_intents_for_technology,
    list_technologies,
)
from nthlayer.dashboards.resolver import ResolutionStatus, create_resolver
from nthlayer.specs.parser import parse_service_file


def validate_dashboard_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    technology: Optional[str] = None,
    show_all: bool = False,
) -> int:
    """Validate dashboard metric resolution for a service.

    This command discovers metrics from Prometheus and shows how each
    intent would be resolved, including fallbacks and guidance.

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus URL for metric discovery
        technology: Specific technology to validate (postgresql, redis, etc.)
        show_all: Show all intents, not just those for service dependencies

    Returns:
        Exit code (0 for success, 1 for errors, 2 for warnings)
    """
    header("Dashboard Metric Validation")

    header("Dashboard Metric Validation")
    console.print()

    try:
        # Parse service file
        console.print(f"[cyan]Service:[/cyan] {service_file}")
        context, resources = parse_service_file(service_file)

        console.print(f"   [muted]Name:[/muted] {context.name}")
        console.print(f"   [muted]Team:[/muted] {context.team}")
        console.print()

        # Extract dependencies
        dependencies = [r for r in resources if r.kind == "Dependencies"]
        technologies = set()

        for dep in dependencies:
            spec = dep.spec if hasattr(dep, "spec") else {}
            databases = spec.get("databases", []) if isinstance(spec, dict) else []
            caches = spec.get("caches", []) if isinstance(spec, dict) else []

            for db in databases:
                db_type = db.get("type", "") if isinstance(db, dict) else getattr(db, "type", "")
                if db_type:
                    technologies.add(db_type)
            for cache in caches:
                cache_type = (
                    cache.get("type", "redis")
                    if isinstance(cache, dict)
                    else getattr(cache, "type", "redis")
                )
                technologies.add(cache_type)

        # Always include HTTP for API services
        if context.type in ("api", "service", "web"):
            technologies.add("http")

        # Filter by technology if specified
        if technology:
            technologies = {technology}

        tech_list = ", ".join(sorted(technologies)) or "none detected"
        console.print(f"[muted]Technologies to validate:[/muted] {tech_list}")
        console.print()

        # Create resolver
        custom_overrides = {}
        for resource in resources:
            if hasattr(resource, "spec") and isinstance(resource.spec, dict):
                metrics = resource.spec.get("metrics", {})
                if isinstance(metrics, dict):
                    custom_overrides.update(metrics)

        resolver = create_resolver(prometheus_url=prometheus_url, custom_overrides=custom_overrides)

        # Discover metrics if Prometheus URL provided
        if prometheus_url:
            console.print(f"[cyan]Discovering metrics from {prometheus_url}...[/cyan]")
            try:
                count = resolver.discover_for_service(context.name)
                console.print(f"   [success]✓[/success] Found {count} metrics")
                console.print()
            except (ConnectionError, TimeoutError, ValueError, OSError) as e:
                warning(f"Discovery failed: {e}")
                console.print("   [muted]Continuing without discovery (intents unresolved)[/muted]")
                console.print()
        else:
            info("No Prometheus URL provided - showing intent structure only")
            console.print(
                "   [muted]Tip: Add --prometheus-url to validate against real metrics[/muted]"
            )
            console.print()

        # Collect intents to validate
        intents_to_check = []
        if show_all:
            intents_to_check = list(ALL_INTENTS.keys())
        else:
            for tech in technologies:
                tech_intents = get_intents_for_technology(tech)
                intents_to_check.extend(tech_intents.keys())

        if not intents_to_check:
            info("No intents to validate. Add --technology or --show-all")
            return 0

        # Resolve all intents
        console.print("[bold]Resolving intents:[/bold]")
        console.print("[muted]─[/muted]" * 60)

        resolved_count = 0
        fallback_count = 0
        unresolved_count = 0
        custom_count = 0

        for intent_name in sorted(intents_to_check):
            result = resolver.resolve(intent_name)

            if result.status == ResolutionStatus.RESOLVED:
                console.print(f"  [success]✓[/success] {intent_name}")
                console.print(f"     [muted]Resolved:[/muted] {result.metric_name}")
                resolved_count += 1
            elif result.status == ResolutionStatus.CUSTOM:
                console.print(f"  [highlight]⚙[/highlight] {intent_name}")
                console.print(f"     [muted]Custom:[/muted] {result.metric_name}")
                custom_count += 1
            elif result.status == ResolutionStatus.FALLBACK:
                console.print(f"  [warning]⚠[/warning] {intent_name}")
                console.print(f"     [muted]Fallback:[/muted] {result.metric_name}")
                console.print(f"     [muted]Note:[/muted] {result.message}")
                fallback_count += 1
            elif result.status == ResolutionStatus.SYNTHESIZED:
                console.print(f"  [cyan]↻[/cyan] {intent_name}")
                console.print(f"     [muted]Synthesized:[/muted] {result.metric_name}")
                console.print(f"     [muted]Expression:[/muted] {result.synthesis_expr}")
                resolved_count += 1
            else:
                console.print(f"  [error]✗[/error] {intent_name}")
                console.print(f"     [muted]{result.message}[/muted]")
                unresolved_count += 1

            console.print()

        # Summary
        console.print("[muted]─[/muted]" * 60)
        console.print("[bold]Summary:[/bold]")
        total = resolved_count + fallback_count + unresolved_count + custom_count
        console.print(f"   [muted]Total intents:[/muted] {total}")
        console.print(f"   [success]✓[/success] Resolved: {resolved_count}")
        if custom_count:
            console.print(f"   [highlight]⚙[/highlight] Custom: {custom_count}")
        if fallback_count:
            console.print(f"   [warning]⚠[/warning] Fallback: {fallback_count}")
        console.print(f"   [error]✗[/error] Unresolved: {unresolved_count}")
        console.print()

        # Exit code based on results
        if unresolved_count > 0:
            if prometheus_url:
                warning(
                    "Some intents could not be resolved. Dashboard will include guidance panels."
                )
                console.print(
                    "[muted]See exporter recommendations above to enable missing metrics.[/muted]"
                )
                return 2  # Warning
            else:
                info("Run with --prometheus-url to validate against real metrics.")
                return 0
        else:
            success("All intents resolved successfully!")
            return 0

    except FileNotFoundError:
        error(f"Service file not found: {service_file}")
        return 1
    except (yaml.YAMLError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"{e}")
        import traceback

        traceback.print_exc()
        return 1


def list_intents_command(technology: Optional[str] = None) -> int:
    """List all available metric intents.

    Args:
        technology: Filter by technology (postgresql, redis, etc.)

    Returns:
        Exit code (0 for success)
    """
    header("Dashboard Metric Validation")

    header("Dashboard Metric Validation")
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
