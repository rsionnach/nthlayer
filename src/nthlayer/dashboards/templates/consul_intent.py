"""Intent-Based Consul Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class ConsulIntentTemplate(IntentBasedTemplate):
    """Consul monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "consul"

    @property
    def display_name(self) -> str:
        return "Consul"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Consul panel specifications with intents."""
        return [
            self._leader_spec(service_name),
            self._peers_spec(service_name),
            self._services_spec(service_name),
            self._health_checks_spec(service_name),
            self._rpc_rate_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Consul panels."""
        specs = [
            self._leader_spec(service_name),
            self._services_spec(service_name),
            self._health_checks_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _leader_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Raft Leader",
            panel_type=PanelType.STAT,
            intent="consul.raft_state_leader",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Whether this node is the Raft leader",
        )

    def _peers_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Raft Peers",
            panel_type=PanelType.TIMESERIES,
            intent="consul.raft_peers",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of Raft peers",
        )

    def _services_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Registered Services",
            panel_type=PanelType.TIMESERIES,
            intent="consul.catalog_services",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of registered services",
        )

    def _health_checks_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Health Checks",
            panel_type=PanelType.TIMESERIES,
            intent="consul.health_checks_critical",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of critical health checks",
        )

    def _rpc_rate_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="RPC Rate",
            panel_type=PanelType.TIMESERIES,
            intent="consul.rpc_request",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="reqps",
            description="RPC requests per second",
        )
