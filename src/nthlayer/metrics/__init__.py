"""
NthLayer Metrics Recommendation Engine.

Provides metric recommendations based on OpenTelemetry Semantic Conventions
for different service types and validates metric coverage against Prometheus.

Supports both legacy (ServiceContext) and new (ReliabilityManifest) APIs.
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricMatch,
    MetricRecommendation,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)
from nthlayer.metrics.recommender import recommend_metrics_from_manifest

__all__ = [
    "AttributeDefinition",
    "MetricDefinition",
    "MetricMatch",
    "MetricRecommendation",
    "MetricType",
    "RequirementLevel",
    "ServiceTypeTemplate",
    # New API (ReliabilityManifest)
    "recommend_metrics_from_manifest",
]
