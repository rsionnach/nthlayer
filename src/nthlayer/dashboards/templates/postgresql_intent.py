"""
Intent-Based PostgreSQL Dashboard Template.

This template uses the intent system for metric resolution, enabling:
- Automatic metric discovery
- Fallback handling when primary metrics unavailable
- Guidance panels for missing instrumentation
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class PostgreSQLIntentTemplate(IntentBasedTemplate):
    """PostgreSQL monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "postgresql"
    
    @property
    def display_name(self) -> str:
        return "PostgreSQL"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get PostgreSQL panel specifications with intents."""
        return [
            self._connections_spec(service_name),
            self._active_queries_spec(service_name),
            self._cache_hit_ratio_spec(service_name),
            self._transactions_spec(service_name),
            self._database_size_spec(service_name),
            self._query_duration_spec(service_name),
            self._deadlocks_spec(service_name),
            self._replication_lag_spec(service_name),
            self._table_bloat_spec(service_name),
            self._connection_pool_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical PostgreSQL panels."""
        specs = [
            self._connections_spec(service_name),
            self._cache_hit_ratio_spec(service_name),
            self._query_duration_spec(service_name),
        ]
        # Build panels from specs
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _connections_spec(self, service: str) -> PanelSpec:
        """PostgreSQL connections panel spec."""
        return PanelSpec(
            title="PostgreSQL Connections",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="postgresql.connections",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="{{datname}} connections",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="postgresql.max_connections",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="Max connections",
                    ref_id="B"
                ),
            ],
            unit="short",
            description="Active database connections vs max connections limit"
        )
    
    def _active_queries_spec(self, service: str) -> PanelSpec:
        """Active queries panel spec."""
        return PanelSpec(
            title="Active Queries",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.active_queries",
            query_template=f'{{{{metric}}}}{{service="{service}",state="active"}}',
            unit="short",
            description="Number of currently executing queries"
        )
    
    def _cache_hit_ratio_spec(self, service: str) -> PanelSpec:
        """Cache hit ratio panel spec."""
        return PanelSpec(
            title="Cache Hit Ratio",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="postgresql.cache_hit",
                    query_template=f'''sum({{{{metric}}}}{{service="{service}"}}) / 
(sum({{{{metric}}}}{{service="{service}"}}) + sum(pg_stat_database_blks_read{{service="{service}"}})) * 100''',
                    legend="Cache hit %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Buffer cache hit ratio - should be >99% for good performance"
        )
    
    def _transactions_spec(self, service: str) -> PanelSpec:
        """Transaction rate panel spec."""
        return PanelSpec(
            title="Transaction Rate",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="postgresql.transactions_committed",
                    query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
                    legend="{{datname}} commits/sec",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="postgresql.transactions_rolled_back",
                    query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
                    legend="{{datname}} rollbacks/sec",
                    ref_id="B"
                ),
            ],
            unit="short",
            description="Transaction commits and rollbacks per second"
        )
    
    def _database_size_spec(self, service: str) -> PanelSpec:
        """Database size panel spec."""
        return PanelSpec(
            title="Database Size",
            panel_type=PanelType.STAT,
            intent="postgresql.database_size",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="Total database size"
        )
    
    def _query_duration_spec(self, service: str) -> PanelSpec:
        """Query duration panel spec."""
        return PanelSpec(
            title="Query Duration (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.query_duration",
            query_template=f'histogram_quantile(0.95, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="Query execution time (95th percentile)",
            # Skip if histogram metrics not available
            skip_if_unavailable=True
        )
    
    def _deadlocks_spec(self, service: str) -> PanelSpec:
        """Deadlocks panel spec."""
        return PanelSpec(
            title="Deadlocks",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.deadlocks",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Deadlocks per second - should be near zero"
        )
    
    def _replication_lag_spec(self, service: str) -> PanelSpec:
        """Replication lag panel spec."""
        return PanelSpec(
            title="Replication Lag",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.replication_lag",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="s",
            description="Replication lag in seconds",
            # Skip if no replicas
            skip_if_unavailable=True
        )
    
    def _table_bloat_spec(self, service: str) -> PanelSpec:
        """Table bloat panel spec."""
        return PanelSpec(
            title="Table Bloat (Dead Tuples)",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.table_bloat",
            query_template=f'sum({{{{metric}}}}{{service="{service}"}}) by (relname)',
            unit="short",
            description="Dead tuples indicating table bloat - vacuum if high"
        )
    
    def _connection_pool_spec(self, service: str) -> PanelSpec:
        """Connection pool utilization panel spec."""
        return PanelSpec(
            title="Connection Pool Utilization",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="postgresql.connections",
                    query_template=f'''{{{{metric}}}}{{service="{service}"}} / 
on() group_left pg_settings_max_connections{{service="{service}"}} * 100''',
                    legend="Pool usage %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Connection pool utilization percentage"
        )
