"""
Intent-Based Redis Dashboard Template.

This template uses the intent system for metric resolution, enabling:
- Works with any Redis exporter (redis_exporter, app metrics, etc.)
- Automatic fallback handling
- Guidance panels for missing instrumentation
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class RedisIntentTemplate(IntentBasedTemplate):
    """Redis monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "redis"
    
    @property
    def display_name(self) -> str:
        return "Redis"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Redis panel specifications with intents."""
        return [
            self._memory_usage_spec(service_name),
            self._hit_rate_spec(service_name),
            self._connected_clients_spec(service_name),
            self._hits_misses_spec(service_name),
            self._evictions_spec(service_name),
            self._expired_keys_spec(service_name),
            self._commands_spec(service_name),
            self._keys_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Redis panels."""
        specs = [
            self._memory_usage_spec(service_name),
            self._hit_rate_spec(service_name),
            self._connected_clients_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _memory_usage_spec(self, service: str) -> PanelSpec:
        """Redis memory usage panel spec."""
        return PanelSpec(
            title="Redis Memory Usage",
            panel_type=PanelType.TIMESERIES,
            intent="redis.memory",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="Redis memory consumption"
        )
    
    def _hit_rate_spec(self, service: str) -> PanelSpec:
        """Cache hit rate panel spec."""
        return PanelSpec(
            title="Cache Hit Rate",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="redis.hits",
                    query_template=f'''sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) / 
(sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) + 
sum(rate(cache_misses_total{{service="{service}"}}[5m]))) * 100''',
                    legend="Hit rate %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Cache hit rate - should be >90% for good performance"
        )
    
    def _connected_clients_spec(self, service: str) -> PanelSpec:
        """Connected clients panel spec."""
        return PanelSpec(
            title="Connected Clients",
            panel_type=PanelType.TIMESERIES,
            intent="redis.connections",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Number of connected clients"
        )
    
    def _hits_misses_spec(self, service: str) -> PanelSpec:
        """Cache hits vs misses panel spec."""
        return PanelSpec(
            title="Cache Hits vs Misses",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="redis.hits",
                    query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
                    legend="Hits/sec",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="redis.misses",
                    query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
                    legend="Misses/sec",
                    ref_id="B"
                ),
            ],
            unit="short",
            description="Cache hits and misses per second"
        )
    
    def _evictions_spec(self, service: str) -> PanelSpec:
        """Evicted keys panel spec."""
        return PanelSpec(
            title="Evicted Keys",
            panel_type=PanelType.TIMESERIES,
            intent="redis.evicted_keys",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Keys evicted due to memory pressure - should be zero"
        )
    
    def _expired_keys_spec(self, service: str) -> PanelSpec:
        """Expired keys panel spec."""
        return PanelSpec(
            title="Expired Keys",
            panel_type=PanelType.TIMESERIES,
            intent="redis.expired_keys",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Keys expired per second due to TTL"
        )
    
    def _commands_spec(self, service: str) -> PanelSpec:
        """Commands per second panel spec."""
        return PanelSpec(
            title="Commands/sec",
            panel_type=PanelType.TIMESERIES,
            intent="redis.commands",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Redis commands processed per second"
        )
    
    def _keys_spec(self, service: str) -> PanelSpec:
        """Total keys panel spec."""
        return PanelSpec(
            title="Total Keys",
            panel_type=PanelType.STAT,
            intent="redis.keys",
            query_template=f'sum({{{{metric}}}}{{service="{service}"}})',
            unit="short",
            description="Total number of keys in database"
        )
