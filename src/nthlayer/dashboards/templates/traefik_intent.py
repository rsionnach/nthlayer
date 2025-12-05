"""Intent-Based Traefik Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class TraefikIntentTemplate(IntentBasedTemplate):
    """Traefik monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "traefik"

    @property
    def display_name(self) -> str:
        return "Traefik"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Traefik panel specifications with intents."""
        return [
            self._requests_spec(service_name),
            self._request_duration_spec(service_name),
            self._status_codes_spec(service_name),
            self._open_connections_spec(service_name),
            self._entrypoint_requests_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Traefik panels."""
        specs = [
            self._requests_spec(service_name),
            self._request_duration_spec(service_name),
            self._status_codes_spec(service_name),
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
            intent="traefik.service_requests_total",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="reqps",
            description="HTTP requests per second",
        )

    def _request_duration_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Request Duration (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="traefik.service_request_duration_seconds",
            query_template=(
                f"histogram_quantile(0.95, sum by (le) "
                f'(rate({{{{metric}}}}_bucket{{service="{service}"}}[5m])))'
            ),
            unit="s",
            description="95th percentile request duration",
        )

    def _status_codes_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Response Status Codes",
            panel_type=PanelType.TIMESERIES,
            intent="traefik.service_requests_total",
            query_template=f'sum by (code) (rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="reqps",
            description="Requests by HTTP status code",
        )

    def _open_connections_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Open Connections",
            panel_type=PanelType.TIMESERIES,
            intent="traefik.service_open_connections",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of open connections",
        )

    def _entrypoint_requests_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Entrypoint Requests",
            panel_type=PanelType.TIMESERIES,
            intent="traefik.entrypoint_requests_total",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="reqps",
            description="Requests per entrypoint",
        )
