"""Environment management CLI commands.

Commands for discovering, comparing, and validating environment configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nthlayer.specs.parser import parse_service_file


def list_environments_command(
    service_file: str | None = None,
    directory: str | None = None
) -> int:
    """List available environments for a service or directory.
    
    Args:
        service_file: Optional path to service YAML file
        directory: Optional directory to search for environment files
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    print("=" * 70)
    print("  NthLayer: List Environments")
    print("=" * 70)
    print()
    
    # Determine search location
    if service_file:
        search_path = Path(service_file).parent
        print(f"📁 Service: {service_file}")
    elif directory:
        search_path = Path(directory)
        print(f"📁 Directory: {directory}")
    else:
        search_path = Path.cwd()
        print(f"📁 Directory: {search_path}")
    
    print()
    
    # Find environments directory
    env_dir = search_path / "environments"
    
    if not env_dir.exists():
        print("❌ No environments directory found")
        print()
        print(f"Expected location: {env_dir}")
        print()
        print("To create environments:")
        print(f"  mkdir -p {env_dir}")
        print(f"  # Create environment files in {env_dir}/")
        print()
        return 1
    
    # Find all environment files
    env_files = list(env_dir.glob("*.yaml")) + list(env_dir.glob("*.yml"))
    
    if not env_files:
        print("❌ No environment files found")
        print()
        print(f"Directory exists but is empty: {env_dir}")
        print()
        return 1
    
    # Parse environment files
    environments = {}
    
    for env_file in sorted(env_files):
        try:
            with open(env_file) as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                continue
            
            env_name = data.get("environment")
            if not env_name:
                continue
            
            # Check if it's a service-specific file
            filename = env_file.stem
            is_service_specific = "-" in filename and filename != env_name
            
            if env_name not in environments:
                environments[env_name] = {
                    "name": env_name,
                    "shared_file": None,
                    "service_files": []
                }
            
            if is_service_specific:
                service_name = filename.rsplit("-", 1)[0]
                environments[env_name]["service_files"].append({
                    "service": service_name,
                    "file": env_file.name
                })
            else:
                environments[env_name]["shared_file"] = env_file.name
                
        except Exception as e:
            print(f"⚠️  Warning: Could not parse {env_file.name}: {e}")
    
    if not environments:
        print("❌ No valid environment files found")
        print()
        return 1
    
    # Display environments
    print(f"✅ Found {len(environments)} environment(s):")
    print()
    
    for env_name in sorted(environments.keys()):
        env = environments[env_name]
        
        print(f"📦 {env_name}")
        
        if env["shared_file"]:
            print(f"   Shared: {env['shared_file']}")
        
        if env["service_files"]:
            print(f"   Service-specific: {len(env['service_files'])} file(s)")
            for svc in sorted(env["service_files"], key=lambda x: x["service"]):
                print(f"      • {svc['service']}: {svc['file']}")
        
        print()
    
    # Show usage examples
    print("💡 Usage:")
    print(f"   nthlayer generate-slo service.yaml --env {list(environments.keys())[0]}")
    print(f"   nthlayer validate service.yaml --env {list(environments.keys())[0]}")
    print()
    
    return 0


def diff_envs_command(
    service_file: str,
    env1: str,
    env2: str,
    show_all: bool = False
) -> int:
    """Compare configurations between two environments.
    
    Args:
        service_file: Path to service YAML file
        env1: First environment name
        env2: Second environment name
        show_all: Show all fields (not just differences)
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    print("=" * 70)
    print("  NthLayer: Compare Environments")
    print("=" * 70)
    print()
    
    print(f"📄 Service: {service_file}")
    print(f"🔀 Comparing: {env1} vs {env2}")
    print()
    
    # Parse service with both environments
    try:
        context1, resources1 = parse_service_file(service_file, environment=env1)
        context2, resources2 = parse_service_file(service_file, environment=env2)
    except Exception as e:
        print(f"❌ Error parsing service: {e}")
        print()
        return 1
    
    has_differences = False
    
    # Compare service context
    print("🔧 Service Configuration:")
    print()
    
    service_fields = ["tier", "type", "team", "template"]
    for field in service_fields:
        val1 = getattr(context1, field, None)
        val2 = getattr(context2, field, None)
        
        if val1 != val2:
            print(f"  {field}:")
            print(f"    {env1}: {val1}")
            print(f"    {env2}: {val2}")
            print()
            has_differences = True
        elif show_all:
            print(f"  {field}: {val1} (same)")
    
    if not has_differences and not show_all:
        print("  ✅ All fields are identical")
        print()
    
    # Compare resources
    print("📦 Resources:")
    print()
    
    # Build resource maps
    resources1_map = {r.name: r for r in resources1}
    resources2_map = {r.name: r for r in resources2}
    
    all_resource_names = set(resources1_map.keys()) | set(resources2_map.keys())
    
    resource_differences = False
    
    for name in sorted(all_resource_names):
        r1 = resources1_map.get(name)
        r2 = resources2_map.get(name)
        
        if r1 and not r2:
            print(f"  ⚠️  {name} (only in {env1})")
            resource_differences = True
        elif r2 and not r1:
            print(f"  ⚠️  {name} (only in {env2})")
            resource_differences = True
        elif r1 and r2:
            # Compare specs
            spec_diff = _diff_dicts(r1.spec, r2.spec)
            if spec_diff:
                print(f"  📋 {name} ({r1.kind}):")
                for key, (v1, v2) in spec_diff.items():
                    print(f"      {key}:")
                    print(f"        {env1}: {v1}")
                    print(f"        {env2}: {v2}")
                print()
                resource_differences = True
            elif show_all:
                print(f"  ✅ {name} ({r1.kind}): identical")
    
    if not resource_differences and not show_all:
        print("  ✅ All resources are identical")
        print()
    
    # Summary
    print("=" * 70)
    if has_differences or resource_differences:
        print("📊 Summary: Configurations differ")
    else:
        print("📊 Summary: Configurations are identical")
    print("=" * 70)
    print()
    
    return 0


def validate_env_command(
    environment: str,
    service_file: str | None = None,
    directory: str | None = None,
    strict: bool = False
) -> int:
    """Validate an environment configuration file.
    
    Args:
        environment: Environment name to validate
        service_file: Optional service file to test against
        directory: Optional directory containing environments
        strict: Treat warnings as errors
        
    Returns:
        Exit code (0 for valid, 1 for invalid)
    """
    print("=" * 70)
    print("  NthLayer: Validate Environment")
    print("=" * 70)
    print()
    
    print(f"🌍 Environment: {environment}")
    
    # Determine search location
    if service_file:
        search_path = Path(service_file).parent
        print(f"📁 Service: {service_file}")
    elif directory:
        search_path = Path(directory)
        print(f"📁 Directory: {directory}")
    else:
        search_path = Path.cwd()
        print(f"📁 Directory: {search_path}")
    
    print()
    
    # Find environment file
    env_dir = search_path / "environments"
    
    if not env_dir.exists():
        print("❌ No environments directory found")
        print()
        print(f"Expected: {env_dir}")
        print()
        return 1
    
    # Look for environment file
    env_files = [
        env_dir / f"{environment}.yaml",
        env_dir / f"{environment}.yml",
    ]
    
    if service_file:
        service_name = Path(service_file).stem
        env_files.insert(0, env_dir / f"{service_name}-{environment}.yaml")
        env_files.insert(1, env_dir / f"{service_name}-{environment}.yml")
    
    env_file = None
    for f in env_files:
        if f.exists():
            env_file = f
            break
    
    if not env_file:
        print(f"❌ Environment file not found: {environment}")
        print()
        print("Searched for:")
        for f in env_files:
            print(f"  • {f.name}")
        print()
        return 1
    
    print(f"✅ Found: {env_file.name}")
    print()
    
    # Parse and validate
    errors = []
    warnings = []
    
    try:
        with open(env_file) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML: {e}")
        print()
        return 1
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        print()
        return 1
    
    # Validate structure
    if not isinstance(data, dict):
        errors.append("Environment file must be a YAML dictionary")
    else:
        # Check required fields
        if "environment" not in data:
            errors.append("Missing required field: 'environment'")
        elif data["environment"] != environment:
            warnings.append(
                f"Environment name mismatch: file contains '{data['environment']}' "
                f"but validating for '{environment}'"
            )
        
        # Check known fields
        valid_fields = {"environment", "service", "resources", "metadata"}
        for field in data.keys():
            if field not in valid_fields:
                warnings.append(f"Unknown field: '{field}'")
        
        # Validate service overrides
        if "service" in data:
            if not isinstance(data["service"], dict):
                errors.append("'service' field must be a dictionary")
            else:
                valid_service_fields = {"tier", "team", "type", "template", "language", "framework", "metadata"}
                for field in data["service"].keys():
                    if field not in valid_service_fields:
                        warnings.append(f"Unknown service field: '{field}'")
        
        # Validate resources
        if "resources" in data:
            if not isinstance(data["resources"], list):
                errors.append("'resources' field must be a list")
            else:
                for i, resource in enumerate(data["resources"]):
                    if not isinstance(resource, dict):
                        errors.append(f"Resource {i} must be a dictionary")
                        continue
                    
                    if "kind" not in resource:
                        warnings.append(f"Resource {i} missing 'kind' field")
                    if "name" not in resource:
                        warnings.append(f"Resource {i} missing 'name' field")
                    if "spec" not in resource:
                        warnings.append(f"Resource {i} missing 'spec' field")
    
    # Test with service file if provided
    if service_file and not errors:
        print("🧪 Testing with service file...")
        try:
            context, resources = parse_service_file(service_file, environment=environment)
            print(f"✅ Successfully merged with {Path(service_file).name}")
            print(f"   Result: tier={context.tier}, {len(resources)} resource(s)")
        except Exception as e:
            errors.append(f"Failed to merge with service: {e}")
        print()
    
    # Display results
    if errors:
        print("❌ Validation failed")
        print()
        print("Errors:")
        for error in errors:
            print(f"  • {error}")
        print()
        return 1
    
    if warnings:
        print("⚠️  Validation warnings")
        print()
        print("Warnings:")
        for warning in warnings:
            print(f"  • {warning}")
        print()
        
        if strict:
            print("❌ Validation failed (strict mode)")
            print()
            return 1
    
    if not errors and not warnings:
        print("✅ Validation passed")
        print()
    elif not errors:
        print("✅ Validation passed (with warnings)")
        print()
    
    return 0


def _diff_dicts(d1: dict, d2: dict, prefix: str = "") -> dict[str, tuple[Any, Any]]:
    """Recursively find differences between two dictionaries.
    
    Args:
        d1: First dictionary
        d2: Second dictionary
        prefix: Key prefix for nested dicts
        
    Returns:
        Dictionary of differences {key: (value1, value2)}
    """
    differences = {}
    
    all_keys = set(d1.keys()) | set(d2.keys())
    
    for key in all_keys:
        full_key = f"{prefix}.{key}" if prefix else key
        
        if key not in d1:
            differences[full_key] = (None, d2[key])
        elif key not in d2:
            differences[full_key] = (d1[key], None)
        else:
            v1, v2 = d1[key], d2[key]
            
            # Recursively compare nested dicts
            if isinstance(v1, dict) and isinstance(v2, dict):
                nested_diff = _diff_dicts(v1, v2, full_key)
                differences.update(nested_diff)
            elif v1 != v2:
                differences[full_key] = (v1, v2)
    
    return differences
