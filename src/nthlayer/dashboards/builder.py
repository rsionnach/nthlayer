"""Dashboard builder for generating Grafana dashboards from service specs.

Automatically creates dashboards with:
- SLO panels (availability, latency, error rate)
- Service metadata
- Template variables
- Technology-specific panels (auto-detected from dependencies)

Now powered by Grafana Foundation SDK for type-safe dashboard generation.
"""

from typing import Any, Dict, List

from grafana_foundation_sdk.builders.dashboard import Row

from nthlayer.dashboards.models import Panel, Target, TemplateVariable
from nthlayer.dashboards.sdk_adapter import SDKAdapter
from nthlayer.dashboards.templates import get_template
from nthlayer.specs.models import Resource, ServiceContext


class DashboardBuilder:
    """Builds Grafana dashboards from service specifications with metric validation.
    
    Now uses Grafana Foundation SDK for type-safe, officially compatible dashboards.
    """
    
    def __init__(
        self,
        service_context: ServiceContext,
        resources: List[Resource],
        full_panels: bool = False,
        discovery_client=None,
        enable_validation: bool = False
    ):
        """Initialize builder with service context and resources.
        
        Args:
            service_context: Service metadata (name, team, tier, etc.)
            resources: List of resources (SLOs, dependencies, etc.)
            full_panels: If True, use all template panels; if False, use overview only
            discovery_client: Optional MetricDiscoveryClient for validation
            enable_validation: Whether to validate panels against discovered metrics
        """
        self.context = service_context
        self.resources = resources
        self.slo_resources = [r for r in resources if r.kind == "SLO"]
        self.dependency_resources = [r for r in resources if r.kind == "Dependencies"]
        self.full_panels = full_panels
        self.validation_warnings = []
        
        # SDK adapter for type-safe dashboard generation
        self.adapter = SDKAdapter()
        
        # Import validator here to avoid circular imports
        if enable_validation and discovery_client:
            from nthlayer.dashboards.validator import DashboardValidator
            self.validator = DashboardValidator(discovery_client)
        else:
            self.validator = None
    
    def build(self) -> Dict[str, Any]:
        """Build complete dashboard with optional metric validation.
        
        Returns:
            Dictionary with Grafana dashboard JSON (compatible with old format)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Create dashboard using SDK
        dashboard = self.adapter.create_dashboard(
            service=self.context,
            editable=True
        )
        
        # Add template variables (TODO: SDK variable support)
        # For now, we'll add them in the final JSON
        template_vars = self._build_template_variables()
        
        # Collect all SDK panel builders
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
        
        # Add technology-specific panels if dependencies exist
        if self.dependency_resources:
            tech_panels = self._build_technology_panels()
            all_panels.extend(tech_panels)
            logger.info(f"Added {len(tech_panels)} technology panels")
        
        # VALIDATE PANELS if validator is enabled
        if self.validator:
            logger.info(f"Validating {len(all_panels)} panels for {self.context.name}...")
            validated_panels, warnings = self.validator.validate_dashboard(
                service_name=self.context.name,
                panels=all_panels,
                discover_metrics=True
            )
            
            self.validation_warnings = warnings
            
            if warnings:
                logger.warning(f"Dashboard validation found {len(warnings)} issues")
            
            removed_count = len(all_panels) - len(validated_panels)
            if removed_count > 0:
                logger.info(f"Removed {removed_count} panels with missing metrics")
            
            all_panels = validated_panels
        
        # Group panels into rows
        if self.slo_resources and any(p.title.endswith('SLO') for p in all_panels):
            slo_row = Row(title="SLO Metrics")
            slo_row.panels = [p for p in all_panels if 'SLO' in p.title]
            dashboard.rows.append(slo_row)
            all_panels = [p for p in all_panels if 'SLO' not in p.title]
        
        if all_panels:
            # Put remaining panels in appropriate rows
            health_row = Row(title="Service Health")
            health_row.panels = [p for p in all_panels if any(x in p.title.lower() for x in ['request', 'latency', 'error', 'cpu', 'memory'])]
            if health_row.panels:
                dashboard.rows.append(health_row)
            
            tech_panels = [p for p in all_panels if p not in health_row.panels]
            if tech_panels:
                tech_row = Row(title="Dependencies")
                tech_row.panels = tech_panels
                dashboard.rows.append(tech_row)
        
        logger.info(f"Dashboard built with {sum(len(r.panels) for r in dashboard.rows)} validated panels")
        
        return dashboard
    
    def _build_template_variables(self) -> List[TemplateVariable]:
        """Build dashboard template variables.
        
        Returns:
            List of template variables for filtering
        """
        variables = []
        
        # Service filter
        variables.append(TemplateVariable(
            name="service",
            label="Service",
            query=f'label_values(up{{service="{self.context.name}"}}, service)',
            datasource="Prometheus",
            current={"text": self.context.name, "value": self.context.name}
        ))
        
        # Environment filter (if environment is set)
        if self.context.environment:
            variables.append(TemplateVariable(
                name="environment",
                label="Environment",
                query='label_values(up{service="$service"}, environment)',
                datasource="Prometheus",
                current={"text": self.context.environment, "value": self.context.environment}
            ))
        
        # Namespace filter (for Kubernetes)
        if self.context.type in ["api", "web", "worker"]:
            variables.append(TemplateVariable(
                name="namespace",
                label="Namespace",
                query='label_values(up{service="$service"}, namespace)',
                datasource="Prometheus",
            ))
        
        return variables
    
    def _build_slo_panels(self) -> List[Panel]:
        """Build panels for SLO metrics.
        
        Returns:
            List of panels showing SLO status
        """
        panels = []
        
        for slo in self.slo_resources:
            slo_name = slo.name
            slo_spec = slo.spec
            
            # Check SLO type from indicators
            indicators = slo_spec.get("indicators", [])
            slo_type = indicators[0].get("type") if indicators else None
            
            # Determine SLO type and create appropriate panel
            if slo_type == "latency" or "latency" in slo_name.lower():
                panel = self._build_latency_slo_panel(slo_name, slo_spec)
            elif slo_type == "availability" or "availability" in slo_name.lower() or "success" in slo_name.lower():
                panel = self._build_availability_slo_panel(slo_name, slo_spec)
            elif "error" in slo_name.lower():
                panel = self._build_error_rate_slo_panel(slo_name, slo_spec)
            else:
                # Generic SLO panel
                panel = self._build_generic_slo_panel(slo_name, slo_spec)
            
            panels.append(panel)
        
        return panels
    
    def _build_availability_slo_panel(self, name: str, spec: dict) -> Panel:
        """Build availability SLO panel (gauge showing current availability)."""
        objective = spec.get("objective", 99.9)
        
        # Check if SLO spec has custom queries
        indicators = spec.get("indicators", [])
        if indicators and "success_ratio" in indicators[0]:
            good_query = indicators[0]["success_ratio"].get("good_query", "")
            total_query = indicators[0]["success_ratio"].get("total_query", "")
            
            # Replace service-specific values with $service template variable
            import re
            good_query = re.sub(r'service="[^"]*"', 'service="$service"', good_query)
            total_query = re.sub(r'service="[^"]*"', 'service="$service"', total_query)
            
            expr = f'({good_query}) / ({total_query}) * 100'
        else:
            # Fallback based on service type
            if self.context.type == 'worker':
                expr = (
                    'sum(rate(notifications_sent_total{service="$service",status!="failed"}[5m])) / '
                    'sum(rate(notifications_sent_total{service="$service"}[5m])) * 100'
                )
            elif self.context.type == 'stream':
                expr = (
                    'sum(rate(events_processed_total{service="$service",status!="error"}[5m])) / '
                    'sum(rate(events_processed_total{service="$service"}[5m])) * 100'
                )
            else:
                # Default: HTTP metrics for API services
                expr = (
                    'sum(rate(http_requests_total{service="$service",status!~"5.."}[5m])) / '
                    'sum(rate(http_requests_total{service="$service"}[5m])) * 100'
                )
        
        return Panel(
            title=f"{name.title()} SLO",
            panel_type="gauge",
            targets=[
                Target(
                    expr=expr,
                    legend_format="Availability %",
                )
            ],
            description=f"Current availability vs {objective}% SLO target",
            unit="percent",
            decimals=2,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": objective - 1, "color": "yellow"},
                {"value": objective, "color": "green"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _build_latency_slo_panel(self, name: str, spec: dict) -> Panel:
        """Build latency SLO panel (showing p50, p95, p99)."""
        objective = spec.get("objective", 99.0)
        threshold_ms = spec.get("threshold_ms", 500)
        
        # Check if SLO spec has custom latency query
        indicators = spec.get("indicators", [])
        if indicators and "latency_query" in indicators[0]:
            base_query = indicators[0]["latency_query"]
            # Extract the metric name and service filter
            # latency_query is already the p99 query, so we need to derive p50 and p95
            if "event_processing_duration_seconds_bucket" in base_query:
                metric = "event_processing_duration_seconds_bucket"
            elif "notification_processing_duration_seconds_bucket" in base_query:
                metric = "notification_processing_duration_seconds_bucket"
            else:
                metric = "http_request_duration_seconds_bucket"
            
            targets = [
                Target(
                    expr=f'histogram_quantile(0.50, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p50",
                    ref_id="A"
                ),
                Target(
                    expr=f'histogram_quantile(0.95, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p95",
                    ref_id="B"
                ),
                Target(
                    expr=f'histogram_quantile(0.99, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p99",
                    ref_id="C"
                ),
            ]
        else:
            # Fallback based on service type
            if self.context.type == 'worker':
                metric = "notification_processing_duration_seconds_bucket"
            elif self.context.type == 'stream':
                metric = "event_processing_duration_seconds_bucket"
            else:
                metric = "http_request_duration_seconds_bucket"
            
            targets = [
                Target(
                    expr=f'histogram_quantile(0.50, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p50",
                    ref_id="A"
                ),
                Target(
                    expr=f'histogram_quantile(0.95, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p95",
                    ref_id="B"
                ),
                Target(
                    expr=f'histogram_quantile(0.99, sum by (le) (rate({metric}{{service="$service"}}[5m]))) * 1000',
                    legend_format="p99",
                    ref_id="C"
                ),
            ]
        
        return Panel(
            title=f"{name.title()} SLO",
            panel_type="timeseries",
            targets=targets,
            description=f"Latency percentiles (target: {objective}% under {threshold_ms}ms)",
            unit="ms",
            decimals=0,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": threshold_ms * 0.8, "color": "yellow"},
                {"value": threshold_ms, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _build_error_rate_slo_panel(self, name: str, spec: dict) -> Panel:
        """Build error rate SLO panel."""
        objective = spec.get("objective", 99.9)
        error_budget = 100 - objective
        
        return Panel(
            title=f"{name.title()} SLO",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=(
                        'sum(rate(http_requests_total{service="$service",status=~"5.."}[5m])) / '
                        'sum(rate(http_requests_total{service="$service"}[5m])) * 100'
                    ),
                    legend_format="Error Rate %",
                )
            ],
            description=f"Error rate vs {error_budget}% budget",
            unit="percent",
            decimals=2,
            min=0,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": error_budget * 0.5, "color": "yellow"},
                {"value": error_budget, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _build_generic_slo_panel(self, name: str, spec: dict) -> Panel:
        """Build generic SLO panel for custom SLO types."""
        objective = spec.get("objective", 99.9)
        
        # Check if there's a custom metric query
        indicators = spec.get("indicators", [])
        if indicators and "metric" in indicators[0]:
            metric_query = indicators[0]["metric"]
            threshold = indicators[0].get("threshold", 100)
            
            return Panel(
                title=f"{name.title()}",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=metric_query,
                        legend_format="Current value",
                    )
                ],
                description=f"SLO objective: {objective}% (threshold: {threshold})",
                unit="short",
                decimals=2,
                grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
            )
        
        # Fallback if no metric specified - just show objective
        return Panel(
            title=f"{name.title()}",
            panel_type="stat",
            targets=[
                Target(
                    expr=f'{objective}',
                    legend_format="Objective",
                )
            ],
            description=f"SLO objective: {objective}%",
            unit="percent",
            decimals=2,
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _build_health_panels(self) -> List[Panel]:
        """Build general service health panels based on service type.
        
        Returns:
            List of panels showing service health metrics
        """
        panels = []
        
        # For API/web services, show HTTP metrics
        if self.context.type in ["api", "web", "service"]:
            # Request rate panel
            panels.append(Panel(
                title="Request Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='sum(rate(http_requests_total{service="$service"}[5m]))',
                        legend_format="Requests/sec",
                    )
                ],
                description="HTTP requests per second",
                unit="reqps",
                decimals=1,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Error rate panel
            panels.append(Panel(
                title="Error Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=(
                            'sum(rate(http_requests_total{service="$service",status=~"5.."}[5m])) / '
                            'sum(rate(http_requests_total{service="$service"}[5m])) * 100'
                        ),
                        legend_format="Error %",
                    )
                ],
                description="Percentage of requests returning 5xx errors",
                unit="percent",
                decimals=2,
                min=0,
                thresholds=[
                    {"value": 0, "color": "green"},
                    {"value": 1, "color": "yellow"},
                    {"value": 5, "color": "red"},
                ],
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Response time panel
            panels.append(Panel(
                title="Response Time (p95)",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m]))) * 1000',
                        legend_format="p95 latency",
                    )
                ],
                description="95th percentile response time",
                unit="ms",
                decimals=0,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
        
        # For stream-processor services, show event processing metrics
        elif self.context.type == "stream-processor":
            # Event rate panel
            panels.append(Panel(
                title="Event Processing Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='sum(rate(events_processed_total{service="$service"}[5m]))',
                        legend_format="Events/sec",
                    )
                ],
                description="Events processed per second",
                unit="ops",
                decimals=1,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Error rate panel
            panels.append(Panel(
                title="Event Error Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=(
                            'sum(rate(events_processed_total{service="$service",status="error"}[5m])) / '
                            'sum(rate(events_processed_total{service="$service"}[5m])) * 100'
                        ),
                        legend_format="Error %",
                    )
                ],
                description="Percentage of events that failed processing",
                unit="percent",
                decimals=2,
                min=0,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Processing time panel
            panels.append(Panel(
                title="Event Processing Time (p95)",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='histogram_quantile(0.95, sum by (le) (rate(event_processing_duration_seconds_bucket{service="$service"}[5m]))) * 1000',
                        legend_format="p95 latency",
                    )
                ],
                description="95th percentile event processing time",
                unit="ms",
                decimals=0,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
        
        # For worker services, show job/notification metrics
        elif self.context.type == "worker":
            # Job/notification rate panel
            panels.append(Panel(
                title="Job Processing Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='sum(rate(notifications_sent_total{service="$service"}[5m]))',
                        legend_format="Jobs/sec",
                    )
                ],
                description="Jobs processed per second",
                unit="ops",
                decimals=1,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Failure rate panel
            panels.append(Panel(
                title="Job Failure Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=(
                            'sum(rate(notifications_sent_total{service="$service",status="failed"}[5m])) / '
                            'sum(rate(notifications_sent_total{service="$service"}[5m])) * 100'
                        ),
                        legend_format="Failure %",
                    )
                ],
                description="Percentage of jobs that failed",
                unit="percent",
                decimals=2,
                min=0,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
            
            # Processing time panel
            panels.append(Panel(
                title="Job Processing Time (p95)",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr='histogram_quantile(0.95, sum by (le) (rate(notification_processing_duration_seconds_bucket{service="$service"}[5m]))) * 1000',
                        legend_format="p95 latency",
                    )
                ],
                description="95th percentile job processing time",
                unit="ms",
                decimals=0,
                grid_pos={"h": 8, "w": 8, "x": 0, "y": 0}
            ))
        
        return panels
    
    def _build_technology_panels(self) -> List[Panel]:
        """Build technology-specific panels based on ACTUAL dependencies.
        
        Only creates panels for technologies explicitly declared in the Dependencies resource.
        No automatic assumptions or generic panels.
        
        Returns:
            List of panels for detected technologies
        """
        panels = []
        seen_technologies = set()
        
        for dep in self.dependency_resources:
            dep_spec = dep.spec
            
            # Check for databases
            databases = dep_spec.get("databases", [])
            for db in databases:
                db_type = db.get("type", "").lower()
                
                # Skip if we've already added panels for this technology
                if db_type in seen_technologies:
                    continue
                seen_technologies.add(db_type)
                
                try:
                    template = get_template(db_type)
                    # Use overview or full panels based on setting
                    if self.full_panels:
                        tech_panels = template.get_panels("$service")
                    else:
                        tech_panels = template.get_overview_panels("$service")
                    panels.extend(tech_panels)
                except KeyError:
                    # Technology not in template registry - skip
                    pass
            
            # Check for message queues
            queues = dep_spec.get("message_queues", [])
            for queue in queues:
                queue_type = queue.get("type", "").lower()
                
                if queue_type in seen_technologies:
                    continue
                seen_technologies.add(queue_type)
                
                try:
                    template = get_template(queue_type)
                    # Use overview or full panels based on setting
                    if self.full_panels:
                        tech_panels = template.get_panels("$service")
                    else:
                        tech_panels = template.get_overview_panels("$service")
                    panels.extend(tech_panels)
                except KeyError:
                    pass
            
            # Check for orchestration platforms (Kubernetes, ECS, etc.)
            orchestration = dep_spec.get("orchestration", [])
            for orch in orchestration:
                orch_type = orch.get("type", "").lower()
                
                if orch_type in seen_technologies:
                    continue
                seen_technologies.add(orch_type)
                
                try:
                    template = get_template(orch_type)
                    # Use overview or full panels based on setting
                    if self.full_panels:
                        tech_panels = template.get_panels("$service")
                    else:
                        tech_panels = template.get_overview_panels("$service")
                    panels.extend(tech_panels)
                except KeyError:
                    pass
        
        return panels


def build_dashboard(service_context: ServiceContext, resources: List[Resource], full_panels: bool = False) -> Dict[str, Any]:
    """Convenience function to build a dashboard.
    
    Args:
        service_context: Service metadata
        resources: List of resources (SLOs, dependencies, etc.)
        full_panels: If True, use all template panels; if False, use overview only
        
    Returns:
        Complete dashboard object
        
    Example:
        >>> from nthlayer.specs.parser import parse_service_file
        >>> context, resources = parse_service_file("payment-api.yaml")
        >>> dashboard = build_dashboard(context, resources)
        >>> json_output = dashboard.to_grafana_payload()
        
        >>> # Generate with all panels
        >>> dashboard_full = build_dashboard(context, resources, full_panels=True)
    """
    builder = DashboardBuilder(service_context, resources, full_panels=full_panels)
    return builder.build()
