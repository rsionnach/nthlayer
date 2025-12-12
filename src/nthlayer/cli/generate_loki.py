"""CLI command for generating Loki LogQL alerts."""

from pathlib import Path

from nthlayer.cli.ux import console, error, header, success


def generate_loki_command(
    service_file: str,
    output: str | None = None,
    dry_run: bool = False,
) -> int:
    """Generate Loki LogQL alerts for a service based on dependencies.

    Automatically generates LogQL alert rules for Grafana Loki Ruler
    based on the service's declared dependencies.

    Args:
        service_file: Path to service YAML file
        output: Output path (default: generated/{service}/loki-alerts.yaml)
        dry_run: Preview alerts without writing file

    Returns:
        Exit code (0 for success, 1 for error)

    Example:
        >>> generate_loki_command("payment-api.yaml")
        0
    """
    service_path = Path(service_file)

    if not service_path.exists():
        error(f"Service file not found: {service_file}")
        return 1

    header("Generate Loki Alerts")

    header("Generate Loki Alerts")
    console.print()
    console.print(f"[cyan]Service:[/cyan] {service_path}")
    if dry_run:
        console.print("[muted]Mode: Dry run (preview only)[/muted]")
    console.print()

    try:
        from nthlayer.loki import LokiAlertGenerator
        from nthlayer.loki.generator import extract_dependencies_from_resources
        from nthlayer.specs.parser import parse_service_file

        context, resources = parse_service_file(str(service_path))

        dependencies = extract_dependencies_from_resources(resources)

        generator = LokiAlertGenerator()
        alerts = generator.generate_for_service(
            service_name=context.name,
            service_type=context.type,
            dependencies=dependencies,
            tier=context.tier,
            labels={"team": context.team} if context.team else {},
        )

        console.print(f"[muted]Service:[/muted] {context.name}")
        console.print(f"[muted]Type:[/muted] {context.type}")
        console.print(f"[muted]Tier:[/muted] {context.tier}")
        console.print(
            f"[muted]Dependencies:[/muted] {', '.join(dependencies) if dependencies else 'none'}"
        )
        console.print()
        console.print(f"[success]✓[/success] Generated {len(alerts)} Loki alerts")
        console.print()

        # Group by category
        service_alerts = [a for a in alerts if a.category == "service"]
        dep_alerts = [a for a in alerts if a.category == "dependency"]

        console.print("[bold]Alert breakdown:[/bold]")
        console.print(f"  [muted]Service alerts:[/muted] {len(service_alerts)}")
        console.print(f"  [muted]Dependency alerts:[/muted] {len(dep_alerts)}")
        console.print()

        if dry_run:
            console.print("[bold]Preview of generated alerts:[/bold]")
            console.print("[muted]─[/muted]" * 50)
            yaml_output = generator.to_ruler_yaml(alerts, group_name=context.name)
            print(yaml_output[:2000])
            if len(yaml_output) > 2000:
                console.print(f"[muted]... ({len(yaml_output)} total characters)[/muted]")
        else:
            if not output:
                output = f"generated/{context.name}/loki-alerts.yaml"

            output_path = Path(output)
            generator.write_ruler_file(alerts, output_path, group_name=context.name)
            success(f"Wrote alerts to: {output_path}")

        console.print()
        success("Done!")
        return 0

    except Exception as e:
        error(f"Error generating Loki alerts: {e}")
        import traceback

        traceback.print_exc()
        return 1


def register_loki_parser(subparsers) -> None:
    """Register the generate-loki-alerts subcommand."""
    parser = subparsers.add_parser(
        "generate-loki-alerts",
        help="Generate Loki LogQL alert rules for a service",
    )
    parser.add_argument(
        "service_file",
        help="Path to service YAML file",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: generated/{service}/loki-alerts.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview alerts without writing file",
    )


def handle_loki_command(args) -> int:
    """Handle the generate-loki-alerts subcommand."""
    return generate_loki_command(
        service_file=args.service_file,
        output=getattr(args, "output", None),
        dry_run=getattr(args, "dry_run", False),
    )
