"""
Validate command.
"""

from __future__ import annotations

from nthlayer.cli.ux import console, error, header, success, warning
from nthlayer.specs.validator import validate_service_file


def validate_command(
    service_file: str,
    environment: str | None = None,
    strict: bool = False,
    registry_dir: str | None = None,
) -> int:
    """
    Validate service definition file.

    Args:
        service_file: Path to service YAML file
        environment: Optional environment name (dev, staging, prod)
        strict: Treat warnings as errors
        registry_dir: Optional directory to scan for contract registry

    Returns:
        Exit code (0 = valid, 1 = invalid)
    """
    header("Validate Service Definition")
    console.print()

    if environment:
        console.print(f"[info]Environment:[/info] {environment}")
        console.print()

    contract_registry = None
    if registry_dir:
        from nthlayer.specs.contracts import ContractRegistry

        console.print(f"[info]Contract registry:[/info] {registry_dir}")
        contract_registry = ContractRegistry.from_directory(registry_dir)
        console.print(f"[info]Registered contracts:[/info] {len(contract_registry.services)}")
        console.print()

    result = validate_service_file(
        service_file,
        environment=environment,
        strict=strict,
        contract_registry=contract_registry,
    )

    if result.valid:
        success("Valid service definition")
        console.print()
        console.print(f"[bold]Service:[/bold] {result.service}")
        console.print(f"[bold]Resources:[/bold] {result.resource_count}")
        console.print()

        if result.warnings:
            warning("Warnings:")
            for warn in result.warnings:
                console.print(f"  [warning]•[/warning] {warn}")
            console.print()

            if strict:
                error("Validation failed (strict mode treats warnings as errors)")
                return 1

        success("Ready to generate SLOs")
        console.print()
        return 0

    else:
        error("Invalid service definition")
        console.print()

        if result.errors:
            console.print("[bold]Errors:[/bold]")
            for err in result.errors:
                console.print(f"  [error]•[/error] {err}")
            console.print()

        return 1
