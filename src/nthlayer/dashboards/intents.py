"""
Metric Intent Registry for NthLayer Dashboard Generation.

This module defines the mapping between abstract panel "intents" (what we want to measure)
and concrete Prometheus metric names (what actually exists in the environment).

The intent system enables:
1. Exporter-agnostic dashboards - works with any version of exporters
2. Fallback chains - if primary metric doesn't exist, try alternatives
3. Metric synthesis - derive metrics from components when direct metric unavailable
4. Custom overrides - users can specify their own metric names

Intent Format:
    "{technology}.{measurement}" 
    e.g., "postgresql.connections", "redis.memory", "http.requests"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class MetricType(Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


@dataclass
class MetricIntent:
    """Definition of a metric intent with resolution candidates."""
    
    intent: str  # e.g., "postgresql.connections"
    description: str
    metric_type: MetricType
    candidates: List[str]  # Ordered list of metric names to try
    fallback: Optional[str] = None  # Fallback metric if none found
    synthesis: Optional[Dict[str, str]] = None  # Components for derived metric
    unit: str = "short"
    
    def __post_init__(self):
        if self.synthesis is None:
            self.synthesis = {}


# =============================================================================
# HTTP / Application Metrics
# =============================================================================

HTTP_INTENTS = {
    "http.requests_total": MetricIntent(
        intent="http.requests_total",
        description="Total HTTP requests",
        metric_type=MetricType.COUNTER,
        candidates=[
            "http_requests_total",
            "http_server_requests_total",
            "http_request_total",
            "requests_total",
            # OTel semantic convention
            "http_server_request_count",
        ],
        unit="reqps"
    ),
    
    "http.request_duration": MetricIntent(
        intent="http.request_duration",
        description="HTTP request duration histogram",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "http_request_duration_seconds_bucket",
            "http_server_request_duration_seconds_bucket",
            "http_request_latency_seconds_bucket",
            "request_duration_seconds_bucket",
            # OTel
            "http_server_duration_bucket",
        ],
        unit="s"
    ),
    
    "http.requests_in_flight": MetricIntent(
        intent="http.requests_in_flight",
        description="Current in-flight requests",
        metric_type=MetricType.GAUGE,
        candidates=[
            "http_requests_in_flight",
            "http_server_requests_in_flight",
            "requests_in_progress",
        ],
        unit="short"
    ),
}

# =============================================================================
# PostgreSQL Metrics
# =============================================================================

POSTGRESQL_INTENTS = {
    "postgresql.connections": MetricIntent(
        intent="postgresql.connections",
        description="Active database connections",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_stat_database_numbackends",
            "postgres_connections",
            "postgresql_connections_active",
            "pgbouncer_pools_active",
        ],
        unit="short"
    ),
    
    "postgresql.max_connections": MetricIntent(
        intent="postgresql.max_connections",
        description="Maximum allowed connections",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_settings_max_connections",
            "postgres_max_connections",
        ],
        unit="short"
    ),
    
    "postgresql.active_queries": MetricIntent(
        intent="postgresql.active_queries",
        description="Currently executing queries",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_stat_activity_count",
            "postgres_stat_activity_count",
            "postgresql_active_queries",
        ],
        unit="short"
    ),
    
    "postgresql.cache_hit": MetricIntent(
        intent="postgresql.cache_hit",
        description="Buffer cache hits",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_database_blks_hit",
            "postgres_blks_hit",
        ],
        unit="short"
    ),
    
    "postgresql.cache_read": MetricIntent(
        intent="postgresql.cache_read",
        description="Disk blocks read",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_database_blks_read",
            "postgres_blks_read",
        ],
        unit="short"
    ),
    
    "postgresql.transactions_committed": MetricIntent(
        intent="postgresql.transactions_committed",
        description="Committed transactions",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_database_xact_commit",
            "postgres_xact_commit",
        ],
        unit="short"
    ),
    
    "postgresql.transactions_rolled_back": MetricIntent(
        intent="postgresql.transactions_rolled_back",
        description="Rolled back transactions",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_database_xact_rollback",
            "postgres_xact_rollback",
        ],
        unit="short"
    ),
    
    "postgresql.database_size": MetricIntent(
        intent="postgresql.database_size",
        description="Database size in bytes",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_database_size_bytes",
            "postgres_database_size_bytes",
            "postgresql_database_size",
        ],
        unit="bytes"
    ),
    
    "postgresql.query_duration": MetricIntent(
        intent="postgresql.query_duration",
        description="Query execution time histogram",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "pg_stat_statements_mean_exec_time_seconds_bucket",
            "postgres_query_duration_seconds_bucket",
            "postgresql_query_duration_bucket",
        ],
        unit="s"
    ),
    
    "postgresql.deadlocks": MetricIntent(
        intent="postgresql.deadlocks",
        description="Deadlock count",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_database_deadlocks",
            "postgres_deadlocks_total",
        ],
        unit="short"
    ),
    
    "postgresql.replication_lag": MetricIntent(
        intent="postgresql.replication_lag",
        description="Replication lag in seconds",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_replication_lag_seconds",
            "postgres_replication_lag",
            "postgresql_replication_lag_seconds",
        ],
        unit="s"
    ),
    
    "postgresql.table_bloat": MetricIntent(
        intent="postgresql.table_bloat",
        description="Dead tuples indicating table bloat",
        metric_type=MetricType.GAUGE,
        candidates=[
            "pg_stat_user_tables_n_dead_tup",
            "postgres_dead_tuples",
            "pg_table_bloat_ratio",  # Less common
        ],
        unit="short"
    ),
    
    "postgresql.index_scans": MetricIntent(
        intent="postgresql.index_scans",
        description="Index scan count",
        metric_type=MetricType.COUNTER,
        candidates=[
            "pg_stat_user_indexes_idx_scan",
            "postgres_index_scans_total",
        ],
        # Fallback to cache hit ratio if index metrics unavailable
        fallback="postgresql.cache_hit_ratio",
        unit="short"
    ),
}

# =============================================================================
# Redis Metrics
# =============================================================================

REDIS_INTENTS = {
    "redis.memory": MetricIntent(
        intent="redis.memory",
        description="Memory used by Redis",
        metric_type=MetricType.GAUGE,
        candidates=[
            "redis_memory_used_bytes",
            "redis_used_memory",
            "redis_memory_bytes",
        ],
        unit="bytes"
    ),
    
    "redis.connections": MetricIntent(
        intent="redis.connections",
        description="Connected clients",
        metric_type=MetricType.GAUGE,
        candidates=[
            "redis_connected_clients",
            "redis_clients_connected",
            "redis_connections",
        ],
        unit="short"
    ),
    
    "redis.keys": MetricIntent(
        intent="redis.keys",
        description="Total keys in database",
        metric_type=MetricType.GAUGE,
        candidates=[
            "redis_db_keys",
            "redis_keys_total",
            "redis_keyspace_keys",
        ],
        unit="short"
    ),
    
    "redis.hits": MetricIntent(
        intent="redis.hits",
        description="Cache hits",
        metric_type=MetricType.COUNTER,
        candidates=[
            "cache_hits_total",
            "redis_keyspace_hits_total",
            "redis_hits_total",
        ],
        unit="short"
    ),
    
    "redis.misses": MetricIntent(
        intent="redis.misses",
        description="Cache misses",
        metric_type=MetricType.COUNTER,
        candidates=[
            "cache_misses_total",
            "redis_keyspace_misses_total",
            "redis_misses_total",
        ],
        unit="short"
    ),
    
    "redis.evicted_keys": MetricIntent(
        intent="redis.evicted_keys",
        description="Evicted keys due to memory pressure",
        metric_type=MetricType.COUNTER,
        candidates=[
            "redis_evicted_keys_total",
            "redis_evicted_keys",
            "redis_keyspace_evicted_keys",
        ],
        unit="short"
    ),
    
    "redis.expired_keys": MetricIntent(
        intent="redis.expired_keys",
        description="Keys expired by TTL",
        metric_type=MetricType.COUNTER,
        candidates=[
            "redis_expired_keys_total",
            "redis_expired_keys",
            "redis_keyspace_expired_keys",
        ],
        unit="short"
    ),
    
    "redis.commands": MetricIntent(
        intent="redis.commands",
        description="Commands processed per second",
        metric_type=MetricType.COUNTER,
        candidates=[
            "redis_commands_processed_total",
            "redis_commands_total",
        ],
        unit="short"
    ),
}

# =============================================================================
# MongoDB Metrics
# =============================================================================

MONGODB_INTENTS = {
    "mongodb.connections": MetricIntent(
        intent="mongodb.connections",
        description="Current connections",
        metric_type=MetricType.GAUGE,
        candidates=[
            "mongodb_connections",
            "mongodb_ss_connections",
            "mongo_connections_current",
        ],
        unit="short"
    ),
    
    "mongodb.operations": MetricIntent(
        intent="mongodb.operations",
        description="Operations per second",
        metric_type=MetricType.COUNTER,
        candidates=[
            "mongodb_op_counters_total",
            "mongodb_opcounters_total",
            "mongodb_operations_total",
            "mongo_operations_total",
        ],
        unit="ops"
    ),
    
    "mongodb.query_duration": MetricIntent(
        intent="mongodb.query_duration",
        description="Query execution time",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "mongodb_mongod_op_latencies_latency_bucket",
            "mongodb_query_duration_seconds_bucket",
        ],
        unit="s"
    ),
}

# =============================================================================
# MySQL Metrics
# =============================================================================

MYSQL_INTENTS = {
    "mysql.connections": MetricIntent(
        intent="mysql.connections",
        description="Current connections",
        metric_type=MetricType.GAUGE,
        candidates=[
            "mysql_global_status_threads_connected",
            "mysql_connections",
            "mysqld_exporter_threads_connected",
        ],
        unit="short"
    ),
    
    "mysql.max_connections": MetricIntent(
        intent="mysql.max_connections",
        description="Maximum connections",
        metric_type=MetricType.GAUGE,
        candidates=[
            "mysql_global_variables_max_connections",
            "mysql_max_connections",
        ],
        unit="short"
    ),
    
    "mysql.queries": MetricIntent(
        intent="mysql.queries",
        description="Total queries executed",
        metric_type=MetricType.COUNTER,
        candidates=[
            "mysql_global_status_queries_total",
            "mysql_queries_total",
        ],
        unit="short"
    ),
}

# =============================================================================
# Kafka Metrics
# =============================================================================

KAFKA_INTENTS = {
    "kafka.consumer_lag": MetricIntent(
        intent="kafka.consumer_lag",
        description="Consumer group lag",
        metric_type=MetricType.GAUGE,
        candidates=[
            "kafka_consumer_lag_seconds",
            "kafka_consumergroup_lag",
            "kafka_consumer_lag",
        ],
        unit="s"
    ),
    
    "kafka.messages_per_second": MetricIntent(
        intent="kafka.messages_per_second",
        description="Message throughput",
        metric_type=MetricType.COUNTER,
        candidates=[
            "kafka_topic_partition_current_offset",
            "kafka_messages_in_total",
            "kafka_consumer_records_per_second",
        ],
        unit="short"
    ),
    
    "kafka.consumer_offset": MetricIntent(
        intent="kafka.consumer_offset",
        description="Consumer offset progress",
        metric_type=MetricType.COUNTER,
        candidates=[
            "kafka_consumer_offset_total",
            "kafka_consumergroup_current_offset",
        ],
        unit="short"
    ),
    
    "kafka.partition_count": MetricIntent(
        intent="kafka.partition_count",
        description="Number of partitions",
        metric_type=MetricType.GAUGE,
        candidates=[
            "kafka_topic_partitions",
            "kafka_partition_count",
        ],
        unit="short"
    ),
}

# =============================================================================
# Elasticsearch Metrics
# =============================================================================

ELASTICSEARCH_INTENTS = {
    "elasticsearch.cluster_health": MetricIntent(
        intent="elasticsearch.cluster_health",
        description="Cluster health status",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_cluster_health_status",
            "es_cluster_health_status",
        ],
        unit="short"
    ),
    
    "elasticsearch.active_shards": MetricIntent(
        intent="elasticsearch.active_shards",
        description="Active shards",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_cluster_health_active_shards",
            "es_cluster_active_shards",
        ],
        unit="short"
    ),
    
    "elasticsearch.relocating_shards": MetricIntent(
        intent="elasticsearch.relocating_shards",
        description="Relocating shards",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_cluster_health_relocating_shards",
            "es_cluster_relocating_shards",
        ],
        unit="short"
    ),
    
    "elasticsearch.search_rate": MetricIntent(
        intent="elasticsearch.search_rate",
        description="Search queries per second",
        metric_type=MetricType.COUNTER,
        candidates=[
            "elasticsearch_indices_search_query_total",
            "es_search_query_total",
        ],
        unit="short"
    ),
    
    "elasticsearch.search_latency": MetricIntent(
        intent="elasticsearch.search_latency",
        description="Search query latency",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "elasticsearch_indices_search_query_time_seconds_bucket",
            "es_search_latency_seconds_bucket",
        ],
        unit="s"
    ),
    
    "elasticsearch.indexing_rate": MetricIntent(
        intent="elasticsearch.indexing_rate",
        description="Indexing rate",
        metric_type=MetricType.COUNTER,
        candidates=[
            "elasticsearch_indices_indexing_index_total",
            "es_indexing_total",
        ],
        unit="short"
    ),
    
    "elasticsearch.index_size": MetricIntent(
        intent="elasticsearch.index_size",
        description="Index size in bytes",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_indices_store_size_bytes",
            "es_indices_size_bytes",
        ],
        unit="bytes"
    ),
    
    "elasticsearch.docs_count": MetricIntent(
        intent="elasticsearch.docs_count",
        description="Total document count",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_indices_docs",
            "es_indices_docs_total",
        ],
        unit="short"
    ),
    
    "elasticsearch.jvm_heap_used": MetricIntent(
        intent="elasticsearch.jvm_heap_used",
        description="JVM heap memory used",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_jvm_memory_used_bytes",
            "es_jvm_heap_used_bytes",
        ],
        unit="bytes"
    ),
    
    "elasticsearch.jvm_heap_max": MetricIntent(
        intent="elasticsearch.jvm_heap_max",
        description="JVM heap memory max",
        metric_type=MetricType.GAUGE,
        candidates=[
            "elasticsearch_jvm_memory_max_bytes",
            "es_jvm_heap_max_bytes",
        ],
        unit="bytes"
    ),
    
    "elasticsearch.gc_time": MetricIntent(
        intent="elasticsearch.gc_time",
        description="Garbage collection time",
        metric_type=MetricType.COUNTER,
        candidates=[
            "elasticsearch_jvm_gc_collection_seconds_sum",
            "es_jvm_gc_seconds_total",
        ],
        unit="s"
    ),
}

# =============================================================================
# Stream/Worker Metrics (non-HTTP services)
# =============================================================================

STREAM_INTENTS = {
    "stream.events_processed": MetricIntent(
        intent="stream.events_processed",
        description="Events processed",
        metric_type=MetricType.COUNTER,
        candidates=[
            "events_processed_total",
            "stream_events_total",
            "messages_processed_total",
        ],
        unit="short"
    ),
    
    "stream.event_duration": MetricIntent(
        intent="stream.event_duration",
        description="Event processing duration",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "event_processing_duration_seconds_bucket",
            "stream_processing_duration_bucket",
            "message_processing_duration_seconds_bucket",
            "kafka_consumer_processing_duration_bucket",
        ],
        unit="s"
    ),
}

WORKER_INTENTS = {
    "worker.jobs_processed": MetricIntent(
        intent="worker.jobs_processed",
        description="Jobs/notifications processed",
        metric_type=MetricType.COUNTER,
        candidates=[
            "notifications_sent_total",
            "jobs_processed_total",
            "tasks_completed_total",
            "background_jobs_total",
            "worker_jobs_processed_total",
        ],
        unit="short"
    ),
    
    "worker.job_duration": MetricIntent(
        intent="worker.job_duration",
        description="Job processing duration",
        metric_type=MetricType.HISTOGRAM,
        candidates=[
            "notification_processing_duration_seconds_bucket",
            "job_duration_seconds_bucket",
            "task_duration_seconds_bucket",
            "worker_job_duration_seconds_bucket",
        ],
        unit="s"
    ),
}

# =============================================================================
# Combined Intent Registry
# =============================================================================

ALL_INTENTS: Dict[str, MetricIntent] = {
    **HTTP_INTENTS,
    **POSTGRESQL_INTENTS,
    **REDIS_INTENTS,
    **MONGODB_INTENTS,
    **MYSQL_INTENTS,
    **KAFKA_INTENTS,
    **ELASTICSEARCH_INTENTS,
    **STREAM_INTENTS,
    **WORKER_INTENTS,
}


def get_intent(intent_name: str) -> Optional[MetricIntent]:
    """Get a metric intent by name."""
    return ALL_INTENTS.get(intent_name)


def get_intents_for_technology(technology: str) -> Dict[str, MetricIntent]:
    """Get all intents for a specific technology."""
    prefix = f"{technology}."
    return {k: v for k, v in ALL_INTENTS.items() if k.startswith(prefix)}


def list_technologies() -> List[str]:
    """List all supported technologies."""
    technologies = set()
    for intent in ALL_INTENTS.keys():
        tech = intent.split('.')[0]
        technologies.add(tech)
    return sorted(technologies)
