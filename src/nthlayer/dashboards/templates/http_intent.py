"""
Intent-Based HTTP/API Service Dashboard Template.

This template provides health panels for HTTP-based services (api, web, service types)
using the intent system for metric resolution.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class HTTPIntentTemplate(IntentBasedTemplate):
    """HTTP/API service monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "http"
    
    @property
    def display_name(self) -> str:
        return "HTTP/API"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get HTTP panel specifications with intents."""
        return [
            self._request_rate_spec(service_name),
            self._error_rate_spec(service_name),
            self._latency_p95_spec(service_name),
            self._latency_p99_spec(service_name),
            self._availability_spec(service_name),
            self._requests_in_flight_spec(service_name),
        ]
    
    def get_health_panels(self, service_name: str = "$service") -> List:
        """Get core health panels for service dashboards."""
        specs = [
            self._request_rate_spec(service_name),
            self._error_rate_spec(service_name),
            self._latency_p95_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _request_rate_spec(self, service: str) -> PanelSpec:
        """Request rate panel spec."""
        return PanelSpec(
            title="Request Rate",
            panel_type=PanelType.TIMESERIES,
            intent="http.requests_total",
            query_template=f'sum(rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="reqps",
            description="Total requests per second"
        )
    
    def _error_rate_spec(self, service: str) -> PanelSpec:
        """Error rate panel spec."""
        return PanelSpec(
            title="Error Rate",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="http.requests_total",
                    query_template=f'sum(rate({{{{metric}}}}{{service="{service}",status=~"5.."}}[5m])) / sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) * 100',
                    legend="error %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Percentage of requests returning 5xx errors"
        )
    
    def _latency_p95_spec(self, service: str) -> PanelSpec:
        """P95 latency panel spec."""
        return PanelSpec(
            title="Request Latency (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="http.request_duration",
            query_template=f'histogram_quantile(0.95, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="95th percentile request duration"
        )
    
    def _latency_p99_spec(self, service: str) -> PanelSpec:
        """P99 latency panel spec."""
        return PanelSpec(
            title="Request Latency (p99)",
            panel_type=PanelType.TIMESERIES,
            intent="http.request_duration",
            query_template=f'histogram_quantile(0.99, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="99th percentile request duration"
        )
    
    def _availability_spec(self, service: str) -> PanelSpec:
        """Availability panel spec."""
        return PanelSpec(
            title="Availability",
            panel_type=PanelType.STAT,
            queries=[
                QuerySpec(
                    intent="http.requests_total",
                    query_template=f'sum(rate({{{{metric}}}}{{service="{service}",status!~"5.."}}[5m])) / sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) * 100',
                    legend="availability %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Percentage of successful (non-5xx) requests"
        )
    
    def _requests_in_flight_spec(self, service: str) -> PanelSpec:
        """Requests in flight panel spec."""
        return PanelSpec(
            title="Requests In Flight",
            panel_type=PanelType.TIMESERIES,
            intent="http.requests_in_flight",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Current in-flight requests",
            skip_if_unavailable=True
        )
