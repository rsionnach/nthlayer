"""PostgreSQL dashboard template.

Comprehensive monitoring panels for PostgreSQL databases.
"""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class PostgreSQLTemplate(TechnologyTemplate):
    """PostgreSQL monitoring template."""
    
    @property
    def name(self) -> str:
        return "postgresql"
    
    @property
    def display_name(self) -> str:
        return "PostgreSQL"
    
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get all PostgreSQL monitoring panels.
        
        Returns comprehensive PostgreSQL monitoring including:
        - Connection metrics
        - Query performance
        - Cache efficiency
        - Database size and growth
        - Transaction metrics
        - Replication lag
        """
        return [
            self._connection_panel(service_name),
            self._active_queries_panel(service_name),
            self._cache_hit_ratio_panel(service_name),
            self._transaction_rate_panel(service_name),
            self._database_size_panel(service_name),
            self._query_duration_panel(service_name),
            self._deadlocks_panel(service_name),
            self._replication_lag_panel(service_name),
            self._disk_io_panel(service_name),
            self._table_bloat_panel(service_name),
            self._index_usage_panel(service_name),
            self._connection_pool_panel(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get most critical PostgreSQL panels for overview."""
        return [
            self._connection_panel(service_name),
            self._cache_hit_ratio_panel(service_name),
            self._query_duration_panel(service_name),
        ]
    
    def _connection_panel(self, service: str) -> Panel:
        """Active database connections."""
        return Panel(
            title="PostgreSQL Connections",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_stat_database_numbackends{{service="{service}"}}',
                    legend_format="{{datname}} connections",
                    ref_id="A"
                ),
                Target(
                    expr=f'pg_settings_max_connections{{service="{service}"}}',
                    legend_format="Max connections",
                    ref_id="B"
                ),
            ],
            description="Active database connections vs max connections limit",
            unit="short",
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 80, "color": "yellow"},
                {"value": 95, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _active_queries_panel(self, service: str) -> Panel:
        """Currently executing queries."""
        return Panel(
            title="Active Queries",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_stat_activity_count{{service="{service}",state="active"}}',
                    legend_format="Active queries",
                    ref_id="A"
                ),
                Target(
                    expr=f'pg_stat_activity_count{{service="{service}",state="idle"}}',
                    legend_format="Idle connections",
                    ref_id="B"
                ),
            ],
            description="Number of currently executing queries",
            unit="short",
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _cache_hit_ratio_panel(self, service: str) -> Panel:
        """Buffer cache hit ratio (should be >99%)."""
        return Panel(
            title="Cache Hit Ratio",
            panel_type="gauge",
            targets=[
                Target(
                    expr=(
                        f'sum(pg_stat_database_blks_hit{{service="{service}"}}) / '
                        f'(sum(pg_stat_database_blks_hit{{service="{service}"}}) + '
                        f'sum(pg_stat_database_blks_read{{service="{service}"}})) * 100'
                    ),
                    legend_format="Cache hit %",
                    ref_id="A"
                ),
            ],
            description="Buffer cache hit ratio - should be >99% for good performance",
            unit="percent",
            decimals=2,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": 95, "color": "yellow"},
                {"value": 99, "color": "green"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _transaction_rate_panel(self, service: str) -> Panel:
        """Transactions per second."""
        return Panel(
            title="Transaction Rate",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(pg_stat_database_xact_commit{{service="{service}"}}[5m])',
                    legend_format="{{datname}} commits/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'rate(pg_stat_database_xact_rollback{{service="{service}"}}[5m])',
                    legend_format="{{datname}} rollbacks/sec",
                    ref_id="B"
                ),
            ],
            description="Transaction commits and rollbacks per second",
            unit="tps",
            decimals=1,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _database_size_panel(self, service: str) -> Panel:
        """Database size and growth."""
        return Panel(
            title="Database Size",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_database_size_bytes{{service="{service}"}}',
                    legend_format="{{datname}} size",
                    ref_id="A"
                ),
            ],
            description="Total database size in bytes",
            unit="bytes",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _query_duration_panel(self, service: str) -> Panel:
        """Query execution time statistics."""
        return Panel(
            title="Query Duration (p95)",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'histogram_quantile(0.95, rate(pg_stat_statements_mean_exec_time_seconds_bucket{{service="{service}"}}[5m]))',
                    legend_format="p95 query time",
                    ref_id="A"
                ),
                Target(
                    expr=f'histogram_quantile(0.99, rate(pg_stat_statements_mean_exec_time_seconds_bucket{{service="{service}"}}[5m]))',
                    legend_format="p99 query time",
                    ref_id="B"
                ),
            ],
            description="Query execution time percentiles",
            unit="s",
            decimals=3,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _deadlocks_panel(self, service: str) -> Panel:
        """Deadlock count."""
        return Panel(
            title="Deadlocks",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(pg_stat_database_deadlocks{{service="{service}"}}[5m])',
                    legend_format="{{datname}} deadlocks/sec",
                    ref_id="A"
                ),
            ],
            description="Deadlocks per second - should be near zero",
            unit="short",
            decimals=3,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 0.01, "color": "yellow"},
                {"value": 0.1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _replication_lag_panel(self, service: str) -> Panel:
        """Replication lag for read replicas."""
        return Panel(
            title="Replication Lag",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_replication_lag_seconds{{service="{service}"}}',
                    legend_format="{{replica}} lag",
                    ref_id="A"
                ),
            ],
            description="Replication lag in seconds - should be <1s",
            unit="s",
            decimals=2,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 1, "color": "yellow"},
                {"value": 5, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _disk_io_panel(self, service: str) -> Panel:
        """Disk I/O operations."""
        return Panel(
            title="Disk I/O",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(pg_stat_database_blks_read{{service="{service}"}}[5m])',
                    legend_format="{{datname}} disk reads/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'rate(pg_stat_database_blks_hit{{service="{service}"}}[5m])',
                    legend_format="{{datname}} cache hits/sec",
                    ref_id="B"
                ),
            ],
            description="Disk I/O vs cache hits - cache should dominate",
            unit="iops",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _table_bloat_panel(self, service: str) -> Panel:
        """Table bloat percentage."""
        return Panel(
            title="Table Bloat",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_table_bloat_ratio{{service="{service}"}}',
                    legend_format="{{table}} bloat %",
                    ref_id="A"
                ),
            ],
            description="Table bloat percentage - vacuum if >20%",
            unit="percent",
            decimals=1,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 20, "color": "yellow"},
                {"value": 40, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _index_usage_panel(self, service: str) -> Panel:
        """Index usage statistics."""
        return Panel(
            title="Index Hit Ratio",
            panel_type="gauge",
            targets=[
                Target(
                    expr=(
                        f'sum(pg_stat_user_indexes_idx_scan{{service="{service}"}}) / '
                        f'(sum(pg_stat_user_indexes_idx_scan{{service="{service}"}}) + '
                        f'sum(pg_stat_user_tables_seq_scan{{service="{service}"}})) * 100'
                    ),
                    legend_format="Index usage %",
                    ref_id="A"
                ),
            ],
            description="Percentage of queries using indexes vs sequential scans",
            unit="percent",
            decimals=1,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": 80, "color": "yellow"},
                {"value": 95, "color": "green"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _connection_pool_panel(self, service: str) -> Panel:
        """Connection pool utilization."""
        return Panel(
            title="Connection Pool Utilization",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'pg_stat_database_numbackends{{service="{service}"}} / pg_settings_max_connections{{service="{service}"}} * 100',
                    legend_format="Pool usage %",
                    ref_id="A"
                ),
            ],
            description="Connection pool utilization percentage",
            unit="percent",
            decimals=1,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 70, "color": "yellow"},
                {"value": 90, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
