"""
Intent-Based MySQL Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for MySQL metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class MySQLIntentTemplate(IntentBasedTemplate):
    """MySQL monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "mysql"
    
    @property
    def display_name(self) -> str:
        return "MySQL"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get MySQL panel specifications with intents."""
        return [
            self._connections_spec(service_name),
            self._queries_spec(service_name),
            self._connection_utilization_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical MySQL panels."""
        specs = self.get_panel_specs(service_name)
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _connections_spec(self, service: str) -> PanelSpec:
        """MySQL connections panel spec."""
        return PanelSpec(
            title="MySQL Connections",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="mysql.connections",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="Current connections",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="mysql.max_connections",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="Max connections",
                    ref_id="B"
                ),
            ],
            unit="short",
            description="Active database connections vs max connections limit"
        )
    
    def _queries_spec(self, service: str) -> PanelSpec:
        """MySQL queries panel spec."""
        return PanelSpec(
            title="MySQL Queries/sec",
            panel_type=PanelType.TIMESERIES,
            intent="mysql.queries",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Total queries executed per second"
        )
    
    def _connection_utilization_spec(self, service: str) -> PanelSpec:
        """MySQL connection pool utilization panel spec."""
        return PanelSpec(
            title="Connection Pool Utilization",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="mysql.connections",
                    query_template=f'''{{{{metric}}}}{{service="{service}"}} / 
on() mysql_global_variables_max_connections{{service="{service}"}} * 100''',
                    legend="Pool usage %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Connection pool utilization percentage"
        )
