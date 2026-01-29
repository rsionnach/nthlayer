"""
CLI command for migrating legacy NthLayer format to OpenSRM format.

Usage:
    nthlayer migrate service.yaml
    nthlayer migrate service.yaml --output /tmp/
    nthlayer migrate service.yaml --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from nthlayer.cli.ux import console, error, header, success, warning
from nthlayer.specs.loader import load_manifest
from nthlayer.specs.manifest import SourceFormat


def register_migrate_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register the migrate command parser."""
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate legacy NthLayer service.yaml to OpenSRM format",
    )
    migrate_parser.add_argument(
        "service_yaml",
        help="Path to legacy service YAML file",
    )
    migrate_parser.add_argument(
        "--output",
        "-o",
        help="Output directory (default: same directory as input)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migrated YAML without writing file",
    )
    migrate_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )


def handle_migrate_command(args: argparse.Namespace) -> int:
    """Handle the migrate command."""
    return migrate_command(
        service_yaml=args.service_yaml,
        output_dir=getattr(args, "output", None),
        dry_run=getattr(args, "dry_run", False),
        force=getattr(args, "force", False),
    )


def migrate_command(
    service_yaml: str,
    output_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """
    Migrate legacy NthLayer format to OpenSRM format.

    Args:
        service_yaml: Path to legacy service YAML file
        output_dir: Output directory (default: same directory as input)
        dry_run: If True, print output without writing file
        force: If True, overwrite existing files

    Returns:
        Exit code (0 for success, 1 for error)
    """
    input_path = Path(service_yaml)

    if not input_path.exists():
        error(f"File not found: {service_yaml}")
        return 1

    # Load manifest (auto-detects format)
    try:
        manifest = load_manifest(input_path, suppress_deprecation_warning=True)
    except Exception as e:
        error(f"Failed to parse {service_yaml}: {e}")
        return 1

    # Check if already OpenSRM format
    if manifest.source_format == SourceFormat.OPENSRM:
        console.print()
        header(f"Migration: {manifest.name}")
        console.print()
        success("File is already in OpenSRM format. No migration needed.")
        console.print()
        return 0

    # Convert to OpenSRM format
    opensrm_data = manifest.to_dict()

    # Generate output YAML
    yaml_output = yaml.dump(
        opensrm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    # Add header comment
    header_comment = (
        "# OpenSRM Service Reliability Manifest\n"
        "# Migrated from legacy NthLayer format\n"
        f"# Original file: {input_path.name}\n"
        "#\n"
        "# For more information, see:\n"
        "# https://github.com/rsionnach/opensrm\n"
        "#\n\n"
    )
    yaml_output = header_comment + yaml_output

    if dry_run:
        # Print to stdout
        console.print()
        header(f"Migration Preview: {manifest.name}")
        console.print()
        console.print("[muted]─" * 60 + "[/muted]")
        print(yaml_output)
        console.print("[muted]─" * 60 + "[/muted]")
        console.print()
        console.print("[muted]Run without --dry-run to write to file[/muted]")
        return 0

    # Determine output path
    if output_dir:
        output_path = Path(output_dir) / f"{manifest.name}.reliability.yaml"
    else:
        output_path = input_path.parent / f"{manifest.name}.reliability.yaml"

    # Check if output file exists
    if output_path.exists() and not force:
        error(f"Output file already exists: {output_path}")
        console.print("[muted]Use --force to overwrite[/muted]")
        return 1

    # Write output file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(yaml_output)
    except Exception as e:
        error(f"Failed to write {output_path}: {e}")
        return 1

    # Print summary
    console.print()
    header(f"Migration Complete: {manifest.name}")
    console.print()

    console.print("  [success]✓[/success] Converted from legacy NthLayer format to OpenSRM")
    console.print()

    console.print("  [bold]Changes:[/bold]")
    console.print("    • Added apiVersion: srm/v1")
    console.print("    • Added kind: ServiceReliabilityManifest")
    console.print("    • Restructured metadata and spec sections")

    if manifest.type in ("background-job", "pipeline"):
        original_type = "background-job" if manifest.type == "worker" else "pipeline"
        console.print(f"    • Normalized service type: {original_type} → {manifest.type}")

    console.print()
    console.print(f"  [bold]Output:[/bold] {output_path}")
    console.print()

    # Show next steps
    console.print("  [bold]Next steps:[/bold]")
    console.print(f"    1. Review the migrated file: [info]{output_path}[/info]")
    console.print(f"    2. Validate: [info]nthlayer validate {output_path}[/info]")
    console.print(f"    3. Test: [info]nthlayer plan {output_path}[/info]")
    console.print()

    # Warn about legacy file
    warning(f"The legacy file ({input_path.name}) can be removed after validation")
    console.print()

    return 0
