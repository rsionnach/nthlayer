"""CLI command for generating Backstage entity JSON."""

from pathlib import Path

from nthlayer.cli.ux import console, error, header, success
from nthlayer.generators.backstage import generate_backstage_entity


def generate_backstage_command(
    service_file: str,
    output: str | None = None,
    environment: str | None = None,
    dry_run: bool = False,
    prometheus_url: str | None = None,
) -> int:
    """Generate Backstage entity JSON for a service.

    Creates a JSON artifact that Backstage can consume to display NthLayer
    reliability data (SLOs, error budgets, scorecard, deployment gate).

    Args:
        service_file: Path to service YAML file
        output: Output directory (default: generated/{service}/)
        environment: Optional environment name (dev, staging, prod)
        dry_run: Preview without writing file
        prometheus_url: Optional Prometheus URL for live data (not used in static mode)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    service_path = Path(service_file)

    # Validate input file exists
    if not service_path.exists():
        error(f"Service file not found: {service_file}")
        return 1

    # Determine output directory
    if not output:
        service_name = service_path.stem
        output = f"generated/{service_name}"

    output_dir = Path(output)

    # Print header
    header("Generate Backstage Entity")
    console.print()
    console.print(f"[cyan]Service:[/cyan] {service_path}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    if dry_run:
        console.print("[muted]Mode: Dry run (preview only)[/muted]")
    else:
        console.print(f"[cyan]Output:[/cyan] {output_dir / 'backstage.json'}")
    console.print()

    try:
        if dry_run:
            # Generate without writing to see what would be created
            from nthlayer.specs.loader import load_manifest

            manifest = load_manifest(
                service_path,
                environment=environment,
                suppress_deprecation_warning=True,
            )

            console.print("[muted]Dry run - backstage.json not written[/muted]")
            console.print()
            console.print("[bold]Would generate:[/bold]")
            console.print(f"   [cyan]Service:[/cyan] {manifest.name}")
            console.print(f"   [cyan]Team:[/cyan] {manifest.team}")
            console.print(f"   [cyan]Tier:[/cyan] {manifest.tier}")
            console.print(f"   [cyan]Type:[/cyan] {manifest.type}")
            console.print(f"   [cyan]SLOs:[/cyan] {len(manifest.slos)}")
            console.print()
            output_path = output_dir / "backstage.json"
            console.print(f"[muted]Run without --dry-run to write to {output_path}[/muted]")
            return 0

        # Generate Backstage entity
        result = generate_backstage_entity(
            service_file=service_path,
            output_dir=output_dir,
            prometheus_url=prometheus_url,
            environment=environment,
        )

        if not result.success:
            error(f"Generation failed: {result.error}")
            return 1

        success(f"Generated backstage.json with {result.slo_count} SLO(s)")
        console.print()
        console.print("[bold]Output:[/bold]")
        console.print(f"   {result.output_file}")
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("   [cyan]1.[/cyan] Configure Backstage catalog to read the JSON:")
        catalog_yaml = f"""      [muted]catalog:
        locations:
          - type: file
            target: ./{result.output_file}[/muted]"""
        console.print(catalog_yaml)
        console.print()
        console.print("   [cyan]2.[/cyan] Or annotate your Component entity:")
        annotation_yaml = f"""      [muted]metadata:
        annotations:
          nthlayer.dev/entity: ./{result.output_file}[/muted]"""
        console.print(annotation_yaml)

        return 0

    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"Error generating Backstage entity: {e}")
        import traceback

        traceback.print_exc()
        return 1
