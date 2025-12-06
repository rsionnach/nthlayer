"""Intent-Based Apache Pulsar Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class PulsarIntentTemplate(IntentBasedTemplate):
    """Pulsar monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "pulsar"

    @property
    def display_name(self) -> str:
        return "Apache Pulsar"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Pulsar panel specifications with intents."""
        return [
            self._throughput_in_spec(service_name),
            self._throughput_out_spec(service_name),
            self._backlog_spec(service_name),
            self._subscriptions_spec(service_name),
            self._storage_size_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Pulsar panels."""
        specs = [
            self._throughput_in_spec(service_name),
            self._backlog_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _throughput_in_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Messages In/sec",
            panel_type=PanelType.TIMESERIES,
            intent="pulsar.rate_in",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Messages received per second",
        )

    def _throughput_out_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Messages Out/sec",
            panel_type=PanelType.TIMESERIES,
            intent="pulsar.rate_out",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Messages delivered per second",
        )

    def _backlog_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Message Backlog",
            panel_type=PanelType.TIMESERIES,
            intent="pulsar.msg_backlog",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of messages in backlog",
        )

    def _subscriptions_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Subscriptions",
            panel_type=PanelType.TIMESERIES,
            intent="pulsar.subscriptions_count",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of subscriptions",
        )

    def _storage_size_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Storage Size",
            panel_type=PanelType.TIMESERIES,
            intent="pulsar.storage_size",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="Storage size used",
        )
