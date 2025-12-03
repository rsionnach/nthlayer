"""
CLI command for applying (generating) all service resources.
"""

import json
from pathlib import Path
from typing import List, Optional

from nthlayer.cli.plan import plan_command
from nthlayer.orchestrator import ApplyResult, ServiceOrchestrator


def print_apply_summary(result: ApplyResult) -> None:
    """Print beautiful apply summary."""
    print()
    print("╔" + "═" * 62 + "╗")
    print(f"║  🚀 Applied: {result.service_name:<48} ║")
    print("╚" + "═" * 62 + "╝")
    print()
    
    if result.errors:
        print("❌ Errors:")
        for error in result.errors:
            print(f"   • {error}")
        print()
        
        # Show partial success if any resources were created
        if result.total_resources > 0:
            print(f"⚠️  Partial success: {result.total_resources} resources created")
            print()
    
    if result.total_resources == 0 and not result.errors:
        print("⚠️  No resources generated")
        print()
        return
    
    # Show what was created
    step = 1
    total_steps = len(result.resources_created)
    
    for resource_type, count in result.resources_created.items():
        icon = "✅"
        type_name = resource_type.replace("-", " ").title()
        
        if resource_type == "slos":
            print(f"{icon} [{step}/{total_steps}] SLOs          → {count} created")
        elif resource_type == "alerts":
            print(f"{icon} [{step}/{total_steps}] Alerts        → {count} created")
        elif resource_type == "dashboard":
            print(f"{icon} [{step}/{total_steps}] Dashboard     → {count} created")
        elif resource_type == "recording-rules":
            print(f"{icon} [{step}/{total_steps}] Recording     → {count} created")
        elif resource_type == "pagerduty":
            print(f"{icon} [{step}/{total_steps}] PagerDuty     → {count} created")
        else:
            print(f"{icon} [{step}/{total_steps}] {type_name:<13} → {count} created")
        
        step += 1
    
    print()
    
    # Summary
    if not result.errors:
        print(f"✅ Successfully applied {result.total_resources} resources in {result.duration_seconds:.1f}s")
    else:
        print(f"⚠️  Completed with errors ({result.total_resources} resources created)")
    
    print()
    print(f"📁 Output directory: {result.output_dir}")
    print()
    
    # List generated files
    if result.output_dir.exists():
        print("   Generated files:")
        for file in sorted(result.output_dir.iterdir()):
            if file.is_file():
                size = file.stat().st_size
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                print(f"   • {file.name:<30} ({size_str})")
        print()


def print_apply_json(result: ApplyResult) -> None:
    """Print apply result in JSON format."""
    output = {
        "service_name": result.service_name,
        "resources_created": result.resources_created,
        "total_resources": result.total_resources,
        "duration_seconds": result.duration_seconds,
        "output_dir": str(result.output_dir),
        "errors": result.errors,
        "success": result.success
    }
    print(json.dumps(output, indent=2))


def apply_command(
    service_yaml: str,
    env: Optional[str] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
    skip: Optional[List[str]] = None,
    only: Optional[List[str]] = None,
    force: bool = False,
    verbose: bool = False,
    output_format: str = "text",
    push_grafana: bool = False
) -> int:
    """
    Generate all resources for a service.
    
    Args:
        service_yaml: Path to service YAML file
        env: Environment name (dev, staging, prod)
        output_dir: Output directory for generated files
        dry_run: Preview without writing files (same as plan)
        skip: Resource types to skip (e.g., ['alerts', 'pagerduty'])
        only: Only generate specific resource types
        force: Force regeneration, ignore cache
        verbose: Show detailed progress
        output_format: Output format (text, json)
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Dry-run delegates to plan command
    if dry_run:
        return plan_command(service_yaml, env=env, verbose=verbose)
    
    # Create orchestrator
    orchestrator = ServiceOrchestrator(Path(service_yaml), env=env, push_to_grafana=push_grafana)
    
    # Override output directory if specified
    if output_dir:
        orchestrator.output_dir = Path(output_dir)
    
    # Apply
    result = orchestrator.apply(skip=skip, only=only, force=force, verbose=verbose)
    
    # Print result
    if output_format == "json":
        print_apply_json(result)
    else:  # text (default)
        print_apply_summary(result)
    
    return 0 if result.success else 1
