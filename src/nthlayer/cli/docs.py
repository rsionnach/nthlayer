"""CLI command for generating service documentation."""

from pathlib import Path

import structlog

from nthlayer.cli.ux import console, error, header, success

logger = structlog.get_logger()


def generate_docs_command(
    service_file: str,
    output: str | None = None,
    environment: str | None = None,
    include_adr: bool = False,
    include_api: bool = False,
    dry_run: bool = False,
) -> int:
    """Generate documentation from a service reliability manifest.

    Args:
        service_file: Path to service YAML file
        output: Output directory (default: generated/{service}/)
        environment: Optional environment name (dev, staging, prod)
        include_adr: Generate ADR scaffold
        include_api: Generate API documentation stub
        dry_run: Preview without writing files

    Returns:
        Exit code (0 for success, 1 for error)
    """
    service_path = Path(service_file)

    if not service_path.exists():
        error(f"Service file not found: {service_file}")
        return 1

    if not output:
        service_name = service_path.stem
        output = f"generated/{service_name}"

    output_dir = Path(output)

    header("Generate Service Documentation")
    console.print()
    console.print(f"[cyan]Service:[/cyan] {service_path}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    if include_adr:
        console.print("[cyan]ADR scaffold:[/cyan] enabled")
    if include_api:
        console.print("[cyan]API docs:[/cyan] enabled")
    if dry_run:
        console.print("[muted]Mode: Dry run (preview only)[/muted]")
    else:
        console.print(f"[cyan]Output:[/cyan] {output_dir}")
    console.print()

    try:
        if dry_run:
            from nthlayer.specs.loader import load_manifest

            manifest = load_manifest(
                service_path,
                environment=environment,
                suppress_deprecation_warning=True,
            )

            console.print("[muted]Dry run - no files written[/muted]")
            console.print()
            console.print("[bold]Would generate:[/bold]")
            console.print(f"   [cyan]Service:[/cyan] {manifest.name}")
            console.print(f"   [cyan]Team:[/cyan] {manifest.team}")
            console.print(f"   [cyan]Tier:[/cyan] {manifest.tier}")
            console.print(f"   [cyan]Type:[/cyan] {manifest.type}")
            console.print(f"   [cyan]SLOs:[/cyan] {len(manifest.slos)}")
            console.print(f"   [cyan]Dependencies:[/cyan] {len(manifest.dependencies)}")

            files = ["README.md"]
            if include_adr:
                files.extend(
                    ["adr/README.md", "adr/template.md", "adr/001-initial-architecture.md"]
                )
            if include_api:
                files.append("api.md")

            console.print()
            console.print("[bold]Files:[/bold]")
            for f in files:
                console.print(f"   {f}")
            console.print()
            console.print(f"[muted]Run without --dry-run to write to {output_dir}[/muted]")
            return 0

        from nthlayer.generators.docs import generate_service_docs

        result = generate_service_docs(
            service_file=service_path,
            output_dir=output_dir,
            environment=environment,
            include_adr=include_adr,
            include_api=include_api,
        )

        if not result.success:
            error(f"Generation failed: {result.error}")
            return 1

        success(f"Generated {len(result.files_generated)} documentation file(s)")
        console.print()
        console.print("[bold]Files generated:[/bold]")
        for f in result.files_generated:
            console.print(f"   {output_dir / f}")
        console.print()

        return 0

    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"Error generating documentation: {e}")
        logger.error("docs_generation_failed", err=str(e), exc_info=True)
        return 1
