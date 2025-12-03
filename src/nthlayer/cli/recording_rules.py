"""CLI command for generating Prometheus recording rules."""

import sys
from pathlib import Path
from typing import Optional

from nthlayer.recording_rules.builder import build_recording_rules
from nthlayer.recording_rules.models import create_rule_groups
from nthlayer.specs.parser import parse_service_file


def generate_recording_rules_command(
    service_file: str,
    output: Optional[str] = None,
    environment: Optional[str] = None,
    dry_run: bool = False
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
        print("=" * 70)
        print("  NthLayer: Generate Prometheus Recording Rules")
        print("=" * 70)
        print()
        print(f"Service: {service_file}")
        
        if environment:
            print(f"🌍 Environment: {environment}")
        
        if dry_run:
            print("Mode: Dry run (preview only)")
        else:
            if output:
                print(f"Output: {output}")
            else:
                print("Output: generated/recording-rules/{service}.yaml")
        
        print()
        
        # Parse service specification
        print("📋 Parsing service specification...")
        context, resources = parse_service_file(service_file, environment=environment)
        
        # Print service info
        print(f"   Service: {context.name}")
        print(f"   Team: {context.team}")
        print(f"   Tier: {context.tier}")
        print(f"   Type: {context.type}")
        
        slo_count = sum(1 for r in resources if r.kind == "SLO")
        print(f"   SLOs: {slo_count}")
        
        print()
        
        # Build recording rules
        print("🏗️  Building recording rules...")
        groups = build_recording_rules(context, resources)
        
        # Count rules
        total_rules = sum(len(group.rules) for group in groups)
        
        print(f"   Groups: {len(groups)}")
        print(f"   Rules: {total_rules}")
        
        for group in groups:
            print(f"   - {group.name}: {len(group.rules)} rules (interval: {group.interval})")
        
        print()
        
        # Generate YAML
        yaml_output = create_rule_groups(groups)
        
        if dry_run:
            # Print to stdout
            print("📄 Recording rules YAML (dry run):")
            print()
            print(yaml_output)
        else:
            # Write to file
            if not output:
                output_dir = Path("generated/recording-rules")
                output_dir.mkdir(parents=True, exist_ok=True)
                output = str(output_dir / f"{context.name}.yaml")
            
            print(f"💾 Writing recording rules to {output}...")
            
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(yaml_output)
            
            print()
            print("✅ Recording rules generated successfully!")
            print()
            print("📊 Next steps:")
            print("   1. Add to Prometheus configuration:")
            print("      rule_files:")
            print(f"        - {output}")
            print()
            print("   2. Reload Prometheus:")
            print("      curl -X POST http://prometheus:9090/-/reload")
            print()
            print("   3. Verify rules are loaded:")
            print("      curl http://prometheus:9090/api/v1/rules")
            print()
        
        return 0
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error generating recording rules: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
