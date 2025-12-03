"""CLI command for generating Grafana dashboards."""

import json
from pathlib import Path
from typing import Optional

from nthlayer.dashboards.builder import build_dashboard
from nthlayer.specs.parser import parse_service_file


def generate_dashboard_command(
    service_file: str,
    output: Optional[str] = None,
    environment: Optional[str] = None,
    dry_run: bool = False,
    full_panels: bool = False,
) -> int:
    """Generate Grafana dashboard from service specification.
    
    Args:
        service_file: Path to service YAML file
        output: Output file path (default: generated/dashboards/{service}.json)
        environment: Environment name (dev, staging, prod)
        dry_run: Print dashboard JSON without writing file
        full_panels: Include all template panels (default: overview only)
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    print("=" * 70)
    print("  NthLayer: Generate Grafana Dashboard")
    print("=" * 70)
    print()
    
    # Show configuration
    print(f"Service: {service_file}")
    if environment:
        print(f"🌍 Environment: {environment}")
    if dry_run:
        print("Mode: Dry run (preview only)")
    else:
        print(f"Output: {output or 'generated/dashboards/{service}.json'}")
    print()
    
    try:
        # Parse service file
        print("📋 Parsing service specification...")
        context, resources = parse_service_file(service_file, environment=environment)
        
        print(f"   Service: {context.name}")
        print(f"   Team: {context.team}")
        print(f"   Tier: {context.tier}")
        print(f"   Type: {context.type}")
        print(f"   Resources: {len(resources)} defined")
        print()
        
        # Count resource types
        slos = [r for r in resources if r.kind == "SLO"]
        dependencies = [r for r in resources if r.kind == "Dependencies"]
        
        print(f"   SLOs: {len(slos)}")
        print(f"   Dependencies: {len(dependencies)}")
        print()
        
        # Build dashboard
        print("🏗️  Building dashboard...")
        if full_panels:
            print("   Mode: Full panels (all templates)")
        else:
            print("   Mode: Overview panels (key metrics)")
        dashboard = build_dashboard(context, resources, full_panels=full_panels)
        
        # Count dashboard components
        panel_count = len(dashboard.panels)
        for row in dashboard.rows:
            panel_count += len(row.panels)
        
        print(f"   Title: {dashboard.title}")
        print(f"   UID: {dashboard.uid}")
        print(f"   Rows: {len(dashboard.rows)}")
        print(f"   Panels: {panel_count}")
        print(f"   Variables: {len(dashboard.template_variables)}")
        print()
        
        # Generate JSON
        dashboard_json = dashboard.to_grafana_payload()
        json_str = json.dumps(dashboard_json, indent=2)
        
        if dry_run:
            # Print JSON to stdout
            print("📄 Dashboard JSON (dry run):")
            print()
            print(json_str)
            print()
            print("✅ Dashboard generated successfully (dry run)")
            return 0
        
        # Determine output path
        if output:
            output_path = Path(output)
        else:
            output_dir = Path("generated") / "dashboards"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{context.name}.json"
        
        # Write to file
        print(f"💾 Writing dashboard to {output_path}...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str)
        
        print()
        print("✅ Dashboard generated successfully!")
        print()
        print("📊 Next steps:")
        print("   1. Import to Grafana:")
        print("      curl -X POST http://grafana:3000/api/dashboards/db \\")
        print("           -H 'Content-Type: application/json' \\")
        print("           -H 'Authorization: Bearer $GRAFANA_TOKEN' \\")
        print(f"           -d @{output_path}")
        print()
        print(f"   2. Or manually import {output_path} in Grafana UI")
        print()
        
        return 0
        
    except FileNotFoundError:
        print(f"❌ Error: Service file not found: {service_file}")
        return 1
    except Exception as e:
        print(f"❌ Error generating dashboard: {e}")
        import traceback
        traceback.print_exc()
        return 1
