"""
Metric standards and naming conventions.

Provides mappings between common Prometheus metric names and
OpenTelemetry Semantic Convention canonical names.
"""

from nthlayer.metrics.standards.aliases import METRIC_ALIASES, get_canonical_name

__all__ = ["METRIC_ALIASES", "get_canonical_name"]
