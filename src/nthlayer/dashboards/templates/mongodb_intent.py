"""
Intent-Based MongoDB Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for MongoDB metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class MongoDBIntentTemplate(IntentBasedTemplate):
    """MongoDB monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "mongodb"
    
    @property
    def display_name(self) -> str:
        return "MongoDB"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get MongoDB panel specifications with intents."""
        return [
            self._connections_spec(service_name),
            self._operations_spec(service_name),
            self._query_duration_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical MongoDB panels."""
        specs = self.get_panel_specs(service_name)
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _connections_spec(self, service: str) -> PanelSpec:
        """MongoDB connections panel spec."""
        return PanelSpec(
            title="MongoDB Connections",
            panel_type=PanelType.TIMESERIES,
            intent="mongodb.connections",
            query_template=f'{{{{metric}}}}{{service="{service}",state="current"}}',
            unit="short",
            description="Active MongoDB connections"
        )
    
    def _operations_spec(self, service: str) -> PanelSpec:
        """MongoDB operations panel spec."""
        return PanelSpec(
            title="MongoDB Operations/sec",
            panel_type=PanelType.TIMESERIES,
            intent="mongodb.operations",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="ops",
            description="Database operations per second by type"
        )
    
    def _query_duration_spec(self, service: str) -> PanelSpec:
        """MongoDB query duration panel spec."""
        return PanelSpec(
            title="MongoDB Query Duration (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="mongodb.query_duration",
            query_template=f'histogram_quantile(0.95, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m]))) * 1000',
            unit="ms",
            description="Query execution time (95th percentile)",
            skip_if_unavailable=True
        )
