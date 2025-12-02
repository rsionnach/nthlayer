"""
Metric discovery module for NthLayer.

This module implements autograf-style metric discovery, querying Prometheus
to find actual metrics for a service and classifying them by technology.
"""

from .client import MetricDiscoveryClient
from .classifier import MetricClassifier
from .models import DiscoveredMetric, MetricType, TechnologyGroup

__all__ = [
    'MetricDiscoveryClient',
    'MetricClassifier',
    'DiscoveredMetric',
    'MetricType',
    'TechnologyGroup',
]
