"""Prometheus recording rules generation.

Generate recording rules for efficient SLO calculations.

Supports both legacy (ServiceContext, Resources) and new (ReliabilityManifest) APIs.
"""

from nthlayer.recording_rules.builder import build_recording_rules
from nthlayer.recording_rules.manifest_builder import (
    ManifestRecordingRuleBuilder,
    build_recording_rules_from_manifest,
)
from nthlayer.recording_rules.models import RecordingRule, RecordingRuleGroup

__all__ = [
    "RecordingRule",
    "RecordingRuleGroup",
    # Legacy API
    "build_recording_rules",
    # New API (ReliabilityManifest)
    "build_recording_rules_from_manifest",
    "ManifestRecordingRuleBuilder",
]
