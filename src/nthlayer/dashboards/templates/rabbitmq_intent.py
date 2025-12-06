"""
Intent-Based RabbitMQ Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for RabbitMQ metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class RabbitmqIntentTemplate(IntentBasedTemplate):
    """RabbitMQ monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "rabbitmq"

    @property
    def display_name(self) -> str:
        return "RabbitMQ"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get RabbitMQ panel specifications with intents."""
        return [
            self._queue_messages_spec(service_name),
            self._queue_consumers_spec(service_name),
            self._message_rate_spec(service_name),
            self._connections_spec(service_name),
            self._memory_usage_spec(service_name),
            self._disk_usage_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical RabbitMQ panels."""
        specs = [
            self._queue_messages_spec(service_name),
            self._message_rate_spec(service_name),
            self._connections_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _queue_messages_spec(self, service: str) -> PanelSpec:
        """RabbitMQ queue messages panel spec."""
        return PanelSpec(
            title="Queue Messages",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.queue_messages",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of messages in queues",
        )

    def _queue_consumers_spec(self, service: str) -> PanelSpec:
        """RabbitMQ queue consumers panel spec."""
        return PanelSpec(
            title="Queue Consumers",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.queue_consumers",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of consumers connected to queues",
        )

    def _message_rate_spec(self, service: str) -> PanelSpec:
        """RabbitMQ message rate panel spec."""
        return PanelSpec(
            title="Message Rate",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.message_publish_rate",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Messages published/delivered per second",
        )

    def _connections_spec(self, service: str) -> PanelSpec:
        """RabbitMQ connections panel spec."""
        return PanelSpec(
            title="Connections",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.connections",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of client connections",
        )

    def _memory_usage_spec(self, service: str) -> PanelSpec:
        """RabbitMQ memory usage panel spec."""
        return PanelSpec(
            title="Memory Usage",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.memory_used",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="RabbitMQ memory usage",
        )

    def _disk_usage_spec(self, service: str) -> PanelSpec:
        """RabbitMQ disk usage panel spec."""
        return PanelSpec(
            title="Disk Free",
            panel_type=PanelType.TIMESERIES,
            intent="rabbitmq.disk_free",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="Free disk space available to RabbitMQ",
        )
