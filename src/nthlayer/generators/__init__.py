"""
Code generators for various formats.

Generates SLO configs, Prometheus rules, etc. from service definitions.

Supports both legacy (ServiceContext, Resources) and new (ReliabilityManifest) APIs.
"""

from nthlayer.generators.alerts import generate_alerts_from_manifest
from nthlayer.generators.sloth import (
    SlothGenerationResult,
    generate_sloth_from_manifest,
    generate_sloth_spec,
)

__all__ = [
    # Legacy API
    "generate_sloth_spec",
    "SlothGenerationResult",
    # New API (ReliabilityManifest)
    "generate_sloth_from_manifest",
    "generate_alerts_from_manifest",
]
