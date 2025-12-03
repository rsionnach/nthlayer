"""
Metric classifier for technology and type detection.

Classifies discovered metrics into technology groups based on naming patterns.
"""

import logging
import re

from .models import DiscoveredMetric, MetricType, TechnologyGroup

logger = logging.getLogger(__name__)


class MetricClassifier:
    """Classifies metrics by technology using pattern matching."""
    
    # Technology patterns (ordered by specificity)
    TECHNOLOGY_PATTERNS = [
        # PostgreSQL
        (r'^pg_', TechnologyGroup.POSTGRESQL),
        (r'postgres', TechnologyGroup.POSTGRESQL),
        
        # Redis
        (r'^redis_', TechnologyGroup.REDIS),
        (r'cache_hits', TechnologyGroup.REDIS),
        (r'cache_misses', TechnologyGroup.REDIS),
        
        # MongoDB  
        (r'^mongodb_', TechnologyGroup.MONGODB),
        (r'^mongo_', TechnologyGroup.MONGODB),
        
        # Kafka
        (r'^kafka_', TechnologyGroup.KAFKA),
        
        # MySQL
        (r'^mysql_', TechnologyGroup.MYSQL),
        
        # RabbitMQ
        (r'^rabbitmq_', TechnologyGroup.RABBITMQ),
        
        # Kubernetes
        (r'^kube_', TechnologyGroup.KUBERNETES),
        (r'^container_', TechnologyGroup.KUBERNETES),
        (r'_pod_', TechnologyGroup.KUBERNETES),
        
        # ECS (treat as Kubernetes for now)
        (r'^ecs_', TechnologyGroup.KUBERNETES),
        
        # HTTP/API
        (r'^http_', TechnologyGroup.HTTP),
        (r'_request', TechnologyGroup.HTTP),
        (r'_response', TechnologyGroup.HTTP),
    ]
    
    # Type inference patterns (fallback if metadata unavailable)
    TYPE_PATTERNS = [
        (r'_total$', MetricType.COUNTER),
        (r'_count$', MetricType.COUNTER),
        (r'_created$', MetricType.COUNTER),
        (r'_bucket$', MetricType.HISTOGRAM),
        (r'_sum$', MetricType.SUMMARY),
        (r'_seconds_', MetricType.HISTOGRAM),  # Usually histograms
        (r'_bytes', MetricType.GAUGE),
        (r'_ratio$', MetricType.GAUGE),
        (r'_percentage$', MetricType.GAUGE),
    ]
    
    def classify(self, metric: DiscoveredMetric) -> DiscoveredMetric:
        """
        Classify a discovered metric by technology.
        
        Args:
            metric: Metric to classify
            
        Returns:
            Metric with technology classification applied
        """
        # Classify technology
        metric.technology = self._classify_technology(metric.name)
        
        # Infer type if unknown
        if metric.type == MetricType.UNKNOWN:
            metric.type = self._infer_type(metric.name)
        
        return metric
    
    def _classify_technology(self, metric_name: str) -> TechnologyGroup:
        """
        Classify metric into technology group based on name patterns.
        """
        metric_lower = metric_name.lower()
        
        for pattern, technology in self.TECHNOLOGY_PATTERNS:
            if re.search(pattern, metric_lower):
                logger.debug(f"Classified {metric_name} as {technology} (pattern: {pattern})")
                return technology
        
        # Default to custom for application-specific metrics
        return TechnologyGroup.CUSTOM
    
    def _infer_type(self, metric_name: str) -> MetricType:
        """
        Infer metric type from naming conventions.
        
        This is a fallback when Prometheus metadata is unavailable.
        """
        metric_lower = metric_name.lower()
        
        for pattern, metric_type in self.TYPE_PATTERNS:
            if re.search(pattern, metric_lower):
                logger.debug(f"Inferred {metric_name} as {metric_type} (pattern: {pattern})")
                return metric_type
        
        return MetricType.GAUGE  # Default assumption
