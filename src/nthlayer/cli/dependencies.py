"""
Dependency validation and visualization commands.
"""

from __future__ import annotations

from nthlayer.slos.dependencies import (
    Dependency,
    DependencyCriticality,
    detect_circular_dependencies,
    validate_dependencies,
)
from nthlayer.specs.parser import parse_service_file


def validate_dependencies_command(
    service_files: list[str],
) -> int:
    """
    Validate dependencies across multiple services.
    
    Checks:
    - All dependencies exist
    - No circular dependencies
    - Criticality levels are valid
    
    Args:
        service_files: List of service YAML files to validate
    
    Returns:
        Exit code (0 = valid, 1 = errors found)
    """
    print("=" * 70)
    print("  NthLayer: Validate Dependencies")
    print("=" * 70)
    print()
    
    # Parse all services
    services = {}
    service_deps = {}
    all_errors = []
    all_warnings = []
    
    for service_file in service_files:
        try:
            context, resources = parse_service_file(service_file)
            services[context.name] = context
            
            # Extract dependencies
            dep_resources = [r for r in resources if r.kind == "Dependencies"]
            if dep_resources:
                deps_spec = dep_resources[0].spec
                
                # Parse dependencies from spec
                deps = []
                for svc in deps_spec.get("services", []):
                    deps.append(Dependency(
                        name=svc["name"],
                        criticality=DependencyCriticality(svc.get("criticality", "medium")),
                        type="service",
                    ))
                
                service_deps[context.name] = [d.name for d in deps]
                services[context.name]._deps = deps  # Store for later
            
        except Exception as e:
            all_errors.append(f"Error parsing {service_file}: {e}")
    
    print(f"📋 Parsed {len(services)} services")
    print()
    
    # Validate each service's dependencies
    all_service_names = set(services.keys())
    
    for service_name, context in services.items():
        deps = getattr(context, "_deps", [])
        if not deps:
            continue
        
        errors, warnings = validate_dependencies(
            service_name,
            deps,
            all_service_names,
        )
        
        if errors or warnings:
            print(f"Service: {service_name}")
            
            if errors:
                for error in errors:
                    print(f"  ❌ {error}")
                    all_errors.append(f"{service_name}: {error}")
            
            if warnings:
                for warning in warnings:
                    print(f"  ⚠️  {warning}")
                    all_warnings.append(f"{service_name}: {warning}")
            
            print()
    
    # Check for circular dependencies
    cycles = detect_circular_dependencies(service_deps)
    
    if cycles:
        print("❌ Circular Dependencies Detected:")
        print()
        
        for cycle in cycles:
            cycle_str = " → ".join(cycle)
            print(f"  • {cycle_str}")
            all_errors.append(f"Circular dependency: {cycle_str}")
        
        print()
    
    # Summary
    print("=" * 70)
    
    if all_errors:
        print(f"❌ Validation failed with {len(all_errors)} error(s)")
        print()
        return 1
    
    if all_warnings:
        print(f"⚠️  {len(all_warnings)} warning(s) found")
        print()
    
    print("✅ All dependencies valid")
    print()
    
    # Display dependency graph summary
    print("📊 Dependency Summary:")
    for service_name, deps in service_deps.items():
        if deps:
            print(f"  {service_name} → {', '.join(deps)}")
    
    print()
    
    return 0
