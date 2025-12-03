"""
Intent-Based Kafka Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for Kafka metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class KafkaIntentTemplate(IntentBasedTemplate):
    """Kafka monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "kafka"
    
    @property
    def display_name(self) -> str:
        return "Apache Kafka"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Kafka panel specifications with intents."""
        return [
            self._consumer_lag_spec(service_name),
            self._throughput_spec(service_name),
            self._offset_progress_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Kafka panels."""
        specs = self.get_panel_specs(service_name)
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _consumer_lag_spec(self, service: str) -> PanelSpec:
        """Kafka consumer lag panel spec."""
        return PanelSpec(
            title="Kafka Consumer Lag",
            panel_type=PanelType.TIMESERIES,
            intent="kafka.consumer_lag",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="s",
            description="Consumer lag in seconds behind latest messages"
        )
    
    def _throughput_spec(self, service: str) -> PanelSpec:
        """Kafka throughput panel spec."""
        return PanelSpec(
            title="Kafka Throughput",
            panel_type=PanelType.TIMESERIES,
            intent="kafka.messages_per_second",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Records consumed/produced per second"
        )
    
    def _offset_progress_spec(self, service: str) -> PanelSpec:
        """Kafka offset progress panel spec."""
        return PanelSpec(
            title="Kafka Offset Progress",
            panel_type=PanelType.TIMESERIES,
            intent="kafka.consumer_offset",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Message offset progression per partition"
        )
