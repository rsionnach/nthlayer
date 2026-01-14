"""
CLI command for applying (generating) all service resources.
"""

import json
from pathlib import Path
from typing import List, Optional

from nthlayer.cli.plan import plan_command
from nthlayer.cli.ux import console
from nthlayer.orchestrator import ApplyResult, ServiceOrchestrator


def print_apply_summary(result: ApplyResult, verbose: bool = False) -> None:
    """Print clean apply summary with rich formatting."""
    console.print()

    # Resource type display config: (label, detail_fn)
    resource_config = {
        "slos": ("SLOs", lambda c: f"{c} created"),
        "alerts": ("Alerts", lambda c: f"{c} generated"),
        "dashboard": ("Dashboard", lambda c: f"{c} generated"),
        "recording-rules": ("Recording", lambda c: f"{c} rules"),
        "pagerduty": ("PagerDuty", lambda c: "configured"),
    }

    warning_types = _get_warning_types(result)

    # Print each resource on one line with rich styling
    for resource_type, count in result.resources_created.items():
        config = resource_config.get(resource_type)
        if config:
            label, detail_fn = config
            detail = detail_fn(count)
        else:
            label = resource_type.replace("-", " ").title()
            detail = f"{count} created"

        if resource_type in warning_types:
            console.print(f"  [yellow]⚠ {label:<12}[/yellow] {detail}")
        else:
            console.print(f"  [green]✓ {label:<12}[/green] {detail}")

    # Summary line
    console.print()
    duration = f" in {result.duration_seconds:.1f}s" if result.duration_seconds > 0 else ""
    if result.success:
        console.print(
            f"[bold green]Applied {result.total_resources} resources{duration}[/bold green] "
            f"→ [cyan]{result.output_dir}/[/cyan]"
        )
    else:
        console.print(
            f"[bold yellow]Applied {result.total_resources} resources "
            f"with errors{duration}[/bold yellow]"
        )

    # Show warnings/errors at end (grouped)
    if result.errors:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for err in result.errors:
            # Truncate long errors in non-verbose mode
            if not verbose and len(err) > 80:
                err = err[:77] + "..."
            console.print(f"  [dim]•[/dim] {err}")

    # Only show file list in verbose mode
    if verbose and result.output_dir.exists():
        console.print()
        console.print("[bold]Generated files:[/bold]")
        for file in sorted(result.output_dir.iterdir()):
            if file.is_file():
                size = file.stat().st_size
                size_str = f"{size:,}B" if size < 1024 else f"{size/1024:.1f}KB"
                console.print(f"  [dim]•[/dim] {file.name} [dim]({size_str})[/dim]")

    console.print()


def _get_warning_types(result: ApplyResult) -> set:
    """Get resource types that had warnings."""
    warning_types = set()
    for error in result.errors:
        error_lower = error.lower()
        if "pagerduty" in error_lower:
            warning_types.add("pagerduty")
        elif "dashboard" in error_lower:
            warning_types.add("dashboard")
        elif "alert" in error_lower:
            warning_types.add("alerts")
    return warning_types


def print_apply_json(result: ApplyResult) -> None:
    """Print apply result in JSON format."""
    output = {
        "service_name": result.service_name,
        "resources_created": result.resources_created,
        "total_resources": result.total_resources,
        "duration_seconds": result.duration_seconds,
        "output_dir": str(result.output_dir),
        "errors": result.errors,
        "success": result.success,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


def apply_command(
    service_yaml: str,
    env: Optional[str] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
    skip: Optional[List[str]] = None,
    only: Optional[List[str]] = None,
    force: bool = False,
    verbose: bool = False,
    output_format: str = "text",
    push_grafana: bool = False,
    push_ruler: bool = False,
    lint: bool = False,
    prometheus_url: Optional[str] = None,
) -> int:
    """
    Generate all resources for a service.

    Args:
        service_yaml: Path to service YAML file
        env: Environment name (dev, staging, prod)
        output_dir: Output directory for generated files
        dry_run: Preview without writing files (same as plan)
        skip: Resource types to skip (e.g., ['alerts', 'pagerduty'])
        only: Only generate specific resource types
        force: Force regeneration, ignore cache
        verbose: Show detailed progress
        output_format: Output format (text, json)
        push_grafana: Push dashboard to Grafana Cloud
        push_ruler: Push alerts to Mimir/Cortex Ruler API
        lint: Validate generated alerts with pint
        prometheus_url: Prometheus URL for metric discovery

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Dry-run delegates to plan command
    if dry_run:
        return plan_command(service_yaml, env=env, verbose=verbose)

    # Create orchestrator
    orchestrator = ServiceOrchestrator(
        Path(service_yaml), env=env, push_to_grafana=push_grafana, prometheus_url=prometheus_url
    )

    # Override output directory if specified
    if output_dir:
        orchestrator.output_dir = Path(output_dir)

    # Apply
    result = orchestrator.apply(skip=skip, only=only, force=force, verbose=verbose)

    # Print result
    if output_format == "json":
        print_apply_json(result)
    else:  # text (default)
        print_apply_summary(result, verbose=verbose)

    # Lint generated alerts if requested
    if lint and result.success:
        lint_exit_code = _lint_generated_alerts(result.output_dir, verbose=verbose)
        if lint_exit_code != 0:
            return lint_exit_code

    # Push alerts to Mimir/Cortex Ruler if requested
    if push_ruler and result.success:
        ruler_exit_code = _push_to_mimir_ruler(
            result.output_dir, result.service_name, verbose=verbose
        )
        if ruler_exit_code != 0:
            return ruler_exit_code

    return 0 if result.success else 1


def _lint_generated_alerts(output_dir: Path, verbose: bool = False) -> int:
    """Lint generated alerts with pint."""
    from nthlayer.validation import PintLinter, is_pint_available

    alerts_file = output_dir / "alerts.yaml"
    if not alerts_file.exists():
        if verbose:
            console.print("  [dim]ℹ No alerts.yaml found, skipping lint[/dim]")
        return 0

    if not is_pint_available():
        console.print()
        console.print("  [yellow]⚠ pint not installed - skipping alert validation[/yellow]")
        console.print("    [dim]Install: brew install cloudflare/cloudflare/pint[/dim]")
        console.print(
            "    [dim]Or download from: https://github.com/cloudflare/pint/releases[/dim]"
        )
        return 0  # Don't fail, just warn

    console.print()
    console.print("[bold]Validating alerts with pint...[/bold]")

    linter = PintLinter()
    result = linter.lint_file(alerts_file)

    console.print(f"  {result.summary()}")

    if result.issues:
        for issue in result.issues:
            if issue.is_error:
                icon = "[red]✗[/red]"
            elif issue.is_warning:
                icon = "[yellow]⚠[/yellow]"
            else:
                icon = "[blue]ℹ[/blue]"
            line_info = f":{issue.line}" if issue.line else ""
            console.print(f"    {icon} [dim][{issue.check}]{line_info}[/dim] {issue.message}")

    if not result.passed:
        console.print()
        console.print("  [red]Alert validation failed. Fix issues before deploying.[/red]")
        return 1

    return 0


def _push_to_mimir_ruler(output_dir: Path, service_name: str, verbose: bool = False) -> int:
    """Push generated alerts to Mimir/Cortex Ruler API."""
    import asyncio
    import os

    from nthlayer.providers.mimir import MimirRulerError, MimirRulerProvider

    alerts_file = output_dir / "alerts.yaml"
    if not alerts_file.exists():
        if verbose:
            console.print("  [dim]ℹ No alerts.yaml found, skipping Mimir push[/dim]")
        return 0

    # Get Mimir configuration from environment
    ruler_url = os.environ.get("MIMIR_RULER_URL")
    if not ruler_url:
        console.print()
        console.print("  [yellow]⚠ MIMIR_RULER_URL not set - skipping Mimir push[/yellow]")
        console.print("    [dim]Set: export MIMIR_RULER_URL=https://your-mimir:8080[/dim]")
        return 0

    tenant_id = os.environ.get("MIMIR_TENANT_ID")
    api_key = os.environ.get("MIMIR_API_KEY")
    username = os.environ.get("MIMIR_USERNAME")
    password = os.environ.get("MIMIR_PASSWORD")

    console.print()
    console.print("[bold]Pushing alerts to Mimir Ruler...[/bold]")
    console.print(f"  [dim]URL: {ruler_url}[/dim]")
    if tenant_id:
        console.print(f"  [dim]Tenant: {tenant_id}[/dim]")

    # Read alerts YAML
    rules_yaml = alerts_file.read_text()

    # Create provider and push
    provider = MimirRulerProvider(
        ruler_url=ruler_url,
        tenant_id=tenant_id,
        api_key=api_key,
        username=username,
        password=password,
    )

    try:
        result = asyncio.run(provider.push_rules(service_name, rules_yaml))

        if result.success:
            console.print(
                f"  [green]✓ Pushed {result.groups_pushed} rule group(s) "
                f"to namespace '{result.namespace}'[/green]"
            )
            return 0
        else:
            console.print(f"  [red]✗ {result.message}[/red]")
            return 1

    except MimirRulerError as e:
        console.print(f"  [red]✗ Mimir error: {e}[/red]")
        return 1
