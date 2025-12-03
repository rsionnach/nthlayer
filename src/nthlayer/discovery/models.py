"""
Data models for metric discovery.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class TechnologyGroup(str, Enum):
    """Technology classification for metrics."""
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    MONGODB = "mongodb"
    KAFKA = "kafka"
    MYSQL = "mysql"
    RABBITMQ = "rabbitmq"
    KUBERNETES = "kubernetes"
    HTTP = "http"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class DiscoveredMetric(BaseModel):
    """A metric discovered from Prometheus."""
    
    name: str = Field(..., description="Metric name")
    type: MetricType = Field(MetricType.UNKNOWN, description="Metric type")
    technology: TechnologyGroup = Field(TechnologyGroup.UNKNOWN, description="Technology classification")
    help_text: Optional[str] = Field(None, description="Metric help text from Prometheus")
    labels: Dict[str, List[str]] = Field(default_factory=dict, description="Available label values")
    
    class Config:
        use_enum_values = True


class DiscoveryResult(BaseModel):
    """Result of metric discovery for a service."""
    
    service: str = Field(..., description="Service name")
    total_metrics: int = Field(..., description="Total metrics discovered")
    metrics: List[DiscoveredMetric] = Field(default_factory=list, description="Discovered metrics")
    metrics_by_technology: Dict[str, List[DiscoveredMetric]] = Field(
        default_factory=dict,
        description="Metrics grouped by technology"
    )
    metrics_by_type: Dict[str, List[DiscoveredMetric]] = Field(
        default_factory=dict,
        description="Metrics grouped by type"
    )
    
    class Config:
        use_enum_values = True
