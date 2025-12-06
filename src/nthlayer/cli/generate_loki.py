"""CLI command for generating Loki LogQL alerts."""

from pathlib import Path


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
        print(f"Error: Service file not found: {service_file}")
        return 1

    print("=" * 70)
    print("  NthLayer: Generate Loki Alerts")
    print("=" * 70)
    print()
    print(f"Service: {service_path}")
    if dry_run:
        print("Mode: Dry run (preview only)")
    print()

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

        print(f"Service: {context.name}")
        print(f"Type: {context.type}")
        print(f"Tier: {context.tier}")
        print(f"Dependencies: {', '.join(dependencies) if dependencies else 'none'}")
        print()
        print(f"Generated {len(alerts)} Loki alerts")
        print()

        # Group by category
        service_alerts = [a for a in alerts if a.category == "service"]
        dep_alerts = [a for a in alerts if a.category == "dependency"]

        print("Alert breakdown:")
        print(f"  Service alerts: {len(service_alerts)}")
        print(f"  Dependency alerts: {len(dep_alerts)}")
        print()

        if dry_run:
            print("Preview of generated alerts:")
            print("-" * 50)
            yaml_output = generator.to_ruler_yaml(alerts, group_name=context.name)
            print(yaml_output[:2000])
            if len(yaml_output) > 2000:
                print(f"... ({len(yaml_output)} total characters)")
        else:
            if not output:
                output = f"generated/{context.name}/loki-alerts.yaml"

            output_path = Path(output)
            generator.write_ruler_file(alerts, output_path, group_name=context.name)
            print(f"Wrote alerts to: {output_path}")

        print()
        print("Done!")
        return 0

    except Exception as e:
        print(f"Error generating Loki alerts: {e}")
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
