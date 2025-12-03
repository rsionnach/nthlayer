"""
Intent-Based Elasticsearch Dashboard Template.

Uses the intent system for metric resolution, enabling automatic
discovery and fallback handling for Elasticsearch metrics.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class ElasticsearchIntentTemplate(IntentBasedTemplate):
    """Elasticsearch monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "elasticsearch"
    
    @property
    def display_name(self) -> str:
        return "Elasticsearch"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get Elasticsearch panel specifications with intents."""
        return [
            self._cluster_health_spec(service_name),
            self._shards_spec(service_name),
            self._search_rate_spec(service_name),
            self._search_latency_spec(service_name),
            self._indexing_rate_spec(service_name),
            self._index_size_spec(service_name),
            self._docs_count_spec(service_name),
            self._jvm_heap_spec(service_name),
            self._gc_time_spec(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical Elasticsearch panels."""
        specs = [
            self._cluster_health_spec(service_name),
            self._search_rate_spec(service_name),
            self._jvm_heap_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _cluster_health_spec(self, service: str) -> PanelSpec:
        """Cluster health status panel spec."""
        return PanelSpec(
            title="Cluster Health Status",
            panel_type=PanelType.STAT,
            intent="elasticsearch.cluster_health",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Elasticsearch cluster health (0=green, 1=yellow, 2=red)"
        )
    
    def _shards_spec(self, service: str) -> PanelSpec:
        """Active shards panel spec."""
        return PanelSpec(
            title="Active Shards",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="elasticsearch.active_shards",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="Active",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="elasticsearch.relocating_shards",
                    query_template=f'{{{{metric}}}}{{service="{service}"}}',
                    legend="Relocating",
                    ref_id="B"
                ),
            ],
            unit="short",
            description="Number of active and relocating shards"
        )
    
    def _search_rate_spec(self, service: str) -> PanelSpec:
        """Search rate panel spec."""
        return PanelSpec(
            title="Search Rate",
            panel_type=PanelType.TIMESERIES,
            intent="elasticsearch.search_rate",
            query_template=f'sum(rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="short",
            description="Search queries per second"
        )
    
    def _search_latency_spec(self, service: str) -> PanelSpec:
        """Search latency panel spec."""
        return PanelSpec(
            title="Search Latency (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="elasticsearch.search_latency",
            query_template=f'histogram_quantile(0.95, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="Search query latency (95th percentile)",
            skip_if_unavailable=True
        )
    
    def _indexing_rate_spec(self, service: str) -> PanelSpec:
        """Indexing rate panel spec."""
        return PanelSpec(
            title="Indexing Rate",
            panel_type=PanelType.TIMESERIES,
            intent="elasticsearch.indexing_rate",
            query_template=f'sum(rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="ops",
            description="Documents indexed per second"
        )
    
    def _index_size_spec(self, service: str) -> PanelSpec:
        """Index size panel spec."""
        return PanelSpec(
            title="Index Size",
            panel_type=PanelType.TIMESERIES,
            intent="elasticsearch.index_size",
            query_template=f'sum({{{{metric}}}}{{service="{service}"}})',
            unit="bytes",
            description="Total size of all indices"
        )
    
    def _docs_count_spec(self, service: str) -> PanelSpec:
        """Document count panel spec."""
        return PanelSpec(
            title="Document Count",
            panel_type=PanelType.STAT,
            intent="elasticsearch.docs_count",
            query_template=f'sum({{{{metric}}}}{{service="{service}"}})',
            unit="short",
            description="Total number of documents across all indices"
        )
    
    def _jvm_heap_spec(self, service: str) -> PanelSpec:
        """JVM heap usage panel spec."""
        return PanelSpec(
            title="JVM Heap Usage",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="elasticsearch.jvm_heap_used",
                    query_template=f'''{{{{metric}}}}{{service="{service}",area="heap"}} / 
on() elasticsearch_jvm_memory_max_bytes{{service="{service}",area="heap"}} * 100''',
                    legend="Heap %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="JVM heap memory utilization percentage"
        )
    
    def _gc_time_spec(self, service: str) -> PanelSpec:
        """Garbage collection time panel spec."""
        return PanelSpec(
            title="GC Time",
            panel_type=PanelType.TIMESERIES,
            intent="elasticsearch.gc_time",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="s",
            description="Garbage collection time per second"
        )
