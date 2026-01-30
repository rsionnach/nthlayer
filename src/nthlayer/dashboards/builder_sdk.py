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

import logging
from typing import Any, Dict, List, Optional

from grafana_foundation_sdk.cog.encoder import JSONEncoder

from nthlayer.dashboards.resolver import MetricResolver, create_resolver
from nthlayer.dashboards.sdk_adapter import SDKAdapter
from nthlayer.dashboards.templates import get_template, get_template_or_none
from nthlayer.specs.models import Resource, ServiceContext

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
        use_intent_templates: bool = True,
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
        self.validation_warnings: list[str] = []
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
                    discovery_client=discovery_client, custom_overrides=custom_metric_overrides
                )
            else:
                self.resolver = create_resolver(
                    prometheus_url=prometheus_url, custom_overrides=custom_metric_overrides
                )
        elif custom_metric_overrides:
            # Create resolver with just custom overrides (no discovery)
            self.resolver = MetricResolver(custom_overrides=custom_metric_overrides)

        # Validator (optional)
        self.validator: Optional["DashboardValidator"] = None
        if enable_validation and discovery_client:
            from nthlayer.dashboards.validator import DashboardValidator

            self.validator = DashboardValidator(discovery_client)

    def _extract_custom_overrides(self) -> Dict[str, str]:
        """Extract custom metric overrides from service resources."""
        overrides = {}

        # Look for metrics section in resources
        for resource in self.resources:
            if hasattr(resource, "spec") and isinstance(resource.spec, dict):
                metrics = resource.spec.get("metrics", {})
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
        # Step 1: Discover metrics if resolver available AND no metrics already discovered
        # Skip discovery if metrics were pre-loaded (e.g., from global discovery)
        if self.resolver and self.resolver.discovery and not self.resolver.discovered_metrics:
            try:
                metric_count = self.resolver.discover_for_service(self.context.name)
                logger.info(f"Discovered {metric_count} metrics for {self.context.name}")
            except Exception as e:
                logger.warning(f"Metric discovery failed: {e}, continuing without discovery")

        # Create dashboard
        dash = self.adapter.create_dashboard(service=self.context, editable=True)

        # Collect all panels organized by section
        all_panels = []

        # Build SLO panels
        slo_panels = []
        if self.slo_resources:
            slo_panels = self._build_slo_panels()
            logger.info(f"Added {len(slo_panels)} SLO panels")

        # Build service health panels
        health_panels = self._build_health_panels()
        logger.info(f"Added {len(health_panels)} health panels")

        # Build technology/dependency panels
        tech_panels = []
        if self.dependency_resources:
            tech_panels = self._build_technology_panels()
            logger.info(f"Added {len(tech_panels)} technology panels")

        # Validate panels if enabled
        if self.validator:
            slo_panels = self._validate_panels(slo_panels) if slo_panels else []
            health_panels = self._validate_panels(health_panels)
            tech_panels = self._validate_panels(tech_panels) if tech_panels else []

        # Log resolution summary if hybrid model active
        if self.resolver:
            summary = self.resolver.get_resolution_summary()
            if summary.get("unresolved", 0) > 0:
                logger.warning(
                    f"Resolution summary: {summary.get('resolved', 0)} resolved, "
                    f"{summary.get('fallback', 0)} fallback, "
                    f"{summary.get('unresolved', 0)} unresolved"
                )

        # Add panels organized into rows (expanded by default)
        # For expanded rows, panels go at root level AFTER the row header

        # Row 1: SLO Metrics
        if slo_panels:
            slo_row = self.adapter.create_row("SLO Metrics")
            dash.with_row(slo_row)
            for panel in slo_panels:
                dash.with_panel(panel)
            all_panels.extend(slo_panels)

        # Row 2: Service Health
        if health_panels:
            health_row = self.adapter.create_row("Service Health")
            dash.with_row(health_row)
            for panel in health_panels:
                dash.with_panel(panel)
            all_panels.extend(health_panels)

        # Row 3: Dependencies
        if tech_panels:
            deps_row = self.adapter.create_row("Dependencies")
            dash.with_row(deps_row)
            for panel in tech_panels:
                dash.with_panel(panel)
            all_panels.extend(tech_panels)

        # Build and serialize
        dash_model = dash.build()
        json_str = JSONEncoder(sort_keys=True, indent=2).encode(dash_model)

        # Parse to dict for compatibility
        import json

        dashboard_dict = json.loads(json_str)

        # Substitute $service variable with actual service name
        json_str = json.dumps(dashboard_dict)
        json_str = json_str.replace('"$service"', f'"{self.context.name}"')
        json_str = json_str.replace("$service", self.context.name)
        dashboard_dict = json.loads(json_str)

        # Post-process panels to add noValue messages for guidance panels
        self._apply_no_value_messages(dashboard_dict, all_panels)

        # Wrap in Grafana API format
        return {
            "dashboard": dashboard_dict,
            "overwrite": True,
            "message": f"Auto-generated dashboard for {self.context.name}",
        }

    def _apply_no_value_messages(self, dashboard_dict: Dict[str, Any], panels: List[Any]) -> None:
        """Apply noValue messages to panels in the dashboard JSON.

        This post-processes the dashboard JSON to add Grafana's noValue
        configuration for guidance panels, making it clear what
        instrumentation is needed when metrics are missing.
        """
        if "panels" not in dashboard_dict:
            return

        # Build a mapping of panel titles to noValue messages
        no_value_map = {}
        for panel in panels:
            if hasattr(panel, "_no_value_message") and panel._no_value_message:
                # Get title from panel builder
                try:
                    panel_model = panel.build() if hasattr(panel, "build") else None
                    if panel_model and hasattr(panel_model, "title"):
                        no_value_map[panel_model.title] = panel._no_value_message
                except (AttributeError, TypeError, ValueError):
                    pass

        # Apply noValue messages to matching panels in JSON
        for panel_json in dashboard_dict.get("panels", []):
            if not isinstance(panel_json, dict):
                continue
            title = panel_json.get("title", "")
            if title in no_value_map:
                # Add noValue configuration to fieldConfig
                if "fieldConfig" not in panel_json or panel_json["fieldConfig"] is None:
                    panel_json["fieldConfig"] = {}
                if (
                    "defaults" not in panel_json["fieldConfig"]
                    or panel_json["fieldConfig"]["defaults"] is None
                ):
                    panel_json["fieldConfig"]["defaults"] = {}

                panel_json["fieldConfig"]["defaults"]["noValue"] = no_value_map[title]

                # Also add to options for stat panels
                if panel_json.get("type") == "stat":
                    if "options" not in panel_json or panel_json["options"] is None:
                        panel_json["options"] = {}
                    panel_json["options"]["colorMode"] = "background"
                    panel_json["options"]["graphMode"] = "none"

    def _build_slo_panels(self) -> List[Any]:
        """Build SLO panels using SDK."""
        panels = []

        for slo_resource in self.slo_resources:
            slo_spec = slo_resource.spec

            # Extract SLO details
            if isinstance(slo_spec, dict):
                slo_name = slo_spec.get("name", slo_resource.name or "Unknown SLO")
                objective = slo_spec.get("objective", 99.9)
                # Check for query in multiple places (spec.query or spec.indicator.query)
                slo_query = slo_spec.get("query", "")
                if not slo_query:
                    indicator = slo_spec.get("indicator", {})
                    slo_query = indicator.get("query", "")
            else:
                slo_name = getattr(slo_spec, "name", slo_resource.name or "Unknown SLO")
                objective = getattr(slo_spec, "target", 99.9)
                slo_query = getattr(slo_spec, "query", "")

            # Create prometheus query
            if slo_query:
                # Use provided query (substitute variables)
                expr = slo_query.replace("${service}", "$service")
                prom_query = self.adapter.create_prometheus_query(expr=expr, legend_format=slo_name)
            else:
                # Generate query from SLO type using adapter (service-type-aware)
                prom_query = self.adapter.convert_slo_to_query(
                    slo_spec, service_type=self.context.type
                )

            # Create panel
            panel = self.adapter.create_timeseries_panel(
                title=slo_name,
                description=f"Target: {objective}%",
                queries=[prom_query],
                unit="percent",
            )

            panels.append(panel)

        return panels

    def _build_health_panels(self) -> List[Any]:
        """Build service health panels using SDK.

        With Hybrid Model (use_intent_templates=True):
        - Uses intent-based templates for service-type-appropriate metrics
        - Provides fallback chains and guidance panels

        Without Hybrid Model (use_intent_templates=False):
        - Uses hardcoded metric names (legacy behavior)
        """
        if self.use_intent_templates:
            return self._build_intent_health_panels()
        else:
            return self._build_legacy_health_panels()

    def _build_intent_health_panels(self) -> List[Any]:
        """Build health panels using intent-based templates."""
        panels = []
        service_type = self.context.type

        # Get appropriate intent template for service type
        health_template = self._get_health_intent_template(service_type)

        if health_template:
            # Set resolver if available
            if self.resolver:
                health_template.resolver = self.resolver

            # Get panels (resolved through intent system)
            template_panels = health_template.get_health_panels("$service")

            # Convert to SDK panels
            for old_panel in template_panels:
                sdk_panel = self._convert_panel_to_sdk(old_panel)
                if sdk_panel:
                    panels.append(sdk_panel)
        else:
            # Fall back to legacy behavior
            logger.debug(f"No intent template for service type {service_type}, using legacy")
            panels = self._build_legacy_health_panels()

        return panels

    def _get_health_intent_template(self, service_type: str):
        """Get intent-based health template for service type.

        Uses centralized template registry instead of hardcoded if-elif chain.
        Falls back to 'http' template for unknown service types.
        """
        # Try exact match first, then fall back to http for unknown types
        template = get_template_or_none(service_type)
        if template is not None:
            return template

        # Default: HTTP-based services (api, web, service, or unknown)
        return get_template_or_none("http")

    def _build_legacy_health_panels(self) -> List[Any]:
        """Build health panels using hardcoded metrics (legacy behavior)."""
        panels = []
        service_type = self.context.type

        if service_type == "stream":
            # Stream processors use events_processed metrics
            rate_query = self.adapter.create_prometheus_query(
                expr='sum(rate(events_processed_total{service="$service"}[5m]))',
                legend_format="events/sec",
            )
            rate_panel = self.adapter.create_timeseries_panel(
                title="Event Rate",
                description="Events processed per second",
                queries=[rate_query],
                unit="short",
            )
            panels.append(rate_panel)

            error_query = self.adapter.create_prometheus_query(
                expr='sum(rate(events_processed_total{service="$service",status="error"}[5m])) / sum(rate(events_processed_total{service="$service"}[5m])) * 100',  # noqa: E501
                legend_format="error %",
            )
            error_panel = self.adapter.create_timeseries_panel(
                title="Error Rate",
                description="Percentage of events failing",
                queries=[error_query],
                unit="percent",
            )
            panels.append(error_panel)

            latency_query = self.adapter.create_prometheus_query(
                expr='histogram_quantile(0.95, sum by (le) (rate(event_processing_duration_seconds_bucket{service="$service"}[5m])))',  # noqa: E501
                legend_format="p95 latency",
            )
            latency_panel = self.adapter.create_timeseries_panel(
                title="Processing Latency (p95)",
                description="95th percentile event processing duration",
                queries=[latency_query],
                unit="s",
            )
            panels.append(latency_panel)

        elif service_type == "worker":
            # Workers use notification/job metrics
            rate_query = self.adapter.create_prometheus_query(
                expr='sum(rate(notifications_sent_total{service="$service"}[5m]))',
                legend_format="notifications/sec",
            )
            rate_panel = self.adapter.create_timeseries_panel(
                title="Notification Rate",
                description="Notifications sent per second",
                queries=[rate_query],
                unit="short",
            )
            panels.append(rate_panel)

            error_query = self.adapter.create_prometheus_query(
                expr='sum(rate(notifications_sent_total{service="$service",status="failed"}[5m])) / sum(rate(notifications_sent_total{service="$service"}[5m])) * 100',  # noqa: E501
                legend_format="error %",
            )
            error_panel = self.adapter.create_timeseries_panel(
                title="Error Rate",
                description="Percentage of notifications failing",
                queries=[error_query],
                unit="percent",
            )
            panels.append(error_panel)

            latency_query = self.adapter.create_prometheus_query(
                expr='histogram_quantile(0.95, sum by (le) (rate(notification_processing_duration_seconds_bucket{service="$service"}[5m])))',  # noqa: E501
                legend_format="p95 latency",
            )
            latency_panel = self.adapter.create_timeseries_panel(
                title="Processing Latency (p95)",
                description="95th percentile notification processing duration",
                queries=[latency_query],
                unit="s",
            )
            panels.append(latency_panel)

        else:
            # Default: HTTP-based services (api, web, service)
            rate_query = self.adapter.create_prometheus_query(
                expr='sum(rate(http_requests_total{service="$service"}[5m]))',
                legend_format="requests/sec",
            )
            rate_panel = self.adapter.create_timeseries_panel(
                title="Request Rate",
                description="Total requests per second",
                queries=[rate_query],
                unit="reqps",
            )
            panels.append(rate_panel)

            error_query = self.adapter.create_prometheus_query(
                expr='sum(rate(http_requests_total{service="$service",status=~"5.."}[5m])) / sum(rate(http_requests_total{service="$service"}[5m])) * 100',  # noqa: E501
                legend_format="error %",
            )
            error_panel = self.adapter.create_timeseries_panel(
                title="Error Rate",
                description="Percentage of requests returning 5xx",
                queries=[error_query],
                unit="percent",
            )
            panels.append(error_panel)

            latency_query = self.adapter.create_prometheus_query(
                expr='histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m])))',  # noqa: E501
                legend_format="p95 latency",
            )
            latency_panel = self.adapter.create_timeseries_panel(
                title="Request Latency (p95)",
                description="95th percentile request duration",
                queries=[latency_query],
                unit="s",
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
            databases = dep_spec.get("databases", []) if isinstance(dep_spec, dict) else []
            caches = dep_spec.get("caches", []) if isinstance(dep_spec, dict) else []
            queues = dep_spec.get("queues", []) if isinstance(dep_spec, dict) else []

            # Combine all technology dependencies
            all_deps = []
            for db in databases:
                db_type = (
                    db.get("type", "unknown")
                    if isinstance(db, dict)
                    else getattr(db, "type", "unknown")
                )
                all_deps.append(("database", db_type))
            for cache in caches:
                cache_type = (
                    cache.get("type", "redis")
                    if isinstance(cache, dict)
                    else getattr(cache, "type", "redis")
                )
                all_deps.append(("cache", cache_type))
            for queue in queues:
                queue_type = (
                    queue.get("type", "kafka")
                    if isinstance(queue, dict)
                    else getattr(queue, "type", "kafka")
                )
                all_deps.append(("queue", queue_type))

            # Build panels for each dependency
            for _dep_category, dep_type in all_deps:
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

            # Use the technology type as service label for dependency panels.
            # Infrastructure exporters (postgres_exporter, redis_exporter, etc.)
            # label metrics with their own service name (e.g. "postgresql"),
            # not the parent application's name (e.g. "payment-api").
            template_panels = intent_template.get_panels(technology)

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
        """Get intent-based template for technology.

        Uses centralized template registry instead of hardcoded if-elif chain.
        Returns None if no template found (triggers legacy fallback).
        """
        return get_template_or_none(technology)

    def _build_legacy_panels(self, technology: str) -> List[Any]:
        """Build panels using legacy templates with hardcoded metrics."""
        panels = []

        # Map technology names
        if technology == "mysql":
            technology = "postgresql"  # Similar metrics structure

        template = get_template(technology)
        if template and hasattr(template, "get_panels"):
            # Use technology name for dependency panels — infrastructure exporters
            # label metrics with their own service name, not the application's.
            template_panels = template.get_panels(technology)

            for old_panel in template_panels:
                sdk_panel = self._convert_panel_to_sdk(old_panel)
                if sdk_panel:
                    panels.append(sdk_panel)

        return panels

    def _convert_panel_to_sdk(self, old_panel) -> Optional[Any]:
        """Convert a legacy Panel to SDK panel.

        Handles:
        - Regular panels with queries
        - Guidance panels (no queries, with noValue message)
        """
        try:
            # Check if this is a guidance panel (no targets, has guidance metadata)
            is_guidance = getattr(old_panel, "is_guidance_panel", False)
            no_value_msg = getattr(old_panel, "no_value_message", None)

            # Create queries with proper RefId assignment
            queries = []
            ref_id_counter = ord("A")  # Start with 'A'
            for target in getattr(old_panel, "targets", []):
                # Get ref_id from target, or generate one
                target_ref_id = getattr(target, "ref_id", None)
                if not target_ref_id:
                    target_ref_id = chr(ref_id_counter)
                    ref_id_counter += 1

                q = self.adapter.create_prometheus_query(
                    expr=target.expr,
                    legend_format=getattr(target, "legend_format", ""),
                    ref_id=target_ref_id,
                )
                queries.append(q)

            # Handle guidance panels specially
            if is_guidance or (not queries and no_value_msg):
                # Create a stat panel that will show noValue message
                panel = self.adapter.create_stat_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, "description", ""),
                    query=None,
                )
                # Store noValue message for post-processing
                if no_value_msg:
                    panel._no_value_message = no_value_msg
                return panel

            if not queries:
                return None

            # Create panel based on type
            panel_type = getattr(old_panel, "panel_type", "timeseries")

            if panel_type == "stat":
                return self.adapter.create_stat_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, "description", ""),
                    query=queries[0],
                )
            elif panel_type == "gauge":
                return self.adapter.create_gauge_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, "description", ""),
                    query=queries[0],
                )
            elif panel_type == "text":
                # Text panel for documentation/guidance
                return self.adapter.create_text_panel(
                    title=old_panel.title, content=getattr(old_panel, "description", "")
                )
            else:
                return self.adapter.create_timeseries_panel(
                    title=old_panel.title,
                    description=getattr(old_panel, "description", ""),
                    queries=queries,
                )
        except Exception as e:
            logger.warning(f"Failed to convert panel {getattr(old_panel, 'title', 'unknown')}: {e}")
            return None

    def _validate_panels(self, panels: List[Any]) -> List[Any]:
        """Validate panels against discovered metrics.

        Note: Panel validation during build is intentionally minimal.
        Full validation (checking if metrics exist in Prometheus) is done
        via the separate 'nthlayer dashboard validate' command, which allows
        dashboard generation to work offline without Prometheus connectivity.
        """
        if not self.validator:
            return panels

        # Validation is handled separately via 'nthlayer dashboard validate'
        # to allow offline dashboard generation. The validator checks intents
        # against Prometheus metrics, but this requires connectivity.
        return panels


def build_dashboard(
    service_context: ServiceContext,
    resources: List[Resource],
    full_panels: bool = False,
    prometheus_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Grafana dashboard from service specification.

    Convenience function for backward compatibility.

    Args:
        service_context: Service metadata
        resources: List of resources
        full_panels: Include all template panels
        prometheus_url: Optional Prometheus URL for metric discovery

    Returns:
        Dashboard JSON dictionary
    """
    builder = DashboardBuilderSDK(
        service_context=service_context,
        resources=resources,
        full_panels=full_panels,
        prometheus_url=prometheus_url,
    )
    return builder.build()
