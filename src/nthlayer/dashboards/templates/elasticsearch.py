"""Elasticsearch monitoring template."""

from typing import List

from nthlayer.dashboards.models import Panel, Target


class ElasticsearchTemplate:
    """Generates Elasticsearch-specific monitoring panels."""
    
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Generate Elasticsearch monitoring panels.
        
        Args:
            service_name: Service variable name for filtering
            
        Returns:
            List of Elasticsearch monitoring panels
        """
        return [
            # Cluster Health
            Panel(
                title="Cluster Health Status",
                panel_type="stat",
                targets=[
                    Target(
                        expr=f'elasticsearch_cluster_health_status{{cluster="{service_name}"}}',
                        legend_format="Status",
                    )
                ],
                description="Elasticsearch cluster health (0=green, 1=yellow, 2=red)",
                unit="short",
                thresholds=[
                    {"value": 0, "color": "green"},
                    {"value": 1, "color": "yellow"},
                    {"value": 2, "color": "red"},
                ],
            ),
            
            # Active Shards
            Panel(
                title="Active Shards",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'elasticsearch_cluster_health_active_shards{{cluster="{service_name}"}}',
                        legend_format="Active",
                    ),
                    Target(
                        expr=f'elasticsearch_cluster_health_relocating_shards{{cluster="{service_name}"}}',
                        legend_format="Relocating",
                    ),
                ],
                description="Number of active and relocating shards",
                unit="short",
            ),
            
            # Search Rate
            Panel(
                title="Search Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(elasticsearch_indices_search_query_total{{cluster="{service_name}"}}[5m])',
                        legend_format="Queries/sec",
                    )
                ],
                description="Search queries per second",
                unit="qps",
            ),
            
            # Search Latency
            Panel(
                title="Search Latency (p95)",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'histogram_quantile(0.95, rate(elasticsearch_indices_search_query_time_seconds_bucket{{cluster="{service_name}"}}[5m]))',
                        legend_format="p95",
                    ),
                    Target(
                        expr=f'histogram_quantile(0.99, rate(elasticsearch_indices_search_query_time_seconds_bucket{{cluster="{service_name}"}}[5m]))',
                        legend_format="p99",
                    ),
                ],
                description="Search query latency percentiles",
                unit="s",
            ),
            
            # Indexing Rate
            Panel(
                title="Indexing Rate",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(elasticsearch_indices_indexing_index_total{{cluster="{service_name}"}}[5m])',
                        legend_format="Docs/sec",
                    )
                ],
                description="Documents indexed per second",
                unit="ops",
            ),
            
            # Index Size
            Panel(
                title="Index Size",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'elasticsearch_indices_store_size_bytes{{cluster="{service_name}"}}',
                        legend_format="{{index}}",
                    )
                ],
                description="Total size of all indices",
                unit="bytes",
            ),
            
            # Document Count
            Panel(
                title="Document Count",
                panel_type="stat",
                targets=[
                    Target(
                        expr=f'elasticsearch_indices_docs{{cluster="{service_name}"}}',
                        legend_format="Documents",
                    )
                ],
                description="Total number of documents across all indices",
                unit="short",
            ),
            
            # JVM Memory Usage
            Panel(
                title="JVM Heap Usage",
                panel_type="gauge",
                targets=[
                    Target(
                        expr=f'elasticsearch_jvm_memory_used_bytes{{cluster="{service_name}",area="heap"}} / elasticsearch_jvm_memory_max_bytes{{cluster="{service_name}",area="heap"}} * 100',
                        legend_format="Heap %",
                    )
                ],
                description="JVM heap memory utilization percentage",
                unit="percent",
                min=0,
                max=100,
                thresholds=[
                    {"value": 0, "color": "green"},
                    {"value": 75, "color": "yellow"},
                    {"value": 90, "color": "red"},
                ],
            ),
            
            # GC Time
            Panel(
                title="GC Time",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(elasticsearch_jvm_gc_collection_seconds_sum{{cluster="{service_name}"}}[5m])',
                        legend_format="{{gc}}",
                    )
                ],
                description="Garbage collection time per second",
                unit="s",
            ),
            
            # Cache Hit Ratio
            Panel(
                title="Query Cache Hit Ratio",
                panel_type="gauge",
                targets=[
                    Target(
                        expr=f'elasticsearch_indices_query_cache_hit_count{{cluster="{service_name}"}} / (elasticsearch_indices_query_cache_hit_count{{cluster="{service_name}"}} + elasticsearch_indices_query_cache_miss_count{{cluster="{service_name}"}}) * 100',
                        legend_format="Hit %",
                    )
                ],
                description="Query cache hit ratio",
                unit="percent",
                min=0,
                max=100,
            ),
            
            # Thread Pool Queue
            Panel(
                title="Thread Pool Queue Size",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'elasticsearch_thread_pool_queue_count{{cluster="{service_name}"}}',
                        legend_format="{{name}}",
                    )
                ],
                description="Number of queued tasks in thread pools",
                unit="short",
            ),
            
            # Rejected Tasks
            Panel(
                title="Rejected Tasks",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(elasticsearch_thread_pool_rejected_count{{cluster="{service_name}"}}[5m])',
                        legend_format="{{name}}",
                    )
                ],
                description="Rate of rejected tasks per thread pool",
                unit="ops",
            ),
        ]
