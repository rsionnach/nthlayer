"""
Intent-Based Nginx Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for Nginx metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class NginxIntentTemplate(IntentBasedTemplate):
    """Nginx monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "nginx"

    @property
    def display_name(self) -> str:
        return "Nginx"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Nginx panel specifications with intents."""
        return [
            self._requests_rate_spec(service_name),
            self._connections_spec(service_name),
            self._response_status_spec(service_name),
            self._request_duration_spec(service_name),
            self._upstream_response_time_spec(service_name),
            self._bytes_sent_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Nginx panels."""
        specs = [
            self._requests_rate_spec(service_name),
            self._connections_spec(service_name),
            self._response_status_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _requests_rate_spec(self, service: str) -> PanelSpec:
        """Nginx requests rate panel spec."""
        return PanelSpec(
            title="Requests/sec",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.requests_total",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="reqps",
            description="HTTP requests per second",
        )

    def _connections_spec(self, service: str) -> PanelSpec:
        """Nginx connections panel spec."""
        return PanelSpec(
            title="Active Connections",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.connections_active",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Current active client connections",
        )

    def _response_status_spec(self, service: str) -> PanelSpec:
        """Nginx response status codes panel spec."""
        return PanelSpec(
            title="Response Status Codes",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.http_requests_total",
            query_template=f'sum by (status) (rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="reqps",
            description="HTTP responses by status code",
        )

    def _request_duration_spec(self, service: str) -> PanelSpec:
        """Nginx request duration panel spec."""
        return PanelSpec(
            title="Request Duration (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.request_duration_seconds",
            query_template=(
                f"histogram_quantile(0.95, sum by (le) "
                f'(rate({{{{metric}}}}_bucket{{service="{service}"}}[5m])))'
            ),
            unit="s",
            description="95th percentile request duration",
        )

    def _upstream_response_time_spec(self, service: str) -> PanelSpec:
        """Nginx upstream response time panel spec."""
        return PanelSpec(
            title="Upstream Response Time",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.upstream_response_time",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="s",
            description="Time to receive response from upstream",
        )

    def _bytes_sent_spec(self, service: str) -> PanelSpec:
        """Nginx bytes sent panel spec."""
        return PanelSpec(
            title="Bytes Sent/sec",
            panel_type=PanelType.TIMESERIES,
            intent="nginx.bytes_sent",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="Bps",
            description="Bytes sent to clients per second",
        )
