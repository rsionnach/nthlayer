"""
Unified manifest loader with format auto-detection.

Supports both OpenSRM format (apiVersion: srm/v1) and legacy NthLayer
format (service: + resources:) with automatic detection.

Usage:
    from nthlayer.specs.loader import load_manifest

    # Auto-detects format
    manifest = load_manifest("service.yaml")

    # Or explicitly specify format
    manifest = load_manifest("service.yaml", format="opensrm")
    manifest = load_manifest("service.yaml", format="legacy")
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

import yaml

from nthlayer.specs.manifest import (
    Dependency,
    DependencyCriticality,
    DependencySLO,
    Ownership,
    PagerDutyConfig,
    ReliabilityManifest,
    SLODefinition,
    SourceFormat,
)
from nthlayer.specs.opensrm_parser import OpenSRMParseError, is_opensrm_format, parse_opensrm


class ManifestLoadError(Exception):
    """Error loading manifest file."""

    pass


class LegacyFormatWarning(UserWarning):
    """Warning for legacy format usage."""

    pass


def load_manifest(
    file_path: str | Path,
    environment: str | None = None,
    format: Literal["auto", "opensrm", "legacy"] | None = "auto",
    suppress_deprecation_warning: bool = False,
) -> ReliabilityManifest:
    """
    Load a reliability manifest from a YAML file.

    Automatically detects the format based on file contents:
    - OpenSRM: Files with `apiVersion: srm/v1`
    - Legacy: Files with `service:` section (NthLayer format)

    Args:
        file_path: Path to the manifest file
        environment: Optional environment name for overrides
        format: Format hint ("auto", "opensrm", or "legacy")
        suppress_deprecation_warning: If True, don't warn about legacy format

    Returns:
        ReliabilityManifest instance

    Raises:
        ManifestLoadError: If loading fails
        FileNotFoundError: If file doesn't exist

    Examples:
        # OpenSRM format (recommended)
        manifest = load_manifest("payment-api.reliability.yaml")

        # Legacy NthLayer format (deprecated)
        manifest = load_manifest("services/payment-api.yaml")

        # With environment overrides
        manifest = load_manifest("payment-api.yaml", environment="production")
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {file_path}")

    # Load YAML
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ManifestLoadError(f"Invalid YAML in {file_path}: {e}") from e

    if not isinstance(data, dict):
        raise ManifestLoadError(f"Expected YAML object in {file_path}")

    # Detect format
    detected_format = _detect_format(data)

    # Use explicit format if provided, otherwise use detected
    if format == "auto":
        use_format = detected_format
    elif format == "opensrm":
        use_format = SourceFormat.OPENSRM
    elif format == "legacy":
        use_format = SourceFormat.LEGACY
    else:
        use_format = detected_format

    # Parse based on format
    if use_format == SourceFormat.OPENSRM:
        try:
            return parse_opensrm(data, source_file=str(path))
        except OpenSRMParseError as e:
            raise ManifestLoadError(str(e)) from e

    else:
        # Legacy format
        if not suppress_deprecation_warning:
            warnings.warn(
                f"Legacy NthLayer format detected in {file_path}. "
                f"Consider migrating to OpenSRM format (apiVersion: srm/v1). "
                f"Run 'nthlayer migrate {file_path}' to convert.",
                LegacyFormatWarning,
                stacklevel=2,
            )

        return _parse_legacy_to_manifest(data, str(path), environment)


def _detect_format(data: dict[str, Any]) -> SourceFormat:
    """
    Detect the format of manifest data.

    Returns:
        SourceFormat.OPENSRM if OpenSRM format, SourceFormat.LEGACY otherwise
    """
    if is_opensrm_format(data):
        return SourceFormat.OPENSRM

    if "service" in data:
        return SourceFormat.LEGACY

    # Default to legacy for backward compatibility
    return SourceFormat.LEGACY


def _parse_legacy_to_manifest(
    data: dict[str, Any],
    source_file: str,
    environment: str | None = None,
) -> ReliabilityManifest:
    """
    Parse legacy NthLayer format into a ReliabilityManifest.

    Converts:
        service:
          name: payment-api
          team: payments
          tier: critical
          type: api
        resources:
          - kind: SLO
            name: availability
            spec: {...}

    To a ReliabilityManifest.
    """
    service_data = data.get("service", {})
    resources_data = data.get("resources", [])

    # Extract required fields
    name = service_data.get("name")
    if not name:
        raise ManifestLoadError("service.name is required")

    team = service_data.get("team")
    if not team:
        raise ManifestLoadError("service.team is required")

    tier = service_data.get("tier")
    if not tier:
        raise ManifestLoadError("service.tier is required")

    service_type = service_data.get("type")
    if not service_type:
        raise ManifestLoadError("service.type is required")

    # Parse SLOs from resources
    slos = _extract_slos_from_resources(resources_data)

    # Parse dependencies from resources
    dependencies = _extract_dependencies_from_resources(resources_data)

    # Parse ownership
    ownership = _extract_ownership(service_data, resources_data)

    # Parse PagerDuty config
    pagerduty_config = None
    if "pagerduty" in service_data:
        pd_data = service_data["pagerduty"]
        pagerduty_config = PagerDutyConfig(
            service_id=pd_data.get("service_id"),
            escalation_policy_id=pd_data.get("escalation_policy"),
        )
        if ownership:
            ownership.pagerduty = pagerduty_config

    return ReliabilityManifest(
        # Metadata
        name=name,
        team=team,
        tier=tier,
        description=service_data.get("description"),
        labels=service_data.get("metadata", {}).get("labels", {}),
        annotations=service_data.get("metadata", {}).get("annotations", {}),
        # Spec
        type=service_type,
        slos=slos,
        dependencies=dependencies,
        ownership=ownership,
        # Legacy fields
        language=service_data.get("language"),
        framework=service_data.get("framework"),
        template=service_data.get("template"),
        support_model=service_data.get("support_model", "self"),
        environment=environment,
        # Source tracking
        source_format=SourceFormat.LEGACY,
        source_file=source_file,
        raw_data=data,
    )


def _extract_slos_from_resources(resources: list[dict[str, Any]]) -> list[SLODefinition]:
    """Extract SLO definitions from legacy resource list."""
    slos = []

    for resource in resources:
        if resource.get("kind") != "SLO":
            continue

        name = resource.get("name", "")
        spec = resource.get("spec", {})

        # Map legacy spec fields to SLODefinition
        target = spec.get("objective") or spec.get("target")
        if target is None:
            continue

        slo = SLODefinition(
            name=name,
            target=float(target),
            window=spec.get("window", "30d"),
            slo_type=spec.get("indicator", {}).get("type"),
            unit=spec.get("unit"),
            percentile=spec.get("percentile"),
            indicator_query=spec.get("indicator", {}).get("query"),
            description=spec.get("description"),
        )
        slos.append(slo)

    return slos


def _extract_dependencies_from_resources(
    resources: list[dict[str, Any]],
) -> list[Dependency]:
    """Extract dependencies from legacy resource list."""
    dependencies = []

    for resource in resources:
        if resource.get("kind") != "Dependencies":
            continue

        spec = resource.get("spec", {})

        # Parse databases
        for db in spec.get("databases", []):
            dep_slo = None
            if "slo" in db:
                dep_slo = DependencySLO(
                    availability=db["slo"].get("availability"),
                    latency_p99=db["slo"].get("latency_p99"),
                )

            criticality = None
            if "criticality" in db:
                try:
                    criticality = DependencyCriticality(db["criticality"])
                except ValueError:
                    logger.warning(
                        "Invalid dependency criticality '%s' for database '%s', ignoring",
                        db["criticality"],
                        db.get("name", "unknown"),
                    )

            dependencies.append(
                Dependency(
                    name=db.get("name", ""),
                    type="database",
                    critical=db.get("criticality") in ("critical", "high"),
                    criticality=criticality,
                    database_type=db.get("type"),
                    slo=dep_slo,
                )
            )

        # Parse upstream services
        for upstream in spec.get("upstream", []):
            dep_slo = None
            if "slo" in upstream:
                dep_slo = DependencySLO(
                    availability=upstream["slo"].get("availability"),
                    latency_p99=upstream["slo"].get("latency_p99"),
                )

            criticality = None
            if "criticality" in upstream:
                try:
                    criticality = DependencyCriticality(upstream["criticality"])
                except ValueError:
                    logger.warning(
                        "Invalid dependency criticality '%s' for upstream '%s', ignoring",
                        upstream["criticality"],
                        upstream.get("name", "unknown"),
                    )

            dependencies.append(
                Dependency(
                    name=upstream.get("name", ""),
                    type="api",
                    critical=upstream.get("criticality") in ("critical", "high"),
                    criticality=criticality,
                    slo=dep_slo,
                )
            )

        # Parse downstream services
        for downstream in spec.get("downstream", []):
            dependencies.append(
                Dependency(
                    name=downstream.get("name", ""),
                    type="api",
                    critical=False,
                )
            )

        # Parse caches
        for cache in spec.get("caches", []):
            dependencies.append(
                Dependency(
                    name=cache.get("name", ""),
                    type="cache",
                    critical=cache.get("criticality") in ("critical", "high"),
                )
            )

        # Parse queues
        for queue in spec.get("queues", []):
            dependencies.append(
                Dependency(
                    name=queue.get("name", ""),
                    type="queue",
                    critical=queue.get("criticality") in ("critical", "high"),
                )
            )

    return dependencies


def _extract_ownership(
    service_data: dict[str, Any],
    resources: list[dict[str, Any]],
) -> Ownership | None:
    """Extract ownership info from legacy service data and resources."""
    team = service_data.get("team")
    if not team:
        return None

    ownership = Ownership(
        team=team,
        slack=service_data.get("slack_channel"),
        email=service_data.get("email"),
        runbook=service_data.get("runbook_url"),
    )

    # Check for PagerDuty resource
    for resource in resources:
        if resource.get("kind") == "PagerDuty":
            spec = resource.get("spec", {})
            ownership.pagerduty = PagerDutyConfig(
                service_id=spec.get("service_id"),
                escalation_policy_id=spec.get("escalation_policy"),
            )
            ownership.escalation = spec.get("escalation_policy")
            break

    return ownership


def is_manifest_file(file_path: str | Path) -> bool:
    """
    Check if a file appears to be a reliability manifest.

    Checks by file extension and basic content validation.

    Args:
        file_path: Path to check

    Returns:
        True if file appears to be a manifest
    """
    path = Path(file_path)

    # Check extension
    if path.suffix not in (".yaml", ".yml"):
        return False

    # Common manifest patterns
    name = path.stem.lower()
    if name.endswith(".reliability"):
        return True
    if name == "service":
        return True

    # Check content
    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return False

        # OpenSRM format
        if is_opensrm_format(data):
            return True

        # Legacy format
        if "service" in data and isinstance(data["service"], dict):
            service = data["service"]
            return all(k in service for k in ("name", "team", "tier", "type"))

    except Exception:
        logger.debug("Could not read %s for manifest detection", path)
        return False

    return False
