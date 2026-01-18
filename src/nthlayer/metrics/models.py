"""
Core data models for the Metrics Recommendation Engine.

Defines metric definitions, service type templates, and recommendation results
based on OpenTelemetry Semantic Conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MetricType(Enum):
    """OpenTelemetry metric instrument types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    UPDOWN_COUNTER = "updown_counter"


class RequirementLevel(Enum):
    """Metric requirement levels for SLO readiness."""

    REQUIRED = "required"  # SLO-critical, blocks deployment
    RECOMMENDED = "recommended"  # Best practice, warns
    OPT_IN = "opt_in"  # Optional enhancement


@dataclass
class AttributeDefinition:
    """Definition of a metric attribute (label/dimension)."""

    name: str
    type: str = "string"  # string, int, bool
    required: bool = False
    examples: list[str] = field(default_factory=list)


@dataclass
class MetricDefinition:
    """
    Definition of a metric following OpenTelemetry Semantic Conventions.

    Attributes:
        name: OTel canonical metric name (e.g., http.server.request.duration)
        type: Metric instrument type
        unit: Unit of measurement (seconds, bytes, {request}, etc.)
        description: Human-readable description
        attributes: Expected attributes/labels
        requirement_level: Required, recommended, or opt-in
        slo_usage: Which SLO types this metric supports (latency, availability, saturation)
        buckets: Histogram bucket boundaries (for histograms only)
    """

    name: str
    type: MetricType
    unit: str
    description: str
    attributes: list[AttributeDefinition] = field(default_factory=list)
    requirement_level: RequirementLevel = RequirementLevel.RECOMMENDED
    slo_usage: list[str] = field(default_factory=list)
    buckets: list[float] | None = None


@dataclass
class ServiceTypeTemplate:
    """
    Metric template for a service type (api, worker, etc.).

    Defines required and recommended metrics based on OpenTelemetry
    Semantic Conventions for the service type.
    """

    name: str  # api, worker, queue-consumer, etc.
    extends: str | None = None  # Parent template for inheritance
    required: list[MetricDefinition] = field(default_factory=list)
    recommended: list[MetricDefinition] = field(default_factory=list)
    slo_formulas: dict[str, str] = field(default_factory=dict)


@dataclass
class MetricMatch:
    """Result of matching a metric definition against discovered metrics."""

    definition: MetricDefinition
    found_as: str | None = None  # Actual metric name in Prometheus
    status: str = "missing"  # found, missing, aliased, unknown
    match_confidence: float = 0.0


@dataclass
class MetricRecommendation:
    """
    Complete metric recommendation for a service.

    Contains matched metrics categorized by requirement level,
    coverage statistics, and SLO readiness status.
    """

    service: str
    service_type: str
    tier: str
    runtime: str | None
    required: list[MetricMatch]
    recommended: list[MetricMatch]
    runtime_metrics: list[MetricMatch]
    required_coverage: float
    recommended_coverage: float
    slo_ready: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "service": self.service,
            "service_type": self.service_type,
            "tier": self.tier,
            "runtime": self.runtime,
            "required": [_match_to_dict(m) for m in self.required],
            "recommended": [_match_to_dict(m) for m in self.recommended],
            "runtime_metrics": [_match_to_dict(m) for m in self.runtime_metrics],
            "summary": {
                "required_coverage": self.required_coverage,
                "recommended_coverage": self.recommended_coverage,
                "slo_ready": self.slo_ready,
            },
        }


def _match_to_dict(match: MetricMatch) -> dict:
    """Convert MetricMatch to dictionary."""
    return {
        "name": match.definition.name,
        "type": match.definition.type.value,
        "unit": match.definition.unit,
        "description": match.definition.description,
        "status": match.status,
        "found_as": match.found_as,
        "match_confidence": match.match_confidence,
        "slo_usage": match.definition.slo_usage,
        "requirement_level": match.definition.requirement_level.value,
    }
