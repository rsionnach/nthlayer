"""Intent-Based NATS Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class NatsIntentTemplate(IntentBasedTemplate):
    """NATS monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "nats"

    @property
    def display_name(self) -> str:
        return "NATS"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get NATS panel specifications with intents."""
        return [
            self._connections_spec(service_name),
            self._messages_spec(service_name),
            self._bytes_spec(service_name),
            self._subscriptions_spec(service_name),
            self._slow_consumers_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical NATS panels."""
        specs = [
            self._connections_spec(service_name),
            self._messages_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _connections_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Connections",
            panel_type=PanelType.TIMESERIES,
            intent="nats.connections",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of client connections",
        )

    def _messages_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Messages/sec",
            panel_type=PanelType.TIMESERIES,
            intent="nats.messages",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Messages per second",
        )

    def _bytes_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Bytes/sec",
            panel_type=PanelType.TIMESERIES,
            intent="nats.bytes",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="Bps",
            description="Bytes transferred per second",
        )

    def _subscriptions_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Subscriptions",
            panel_type=PanelType.TIMESERIES,
            intent="nats.subscriptions",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of subscriptions",
        )

    def _slow_consumers_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Slow Consumers",
            panel_type=PanelType.TIMESERIES,
            intent="nats.slow_consumers",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of slow consumers",
        )
