"""
Service specification parsing and validation.

Supports both OpenSRM format (apiVersion: srm/v1) and legacy NthLayer
format (service: + resources:) with automatic detection.

Recommended usage:
    from nthlayer.specs import load_manifest

    manifest = load_manifest("service.yaml")

Legacy usage (still supported):
    from nthlayer.specs import parse_service_file

    context, resources = parse_service_file("service.yaml")
"""

# New unified API (recommended)
from nthlayer.specs.helpers import extract_dependency_technologies
from nthlayer.specs.loader import (
    LegacyFormatWarning,
    ManifestLoadError,
    is_manifest_file,
    load_manifest,
)
from nthlayer.specs.manifest import (
    JUDGMENT_SLO_TYPES,
    SERVICE_TYPE_ALIASES,
    STANDARD_SLO_TYPES,
    VALID_SERVICE_TYPES,
    VALID_TIERS,
    Contract,
    Dependency,
    DependencyCriticality,
    DependencySLO,
    DeploymentConfig,
    Instrumentation,
    Observability,
    Ownership,
    ReliabilityManifest,
    SLODefinition,
    SourceFormat,
)
from nthlayer.specs.opensrm_parser import (
    OpenSRMParseError,
    is_opensrm_format,
    parse_opensrm,
    parse_opensrm_file,
)

# Legacy API (deprecated, for backward compatibility)
from nthlayer.specs.parser import Resource, ServiceContext, parse_service_file
from nthlayer.specs.validator import ValidationResult, validate_service_file

__all__ = [
    # New unified API
    "load_manifest",
    "ReliabilityManifest",
    "SLODefinition",
    "Dependency",
    "DependencySLO",
    "DependencyCriticality",
    "Ownership",
    "Observability",
    "DeploymentConfig",
    "Contract",
    "Instrumentation",
    "SourceFormat",
    "ManifestLoadError",
    "LegacyFormatWarning",
    "is_manifest_file",
    # OpenSRM parser
    "parse_opensrm",
    "parse_opensrm_file",
    "is_opensrm_format",
    "OpenSRMParseError",
    # Helpers
    "extract_dependency_technologies",
    # Constants
    "VALID_TIERS",
    "VALID_SERVICE_TYPES",
    "SERVICE_TYPE_ALIASES",
    "STANDARD_SLO_TYPES",
    "JUDGMENT_SLO_TYPES",
    # Legacy API (deprecated)
    "parse_service_file",
    "ServiceContext",
    "Resource",
    "validate_service_file",
    "ValidationResult",
]
