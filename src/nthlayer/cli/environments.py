"""Environment management CLI commands.

Commands for discovering, comparing, and validating environment configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nthlayer.cli.ux import console, error, header, success, warning
from nthlayer.specs.parser import parse_service_file


def list_environments_command(service_file: str | None = None, directory: str | None = None) -> int:
    """List available environments for a service or directory.

    Args:
        service_file: Optional path to service YAML file
        directory: Optional directory to search for environment files

    Returns:
        Exit code (0 for success, 1 for error)
    """
    header("NthLayer: List Environments")

    header("NthLayer: List Environments")
    console.print()

    # Determine search location
    if service_file:
        search_path = Path(service_file).parent
        console.print(f"[cyan]Service:[/cyan] {service_file}")
    elif directory:
        search_path = Path(directory)
        console.print(f"[cyan]Directory:[/cyan] {directory}")
    else:
        search_path = Path.cwd()
        console.print(f"[cyan]Directory:[/cyan] {search_path}")

    console.print()

    # Find environments directory
    env_dir = search_path / "environments"

    if not env_dir.exists():
        error("No environments directory found")
        console.print()
        console.print(f"[muted]Expected location: {env_dir}[/muted]")
        console.print()
        console.print("[bold]To create environments:[/bold]")
        console.print(f"  [cyan]mkdir -p {env_dir}[/cyan]")
        console.print(f"  [muted]# Create environment files in {env_dir}/[/muted]")
        console.print()
        return 1

    # Find all environment files
    env_files = list(env_dir.glob("*.yaml")) + list(env_dir.glob("*.yml"))

    if not env_files:
        print("✗ No environment files found")
        console.print()
        console.print(f"[muted]Directory exists but is empty: {env_dir}[/muted]")
        console.print()
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
                    "service_files": [],
                }

            if is_service_specific:
                service_name = filename.rsplit("-", 1)[0]
                environments[env_name]["service_files"].append(
                    {"service": service_name, "file": env_file.name}
                )
            else:
                environments[env_name]["shared_file"] = env_file.name

        except (FileNotFoundError, yaml.YAMLError, KeyError, ValueError) as e:
            warning(f"Could not parse {env_file.name}: {e}")

    if not environments:
        error("No valid environment files found")
        console.print()
        return 1

    # Display environments
    console.print(f"[success]✓[/success] Found {len(environments)} environment(s):")
    console.print()

    for env_name in sorted(environments.keys()):
        env = environments[env_name]

        console.print(f"[cyan]📦 {env_name}[/cyan]")

        if env["shared_file"]:
            console.print(f"   [muted]Shared:[/muted] {env['shared_file']}")

        if env["service_files"]:
            console.print(
                f"   [muted]Service-specific:[/muted] {len(env['service_files'])} file(s)"
            )
            for svc in sorted(env["service_files"], key=lambda x: x["service"]):
                console.print(f"      [muted]•[/muted] {svc['service']}: {svc['file']}")

        console.print()

    # Show usage examples
    console.print("[bold]Usage:[/bold]")
    console.print(
        f"   [cyan]nthlayer generate-slo[/cyan] service.yaml --env {list(environments.keys())[0]}"
    )
    console.print(
        f"   [cyan]nthlayer validate[/cyan] service.yaml --env {list(environments.keys())[0]}"
    )
    console.print()

    return 0


def diff_envs_command(service_file: str, env1: str, env2: str, show_all: bool = False) -> int:
    """Compare configurations between two environments.

    Args:
        service_file: Path to service YAML file
        env1: First environment name
        env2: Second environment name
        show_all: Show all fields (not just differences)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    header("NthLayer: List Environments")

    header("NthLayer: List Environments")
    console.print()

    console.print(f"[cyan]Service:[/cyan] {service_file}")
    console.print(f"[cyan]Comparing:[/cyan] {env1} vs {env2}")
    console.print()

    # Parse service with both environments
    try:
        context1, resources1 = parse_service_file(service_file, environment=env1)
        context2, resources2 = parse_service_file(service_file, environment=env2)
    except (FileNotFoundError, yaml.YAMLError, KeyError, ValueError, TypeError) as e:
        error(f"Error parsing service: {e}")
        console.print()
        return 1

    has_differences = False

    # Compare service context
    console.print("[bold]Service Configuration:[/bold]")
    console.print()

    service_fields = ["tier", "type", "team", "template"]
    for field in service_fields:
        val1 = getattr(context1, field, None)
        val2 = getattr(context2, field, None)

        if val1 != val2:
            console.print(f"  [cyan]{field}:[/cyan]")
            console.print(f"    [muted]{env1}:[/muted] {val1}")
            console.print(f"    [muted]{env2}:[/muted] {val2}")
            console.print()
            has_differences = True
        elif show_all:
            console.print(f"  [muted]{field}: {val1} (same)[/muted]")

    if not has_differences and not show_all:
        print("  ✓ All fields are identical")
        console.print()

    # Compare resources
    console.print("[bold]Resources:[/bold]")
    console.print()

    # Build resource maps
    resources1_map = {r.name: r for r in resources1}
    resources2_map = {r.name: r for r in resources2}

    all_resource_names = set(resources1_map.keys()) | set(resources2_map.keys())

    resource_differences = False

    for name in sorted(all_resource_names):
        r1 = resources1_map.get(name)
        r2 = resources2_map.get(name)

        if r1 and not r2:
            console.print(f"  [warning]⚠[/warning] {name} (only in {env1})")
            resource_differences = True
        elif r2 and not r1:
            console.print(f"  [warning]⚠[/warning] {name} (only in {env2})")
            resource_differences = True
        elif r1 and r2:
            # Compare specs
            spec_diff = _diff_dicts(r1.spec, r2.spec)
            if spec_diff:
                console.print(f"  [cyan]{name}[/cyan] ({r1.kind}):")
                for key, (v1, v2) in spec_diff.items():
                    console.print(f"      [cyan]{key}:[/cyan]")
                    console.print(f"        [muted]{env1}:[/muted] {v1}")
                    console.print(f"        [muted]{env2}:[/muted] {v2}")
                console.print()
                resource_differences = True
            elif show_all:
                console.print(f"  [success]✓[/success] {name} ({r1.kind}): identical")

    if not resource_differences and not show_all:
        console.print("  [success]✓[/success] All resources are identical")
        console.print()

    # Summary
    header("NthLayer: List Environments")
    if has_differences or resource_differences:
        console.print("[bold yellow]Summary: Configurations differ[/bold yellow]")
    else:
        console.print("[bold green]Summary: Configurations are identical[/bold green]")
    header("NthLayer: List Environments")
    console.print()

    return 0


def validate_env_command(
    environment: str,
    service_file: str | None = None,
    directory: str | None = None,
    strict: bool = False,
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
    header("NthLayer: List Environments")

    header("NthLayer: List Environments")
    console.print()

    console.print(f"[cyan]Environment:[/cyan] {environment}")

    # Determine search location
    if service_file:
        search_path = Path(service_file).parent
        console.print(f"[cyan]Service:[/cyan] {service_file}")
    elif directory:
        search_path = Path(directory)
        console.print(f"[cyan]Directory:[/cyan] {directory}")
    else:
        search_path = Path.cwd()
        console.print(f"[cyan]Directory:[/cyan] {search_path}")

    console.print()

    # Find environment file
    env_dir = search_path / "environments"

    if not env_dir.exists():
        error("No environments directory found")
        console.print()
        console.print(f"[muted]Expected: {env_dir}[/muted]")
        console.print()
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
        error(f"Environment file not found: {environment}")
        console.print()
        console.print("[muted]Searched for:[/muted]")
        for f in env_files:
            console.print(f"  [muted]•[/muted] {f.name}")
        console.print()
        return 1

    success(f"Found: {env_file.name}")
    console.print()

    # Parse and validate
    errors = []
    warnings = []

    try:
        with open(env_file) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        error(f"Invalid YAML: {e}")
        console.print()
        return 1
    except (FileNotFoundError, OSError, PermissionError) as e:
        error(f"Error reading file: {e}")
        console.print()
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
                valid_service_fields = {
                    "tier",
                    "team",
                    "type",
                    "template",
                    "language",
                    "framework",
                    "metadata",
                }
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
        console.print("[cyan]Testing with service file...[/cyan]")
        try:
            context, resources = parse_service_file(service_file, environment=environment)
            success(f"Successfully merged with {Path(service_file).name}")
            console.print(f"   [muted]Result: tier={context.tier}, {len(resources)} resource(s)")
        except (FileNotFoundError, yaml.YAMLError, KeyError, ValueError, TypeError) as e:
            errors.append(f"Failed to merge with service: {e}")
        console.print()

    # Display results
    if errors:
        error("Validation failed")
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for err in errors:
            console.print(f"  [muted]•[/muted] {err}")
        console.print()
        return 1

    if warnings:
        warning("Validation warnings")
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warn in warnings:
            console.print(f"  [muted]•[/muted] {warn}")
        console.print()

        if strict:
            error("Validation failed (strict mode)")
            console.print()
            return 1

    if not errors and not warnings:
        success("Validation passed")
        console.print()
    elif not errors:
        success("Validation passed (with warnings)")
        console.print()

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
