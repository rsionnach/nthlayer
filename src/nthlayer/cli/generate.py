"""
Generate SLO command.
"""

from __future__ import annotations

from pathlib import Path

from nthlayer.cli.ux import console, error, header, info, success
from nthlayer.generators.sloth import generate_sloth_spec


def generate_slo_command(
    service_file: str,
    output_dir: str = "generated",
    format: str = "sloth",
    environment: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    Generate SLO configs from service definition.

    Args:
        service_file: Path to service YAML file
        output_dir: Output directory for generated files
        format: Output format (sloth, prometheus, openslo)
        environment: Environment name (dev, staging, prod) - optional
        dry_run: Preview without writing files

    Returns:
        Exit code (0 = success, 1 = error)
    """
    header("Generate SLOs")
    console.print()

    if environment:
        console.print(f"[info]Environment:[/info] {environment}")
        console.print()

    if dry_run:
        info("DRY RUN MODE - No files will be written")
        console.print()

    # For MVP, only support sloth format
    if format not in ["sloth"]:
        error(f"Unsupported format: {format}")
        console.print("   [muted]Supported formats: sloth[/muted]")
        console.print()
        return 1

    # Generate based on format
    if format == "sloth":
        output_path = Path(output_dir) / "sloth"

        if dry_run:
            console.print(f"Would generate Sloth spec to: {output_path}")
            console.print()
            return 0

        result = generate_sloth_spec(service_file, output_path, environment=environment)

        if not result.success:
            error(f"Generation failed: {result.error}")
            console.print()
            return 1

        success(f"Generated SLOs for {result.service}")
        console.print(f"   [muted]SLO count:[/muted] {result.slo_count}")
        console.print(f"   [muted]Output:[/muted] {result.output_file}")
        console.print()
        console.print("[bold]Generated SLOs:[/bold]")

        # Read and display SLO names
        import yaml

        if result.output_file:
            with open(result.output_file) as f:
                sloth_spec = yaml.safe_load(f)
                for slo in sloth_spec.get("slos", []):
                    name = slo.get("name", "unknown")
                    objective = slo.get("objective", 0)
                    console.print(
                        f"   [success]•[/success] {result.service}-{name} "
                        f"[muted]({objective}%)[/muted]"
                    )

        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print(f"   [muted]1.[/muted] Review generated spec: {result.output_file}")
        console.print(
            f"   [muted]2.[/muted] Generate Prometheus rules: "
            f"[info]sloth generate -i {result.output_file}[/info]"
        )
        console.print("   [muted]3.[/muted] Deploy rules to Prometheus")
        console.print()

    return 0
