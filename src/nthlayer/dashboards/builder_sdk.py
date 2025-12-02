"""
SDK-based Dashboard Builder - Grafana Foundation SDK implementation.

This is a new implementation of DashboardBuilder using the official Grafana Foundation SDK
for type-safe, officially compatible dashboard generation.

Enhanced with the Hybrid Model:
- Intent-based templates for exporter-agnostic dashboards
- Metric discovery and resolution
- Fallback chains and guidance panels
- Custom metric overrides from service YAML
"""

from typing import List, Optional, Any, Dict
import logging

from grafana_foundation_sdk.builders import dashboard, timeseries, stat, gauge, prometheus
from grafana_foundation_sdk.cog.encoder import JSONEncoder

from nthlayer.specs.models import Resource, ServiceContext
from nthlayer.dashboards.sdk_adapter import SDKAdapter
from nthlayer.dashboards.templates import get_template
from nthlayer.dashboards.resolver import MetricResolver, create_resolver, ResolutionStatus

logger = logging.getLogger(__name__)


class DashboardBuilderSDK:
    """Builds Grafana dashboards using Foundation SDK for type safety."""
    
    def __init__(
        self,
        service_context: ServiceContext,
        resources: List[Resource],
        full_panels: bool = False,
        discovery_client=None,
        enable_validation: bool = False,
        prometheus_url: Optional[str] = None,
        custom_metric_overrides: Optional[Dict[str, str]] = None,
        use_intent_templates: bool = True
    ):
        """Initialize SDK-based builder.
        
        Args:
            service_context: Service metadata
            resources: List of resources (SLOs, dependencies)
            full_panels: If True, use all template panels
            discovery_client: Optional for validation
            enable_validation: Whether to validate against discovered metrics
            prometheus_url: URL for metric discovery (enables hybrid model)
            custom_metric_overrides: Dict of intent -> custom metric mappings
            use_intent_templates: Whether to use intent-based templates (default True)
        """
        self.context = service_context
        self.resources = resources
        self.slo_resources = [r for r in resources if r.kind == "SLO"]
        self.dependency_resources = [r for r in resources if r.kind == "Dependencies"]
        self.full_panels = full_panels
        self.validation_warnings = []
        self.use_intent_templates = use_intent_templates
        
        # SDK adapter
        self.adapter = SDKAdapter()
        
        # Extract custom metric overrides from resources if not provided
        if custom_metric_overrides is None:
            custom_metric_overrides = self._extract_custom_overrides()
        
        # Create metric resolver for hybrid model
        self.resolver: Optional[MetricResolver] = None
        if prometheus_url or discovery_client:
            if discovery_client:
                self.resolver = MetricResolver(
                    discovery_client=discovery_client,
                    custom_overrides=custom_metric_overrides
                )
            else:
                self.resolver = create_resolver(
                    prometheus_url=prometheus_url,
                    custom_overrides=custom_metric_overrides
                )
        elif custom_metric_overrides:
            # Create resolver with just custom overrides (no discovery)
            self.resolver = MetricResolver(custom_overrides=custom_metric_overrides)
        
        # Validator (optional)
        if enable_validation and discovery_client:
            from nthlayer.dashboards.validator import DashboardValidator
            self.validator = DashboardValidator(discovery_client)
        else:
            self.validator = None
    
    def _extract_custom_overrides(self) -> Dict[str, str]:
        """Extract custom metric overrides from service resources."""
        overrides = {}
        
        # Look for metrics section in resources
        for resource in self.resources:
            if hasattr(resource, 'spec') and isinstance(resource.spec, dict):
                metrics = resource.spec.get('metrics', {})
                if isinstance(metrics, dict):
                    overrides.update(metrics)
        
        return overrides
    
    def build(self) -> Dict[str, Any]:
        """Build complete dashboard with SDK.
        
        With Hybrid Model enabled (resolver configured):
        1. Discovers available metrics for the service
        2. Resolves intents to actual metric names
        3. Uses fallbacks when primary metrics unavailable
        4. Generates guidance panels for missing instrumentation
        
        Returns:
            Dictionary with dashboard JSON for Grafana
        """
        # Step 1: Discover metrics if resolver available
        if self.resolver and self.resolver.discovery:
            try:
                metric_count = self.resolver.discover_for_service(self.context.name)
                logger.info(f"Discovered {metric_count} metrics for {self.context.name}")
            except Exception as e:
                logger.warning(f"Metric discovery failed: {e}, continuing without discovery")
        
        # Create dashboard
        dash = self.adapter.create_dashboard(
            service=self.context,
            editable=True
        )
        
        # Collect all panels
        all_panels = []
        
        # Add SLO panels
        if self.slo_resources:
            slo_panels = self._build_slo_panels()
            all_panels.extend(slo_panels)
            logger.info(f"Added {len(slo_panels)} SLO panels")
        
        # Add service health panels
        health_panels = self._build_health_panels()
        all_panels.extend(health_panels)
        logger.info(f"Added {len(health_panels)} health panels")
        
        # Add technology panels
        if self.dependency_resources:
            tech_panels = self._build_technology_panels()
            all_panels.extend(tech_panels)
            logger.info(f"Added {len(tech_panels)} technology panels")
        
        # Validate panels if enabled
        if self.validator:
            validated_panels = self._validate_panels(all_panels)
            logger.info(f"Validation: {len(validated_panels)}/{len(all_panels)} panels valid")
            all_panels = validated_panels
        
        # Log resolution summary if hybrid model active
        if self.resolver:
            summary = self.resolver.get_resolution_summary()
            if summary.get('unresolved', 0) > 0:
                logger.warning(
                    f"Resolution summary: {summary.get('resolved', 0)} resolved, "
                    f"{summary.get('fallback', 0)} fallback, "
                    f"{summary.get('unresolved', 0)} unresolved"
                )
        
        # Add panels to dashboard
        for panel_builder in all_panels:
            dash.with_panel(panel_builder)
        
        # Build and serialize
        dash_model = dash.build()
        json_str = JSONEncoder(sort_keys=False, indent=2).encode(dash_model)
        
        # Parse to dict for compatibility
        import json
        dashboard_dict = json.loads(json_str)
        
        # Wrap in Grafana API format
        return {
            "dashboard": dashboard_dict,
            "overwrite": True,
            "message": f"Auto-generated dashboard for {self.context.name}"
        }
    
    def _build_slo_panels(self) -> List[Any]:
        """Build SLO panels using SDK."""
        panels = []
        
        for slo_resource in self.slo_resources:
            slo_spec = slo_resource.spec
            
            # Extract SLO details
            if isinstance(slo_spec, dict):
                slo_name = slo_spec.get('name', slo_resource.name or 'Unknown SLO')
                objective = slo_spec.get('objective', 99.9)
                indicator = slo_spec.get('indicator', {})
                slo_query = indicator.get('query', '')
            else:
                slo_name = getattr(slo_spec, 'name', slo_resource.name or 'Unknown SLO')
                objective = getattr(slo_spec, 'target', 99.9)
                slo_query = getattr(slo_spec, 'query', '')
            
            # Create prometheus query
            if slo_query:
                # Use provided query (substitute variables)
                expr = slo_query.replace('${service}', '$service')
                prom_query = self.adapter.create_prometheus_query(
                    expr=expr,
                    legend_format=slo_name
                )
            else:
                # Generate query from SLO type using adapter
                prom_query = self.adapter.convert_slo_to_query(slo_spec)
            
            # Create panel
            panel = self.adapter.create_timeseries_panel(
                title=slo_name,
                description=f"Target: {objective}%",
                queries=[prom_query],
                unit="percent"
            )
            
            panels.append(panel)
        
        return panels
    
    def _build_health_panels(self) -> List[Any]:
        """Build service health panels using SDK."""
        panels = []
        
        # Request rate panel
        rate_query = self.adapter.create_prometheus_query(
            expr='sum(rate(http_requests_total{service="$service"}[5m]))',
            legend_format="requests/sec"
        )
        rate_panel = self.adapter.create_timeseries_panel(
            title="Request Rate",
            description="Total requests per second",
            queries=[rate_query],
            unit="reqps"
        )
        panels.append(rate_panel)
        
        # Error rate panel
        error_query = self.adapter.create_prometheus_query(
            expr='sum(rate(http_requests_total{service="$service",status=~"5.."}[5m])) / sum(rate(http_requests_total{service="$service"}[5m])) * 100',
            legend_format="error %"
        )
        error_panel = self.adapter.create_timeseries_panel(
            title="Error Rate",
            description="Percentage of requests returning 5xx",
            queries=[error_query],
            unit="percent"
        )
        panels.append(error_panel)
        
        # Latency panel (p95)
        latency_query = self.adapter.create_prometheus_query(
            expr='histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m])))',
            legend_format="p95 latency"
        )
        latency_panel = self.adapter.create_timeseries_panel(
            title="Request Latency (p95)",
            description="95th percentile request duration",
            queries=[latency_query],
            unit="s"
        )
        panels.append(latency_panel)
        
        return panels
    
    def _build_technology_panels(self) -> List[Any]:
        """Build technology-specific panels using SDK.
        
        With Hybrid Model (use_intent_templates=True):
        - Uses intent-based templates that resolve metrics at generation time
        - Provides fallback chains and guidance panels
        
        Without Hybrid Model (use_intent_templates=False):
        - Uses legacy templates with hardcoded metrics
        """
        panels = []
        
        for dep_resource in self.dependency_resources:
            dep_spec = dep_resource.spec
            
            # Extract dependencies
            databases = dep_spec.get('databases', []) if isinstance(dep_spec, dict) else []
            caches = dep_spec.get('caches', []) if isinstance(dep_spec, dict) else []
            
            # Combine all technology dependencies
            all_deps = []
            for db in databases:
                db_type = db.get('type', 'unknown') if isinstance(db, dict) else getattr(db, 'type', 'unknown')
                all_deps.append(('database', db_type))
            for cache in caches:
                cache_type = cache.get('type', 'redis') if isinstance(cache, dict) else getattr(cache, 'type', 'redis')
                all_deps.append(('cache', cache_type))
            
            # Build panels for each dependency
            for dep_category, dep_type in all_deps:
                if self.use_intent_templates:
                    # Use intent-based templates with resolver
                    tech_panels = self._build_intent_panels(dep_type)
                else:
                    # Use legacy templates
                    tech_panels = self._build_legacy_panels(dep_type)
                
                panels.extend(tech_panels)
        
        return panels
    
    def _build_intent_panels(self, technology: str) -> List[Any]:
        """Build panels using intent-based templates."""
        panels = []
        
        # Get intent-based template
        intent_template = self._get_intent_template(technology)
        
        if intent_template:
            # Set resolver if available
            if self.resolver:
                intent_template.resolver = self.resolver
            
            # Get panels (resolved through intent system)
            template_panels = intent_template.get_panels(f"$service")
            
            # Convert to SDK panels
            for old_panel in template_panels:
                sdk_panel = self._convert_panel_to_sdk(old_panel)
                if sdk_panel:
                    panels.append(sdk_panel)
        else:
            # Fall back to legacy template
            logger.debug(f"No intent template for {technology}, using legacy")
            panels = self._build_legacy_panels(technology)
        
        return panels
    
    def _get_intent_template(self, technology: str):
        """Get intent-based template for technology."""
        try:
            if technology in ('postgresql', 'postgres'):
                from nthlayer.dashboards.templates.postgresql_intent import PostgreSQLIntentTemplate
                return PostgreSQLIntentTemplate()
            elif technology == 'redis':
                from nthlayer.dashboards.templates.redis_intent import RedisIntentTemplate
                return RedisIntentTemplate()
            elif technology in ('mongodb', 'mongo'):
                from nthlayer.dashboards.templates.mongodb_intent import MongoDBIntentTemplate
                return MongoDBIntentTemplate()
            elif technology == 'mysql':
                from nthlayer.dashboards.templates.mysql_intent import MySQLIntentTemplate
                return MySQLIntentTemplate()
            elif technology == 'kafka':
                from nthlayer.dashboards.templates.kafka_intent import KafkaIntentTemplate
                return KafkaIntentTemplate()
            elif technology == 'elasticsearch':
                from nthlayer.dashboards.templates.elasticsearch_intent import ElasticsearchIntentTemplate
                return ElasticsearchIntentTemplate()
            return None
        except ImportError as e:
            logger.debug(f"Intent template not available for {technology}: {e}")
            return None
    
    def _build_legacy_panels(self, technology: str) -> List[Any]:
        """Build panels using legacy templates with hardcoded metrics."""
        panels = []
        
        # Map technology names
        if technology == 'mysql':
            technology = 'postgresql'  # Similar metrics structure
        
        template = get_template(technology)
        if template and hasattr(template, 'get_panels'):
            template_panels = template.get_panels(self.context.name)
            
            for old_panel in template_panels:
                sdk_panel = self._convert_panel_to_sdk(old_panel)
                if sdk_panel:
                    panels.append(sdk_panel)
        
        return panels
    
    def _convert_panel_to_sdk(self, old_panel) -> Optional[Any]:
        """Convert a legacy Panel to SDK panel."""
        try:
            # Create queries
            queries = []
            for target in getattr(old_panel, 'targets', []):
                q = self.adapter.create_prometheus_query(
                    expr=target.expr,
                    legend_format=getattr(target, 'legend_format', '')
                )
                queries.append(q)
            
            if not queries:
                return None
            
            # Create panel based on type
            panel_type = getattr(old_panel, 'panel_type', 'timeseries')
            
            if panel_type == 'stat':
                return self.adapter.create_stat_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, 'description', ''),
                    query=queries[0]
                )
            elif panel_type == 'gauge':
                return self.adapter.create_gauge_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, 'description', ''),
                    query=queries[0]
                )
            elif panel_type == 'text':
                # Guidance panel - create as text panel
                return self.adapter.create_text_panel(
                    title=old_panel.title,
                    content=getattr(old_panel, 'description', '')
                )
            else:
                return self.adapter.create_timeseries_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, 'description', ''),
                    queries=queries
                )
        except Exception as e:
            logger.warning(f"Failed to convert panel {getattr(old_panel, 'title', 'unknown')}: {e}")
            return None
    
    def _validate_panels(self, panels: List[Any]) -> List[Any]:
        """Validate panels against discovered metrics."""
        if not self.validator:
            return panels
        
        # For now, return all panels
        # TODO: Implement SDK panel validation
        logger.warning("SDK panel validation not yet implemented")
        return panels


def build_dashboard(
    service_context: ServiceContext,
    resources: List[Resource],
    full_panels: bool = False
) -> Dict[str, Any]:
    """
    Build Grafana dashboard from service specification.
    
    Convenience function for backward compatibility.
    
    Args:
        service_context: Service metadata
        resources: List of resources
        full_panels: Include all template panels
        
    Returns:
        Dashboard JSON dictionary
    """
    builder = DashboardBuilderSDK(
        service_context=service_context,
        resources=resources,
        full_panels=full_panels
    )
    return builder.build()
