"""Prometheus recording rules generation.

Generate recording rules for efficient SLO calculations.
"""

from nthlayer.recording_rules.builder import build_recording_rules
from nthlayer.recording_rules.models import RecordingRule, RecordingRuleGroup

__all__ = [
    "RecordingRule",
    "RecordingRuleGroup",
    "build_recording_rules",
]
