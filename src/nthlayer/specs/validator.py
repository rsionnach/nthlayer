"""
Service definition validation.

Supports both OpenSRM format (apiVersion: srm/v1) and legacy NthLayer format.
"""

from __future__ import annotations

import re
import warnings as stdlib_warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nthlayer.specs.models import VALID_RESOURCE_KINDS
from nthlayer.specs.manifest import SERVICE_TYPE_ALIASES, VALID_SERVICE_TYPES, VALID_TIERS
from nthlayer.specs.loader import (
    LegacyFormatWarning,
    ManifestLoadError,
    load_manifest,
)
from nthlayer.specs.parser import ServiceParseError, parse_service_file
from nthlayer.specs.template import validate_template_variables


@dataclass
class ValidationResult:
    """Result of service file validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    service: str | None = None
    resource_count: int = 0

    def __str__(self) -> str:
        """Format validation result as string."""
        lines = []

        if self.valid:
            lines.append(f"✅ Valid service definition: {self.service}")
            lines.append(f"   Resources: {self.resource_count}")
        else:
            lines.append("❌ Invalid service definition")

        if self.errors:
            lines.append("\nErrors:")
            for error in self.errors:
                lines.append(f"  • {error}")

        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")

        return "\n".join(lines)


def validate_service_file(
    file_path: str | Path,
    environment: str | None = None,
    strict: bool = False,
    validate_filename: bool = True,
) -> ValidationResult:
    """
    Validate service YAML file.

    Checks:
    1. File can be parsed
    2. Service name is valid format
    3. Service tier is valid
    4. Service type is valid
    5. All resource kinds are valid
    6. No duplicate resource names
    7. Template variables are valid
    8. Template exists (if specified)
    9. Filename matches service name (optional)

    Args:
        file_path: Path to service YAML file
        environment: Optional environment name (dev, staging, prod)
        strict: If True, treat warnings as errors
        validate_filename: Check if filename matches service name

    Returns:
        ValidationResult with errors and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Try to parse file - supports both OpenSRM and legacy formats
    file_path = Path(file_path)

    # First, detect the format to use appropriate parser
    from nthlayer.specs.opensrm_parser import is_opensrm_format
    import yaml

    try:
        with open(file_path) as f:
            raw_data = yaml.safe_load(f)
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[f"Failed to parse YAML: {e}"],
        )

    use_opensrm = is_opensrm_format(raw_data) if isinstance(raw_data, dict) else False

    # Variables for the parsed service
    service_context: Any  # Either MockContext or ServiceContext
    resources: list[Any] = []
    resource_count: int = 0

    if use_opensrm:
        # Use unified loader for OpenSRM format
        try:
            with stdlib_warnings.catch_warnings():
                stdlib_warnings.simplefilter("ignore", LegacyFormatWarning)
                manifest = load_manifest(
                    file_path, environment=environment, suppress_deprecation_warning=True
                )

            # Create a mock service context for validation
            class MockContext:
                def __init__(self, m: Any) -> None:
                    self.name = m.name
                    self.team = m.team
                    self.tier = m.tier
                    self.type = m.type
                    self.template = m.template

            service_context = MockContext(manifest)
            resources = []  # OpenSRM manifests have SLOs inline, not as resources
            resource_count = len(manifest.slos) + len(manifest.dependencies)

        except ManifestLoadError as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
            )
        except (FileNotFoundError, ValueError) as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
            )
    else:
        # Use legacy parser for legacy format (preserves resource list for validation)
        try:
            service_context, resources = parse_service_file(file_path, environment=environment)
            resource_count = len(resources)
        except ServiceParseError as parse_err:
            return ValidationResult(
                valid=False,
                errors=[str(parse_err)],
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[f"Unexpected error parsing file: {e}"],
            )

    # Validate filename matches service name
    if validate_filename:
        # Accept both .yaml and .reliability.yaml extensions
        expected_filenames = [
            f"{service_context.name}.yaml",
            f"{service_context.name}.reliability.yaml",
        ]
        actual_filename = file_path.name
        if actual_filename not in expected_filenames:
            # Don't error for OpenSRM files with different naming conventions
            # Many OpenSRM files use descriptive names like api-basic.reliability.yaml
            if not actual_filename.endswith(".reliability.yaml"):
                errors.append(
                    f"Filename mismatch: expected '{expected_filenames[0]}' for service '{service_context.name}', "
                    f"got '{actual_filename}'"
                )

    # Validate service name format
    if not re.match(r"^[a-z][a-z0-9-]*$", service_context.name):
        errors.append(
            f"Invalid service name: '{service_context.name}'. "
            "Must start with lowercase letter and contain only lowercase letters, "
            "numbers, and hyphens."
        )

    # Validate tier
    if service_context.tier not in VALID_TIERS:
        errors.append(
            f"Invalid tier: '{service_context.tier}'. "
            f"Must be one of: {', '.join(sorted(VALID_TIERS))}"
        )

    # Validate type (accept canonical types and legacy aliases)
    all_valid_types = VALID_SERVICE_TYPES | set(SERVICE_TYPE_ALIASES.keys())
    if service_context.type not in all_valid_types:
        errors.append(
            f"Invalid type: '{service_context.type}'. "
            f"Must be one of: {', '.join(sorted(VALID_SERVICE_TYPES))}"
        )

    # Check for duplicate resource names
    resource_names = [r.name for r in resources if r.name]
    duplicates = [n for n in set(resource_names) if resource_names.count(n) > 1]
    if duplicates:
        errors.append(f"Duplicate resource names: {', '.join(duplicates)}")

    # Validate each resource
    for resource in resources:
        # Check resource kind
        if resource.kind not in VALID_RESOURCE_KINDS:
            errors.append(
                f"Resource {resource.kind}/{resource.name}: "
                f"Invalid kind '{resource.kind}'. "
                f"Must be one of: {', '.join(sorted(VALID_RESOURCE_KINDS))}"
            )

        # Validate template variables in spec
        invalid_vars = validate_template_variables(resource.spec)
        if invalid_vars:
            warnings.append(
                f"Resource '{resource.kind}/{resource.name}': "
                f"Uses unknown template variables: {', '.join(invalid_vars)}"
            )

    # Template warning (can't validate existence without template loader)
    if service_context.template:
        warnings.append(
            f"Service uses template '{service_context.template}'. "
            "Ensure template exists and is valid."
        )

    # Determine if valid
    valid = len(errors) == 0
    if strict and warnings:
        valid = False
        errors.extend(warnings)
        warnings = []

    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        service=service_context.name,
        resource_count=resource_count,
    )
