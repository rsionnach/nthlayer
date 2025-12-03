"""Redis dashboard template.

Comprehensive monitoring panels for Redis cache/data store.
"""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class RedisTemplate(TechnologyTemplate):
    """Redis monitoring template."""
    
    @property
    def name(self) -> str:
        return "redis"
    
    @property
    def display_name(self) -> str:
        return "Redis"
    
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get all Redis monitoring panels."""
        return [
            self._memory_usage_panel(service_name),
            self._hit_rate_panel(service_name),
            self._commands_per_sec_panel(service_name),
            self._connected_clients_panel(service_name),
            self._evictions_panel(service_name),
            self._keyspace_hits_misses_panel(service_name),
            self._expired_keys_panel(service_name),
            self._network_io_panel(service_name),
            self._slowlog_panel(service_name),
            self._fragmentation_ratio_panel(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get most critical Redis panels."""
        return [
            self._memory_usage_panel(service_name),
            self._hit_rate_panel(service_name),
            self._commands_per_sec_panel(service_name),
        ]
    
    def _memory_usage_panel(self, service: str) -> Panel:
        """Redis memory usage."""
        return Panel(
            title="Redis Memory Usage",
            panel_type="stat",
            targets=[
                Target(
                    expr=f'redis_memory_used_bytes{{service="{service}"}}',
                    legend_format="Used memory",
                    ref_id="A"
                )
            ],
            description="Redis memory consumption",
            unit="bytes",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _hit_rate_panel(self, service: str) -> Panel:
        """Cache hit rate."""
        return Panel(
            title="Cache Hit Rate",
            panel_type="gauge",
            targets=[
                Target(
                    expr=(
                        f'sum(rate(cache_hits_total{{service="{service}"}}[5m])) / '
                        f'(sum(rate(cache_hits_total{{service="{service}"}}[5m])) + '
                        f'sum(rate(cache_misses_total{{service="{service}"}}[5m]))) * 100'
                    ),
                    legend_format="Hit rate %",
                    ref_id="A"
                ),
            ],
            description="Cache hit rate - should be >90% for good performance",
            unit="percent",
            decimals=2,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": 80, "color": "yellow"},
                {"value": 90, "color": "green"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _commands_per_sec_panel(self, service: str) -> Panel:
        """Redis connections."""
        return Panel(
            title="Redis Connections",
            panel_type="stat",
            targets=[
                Target(
                    expr=f'redis_connected_clients{{service="{service}"}}',
                    legend_format="Connections",
                    ref_id="A"
                ),
            ],
            description="Number of client connections",
            unit="short",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _connected_clients_panel(self, service: str) -> Panel:
        """Number of connected clients."""
        return Panel(
            title="Connected Clients",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'redis_connected_clients{{service="{service}"}}',
                    legend_format="Clients",
                    ref_id="A"
                ),
                Target(
                    expr=f'redis_config_maxclients{{service="{service}"}}',
                    legend_format="Max clients",
                    ref_id="B"
                ),
            ],
            description="Connected clients vs maximum allowed",
            unit="short",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _evictions_panel(self, service: str) -> Panel:
        """Key evictions (memory pressure indicator)."""
        return Panel(
            title="Evicted Keys",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(redis_evicted_keys_total{{service="{service}"}}[5m])',
                    legend_format="Evictions/sec",
                    ref_id="A"
                ),
            ],
            description="Keys evicted due to memory pressure - should be zero",
            unit="short",
            decimals=2,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 0.1, "color": "yellow"},
                {"value": 1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _keyspace_hits_misses_panel(self, service: str) -> Panel:
        """Cache hits vs misses."""
        return Panel(
            title="Cache Hits vs Misses",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(redis_keyspace_hits_total{{service="{service}"}}[5m])',
                    legend_format="Hits/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'rate(redis_keyspace_misses_total{{service="{service}"}}[5m])',
                    legend_format="Misses/sec",
                    ref_id="B"
                ),
            ],
            description="Cache hits and misses per second",
            unit="ops",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _expired_keys_panel(self, service: str) -> Panel:
        """Expired keys (TTL monitoring)."""
        return Panel(
            title="Expired Keys",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(redis_expired_keys_total{{service="{service}"}}[5m])',
                    legend_format="Expirations/sec",
                    ref_id="A"
                ),
            ],
            description="Keys expired per second due to TTL",
            unit="ops",
            decimals=1,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _network_io_panel(self, service: str) -> Panel:
        """Network I/O throughput."""
        return Panel(
            title="Network I/O",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(redis_net_input_bytes_total{{service="{service}"}}[5m])',
                    legend_format="Input bytes/sec",
                    ref_id="A"
                ),
                Target(
                    expr=f'rate(redis_net_output_bytes_total{{service="{service}"}}[5m])',
                    legend_format="Output bytes/sec",
                    ref_id="B"
                ),
            ],
            description="Network input and output throughput",
            unit="Bps",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _slowlog_panel(self, service: str) -> Panel:
        """Slow commands from slowlog."""
        return Panel(
            title="Slow Commands",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'redis_slowlog_length{{service="{service}"}}',
                    legend_format="Slow commands",
                    ref_id="A"
                ),
            ],
            description="Number of commands in slowlog",
            unit="short",
            decimals=0,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 10, "color": "yellow"},
                {"value": 50, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _fragmentation_ratio_panel(self, service: str) -> Panel:
        """Memory fragmentation ratio."""
        return Panel(
            title="Memory Fragmentation",
            panel_type="gauge",
            targets=[
                Target(
                    expr=f'redis_mem_fragmentation_ratio{{service="{service}"}}',
                    legend_format="Fragmentation ratio",
                    ref_id="A"
                ),
            ],
            description="Memory fragmentation ratio - ideal is 1.0-1.5",
            unit="short",
            decimals=2,
            min=0,
            max=3,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": 1.0, "color": "green"},
                {"value": 1.5, "color": "yellow"},
                {"value": 2.0, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
