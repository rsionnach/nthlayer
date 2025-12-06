"""Intent-Based HAProxy Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class HaproxyIntentTemplate(IntentBasedTemplate):
    """HAProxy monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "haproxy"

    @property
    def display_name(self) -> str:
        return "HAProxy"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get HAProxy panel specifications with intents."""
        return [
            self._requests_spec(service_name),
            self._connections_spec(service_name),
            self._response_time_spec(service_name),
            self._backend_status_spec(service_name),
            self._error_rate_spec(service_name),
            self._queue_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical HAProxy panels."""
        specs = [
            self._requests_spec(service_name),
            self._backend_status_spec(service_name),
            self._error_rate_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _requests_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Requests/sec",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.http_requests_total",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="reqps",
            description="HTTP requests per second",
        )

    def _connections_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Current Connections",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.current_sessions",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Current active sessions",
        )

    def _response_time_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Response Time (avg)",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.response_time_average_seconds",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="s",
            description="Average response time",
        )

    def _backend_status_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Backend Servers Up",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.backend_up",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of healthy backend servers",
        )

    def _error_rate_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Error Rate",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.http_responses_total",
            query_template=(
                f'sum(rate({{{{metric}}}}{{service="{service}",code=~"5.."}}[5m])) / '
                f'sum(rate({{{{metric}}}}{{service="{service}"}}[5m]))'
            ),
            unit="percentunit",
            description="Percentage of 5xx responses",
        )

    def _queue_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Queue Size",
            panel_type=PanelType.TIMESERIES,
            intent="haproxy.backend_queue_current",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Requests waiting in queue",
        )
