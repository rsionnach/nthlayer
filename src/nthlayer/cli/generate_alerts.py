"""CLI command for generating alerts from awesome-prometheus-alerts."""

from pathlib import Path

from nthlayer.cli.ux import console, error, header
from nthlayer.generators.alerts import generate_alerts_for_service
from nthlayer.specs.environment_alerts import explain_alert_filtering


def generate_alerts_command(
    service_file: str,
    output: str | None = None,
    environment: str | None = None,
    dry_run: bool = False,
    runbook_url: str = "",
    notification_channel: str = "",
) -> int:
    """Generate alerts for a service based on dependencies.

    Automatically generates production-ready alert rules from awesome-prometheus-alerts
    based on the service's declared dependencies.

    Args:
        service_file: Path to service YAML file
        output: Output path (default: generated/alerts/{service}.yaml)
        environment: Optional environment name (dev, staging, prod)
        dry_run: Preview alerts without writing file
        runbook_url: Base URL for runbook links
        notification_channel: Notification channel (pagerduty, slack, etc.)

    Returns:
        Exit code (0 for success, 1 for error)

    Example:
        >>> generate_alerts_command("payment-api.yaml")
        0
    """
    service_path = Path(service_file)

    # Validate input file exists
    if not service_path.exists():
        error(f"Service file not found: {service_file}")
        return 1

    # Determine output path
    if not output:
        service_name = service_path.stem
        output = f"generated/alerts/{service_name}.yaml"

    output_path = None if dry_run else Path(output)

    # Print header
    header("Generate Alerts")

    header("Generate Alerts")
    console.print()
    console.print(f"[cyan]Service:[/cyan] {service_path}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    if dry_run:
        console.print("[muted]Mode: Dry run (preview only)[/muted]")
    else:
        console.print(f"[cyan]Output:[/cyan] {output}")
    console.print()

    # Show alert filtering strategy if environment specified
    if environment:
        from nthlayer.specs.parser import parse_service_file

        try:
            context, _ = parse_service_file(service_path, environment=environment)
            explain_alert_filtering(environment, context.tier)
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            # If parsing fails, continue anyway
            pass

    try:
        # Generate alerts
        alerts = generate_alerts_for_service(
            service_path,
            output_path,
            environment=environment,
            runbook_url=runbook_url,
            notification_channel=notification_channel,
        )

        if not alerts:
            console.print("\n[bold]Tip:[/bold] Add a Dependencies resource to your service YAML:")
            console.print("[muted]   resources:[/muted]")
            console.print("[muted]     - kind: Dependencies[/muted]")
            console.print("[muted]       name: upstream[/muted]")
            console.print("[muted]       spec:[/muted]")
            console.print("[muted]         databases:[/muted]")
            console.print("[muted]           - type: postgres[/muted]")
            console.print("[muted]           - type: redis[/muted]")
            return 1

        if dry_run:
            console.print("\n[muted]Dry run - alerts not written to file[/muted]")
            console.print("\n[bold]Sample alerts generated:[/bold]")
            for i, alert in enumerate(alerts[:5], 1):
                console.print(
                    f"   [cyan]{i}.[/cyan] {alert.name} ({alert.severity}, {alert.technology})"
                )

            if len(alerts) > 5:
                console.print(f"   [muted]... and {len(alerts) - 5} more[/muted]")

            console.print(f"\n[muted]Run without --dry-run to write to {output}[/muted]")
        else:
            console.print("\n[bold]Next steps:[/bold]")
            console.print(f"   [cyan]1.[/cyan] Review generated alerts: cat {output}")
            console.print(f"   [cyan]2.[/cyan] Deploy to Prometheus: kubectl apply -f {output}")
            console.print("   [cyan]3.[/cyan] Verify alerts are firing: check Prometheus UI")

        return 0

    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"Error generating alerts: {e}")
        import traceback

        traceback.print_exc()
        return 1
