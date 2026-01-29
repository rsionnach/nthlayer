"""
NthLayer Loki Module

Generate LogQL alert rules from service definitions.

Features:
- LogQL alert rules for application logs
- Technology-specific log patterns (PostgreSQL, Redis, Kafka, Kubernetes)
- Tier-based severity configuration
- Grafana Loki ruler format output
"""

from .generator import (
    LokiAlertGenerator,
    generate_loki_alerts_from_manifest,
)
from .models import LogQLAlert
from .templates import LOG_PATTERNS, get_patterns_for_technology

__all__ = [
    "LokiAlertGenerator",
    "LogQLAlert",
    "LOG_PATTERNS",
    "get_patterns_for_technology",
    # New API (ReliabilityManifest)
    "generate_loki_alerts_from_manifest",
]
