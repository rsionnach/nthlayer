"""
Generate SLO command.
"""

from __future__ import annotations

from pathlib import Path

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
    print("=" * 70)
    print("  NthLayer: Generate SLOs")
    print("=" * 70)
    print()
    
    if environment:
        print(f"🌍 Environment: {environment}")
        print()
    
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be written")
        print()
    
    # For MVP, only support sloth format
    if format not in ["sloth"]:
        print(f"❌ Unsupported format: {format}")
        print("   Supported formats: sloth")
        print()
        return 1
    
    # Generate based on format
    if format == "sloth":
        output_path = Path(output_dir) / "sloth"
        
        if dry_run:
            print(f"Would generate Sloth spec to: {output_path}")
            print()
            # TODO: Parse and show what would be generated
            return 0
        
        result = generate_sloth_spec(service_file, output_path, environment=environment)
        
        if not result.success:
            print(f"❌ Generation failed: {result.error}")
            print()
            return 1
        
        print(f"✅ Generated SLOs for {result.service}")
        print(f"   SLO count: {result.slo_count}")
        print(f"   Output: {result.output_file}")
        print()
        print("📋 Generated SLOs:")
        
        # Read and display SLO names
        import yaml
        if result.output_file:
            with open(result.output_file) as f:
                sloth_spec = yaml.safe_load(f)
                for slo in sloth_spec.get("slos", []):
                    name = slo.get("name", "unknown")
                    objective = slo.get("objective", 0)
                    print(f"   • {result.service}-{name} ({objective}%)")
        
        print()
        print("💡 Next steps:")
        print(f"   1. Review generated spec: {result.output_file}")
        print(f"   2. Generate Prometheus rules: sloth generate -i {result.output_file}")
        print("   3. Deploy rules to Prometheus")
        print()
    
    return 0
