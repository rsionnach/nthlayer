"""
Multi-service demo app for NthLayer Gallery
Emits metrics for all 5 demo services with shared metric objects
"""

from flask import Flask, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry
import random
import os

app = Flask(__name__)

# Use custom registry
registry = CollectorRegistry()

# Basic Auth
METRICS_USERNAME = "nthlayer"
METRICS_PASSWORD = os.environ.get("METRICS_PASSWORD", "demo")

def check_auth(username, password):
    return username == METRICS_USERNAME and password == METRICS_PASSWORD

def authenticate():
    return Response(
        'Authentication required', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

# =============================================================================
# SHARED METRICS - One metric object per metric name, use service labels
# =============================================================================

# HTTP metrics (shared by all API services)
http_requests = Counter(
    'http_requests_total', 'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status'],
    registry=registry
)
http_duration = Histogram(
    'http_request_duration_seconds', 'Request duration',
    ['service', 'method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry
)
http_in_flight = Gauge(
    'http_requests_in_flight', 'Current in-flight requests',
    ['service'],
    registry=registry
)

# PostgreSQL metrics (payment-api, identity-service)
pg_connections = Gauge(
    'pg_stat_database_numbackends', 'Active connections',
    ['service', 'datname'],
    registry=registry
)
pg_max_conn = Gauge(
    'pg_settings_max_connections', 'Max connections',
    ['service'],
    registry=registry
)
pg_blks_hit = Gauge(
    'pg_stat_database_blks_hit', 'Buffer cache hits',
    ['service', 'datname'],
    registry=registry
)
pg_blks_read = Gauge(
    'pg_stat_database_blks_read', 'Disk reads',
    ['service', 'datname'],
    registry=registry
)
pg_query_duration = Histogram(
    'pg_stat_statements_mean_exec_time_seconds', 'Query duration',
    ['service'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=registry
)
# Alias for consistency
pg_query_time = pg_query_duration

# Additional PostgreSQL metrics
pg_activity_count = Gauge(
    'pg_stat_activity_count', 'Connections by state',
    ['service', 'state'],
    registry=registry
)
pg_xact_commit = Gauge(
    'pg_stat_database_xact_commit', 'Committed transactions',
    ['service', 'datname'],
    registry=registry
)
pg_xact_rollback = Gauge(
    'pg_stat_database_xact_rollback', 'Rolled back transactions',
    ['service', 'datname'],
    registry=registry
)
pg_database_size = Gauge(
    'pg_database_size_bytes', 'Database size',
    ['service', 'datname'],
    registry=registry
)
pg_deadlocks = Gauge(
    'pg_stat_database_deadlocks', 'Deadlocks',
    ['service', 'datname'],
    registry=registry
)
pg_replication_lag = Gauge(
    'pg_replication_lag_seconds', 'Replication lag',
    ['service'],
    registry=registry
)
pg_dead_tuples = Gauge(
    'pg_stat_user_tables_n_dead_tup', 'Dead tuples (bloat)',
    ['service', 'schemaname', 'relname'],
    registry=registry
)
pg_index_scans = Counter(
    'pg_stat_user_indexes_idx_scan', 'Index scans',
    ['service', 'schemaname', 'relname', 'indexrelname'],
    registry=registry
)

# Redis metrics (payment-api, notification-worker, identity-service)
redis_connections = Gauge(
    'redis_connected_clients', 'Connected clients',
    ['service'],
    registry=registry
)
redis_memory = Gauge(
    'redis_memory_used_bytes', 'Memory used',
    ['service'],
    registry=registry
)
redis_keys = Gauge(
    'redis_db_keys', 'Total keys',
    ['service', 'db'],
    registry=registry
)

# Cache metrics (payment-api uses these for Redis)
cache_hits = Counter(
    'cache_hits_total', 'Cache hits',
    ['service'],
    registry=registry
)
cache_misses = Counter(
    'cache_misses_total', 'Cache misses',
    ['service'],
    registry=registry
)

# Additional Redis metrics
redis_evicted_keys = Counter(
    'redis_evicted_keys_total', 'Evicted keys due to memory pressure',
    ['service'],
    registry=registry
)
redis_expired_keys = Counter(
    'redis_expired_keys_total', 'Keys expired by TTL',
    ['service'],
    registry=registry
)
redis_commands = Counter(
    'redis_commands_processed_total', 'Commands processed',
    ['service'],
    registry=registry
)

# Kubernetes metrics (payment-api, notification-worker, analytics-stream)
kube_pod_status = Gauge(
    'kube_pod_status_phase', 'Pod status',
    ['service', 'pod', 'phase'],
    registry=registry
)
container_cpu = Counter(
    'container_cpu_usage_seconds_total', 'CPU usage',
    ['service', 'pod', 'container'],
    registry=registry
)
container_memory = Gauge(
    'container_memory_working_set_bytes', 'Memory usage',
    ['service', 'pod', 'container'],
    registry=registry
)

# MySQL metrics (checkout-service)
mysql_connections = Gauge(
    'mysql_global_status_threads_connected', 'MySQL connections',
    ['service'],
    registry=registry
)
mysql_max_conn = Gauge(
    'mysql_global_variables_max_connections', 'Max connections',
    ['service'],
    registry=registry
)
mysql_queries = Counter(
    'mysql_global_status_queries_total', 'Total queries',
    ['service'],
    registry=registry
)

# RabbitMQ metrics (checkout-service)
rabbitmq_messages = Gauge(
    'rabbitmq_queue_messages', 'Messages in queue',
    ['service', 'queue'],
    registry=registry
)
rabbitmq_consumers = Gauge(
    'rabbitmq_queue_consumers', 'Active consumers',
    ['service', 'queue'],
    registry=registry
)
rabbitmq_published = Counter(
    'rabbitmq_queue_messages_published_total', 'Published messages',
    ['service', 'queue'],
    registry=registry
)

# ECS metrics (checkout-service, identity-service)
ecs_tasks = Gauge(
    'ecs_service_running_count', 'Running tasks',
    ['service', 'cluster'],
    registry=registry
)
ecs_cpu = Gauge(
    'ecs_task_cpu_utilization', 'CPU utilization %',
    ['service', 'task'],
    registry=registry
)
ecs_memory = Gauge(
    'ecs_task_memory_utilization', 'Memory utilization %',
    ['service', 'task'],
    registry=registry
)

# Notification worker metrics
notif_sent = Counter(
    'notifications_sent_total', 'Notifications sent',
    ['service', 'status'],
    registry=registry
)
notif_duration = Histogram(
    'notification_processing_duration_seconds', 'Processing duration',
    ['service'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

# Kafka metrics (notification-worker, analytics-stream)
kafka_lag = Gauge(
    'kafka_consumer_lag_seconds', 'Consumer lag',
    ['service', 'topic'],
    registry=registry
)
kafka_offset = Counter(
    'kafka_consumer_offset_total', 'Consumer offset',
    ['service', 'topic', 'partition'],
    registry=registry
)
kafka_throughput = Gauge(
    'kafka_consumer_records_per_second', 'Records/sec',
    ['service', 'topic'],
    registry=registry
)
kafka_partitions = Gauge(
    'kafka_topic_partitions', 'Number of partitions',
    ['service', 'topic'],
    registry=registry
)

# Analytics stream metrics
events_processed = Counter(
    'events_processed_total', 'Events processed',
    ['service', 'status'],
    registry=registry
)
event_duration = Histogram(
    'event_processing_duration_seconds', 'Processing duration',
    ['service'],
    buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=registry
)
stream_throughput = Gauge(
    'stream_throughput_events_per_second', 'Throughput',
    ['service'],
    registry=registry
)

# MongoDB metrics (analytics-stream)
mongo_connections = Gauge(
    'mongodb_connections', 'Active connections',
    ['service', 'state'],
    registry=registry
)
mongo_ops = Counter(
    'mongodb_operations_total', 'Operations',
    ['service', 'type'],
    registry=registry
)
mongo_query_time = Histogram(
    'mongodb_query_duration_seconds', 'Query duration',
    ['service'],
    buckets=[0.001, 0.01, 0.05, 0.1, 0.5],
    registry=registry
)

# Identity service metrics
login_attempts = Counter(
    'login_attempts_total', 'Login attempts',
    ['service', 'status'],
    registry=registry
)
user_registrations = Counter(
    'user_registrations_total', 'User registrations',
    ['service'],
    registry=registry
)
password_resets = Counter(
    'password_reset_total', 'Password resets',
    ['service'],
    registry=registry
)

# Elasticsearch metrics (search-api)
es_cluster_health = Gauge(
    'elasticsearch_cluster_health_status', 'Cluster health (0=red, 1=yellow, 2=green)',
    ['service', 'cluster'],
    registry=registry
)
es_active_shards = Gauge(
    'elasticsearch_cluster_health_active_shards', 'Active shards',
    ['service', 'cluster'],
    registry=registry
)
es_relocating_shards = Gauge(
    'elasticsearch_cluster_health_relocating_shards', 'Relocating shards',
    ['service', 'cluster'],
    registry=registry
)
es_search_total = Counter(
    'elasticsearch_indices_search_query_total', 'Search queries',
    ['service', 'index'],
    registry=registry
)
es_search_time = Histogram(
    'elasticsearch_indices_search_query_time_seconds', 'Search latency',
    ['service', 'index'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=registry
)
es_indexing_total = Counter(
    'elasticsearch_indices_indexing_index_total', 'Indexing operations',
    ['service', 'index'],
    registry=registry
)
es_index_size = Gauge(
    'elasticsearch_indices_store_size_bytes', 'Index size',
    ['service', 'index'],
    registry=registry
)
es_docs_count = Gauge(
    'elasticsearch_indices_docs', 'Document count',
    ['service', 'index'],
    registry=registry
)
es_jvm_heap_used = Gauge(
    'elasticsearch_jvm_memory_used_bytes', 'JVM heap used',
    ['service', 'area'],
    registry=registry
)
es_jvm_heap_max = Gauge(
    'elasticsearch_jvm_memory_max_bytes', 'JVM heap max',
    ['service', 'area'],
    registry=registry
)
es_gc_time = Counter(
    'elasticsearch_jvm_gc_collection_seconds_sum', 'GC time',
    ['service', 'gc'],
    registry=registry
)

# =============================================================================
# Simulation Functions
# =============================================================================

def simulate_payment_api():
    """payment-api: PostgreSQL, Redis, Kubernetes"""
    svc = 'payment-api'
    
    # HTTP traffic
    http_in_flight.labels(service=svc).set(random.randint(2, 15))
    for _ in range(random.randint(5, 15)):
        status = random.choices([200, 201, 400, 500], weights=[85, 10, 3, 2])[0]
        endpoint = random.choice(['/payments', '/checkout', '/refund'])
        duration = random.uniform(0.05, 0.3) if status < 400 else random.uniform(0.5, 2.0)
        
        http_requests.labels(service=svc, method='POST', endpoint=endpoint, status=status).inc()
        http_duration.labels(service=svc, method='POST', endpoint=endpoint).observe(duration)
    
    # PostgreSQL
    pg_connections.labels(service=svc, datname='payments').set(random.randint(15, 35))
    pg_max_conn.labels(service=svc).set(100)
    # Use cumulative values for cache hits/reads to simulate realistic ratios
    pg_blks_hit.labels(service=svc, datname='payments').set(random.randint(90000, 100000))
    pg_blks_read.labels(service=svc, datname='payments').set(random.randint(1000, 2000))
    pg_query_duration.labels(service=svc).observe(random.uniform(0.001, 0.05))
    
    # Additional PostgreSQL metrics
    pg_activity_count.labels(service=svc, state='active').set(random.randint(2, 12))
    pg_activity_count.labels(service=svc, state='idle').set(random.randint(5, 25))
    pg_activity_count.labels(service=svc, state='idle_in_transaction').set(random.randint(0, 3))
    pg_xact_commit.labels(service=svc, datname='payments').set(random.randint(10000, 100000))
    pg_xact_rollback.labels(service=svc, datname='payments').set(random.randint(10, 200))
    pg_database_size.labels(service=svc, datname='payments').set(random.randint(2_000_000_000, 15_000_000_000))
    pg_deadlocks.labels(service=svc, datname='payments').set(random.randint(0, 5))
    pg_replication_lag.labels(service=svc).set(random.uniform(0.0, 3.0))
    for table in ['users', 'orders', 'sessions', 'audit_log']:
        pg_dead_tuples.labels(service=svc, schemaname='public', relname=table).set(random.randint(100, 15000))
        pg_index_scans.labels(service=svc, schemaname='public', relname=table, indexrelname=f'{table}_pkey').inc(random.randint(100, 500))
    
    # Redis
    cache_hits.labels(service=svc).inc(random.randint(80, 120))
    cache_misses.labels(service=svc).inc(random.randint(5, 15))
    redis_connections.labels(service=svc).set(random.randint(10, 20))
    redis_memory.labels(service=svc).set(random.randint(100_000_000, 200_000_000))
    redis_keys.labels(service=svc, db='0').set(random.randint(2000, 8000))
    redis_evicted_keys.labels(service=svc).inc(random.randint(0, 5))
    redis_expired_keys.labels(service=svc).inc(random.randint(10, 50))
    redis_commands.labels(service=svc).inc(random.randint(500, 1500))
    
    # Kubernetes
    for i in range(1, 4):
        pod = f'payment-api-{i}'
        kube_pod_status.labels(service=svc, pod=pod, phase='Running').set(1)
        container_cpu.labels(service=svc, pod=pod, container='payment-api').inc(random.uniform(0.01, 0.05))
        container_memory.labels(service=svc, pod=pod, container='payment-api').set(random.randint(200_000_000, 400_000_000))

def simulate_checkout_service():
    """checkout-service: MySQL, RabbitMQ, Redis, ECS"""
    svc = 'checkout-service'
    
    # HTTP traffic
    http_in_flight.labels(service=svc).set(random.randint(1, 10))
    for _ in range(random.randint(3, 10)):
        status = random.choices([200, 400, 500], weights=[90, 7, 3])[0]
        endpoint = random.choice(['/cart', '/checkout', '/order'])
        duration = random.uniform(0.1, 0.5) if status < 400 else random.uniform(1.0, 3.0)
        
        http_requests.labels(service=svc, method='POST', endpoint=endpoint, status=status).inc()
        http_duration.labels(service=svc, method='POST', endpoint=endpoint).observe(duration)
    
    # MySQL
    mysql_connections.labels(service=svc).set(random.randint(10, 25))
    mysql_max_conn.labels(service=svc).set(150)
    mysql_queries.labels(service=svc).inc(random.randint(50, 200))
    
    # Redis (session cache)
    redis_memory.labels(service=svc).set(random.randint(60_000_000, 120_000_000))
    redis_connections.labels(service=svc).set(random.randint(8, 20))
    redis_keys.labels(service=svc, db='0').set(random.randint(800, 3000))
    cache_hits.labels(service=svc).inc(random.randint(80, 150))
    cache_misses.labels(service=svc).inc(random.randint(3, 10))
    redis_evicted_keys.labels(service=svc).inc(random.randint(0, 3))
    redis_expired_keys.labels(service=svc).inc(random.randint(5, 30))
    redis_commands.labels(service=svc).inc(random.randint(300, 800))
    
    # RabbitMQ
    rabbitmq_messages.labels(service=svc, queue='order_queue').set(random.randint(0, 50))
    rabbitmq_consumers.labels(service=svc, queue='order_queue').set(3)
    rabbitmq_published.labels(service=svc, queue='order_queue').inc(random.randint(5, 20))
    
    # ECS
    ecs_tasks.labels(service=svc, cluster='production').set(4)
    for i in range(1, 5):
        task = f'task-{i}'
        ecs_cpu.labels(service=svc, task=task).set(random.uniform(20, 50))
        ecs_memory.labels(service=svc, task=task).set(random.uniform(30, 60))

def simulate_notification_worker():
    """notification-worker: Redis, Kafka, Kubernetes"""
    svc = 'notification-worker'
    
    # Notifications
    for _ in range(random.randint(10, 30)):
        status = random.choices(['delivered', 'failed'], weights=[95, 5])[0]
        notif_sent.labels(service=svc, status=status).inc()
        notif_duration.labels(service=svc).observe(random.uniform(0.5, 3.0))
    
    # Kafka
    kafka_lag.labels(service=svc, topic='notifications').set(random.uniform(0.1, 2.0))
    kafka_throughput.labels(service=svc, topic='notifications').set(random.uniform(500, 900))
    kafka_partitions.labels(service=svc, topic='notifications').set(3)
    for partition in range(3):
        kafka_offset.labels(service=svc, topic='notifications', partition=str(partition)).inc(random.randint(10, 50))
    
    # Redis (cache for notification templates)
    # NOTE: redis_keys intentionally omitted to demo guidance panels
    redis_connections.labels(service=svc).set(random.randint(5, 15))
    redis_memory.labels(service=svc).set(random.randint(50_000_000, 100_000_000))
    cache_hits.labels(service=svc).inc(random.randint(50, 100))
    cache_misses.labels(service=svc).inc(random.randint(2, 8))
    redis_evicted_keys.labels(service=svc).inc(random.randint(0, 2))
    redis_expired_keys.labels(service=svc).inc(random.randint(5, 20))
    redis_commands.labels(service=svc).inc(random.randint(200, 600))
    
    # Kubernetes
    for i in range(1, 4):
        pod = f'notification-worker-{i}'
        kube_pod_status.labels(service=svc, pod=pod, phase='Running').set(1)
        container_cpu.labels(service=svc, pod=pod, container='worker').inc(random.uniform(0.02, 0.08))
        container_memory.labels(service=svc, pod=pod, container='worker').set(random.randint(150_000_000, 300_000_000))

def simulate_analytics_stream():
    """analytics-stream: MongoDB, Redis, Kafka, Kubernetes"""
    svc = 'analytics-stream'
    
    # Events
    for _ in range(random.randint(20, 50)):
        status = random.choices(['success', 'error'], weights=[98, 2])[0]
        events_processed.labels(service=svc, status=status).inc()
        event_duration.labels(service=svc).observe(random.uniform(0.001, 0.05))
    
    stream_throughput.labels(service=svc).set(random.uniform(500, 1500))
    
    # MongoDB
    mongo_connections.labels(service=svc, state='current').set(random.randint(8, 20))
    mongo_ops.labels(service=svc, type='insert').inc(random.randint(50, 200))
    mongo_ops.labels(service=svc, type='query').inc(random.randint(100, 400))
    mongo_ops.labels(service=svc, type='update').inc(random.randint(20, 100))
    mongo_query_time.labels(service=svc).observe(random.uniform(0.005, 0.05))
    
    # Redis (stream cache)
    redis_memory.labels(service=svc).set(random.randint(80_000_000, 150_000_000))
    redis_connections.labels(service=svc).set(random.randint(5, 12))
    redis_keys.labels(service=svc, db='0').set(random.randint(1000, 5000))
    cache_hits.labels(service=svc).inc(random.randint(100, 200))
    cache_misses.labels(service=svc).inc(random.randint(5, 15))
    redis_evicted_keys.labels(service=svc).inc(random.randint(0, 5))
    redis_expired_keys.labels(service=svc).inc(random.randint(10, 40))
    redis_commands.labels(service=svc).inc(random.randint(400, 1000))
    
    # Kafka
    kafka_lag.labels(service=svc, topic='events').set(random.uniform(0.05, 0.5))
    kafka_throughput.labels(service=svc, topic='events').set(random.uniform(800, 1200))
    kafka_partitions.labels(service=svc, topic='events').set(3)
    for partition in range(3):
        kafka_offset.labels(service=svc, topic='events', partition=str(partition)).inc(random.randint(100, 300))
    
    # Kubernetes
    for i in range(1, 5):
        pod = f'analytics-stream-{i}'
        kube_pod_status.labels(service=svc, pod=pod, phase='Running').set(1)
        container_cpu.labels(service=svc, pod=pod, container='stream-processor').inc(random.uniform(0.05, 0.15))
        container_memory.labels(service=svc, pod=pod, container='stream-processor').set(random.randint(300_000_000, 600_000_000))

def simulate_identity_service():
    """identity-service: PostgreSQL, Redis, ECS"""
    svc = 'identity-service'
    
    # HTTP traffic
    http_in_flight.labels(service=svc).set(random.randint(1, 12))
    for _ in range(random.randint(5, 20)):
        status = random.choices([200, 401, 500], weights=[85, 12, 3])[0]
        endpoint = random.choice(['/login', '/register', '/verify'])
        duration = random.uniform(0.05, 0.2) if status < 400 else random.uniform(0.3, 1.0)
        
        http_requests.labels(service=svc, method='POST', endpoint=endpoint, status=status).inc()
        http_duration.labels(service=svc, method='POST', endpoint=endpoint).observe(duration)
    
    # Auth metrics
    login_attempts.labels(service=svc, status='success').inc(random.randint(10, 30))
    login_attempts.labels(service=svc, status='failed').inc(random.randint(1, 5))
    user_registrations.labels(service=svc).inc(random.randint(0, 3))
    password_resets.labels(service=svc).inc(random.randint(0, 2))
    
    # PostgreSQL
    pg_connections.labels(service=svc, datname='identity').set(random.randint(10, 20))
    pg_max_conn.labels(service=svc).set(100)
    # PostgreSQL cache metrics
    pg_blks_hit.labels(service=svc, datname='identity').set(random.randint(80000, 100000))
    pg_blks_read.labels(service=svc, datname='identity').set(random.randint(1000, 3000))
    # PostgreSQL query performance
    pg_query_time.labels(service=svc).observe(random.uniform(0.001, 0.02))
    
    # Additional PostgreSQL metrics
    pg_activity_count.labels(service=svc, state='active').set(random.randint(2, 12))
    pg_activity_count.labels(service=svc, state='idle').set(random.randint(5, 25))
    pg_activity_count.labels(service=svc, state='idle_in_transaction').set(random.randint(0, 3))
    pg_xact_commit.labels(service=svc, datname='identity').set(random.randint(10000, 100000))
    pg_xact_rollback.labels(service=svc, datname='identity').set(random.randint(10, 200))
    pg_database_size.labels(service=svc, datname='identity').set(random.randint(2_000_000_000, 15_000_000_000))
    pg_deadlocks.labels(service=svc, datname='identity').set(random.randint(0, 5))
    pg_replication_lag.labels(service=svc).set(random.uniform(0.0, 3.0))
    for table in ['users', 'orders', 'sessions', 'audit_log']:
        pg_dead_tuples.labels(service=svc, schemaname='public', relname=table).set(random.randint(100, 15000))
        pg_index_scans.labels(service=svc, schemaname='public', relname=table, indexrelname=f'{table}_pkey').inc(random.randint(50, 300))
    
    # Redis (session cache)
    redis_keys.labels(service=svc, db='0').set(random.randint(1000, 5000))
    redis_memory.labels(service=svc).set(random.randint(80_000_000, 150_000_000))
    redis_connections.labels(service=svc).set(random.randint(10, 25))
    cache_hits.labels(service=svc).inc(random.randint(60, 120))
    cache_misses.labels(service=svc).inc(random.randint(3, 12))
    redis_evicted_keys.labels(service=svc).inc(random.randint(0, 3))
    redis_expired_keys.labels(service=svc).inc(random.randint(20, 60))
    redis_commands.labels(service=svc).inc(random.randint(300, 900))
    
    # ECS
    ecs_tasks.labels(service=svc, cluster='production').set(3)
    for i in range(1, 4):
        task = f'task-{i}'
        ecs_cpu.labels(service=svc, task=task).set(random.uniform(15, 40))


def simulate_search_api():
    """search-api: Elasticsearch, Redis, Kubernetes"""
    svc = 'search-api'
    
    # HTTP traffic
    http_in_flight.labels(service=svc).set(random.randint(2, 20))
    for _ in range(random.randint(10, 30)):
        status = random.choices([200, 400, 500], weights=[92, 5, 3])[0]
        endpoint = random.choice(['/search', '/suggest', '/index'])
        duration = random.uniform(0.02, 0.2) if status < 400 else random.uniform(0.5, 2.0)
        
        http_requests.labels(service=svc, method='GET', endpoint=endpoint, status=status).inc()
        http_duration.labels(service=svc, method='GET', endpoint=endpoint).observe(duration)
    
    # Elasticsearch
    es_cluster_health.labels(service=svc, cluster='search-cluster').set(2)  # 2 = green
    es_active_shards.labels(service=svc, cluster='search-cluster').set(random.randint(20, 30))
    es_relocating_shards.labels(service=svc, cluster='search-cluster').set(random.randint(0, 2))
    
    for index in ['products', 'users', 'content']:
        es_search_total.labels(service=svc, index=index).inc(random.randint(50, 200))
        es_search_time.labels(service=svc, index=index).observe(random.uniform(0.01, 0.15))
        es_indexing_total.labels(service=svc, index=index).inc(random.randint(10, 50))
        es_index_size.labels(service=svc, index=index).set(random.randint(500_000_000, 5_000_000_000))
        es_docs_count.labels(service=svc, index=index).set(random.randint(100_000, 10_000_000))
    
    # NOTE: es_jvm_heap_used and es_jvm_heap_max intentionally omitted to demo guidance panels
    es_gc_time.labels(service=svc, gc='young').inc(random.uniform(0.01, 0.1))
    es_gc_time.labels(service=svc, gc='old').inc(random.uniform(0.001, 0.05))
    
    # Redis (search cache)
    redis_memory.labels(service=svc).set(random.randint(100_000_000, 300_000_000))
    redis_connections.labels(service=svc).set(random.randint(10, 30))
    redis_keys.labels(service=svc, db='0').set(random.randint(50000, 200000))
    cache_hits.labels(service=svc).inc(random.randint(200, 500))
    cache_misses.labels(service=svc).inc(random.randint(20, 80))
    redis_evicted_keys.labels(service=svc).inc(random.randint(5, 20))
    redis_expired_keys.labels(service=svc).inc(random.randint(50, 150))
    redis_commands.labels(service=svc).inc(random.randint(1000, 3000))
    
    # Kubernetes
    for i in range(1, 4):
        pod = f'search-api-{i}'
        kube_pod_status.labels(service=svc, pod=pod, phase='Running').set(1)
        container_cpu.labels(service=svc, pod=pod, container='search-api').inc(random.uniform(0.02, 0.1))
        container_memory.labels(service=svc, pod=pod, container='search-api').set(random.randint(400_000_000, 800_000_000))


# =============================================================================
# Flask Routes
# =============================================================================

@app.route('/')
def index():
    return """
    <h1>NthLayer Multi-Service Demo</h1>
    <p>Emitting metrics for 6 services:</p>
    <ul>
        <li><strong>payment-api</strong> - PostgreSQL, Redis, Kubernetes</li>
        <li><strong>checkout-service</strong> - MySQL, RabbitMQ, ECS</li>
        <li><strong>notification-worker</strong> - Redis, Kafka, Kubernetes</li>
        <li><strong>analytics-stream</strong> - MongoDB, Kafka, Kubernetes</li>
        <li><strong>identity-service</strong> - PostgreSQL, Redis, ECS</li>
        <li><strong>search-api</strong> - Elasticsearch, Redis, Kubernetes</li>
    </ul>
    <p><a href="/metrics">View Prometheus metrics</a> (requires auth)</p>
    """

@app.route('/health')
def health():
    return {'status': 'healthy', 'services': 6}

@app.route('/metrics')
def metrics():
    from flask import request
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
    
    # Simulate all services
    simulate_payment_api()
    simulate_checkout_service()
    simulate_notification_worker()
    simulate_analytics_stream()
    simulate_identity_service()
    simulate_search_api()
    
    return Response(generate_latest(registry), mimetype='text/plain')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
