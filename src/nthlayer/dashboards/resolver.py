"""
Metric Resolver for NthLayer Dashboard Generation.

The resolver bridges the gap between abstract "intents" (what we want to measure)
and concrete Prometheus metrics (what actually exists in the environment).

Resolution Waterfall:
1. Custom Override (from service YAML)
2. Primary Discovery (check if candidates exist)
3. Fallback Chain (try alternative metrics)
4. Recording Rule Synthesis (derive from components)
5. Guidance (return instrumentation instructions)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from nthlayer.dashboards.intents import MetricIntent, get_intent
from nthlayer.discovery.client import MetricDiscoveryClient
from nthlayer.discovery.models import DiscoveryResult

logger = logging.getLogger(__name__)


class ResolutionStatus(Enum):
    """Status of metric resolution."""
    RESOLVED = "resolved"           # Found exact or primary match
    FALLBACK = "fallback"           # Using fallback metric
    SYNTHESIZED = "synthesized"     # Derived from components
    CUSTOM = "custom"               # User-specified override
    UNRESOLVED = "unresolved"       # Nothing found, needs guidance


@dataclass
class ResolutionResult:
    """Result of resolving an intent to a metric."""
    
    intent: str
    status: ResolutionStatus
    metric_name: Optional[str] = None
    message: str = ""
    synthesis_expr: Optional[str] = None  # For derived metrics
    
    @property
    def resolved(self) -> bool:
        """Check if resolution was successful."""
        return self.status in (
            ResolutionStatus.RESOLVED,
            ResolutionStatus.FALLBACK,
            ResolutionStatus.SYNTHESIZED,
            ResolutionStatus.CUSTOM
        )


@dataclass
class ExporterRecommendation:
    """Recommendation for installing an exporter."""
    
    technology: str
    name: str
    helm: Optional[str] = None
    docker: Optional[str] = None
    docs_url: Optional[str] = None
    metrics_enabled: List[str] = field(default_factory=list)


# Exporter recommendations for guidance panels
EXPORTER_RECOMMENDATIONS: Dict[str, ExporterRecommendation] = {
    "postgresql": ExporterRecommendation(
        technology="postgresql",
        name="postgres_exporter",
        helm="helm install postgres-exporter prometheus-community/prometheus-postgres-exporter",
        docker="docker run -p 9187:9187 quay.io/prometheuscommunity/postgres-exporter",
        docs_url="https://github.com/prometheus-community/postgres_exporter",
        metrics_enabled=["pg_stat_database_*", "pg_stat_user_tables_*", "pg_settings_*"]
    ),
    "redis": ExporterRecommendation(
        technology="redis",
        name="redis_exporter",
        helm="helm install redis-exporter prometheus-community/prometheus-redis-exporter",
        docker="docker run -p 9121:9121 oliver006/redis_exporter",
        docs_url="https://github.com/oliver006/redis_exporter",
        metrics_enabled=["redis_*"]
    ),
    "mongodb": ExporterRecommendation(
        technology="mongodb",
        name="mongodb_exporter",
        helm="helm install mongodb-exporter prometheus-community/prometheus-mongodb-exporter",
        docker="docker run -p 9216:9216 percona/mongodb_exporter",
        docs_url="https://github.com/percona/mongodb_exporter",
        metrics_enabled=["mongodb_*"]
    ),
    "mysql": ExporterRecommendation(
        technology="mysql",
        name="mysqld_exporter",
        helm="helm install mysql-exporter prometheus-community/prometheus-mysql-exporter",
        docker="docker run -p 9104:9104 prom/mysqld-exporter",
        docs_url="https://github.com/prometheus/mysqld_exporter",
        metrics_enabled=["mysql_*"]
    ),
    "kafka": ExporterRecommendation(
        technology="kafka",
        name="kafka_exporter",
        helm="helm install kafka-exporter prometheus-community/prometheus-kafka-exporter",
        docker="docker run -p 9308:9308 danielqsj/kafka-exporter",
        docs_url="https://github.com/danielqsj/kafka-exporter",
        metrics_enabled=["kafka_*"]
    ),
    "elasticsearch": ExporterRecommendation(
        technology="elasticsearch",
        name="elasticsearch_exporter",
        helm="helm install es-exporter prometheus-community/prometheus-elasticsearch-exporter",
        docker="docker run -p 9114:9114 quay.io/prometheuscommunity/elasticsearch-exporter",
        docs_url="https://github.com/prometheus-community/elasticsearch_exporter",
        metrics_enabled=["elasticsearch_*"]
    ),
}


class MetricResolver:
    """
    Resolves metric intents to actual Prometheus metric names.
    
    Uses metric discovery to find available metrics, then resolves
    abstract intents to concrete metric names using fallback chains.
    """
    
    def __init__(
        self,
        discovery_client: Optional[MetricDiscoveryClient] = None,
        custom_overrides: Optional[Dict[str, str]] = None
    ):
        """
        Initialize resolver.
        
        Args:
            discovery_client: Optional client for discovering metrics from Prometheus
            custom_overrides: Optional dict of intent -> metric name overrides
        """
        self.discovery = discovery_client
        self.custom_overrides = custom_overrides or {}
        self.discovered_metrics: Set[str] = set()
        self.discovery_result: Optional[DiscoveryResult] = None
        self._resolution_cache: Dict[str, ResolutionResult] = {}
    
    def discover_for_service(self, service_name: str) -> int:
        """
        Discover all metrics for a service.
        
        Args:
            service_name: Service name to discover metrics for
            
        Returns:
            Number of metrics discovered
        """
        if not self.discovery:
            logger.warning("No discovery client configured, skipping metric discovery")
            return 0
        
        try:
            selector = f'{{service="{service_name}"}}'
            self.discovery_result = self.discovery.discover(selector)
            self.discovered_metrics = {m.name for m in self.discovery_result.metrics}
            
            logger.info(f"Discovered {len(self.discovered_metrics)} metrics for {service_name}")
            return len(self.discovered_metrics)
            
        except Exception as e:
            logger.error(f"Failed to discover metrics for {service_name}: {e}")
            return 0
    
    def set_discovered_metrics(self, metrics: Set[str]) -> None:
        """
        Set discovered metrics directly (useful for testing or offline mode).
        
        Args:
            metrics: Set of metric names
        """
        self.discovered_metrics = metrics
        self._resolution_cache.clear()
    
    def resolve(self, intent_name: str) -> ResolutionResult:
        """
        Resolve an intent to a concrete metric name.
        
        Resolution waterfall:
        1. Check custom overrides
        2. Try primary candidates from discovery
        3. Try fallback chain
        4. Return unresolved with guidance
        
        Args:
            intent_name: Intent to resolve (e.g., "postgresql.connections")
            
        Returns:
            ResolutionResult with status and resolved metric (if any)
        """
        # Check cache first
        if intent_name in self._resolution_cache:
            return self._resolution_cache[intent_name]
        
        result = self._do_resolve(intent_name)
        self._resolution_cache[intent_name] = result
        return result
    
    def _do_resolve(self, intent_name: str) -> ResolutionResult:
        """Internal resolution logic."""
        
        # Step 1: Check custom overrides
        if intent_name in self.custom_overrides:
            custom_metric = self.custom_overrides[intent_name]
            return ResolutionResult(
                intent=intent_name,
                status=ResolutionStatus.CUSTOM,
                metric_name=custom_metric,
                message=f"Using custom override: {custom_metric}"
            )
        
        # Step 2: Get intent definition
        intent = get_intent(intent_name)
        if not intent:
            return ResolutionResult(
                intent=intent_name,
                status=ResolutionStatus.UNRESOLVED,
                message=f"Unknown intent: {intent_name}"
            )
        
        # Step 3: Try primary candidates
        for candidate in intent.candidates:
            if self._metric_exists(candidate):
                return ResolutionResult(
                    intent=intent_name,
                    status=ResolutionStatus.RESOLVED,
                    metric_name=candidate,
                    message=f"Resolved to primary candidate: {candidate}"
                )
        
        # Step 4: Try fallback if defined
        if intent.fallback:
            fallback_result = self.resolve(intent.fallback)
            if fallback_result.resolved:
                return ResolutionResult(
                    intent=intent_name,
                    status=ResolutionStatus.FALLBACK,
                    metric_name=fallback_result.metric_name,
                    message=f"Using fallback intent: {intent.fallback} -> {fallback_result.metric_name}"
                )
        
        # Step 5: Check for synthesis opportunity
        if intent.synthesis:
            synthesis_result = self._try_synthesis(intent)
            if synthesis_result:
                return synthesis_result
        
        # Step 6: Unresolved - return guidance
        technology = intent_name.split('.')[0]
        recommendation = EXPORTER_RECOMMENDATIONS.get(technology)
        
        if recommendation:
            message = (
                f"No metric found for {intent_name}. "
                f"Install {recommendation.name}: {recommendation.helm or recommendation.docker}"
            )
        else:
            message = f"No metric found for {intent_name}. Add instrumentation to your application."
        
        return ResolutionResult(
            intent=intent_name,
            status=ResolutionStatus.UNRESOLVED,
            message=message
        )
    
    def _metric_exists(self, metric_name: str) -> bool:
        """Check if a metric exists in discovered metrics."""
        # Exact match
        if metric_name in self.discovered_metrics:
            return True
        
        # Prefix match for histograms (metric_bucket, metric_count, metric_sum)
        base_name = metric_name.replace('_bucket', '').replace('_count', '').replace('_sum', '')
        for discovered in self.discovered_metrics:
            if discovered.startswith(base_name):
                return True
        
        return False
    
    def _try_synthesis(self, intent: MetricIntent) -> Optional[ResolutionResult]:
        """
        Try to synthesize a metric from components.
        
        For example, cache_hit_ratio = cache_hits_total / (cache_hits_total + cache_misses_total)
        """
        if not intent.synthesis:
            return None
        
        # Check if all component metrics exist
        components = intent.synthesis
        missing = []
        for component_name, component_metric in components.items():
            if not self._metric_exists(component_metric):
                missing.append(component_metric)
        
        if missing:
            return None
        
        # All components available - can synthesize
        # Build synthesis expression
        expr = intent.synthesis.get('expr', '')
        
        return ResolutionResult(
            intent=intent.intent,
            status=ResolutionStatus.SYNTHESIZED,
            metric_name=f"nthlayer:{intent.intent.replace('.', ':')}",
            synthesis_expr=expr,
            message=f"Synthesized from components: {list(components.values())}"
        )
    
    def resolve_all(self, intents: List[str]) -> Dict[str, ResolutionResult]:
        """
        Resolve multiple intents at once.
        
        Args:
            intents: List of intent names to resolve
            
        Returns:
            Dict mapping intent names to resolution results
        """
        return {intent: self.resolve(intent) for intent in intents}
    
    def get_resolution_summary(self) -> Dict[str, int]:
        """Get summary of resolution statuses."""
        summary = {status.value: 0 for status in ResolutionStatus}
        for result in self._resolution_cache.values():
            summary[result.status.value] += 1
        return summary
    
    def get_unresolved_intents(self) -> List[ResolutionResult]:
        """Get list of all unresolved intents with guidance."""
        return [
            r for r in self._resolution_cache.values()
            if r.status == ResolutionStatus.UNRESOLVED
        ]
    
    def get_exporter_recommendation(self, technology: str) -> Optional[ExporterRecommendation]:
        """Get exporter recommendation for a technology."""
        return EXPORTER_RECOMMENDATIONS.get(technology)


def create_resolver(
    prometheus_url: Optional[str] = None,
    custom_overrides: Optional[Dict[str, str]] = None,
    **discovery_kwargs
) -> MetricResolver:
    """
    Factory function to create a MetricResolver.
    
    Args:
        prometheus_url: Optional Prometheus URL for discovery
        custom_overrides: Optional metric overrides from service YAML
        **discovery_kwargs: Additional kwargs for MetricDiscoveryClient
        
    Returns:
        Configured MetricResolver
    """
    discovery = None
    if prometheus_url:
        discovery = MetricDiscoveryClient(prometheus_url, **discovery_kwargs)
    
    return MetricResolver(
        discovery_client=discovery,
        custom_overrides=custom_overrides
    )
