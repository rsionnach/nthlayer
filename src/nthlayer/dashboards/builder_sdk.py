"""
SDK-based Dashboard Builder - Grafana Foundation SDK implementation.

This is a new implementation of DashboardBuilder using the official Grafana Foundation SDK
for type-safe, officially compatible dashboard generation.
"""

from typing import List, Optional, Any, Dict
import logging

from grafana_foundation_sdk.builders import dashboard, timeseries, stat, gauge, prometheus
from grafana_foundation_sdk.cog.encoder import JSONEncoder

from nthlayer.specs.models import Resource, ServiceContext
from nthlayer.dashboards.sdk_adapter import SDKAdapter
from nthlayer.dashboards.templates import get_template

logger = logging.getLogger(__name__)


class DashboardBuilderSDK:
    """Builds Grafana dashboards using Foundation SDK for type safety."""
    
    def __init__(
        self,
        service_context: ServiceContext,
        resources: List[Resource],
        full_panels: bool = False,
        discovery_client=None,
        enable_validation: bool = False
    ):
        """Initialize SDK-based builder.
        
        Args:
            service_context: Service metadata
            resources: List of resources (SLOs, dependencies)
            full_panels: If True, use all template panels
            discovery_client: Optional for validation
            enable_validation: Whether to validate against discovered metrics
        """
        self.context = service_context
        self.resources = resources
        self.slo_resources = [r for r in resources if r.kind == "SLO"]
        self.dependency_resources = [r for r in resources if r.kind == "Dependencies"]
        self.full_panels = full_panels
        self.validation_warnings = []
        
        # SDK adapter
        self.adapter = SDKAdapter()
        
        # Validator (optional)
        if enable_validation and discovery_client:
            from nthlayer.dashboards.validator import DashboardValidator
            self.validator = DashboardValidator(discovery_client)
        else:
            self.validator = None
    
    def build(self) -> Dict[str, Any]:
        """Build complete dashboard with SDK.
        
        Returns:
            Dictionary with dashboard JSON for Grafana
        """
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
            
            # Create query
            if slo_query:
                # Use provided query (substitute variables)
                expr = slo_query.replace('${service}', '$service')
            else:
                # Generate query from SLO type
                query = self.adapter.convert_slo_to_query(slo_spec)
                expr = query.internal_.expr
            
            # Create prometheus query
            prom_query = self.adapter.create_prometheus_query(
                expr=expr,
                legend_format=slo_name
            )
            
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
        """Build technology-specific panels using SDK."""
        panels = []
        
        for dep_resource in self.dependency_resources:
            dep_spec = dep_resource.spec
            
            # Extract dependencies
            databases = dep_spec.get('databases', []) if isinstance(dep_spec, dict) else []
            
            # Add database panels
            for db in databases:
                db_type = db.get('type', 'unknown') if isinstance(db, dict) else getattr(db, 'type', 'unknown')
                db_name = db.get('name', 'database') if isinstance(db, dict) else getattr(db, 'name', 'database')
                
                # Get technology template
                template = get_template(db_type)
                if template and hasattr(template, 'get_panels'):
                    # Convert template panels to SDK panels
                    template_panels = template.get_panels(
                        self.context,
                        overview_only=not self.full_panels
                    )
                    
                    # Convert each panel to SDK format
                    for old_panel in template_panels:
                        # Create queries
                        queries = []
                        for target in old_panel.targets:
                            q = self.adapter.create_prometheus_query(
                                expr=target.expr,
                                legend_format=getattr(target, 'legend_format', '')
                            )
                            queries.append(q)
                        
                        # Create panel based on type
                        panel_type = getattr(old_panel, 'panel_type', 'timeseries')
                        if panel_type == 'stat':
                            sdk_panel = self.adapter.create_stat_panel(
                                title=old_panel.title,
                                description=getattr(old_panel, 'description', ''),
                                query=queries[0] if queries else None
                            )
                        elif panel_type == 'gauge':
                            sdk_panel = self.adapter.create_gauge_panel(
                                title=old_panel.title,
                                description=getattr(old_panel, 'description', ''),
                                query=queries[0] if queries else None
                            )
                        else:
                            sdk_panel = self.adapter.create_timeseries_panel(
                                title=old_panel.title,
                                description=getattr(old_panel, 'description', ''),
                                queries=queries
                            )
                        
                        panels.append(sdk_panel)
        
        return panels
    
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
