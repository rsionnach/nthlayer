"""HTTP/API dashboard template.

Comprehensive monitoring panels for HTTP APIs and web services.
"""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class HTTPAPITemplate(TechnologyTemplate):
    """HTTP/API monitoring template."""
    
    @property
    def name(self) -> str:
        return "http_api"
    
    @property
    def display_name(self) -> str:
        return "HTTP/API"
    
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get all HTTP/API monitoring panels."""
        return [
            self._request_rate_panel(service_name),
            self._error_rate_panel(service_name),
            self._latency_percentiles_panel(service_name),
            self._status_code_distribution_panel(service_name),
            self._endpoint_latency_panel(service_name),
            self._request_duration_heatmap_panel(service_name),
            self._throughput_panel(service_name),
            self._active_requests_panel(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get most critical HTTP/API panels."""
        return [
            self._request_rate_panel(service_name),
            self._error_rate_panel(service_name),
            self._latency_percentiles_panel(service_name),
        ]
    
    def _request_rate_panel(self, service: str) -> Panel:
        """Requests per second."""
        return Panel(
            title="Request Rate",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(http_requests_total{{service="{service}"}}[5m]))',
                    legend_format="Total requests/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'sum(rate(http_requests_total{{service="{service}",status=~"2.."}}[5m]))',
                    legend_format="2xx/sec",
                    ref_id="B"
                ),
                Target(
                    expr=f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]))',
                    legend_format="5xx/sec",
                    ref_id="C"
                ),
            ],
            description="HTTP requests per second by status code",
            unit="reqps",
            decimals=1,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _error_rate_panel(self, service: str) -> Panel:
        """Error rate percentage."""
        return Panel(
            title="Error Rate",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=(
                        f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])) / '
                        f'sum(rate(http_requests_total{{service="{service}"}}[5m])) * 100'
                    ),
                    legend_format="Error rate %",
                    ref_id="A"
                ),
            ],
            description="Percentage of requests returning 5xx errors",
            unit="percent",
            decimals=3,
            min=0,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 0.1, "color": "yellow"},
                {"value": 1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _latency_percentiles_panel(self, service: str) -> Panel:
        """Response time percentiles."""
        return Panel(
            title="Response Time Percentiles",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) * 1000',
                    legend_format="p50",
                    ref_id="A"
                ),
                Target(
                    expr=f'histogram_quantile(0.90, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) * 1000',
                    legend_format="p90",
                    ref_id="B"
                ),
                Target(
                    expr=f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) * 1000',
                    legend_format="p95",
                    ref_id="C"
                ),
                Target(
                    expr=f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) * 1000',
                    legend_format="p99",
                    ref_id="D"
                ),
            ],
            description="Response time at various percentiles",
            unit="ms",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _status_code_distribution_panel(self, service: str) -> Panel:
        """HTTP status code distribution."""
        return Panel(
            title="Status Code Distribution",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(http_requests_total{{service="{service}"}}[5m])) by (status)',
                    legend_format="{{status}}",
                    ref_id="A"
                ),
            ],
            description="Request rate by HTTP status code",
            unit="reqps",
            decimals=1,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _endpoint_latency_panel(self, service: str) -> Panel:
        """Latency by endpoint."""
        return Panel(
            title="Latency by Endpoint (p95)",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) by (le, endpoint)) * 1000',
                    legend_format="{{endpoint}}",
                    ref_id="A"
                ),
            ],
            description="p95 latency per endpoint - identify slow endpoints",
            unit="ms",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _request_duration_heatmap_panel(self, service: str) -> Panel:
        """Request duration heatmap."""
        return Panel(
            title="Request Duration Heatmap",
            panel_type="heatmap",
            targets=[
                Target(
                    expr=f'sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) by (le)',
                    legend_format="{{le}}",
                    ref_id="A"
                ),
            ],
            description="Distribution of request durations over time",
            unit="s",
            decimals=3,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _throughput_panel(self, service: str) -> Panel:
        """Request and response throughput."""
        return Panel(
            title="Throughput",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(http_request_size_bytes_sum{{service="{service}"}}[5m]))',
                    legend_format="Request bytes/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'sum(rate(http_response_size_bytes_sum{{service="{service}"}}[5m]))',
                    legend_format="Response bytes/sec",
                    ref_id="B"
                ),
            ],
            description="HTTP request and response throughput",
            unit="Bps",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _active_requests_panel(self, service: str) -> Panel:
        """Currently in-flight requests."""
        return Panel(
            title="Active Requests",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'http_requests_in_flight{{service="{service}"}}',
                    legend_format="In-flight requests",
                    ref_id="A"
                ),
            ],
            description="Number of requests currently being processed",
            unit="short",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
