"""
SLO ceiling validation based on dependency SLAs.

Implements the "Rule of the Extra 9" from Google SRE:
Your service's SLO cannot exceed the product of your dependencies' SLAs.

Example:
    If you depend on postgres (SLA: 99.95%) and stripe (SLA: 99.9%),
    your max achievable SLO = 99.95% × 99.9% = 99.85%

This feature is OPT-IN: ceiling validation only runs if at least one
dependency has an explicit `sla` field. Teams not ready to map out
their dependency SLAs can simply omit the field.

Usage:
    # Opt-in by adding sla field to dependencies
    resources:
      - kind: Dependencies
        spec:
          databases:
            - name: postgres-main
              sla: 99.95  # Opts you into ceiling validation
          external_apis:
            - name: stripe
              sla: 99.9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DependencySLA:
    """A dependency with its SLA value."""

    name: str
    sla: float | None  # As percentage (e.g., 99.95), None if not specified


@dataclass
class CeilingValidationResult:
    """Result of SLO ceiling validation."""

    is_valid: bool
    target_slo: float
    ceiling_slo: float
    dependencies_with_sla: list[DependencySLA]
    dependencies_missing_sla: list[str] = field(default_factory=list)
    opted_in: bool = False  # True if at least one dep has SLA
    message: str = ""

    @property
    def dependency_slas(self) -> dict[str, float]:
        """Get dependency SLAs as a dict."""
        return {d.name: d.sla for d in self.dependencies_with_sla if d.sla is not None}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "is_valid": self.is_valid,
            "target_slo": self.target_slo,
            "ceiling_slo": self.ceiling_slo,
            "dependencies_with_sla": [
                {"name": d.name, "sla": d.sla} for d in self.dependencies_with_sla
            ],
            "dependencies_missing_sla": self.dependencies_missing_sla,
            "opted_in": self.opted_in,
            "message": self.message,
        }


def extract_dependencies_with_slas(
    spec: dict[str, Any],
) -> tuple[list[DependencySLA], list[str], bool]:
    """
    Extract dependencies from a service spec with their SLA values.

    Args:
        spec: Parsed service YAML

    Returns:
        Tuple of (deps_with_sla, deps_missing_sla, opted_in)
        - deps_with_sla: Dependencies that have explicit SLA values
        - deps_missing_sla: Names of dependencies without SLA values
        - opted_in: True if at least one dependency has an SLA
    """
    deps_with_sla: list[DependencySLA] = []
    deps_missing_sla: list[str] = []
    seen: set[str] = set()

    resources = spec.get("resources", [])
    for resource in resources:
        if resource.get("kind") != "Dependencies":
            continue

        resource_spec = resource.get("spec", {})

        # Process all dependency types
        dep_sections = ["databases", "services", "external_apis", "queues"]

        for section_name in dep_sections:
            for dep in resource_spec.get(section_name, []):
                name = dep.get("name", "")
                if not name:
                    continue

                # Skip duplicates
                if name.lower() in seen:
                    continue
                seen.add(name.lower())

                # Check for explicit SLA declaration
                explicit_sla = dep.get("sla")
                if explicit_sla is not None:
                    deps_with_sla.append(DependencySLA(name=name, sla=float(explicit_sla)))
                else:
                    deps_missing_sla.append(name)

    # Opted in if at least one dependency has an SLA
    opted_in = len(deps_with_sla) > 0

    return deps_with_sla, deps_missing_sla, opted_in


def calculate_slo_ceiling(dependencies: list[DependencySLA]) -> float:
    """
    Calculate the maximum achievable SLO based on dependency SLAs.

    Uses the multiplication rule: if A has 99.9% and B has 99.99%,
    combined ceiling = 99.9% × 99.99% ≈ 99.89%

    Args:
        dependencies: List of DependencySLA objects with SLA values

    Returns:
        Ceiling percentage (e.g., 99.94)
    """
    if not dependencies:
        return 100.0  # No constraints

    # Start with 1.0 (100% as a decimal)
    ceiling_decimal = 1.0

    for dep in dependencies:
        if dep.sla is not None:
            ceiling_decimal = ceiling_decimal * (dep.sla / 100.0)

    # Convert back to percentage and round
    ceiling = round(ceiling_decimal * 100.0, 4)

    return ceiling


def validate_slo_ceiling(
    target_slo: float,
    spec: dict[str, Any],
) -> CeilingValidationResult:
    """
    Validate that an SLO target is achievable given dependencies.

    This is an OPT-IN feature. Validation only runs if at least one
    dependency has an explicit `sla` field. If no dependencies have
    SLA values, validation passes silently.

    Args:
        target_slo: Target SLO percentage (e.g., 99.95)
        spec: Parsed service YAML containing Dependencies

    Returns:
        CeilingValidationResult with validation details
    """
    deps_with_sla, deps_missing_sla, opted_in = extract_dependencies_with_slas(spec)

    # Not opted in - skip validation entirely
    if not opted_in:
        return CeilingValidationResult(
            is_valid=True,
            target_slo=target_slo,
            ceiling_slo=100.0,
            dependencies_with_sla=[],
            dependencies_missing_sla=[],
            opted_in=False,
            message="Ceiling validation skipped (no dependencies have sla field)",
        )

    ceiling = calculate_slo_ceiling(deps_with_sla)

    # Check if target exceeds ceiling
    exceeds_ceiling = target_slo > ceiling

    # Build message
    if exceeds_ceiling:
        deps_str = ", ".join(f"{d.name}={d.sla:.2f}%" for d in deps_with_sla)
        message = (
            f"Target {target_slo:.2f}% exceeds achievable ceiling {ceiling:.2f}% "
            f"based on dependencies ({deps_str})"
        )
        is_valid = False
    elif deps_missing_sla:
        # Some dependencies missing SLA - warn but don't fail
        deps_str = ", ".join(f"{d.name}={d.sla:.2f}%" for d in deps_with_sla)
        missing_str = ", ".join(deps_missing_sla)
        message = (
            f"Partial ceiling {ceiling:.2f}% based on [{deps_str}]. "
            f"Missing sla for: [{missing_str}]"
        )
        is_valid = True  # Don't fail, just inform
    else:
        margin = ceiling - target_slo
        if margin < 0.1:
            message = (
                f"Target {target_slo:.2f}% is close to ceiling {ceiling:.2f}% "
                f"({margin:.2f}% margin)"
            )
        else:
            message = f"Target {target_slo:.2f}% is achievable (ceiling: {ceiling:.2f}%)"
        is_valid = True

    return CeilingValidationResult(
        is_valid=is_valid,
        target_slo=target_slo,
        ceiling_slo=ceiling,
        dependencies_with_sla=deps_with_sla,
        dependencies_missing_sla=deps_missing_sla,
        opted_in=True,
        message=message,
    )


# Backwards compatibility
def extract_dependencies_from_spec(spec: dict[str, Any]) -> list[str]:
    """
    Extract dependency names from a service spec.

    Args:
        spec: Parsed service YAML

    Returns:
        List of dependency names
    """
    deps_with_sla, deps_missing_sla, _ = extract_dependencies_with_slas(spec)
    return [d.name for d in deps_with_sla] + deps_missing_sla
