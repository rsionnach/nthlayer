"""CLI command for generating Prometheus recording rules."""

from pathlib import Path
from typing import Optional

from nthlayer.cli.ux import console, error, header, success
from nthlayer.recording_rules.builder import build_recording_rules
from nthlayer.recording_rules.models import create_rule_groups
from nthlayer.specs.parser import parse_service_file


def generate_recording_rules_command(
    service_file: str,
    output: Optional[str] = None,
    environment: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """Generate Prometheus recording rules from service specification.

    Args:
        service_file: Path to service YAML file
        output: Output file path (default: generated/recording-rules/{service}.yaml)
        environment: Environment name (dev, staging, prod)
        dry_run: If True, print YAML to stdout instead of writing file

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Print header
        header("Generate Prometheus Recording Rules")
        console.print()
        console.print(f"[cyan]Service:[/cyan] {service_file}")

        if environment:
            console.print(f"[cyan]Environment:[/cyan] {environment}")

        if dry_run:
            console.print("[muted]Mode: Dry run (preview only)[/muted]")
        else:
            if output:
                console.print(f"[cyan]Output:[/cyan] {output}")
            else:
                console.print("[cyan]Output:[/cyan] generated/recording-rules/{service}.yaml")

        console.print()

        # Parse service specification
        console.print("[bold]Parsing service specification...[/bold]")
        context, resources = parse_service_file(service_file, environment=environment)

        # Print service info
        console.print(f"   [muted]Service:[/muted] {context.name}")
        console.print(f"   [muted]Team:[/muted] {context.team}")
        console.print(f"   [muted]Tier:[/muted] {context.tier}")
        console.print(f"   [muted]Type:[/muted] {context.type}")

        slo_count = sum(1 for r in resources if r.kind == "SLO")
        console.print(f"   [muted]SLOs:[/muted] {slo_count}")

        console.print()

        # Build recording rules
        console.print("[bold]Building recording rules...[/bold]")
        groups = build_recording_rules(context, resources)

        # Count rules
        total_rules = sum(len(group.rules) for group in groups)

        console.print(f"   [muted]Groups:[/muted] {len(groups)}")
        console.print(f"   [muted]Rules:[/muted] {total_rules}")

        for group in groups:
            info = f"{len(group.rules)} rules (interval: {group.interval})"
            console.print(f"   [muted]•[/muted] {group.name}: {info}")

        console.print()

        # Generate YAML
        yaml_output = create_rule_groups(groups)

        if dry_run:
            # Print to stdout
            console.print("[bold]Recording rules YAML (dry run):[/bold]")
            console.print()
            print(yaml_output)
        else:
            # Write to file
            if not output:
                output_dir = Path("generated/recording-rules")
                output_dir.mkdir(parents=True, exist_ok=True)
                output = str(output_dir / f"{context.name}.yaml")

            console.print(f"[cyan]Writing recording rules to {output}...[/cyan]")

            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(yaml_output)

            console.print()
            success("Recording rules generated successfully!")
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print("   [cyan]1.[/cyan] Add to Prometheus configuration:")
            console.print("      rule_files:")
            console.print(f"        - {output}")
            console.print()
            console.print("   [cyan]2.[/cyan] Reload Prometheus:")
            console.print("      [muted]curl -X POST http://prometheus:9090/-/reload[/muted]")
            console.print()
            console.print("   [cyan]3.[/cyan] Verify rules are loaded:")
            console.print("      [muted]curl http://prometheus:9090/api/v1/rules[/muted]")
            console.print()

        return 0

    except FileNotFoundError as e:
        error(f"Error: {e}")
        return 1
    except Exception as e:
        error(f"Error generating recording rules: {e}")
        import traceback

        traceback.print_exc()
        return 1
