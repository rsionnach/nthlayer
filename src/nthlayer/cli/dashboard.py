"""CLI command for generating Grafana dashboards."""

import json
from pathlib import Path
from typing import Optional

import yaml

from nthlayer.cli.ux import console, error, header
from nthlayer.dashboards.builder_sdk import build_dashboard
from nthlayer.specs.parser import parse_service_file


def generate_dashboard_command(
    service_file: str,
    output: Optional[str] = None,
    environment: Optional[str] = None,
    dry_run: bool = False,
    full_panels: bool = False,
    quiet: bool = False,
    prometheus_url: Optional[str] = None,
) -> int:
    """Generate Grafana dashboard from service specification.

    Args:
        service_file: Path to service YAML file
        output: Output file path (default: generated/dashboards/{service}.json)
        environment: Environment name (dev, staging, prod)
        dry_run: Print dashboard JSON without writing file
        full_panels: Include all template panels (default: overview only)
        quiet: Suppress output (for use in orchestrator)
        prometheus_url: Optional Prometheus URL for metric discovery

    Returns:
        Exit code (0 for success, 1 for error)
    """

    def log(msg: str) -> None:
        if not quiet:
            console.print(msg)

    if not quiet:
        header("Generate Grafana Dashboard")
    log("")

    # Show configuration
    log(f"Service: {service_file}")
    if environment:
        log(f"Environment: {environment}")
    if dry_run:
        log("Mode: Dry run (preview only)")
    else:
        log(f"Output: {output or 'generated/dashboards/{service}.json'}")
    log("")

    try:
        # Parse service file
        log("Parsing service specification...")
        context, resources = parse_service_file(service_file, environment=environment)

        log(f"   Service: {context.name}")
        log(f"   Team: {context.team}")
        log(f"   Tier: {context.tier}")
        log(f"   Type: {context.type}")
        log(f"   Resources: {len(resources)} defined")
        log("")

        # Count resource types
        slos = [r for r in resources if r.kind == "SLO"]
        dependencies = [r for r in resources if r.kind == "Dependencies"]

        log(f"   SLOs: {len(slos)}")
        log(f"   Dependencies: {len(dependencies)}")
        log("")

        # Build dashboard
        log("Building dashboard...")
        if full_panels:
            log("   Mode: Full panels (all templates)")
        else:
            log("   Mode: Overview panels (key metrics)")
        if prometheus_url:
            log(f"   Discovery: {prometheus_url}")
        dashboard = build_dashboard(
            context, resources, full_panels=full_panels, prometheus_url=prometheus_url
        )

        # Dashboard is now a dict from SDK builder
        if isinstance(dashboard, dict):
            dashboard_json = dashboard
            title = dashboard.get("title", context.name)
            uid = dashboard.get("uid", f"{context.name}-overview")
            panels = dashboard.get("panels", [])
            panel_count = len(panels)
        else:
            # Legacy object format
            panel_count = len(dashboard.panels)
            for row in dashboard.rows:
                panel_count += len(row.panels)
            title = dashboard.title
            uid = dashboard.uid
            dashboard_json = dashboard.to_grafana_payload()

        log(f"   Title: {title}")
        log(f"   UID: {uid}")
        log(f"   Panels: {panel_count}")
        log("")

        json_str = json.dumps(dashboard_json, indent=2, sort_keys=True)

        if dry_run:
            # Print JSON to stdout (always print for dry run)
            print("Dashboard JSON (dry run):")
            print()
            print(json_str)
            print()
            log("Dashboard generated successfully (dry run)")
            return 0

        # Determine output path
        if output:
            output_path = Path(output)
        else:
            output_dir = Path("generated") / "dashboards"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{context.name}.json"

        # Write to file
        log(f"Writing dashboard to {output_path}...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str)

        log("")
        log("Dashboard generated successfully!")
        log("")

        return 0

    except FileNotFoundError:
        error(f"Service file not found: {service_file}")
        return 1
    except (yaml.YAMLError, ValueError, KeyError, TypeError, OSError) as e:
        error(f"Error generating dashboard: {e}")
        import traceback

        traceback.print_exc()
        return 1
