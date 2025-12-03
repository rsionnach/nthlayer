"""
SDK Adapter - Bridge between NthLayer abstractions and Grafana Foundation SDK.

This module converts NthLayer service specifications into Grafana Foundation SDK
builders, providing type-safe dashboard generation with official Grafana support.
"""

from typing import Any, List, Optional

from grafana_foundation_sdk.builders import dashboard, gauge, prometheus, stat, timeseries
from grafana_foundation_sdk.builders.dashboard import Row
from grafana_foundation_sdk.cog.encoder import JSONEncoder

from nthlayer.dashboards.models import Panel, TemplateVariable
from nthlayer.slos.models import SLO
from nthlayer.specs.models import ServiceContext


class SDKAdapter:
    """Adapter to convert NthLayer models to Grafana Foundation SDK builders."""
    
    @staticmethod
    def create_dashboard(
        service: ServiceContext,
        uid: Optional[str] = None,
        editable: bool = True
    ) -> dashboard.Dashboard:
        """
        Create Grafana dashboard from service context.
        
        Args:
            service: Service context with metadata
            uid: Optional dashboard UID (defaults to f"{service.name}-overview")
            editable: Whether dashboard is editable
            
        Returns:
            Dashboard builder configured with service metadata
        """
        dash = dashboard.Dashboard(f"{service.name} - Service Dashboard")
        
        # Set UID
        dash_uid = uid or f"{service.name}-overview"
        dash.uid(dash_uid)
        
        # Add service metadata as tags
        tags = [service.team, service.tier, service.type]
        if hasattr(service, 'environment') and service.environment:
            tags.append(service.environment)
        dash.tags(tags)
        
        # Set description
        description = f"Auto-generated dashboard for {service.name} service"
        if hasattr(service, 'description') and service.description:
            description = service.description
        dash.description(description)
        
        # Configure dashboard settings
        if editable:
            dash.editable()
        else:
            dash.readonly()
        
        # Set time range (default: 6 hours)
        dash.time("now-6h", "now")
        
        # Set timezone to browser
        dash.timezone("browser")
        
        return dash
    
    @staticmethod
    def create_row(
        title: str,
        collapsed: bool = False
    ) -> Row:
        """
        Create a dashboard row for organizing panels.
        
        Args:
            title: Row title (e.g., "SLO Metrics", "Service Health", "Dependencies")
            collapsed: Whether the row should be collapsed by default
            
        Returns:
            Row builder
        """
        row = Row(title)
        if collapsed:
            row.collapsed(True)
        return row
    
    @staticmethod
    def create_timeseries_panel(
        title: str,
        description: str = "",
        queries: Optional[List[prometheus.Dataquery]] = None,
        unit: str = "short",
        min_val: Optional[float] = None,
        legend_format: Optional[str] = None
    ) -> timeseries.Panel:
        """
        Create timeseries panel with Prometheus queries.
        
        Args:
            title: Panel title
            description: Panel description
            queries: List of Prometheus queries
            unit: Y-axis unit (short, percent, bytes, etc.)
            min_val: Minimum Y-axis value
            legend_format: Format for legend labels
            
        Returns:
            Timeseries panel builder
        """
        panel = timeseries.Panel()
        panel.title(title)
        
        if description:
            panel.description(description)
        
        # Add queries
        if queries:
            for query in queries:
                if legend_format and not hasattr(query, 'legend_format'):
                    query.legend_format(legend_format)
                panel.with_target(query)
        
        return panel
    
    @staticmethod
    def create_stat_panel(
        title: str,
        description: str = "",
        query: Optional[prometheus.Dataquery] = None,
        unit: str = "short",
        color_mode: str = "value"
    ) -> stat.Panel:
        """
        Create stat panel for single value display.
        
        Args:
            title: Panel title
            description: Panel description
            query: Prometheus query
            unit: Display unit
            color_mode: Color mode ("value", "background", "none")
            
        Returns:
            Stat panel builder
        """
        panel = stat.Panel()
        panel.title(title)
        
        if description:
            panel.description(description)
        
        if query:
            panel.with_target(query)
        
        return panel
    
    @staticmethod
    def create_gauge_panel(
        title: str,
        description: str = "",
        query: Optional[prometheus.Dataquery] = None,
        unit: str = "percent",
        min_val: float = 0,
        max_val: float = 100
    ) -> gauge.Panel:
        """
        Create gauge panel for percentage/ratio display.
        
        Args:
            title: Panel title
            description: Panel description
            query: Prometheus query
            unit: Display unit
            min_val: Minimum gauge value
            max_val: Maximum gauge value
            
        Returns:
            Gauge panel builder
        """
        panel = gauge.Panel()
        panel.title(title)
        
        if description:
            panel.description(description)
        
        if query:
            panel.with_target(query)
        
        return panel
    
    @staticmethod
    def create_text_panel(
        title: str,
        content: str = "",
        mode: str = "markdown"
    ) -> Any:
        """
        Create text panel for guidance/documentation.
        
        Args:
            title: Panel title
            content: Markdown or HTML content
            mode: Content mode ("markdown" or "html")
            
        Returns:
            Text panel builder (or fallback to dict if SDK doesn't support)
        """
        try:
            from grafana_foundation_sdk.builders import text
            panel = text.Panel()
            panel.title(title)
            if hasattr(panel, 'content'):
                panel.content(content)
            if hasattr(panel, 'mode'):
                panel.mode(mode)
            return panel
        except ImportError:
            # Fallback: create a stat panel with the title indicating guidance
            panel = stat.Panel()
            panel.title(f"{title}")
            panel.description(content)
            return panel
    
    @staticmethod
    def create_guidance_panel(
        title: str,
        missing_intents: list,
        exporter_recommendation: str = "",
        technology: str = ""
    ) -> Any:
        """
        Create a guidance panel with noValue message for missing metrics.
        
        Uses Grafana's built-in "No data" message configuration to provide
        clear instructions when metrics are unavailable.
        
        Args:
            title: Panel title
            missing_intents: List of unresolved intent names
            exporter_recommendation: Helm/docker command to install exporter
            technology: Technology name for context
            
        Returns:
            Stat panel configured with noValue guidance message
        """
        # Build guidance message for noValue
        if exporter_recommendation:
            no_value_msg = f"Install {technology} exporter: {exporter_recommendation}"
        else:
            intent_list = ", ".join(missing_intents[:3])
            if len(missing_intents) > 3:
                intent_list += f" (+{len(missing_intents) - 3} more)"
            no_value_msg = f"Missing metrics: {intent_list}. Add instrumentation."
        
        # Create stat panel with noValue configuration
        panel = stat.Panel()
        panel.title(f"{title}")
        panel.description(
            f"This panel requires metrics that aren't currently available.\n\n"
            f"**Missing:** {', '.join(missing_intents)}\n\n"
            f"**Solution:** {exporter_recommendation or 'Add custom metrics to service YAML'}"
        )
        
        # Note: The noValue configuration will be added post-build
        # since the SDK may not support all options directly
        return panel, no_value_msg
    
    @staticmethod
    def create_prometheus_query(
        expr: str,
        legend_format: Optional[str] = None,
        interval: Optional[str] = None,
        ref_id: str = "A"
    ) -> prometheus.Dataquery:
        """
        Create Prometheus query for panels.
        
        Args:
            expr: PromQL expression
            legend_format: Legend format (e.g., "{{method}}")
            interval: Query interval (e.g., "30s")
            ref_id: Query reference ID
            
        Returns:
            Prometheus dataquery
        """
        query = prometheus.Dataquery()
        query.expr(expr)
        
        if legend_format:
            query.legend_format(legend_format)
        
        if interval:
            query.interval(interval)
        
        # Set ref_id if available
        if hasattr(query, 'ref_id'):
            query.ref_id(ref_id)
        
        return query
    
    @staticmethod
    def convert_panel_to_sdk(panel: Panel) -> Any:
        """
        Convert NthLayer Panel to SDK panel builder.
        
        Args:
            panel: NthLayer Panel model
            
        Returns:
            SDK panel builder (timeseries, stat, or gauge)
        """
        # Determine panel type from NthLayer panel
        panel_type = getattr(panel, 'type', 'timeseries')
        
        # Create queries
        queries = []
        for target in panel.targets:
            query = SDKAdapter.create_prometheus_query(
                expr=target.expr,
                legend_format=getattr(target, 'legend_format', None)
            )
            queries.append(query)
        
        # Create appropriate panel type
        if panel_type == 'stat':
            sdk_panel = SDKAdapter.create_stat_panel(
                title=panel.title,
                description=getattr(panel, 'description', ''),
                query=queries[0] if queries else None
            )
        elif panel_type == 'gauge':
            sdk_panel = SDKAdapter.create_gauge_panel(
                title=panel.title,
                description=getattr(panel, 'description', ''),
                query=queries[0] if queries else None
            )
        else:
            # Default to timeseries
            sdk_panel = SDKAdapter.create_timeseries_panel(
                title=panel.title,
                description=getattr(panel, 'description', ''),
                queries=queries
            )
        
        return sdk_panel
    
    @staticmethod
    def convert_slo_to_query(slo: Any, time_window: str = "5m", service_type: str = "api") -> prometheus.Dataquery:
        """
        Convert SLO specification to Prometheus query.
        
        Args:
            slo: SLO model or dict spec
            time_window: Time window for rate calculations
            service_type: Service type (api, worker, stream) for metric selection
            
        Returns:
            Prometheus query for SLO metric
        """
        # Handle both SLO objects and dicts
        if isinstance(slo, dict):
            slo_name = slo.get('name', '')
            slo_query = slo.get('query', '')
            target = slo.get('target', 99.9)
        else:
            slo_name = slo.name
            slo_query = getattr(slo, 'query', '')
            target = slo.target
        
        # If SLO already has a query, use it
        if slo_query:
            expr = slo_query
        else:
            # Build query based on SLO name/type AND service type
            # For availability SLOs (success rate)
            if "availability" in slo_name.lower() or "success" in slo_name.lower():
                if service_type == 'worker':
                    expr = f"sum(rate(notifications_sent_total{{service=\"$service\",status!=\"failed\"}}[{time_window}])) / sum(rate(notifications_sent_total{{service=\"$service\"}}[{time_window}])) * 100"
                elif service_type == 'stream':
                    expr = f"sum(rate(events_processed_total{{service=\"$service\",status!=\"error\"}}[{time_window}])) / sum(rate(events_processed_total{{service=\"$service\"}}[{time_window}])) * 100"
                else:
                    expr = f"sum(rate(http_requests_total{{service=\"$service\",status!~\"5..\"}}[{time_window}])) / sum(rate(http_requests_total{{service=\"$service\"}}[{time_window}])) * 100"
            # For latency SLOs (percentile)
            elif "latency" in slo_name.lower() or "p95" in slo_name.lower() or "p99" in slo_name.lower():
                percentile = "0.95" if "p95" in slo_name.lower() else "0.99"
                if service_type == 'worker':
                    expr = f"histogram_quantile({percentile}, sum by (le) (rate(notification_processing_duration_seconds_bucket{{service=\"$service\"}}[{time_window}]))) * 1000"
                elif service_type == 'stream':
                    expr = f"histogram_quantile({percentile}, sum by (le) (rate(event_processing_duration_seconds_bucket{{service=\"$service\"}}[{time_window}]))) * 1000"
                else:
                    expr = f"histogram_quantile({percentile}, sum by (le) (rate(http_request_duration_seconds_bucket{{service=\"$service\"}}[{time_window}]))) * 1000"
            # For error rate SLOs
            elif "error" in slo_name.lower():
                if service_type == 'worker':
                    expr = f"sum(rate(notifications_sent_total{{service=\"$service\",status=\"failed\"}}[{time_window}])) / sum(rate(notifications_sent_total{{service=\"$service\"}}[{time_window}])) * 100"
                elif service_type == 'stream':
                    expr = f"sum(rate(events_processed_total{{service=\"$service\",status=\"error\"}}[{time_window}])) / sum(rate(events_processed_total{{service=\"$service\"}}[{time_window}])) * 100"
                else:
                    expr = f"sum(rate(http_requests_total{{service=\"$service\",status=~\"5..\"}}[{time_window}])) / sum(rate(http_requests_total{{service=\"$service\"}}[{time_window}])) * 100"
            else:
                # Default: simple rate
                if service_type == 'worker':
                    expr = f"sum(rate(notifications_sent_total{{service=\"$service\"}}[{time_window}]))"
                elif service_type == 'stream':
                    expr = f"sum(rate(events_processed_total{{service=\"$service\"}}[{time_window}]))"
                else:
                    expr = f"sum(rate(http_requests_total{{service=\"$service\"}}[{time_window}]))"
        
        query = SDKAdapter.create_prometheus_query(
            expr=expr,
            legend_format=slo_name
        )
        
        return query
    
    @staticmethod
    def serialize_dashboard(dash: dashboard.Dashboard) -> str:
        """
        Serialize dashboard to Grafana JSON.
        
        Args:
            dash: Dashboard builder
            
        Returns:
            JSON string for Grafana import
        """
        model = dash.build()
        encoder = JSONEncoder(sort_keys=False, indent=2)
        return encoder.encode(model)
    
    @staticmethod
    def add_template_variables(
        dash: dashboard.Dashboard,
        variables: List[TemplateVariable]
    ) -> dashboard.Dashboard:
        """
        Add template variables to dashboard.
        
        Args:
            dash: Dashboard builder
            variables: List of template variables
            
        Returns:
            Dashboard with variables added
        """
        # Note: SDK variable support may need special handling
        # For now, we'll skip this and handle in the builder integration
        # TODO: Implement once we understand SDK's variable API
        return dash


# Convenience functions for common patterns

def create_service_dashboard(
    service: ServiceContext,
    slos: Optional[List[SLO]] = None
) -> dashboard.Dashboard:
    """
    Create complete dashboard for a service with SLO panels.
    
    Args:
        service: Service context
        slos: List of SLOs to visualize
        
    Returns:
        Configured dashboard builder
    """
    adapter = SDKAdapter()
    dash = adapter.create_dashboard(service)
    
    # Add SLO panels if provided
    if slos:
        for slo in slos:
            query = adapter.convert_slo_to_query(slo)
            panel = adapter.create_timeseries_panel(
                title=slo.name,
                description=f"Target: {slo.target}",
                queries=[query]
            )
            # Note: Panel addition handled by builder
    
    return dash
