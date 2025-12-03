"""
Validate command.
"""

from __future__ import annotations

from nthlayer.specs.validator import validate_service_file


def validate_command(
    service_file: str,
    environment: str | None = None,
    strict: bool = False,
) -> int:
    """
    Validate service definition file.
    
    Args:
        service_file: Path to service YAML file
        environment: Optional environment name (dev, staging, prod)
        strict: Treat warnings as errors
    
    Returns:
        Exit code (0 = valid, 1 = invalid)
    """
    print("=" * 70)
    print("  NthLayer: Validate Service Definition")
    print("=" * 70)
    print()
    
    if environment:
        print(f"🌍 Environment: {environment}")
        print()
    
    result = validate_service_file(service_file, environment=environment, strict=strict)
    
    if result.valid:
        print("✅ Valid service definition")
        print()
        print(f"Service: {result.service}")
        print(f"Resources: {result.resource_count}")
        print()
        
        if result.warnings:
            print("⚠️  Warnings:")
            for warning in result.warnings:
                print(f"  • {warning}")
            print()
            
            if strict:
                print("❌ Validation failed (strict mode treats warnings as errors)")
                return 1
        
        print("✅ Ready to generate SLOs")
        print()
        return 0
    
    else:
        print("❌ Invalid service definition")
        print()
        
        if result.errors:
            print("Errors:")
            for error in result.errors:
                print(f"  • {error}")
            print()
        
        return 1
