#!/usr/bin/env python3
"""
Push synthetic demo metrics to Grafana Cloud via Prometheus remote write.

Generates the same metrics as the Fly.io demo app for 6 services:
- payment-api: PostgreSQL, Redis, Kubernetes
- checkout-service: MySQL, RabbitMQ, Redis, ECS
- notification-worker: Redis, Kafka, Kubernetes
- analytics-stream: MongoDB, Redis, Kafka, Kubernetes
- identity-service: PostgreSQL, Redis, ECS
- search-api: Elasticsearch, Redis, Kubernetes

Usage:
    export GRAFANA_REMOTE_WRITE_URL=https://...
    export GRAFANA_CLOUD_USER=...
    export GRAFANA_CLOUD_KEY=...
    python scripts/push_demo_metrics.py
"""

import os
import random
import struct
import time
from typing import NamedTuple

import requests
import snappy

# Prometheus remote write protobuf wire format (simplified)
# We construct the wire format directly to avoid protobuf dependency


class Sample(NamedTuple):
    timestamp_ms: int
    value: float


class Label(NamedTuple):
    name: str
    value: str


class TimeSeries(NamedTuple):
    labels: list[Label]
    samples: list[Sample]


def encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    parts = []
    while value > 127:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value)
    return bytes(parts)


def encode_string(field_num: int, s: str) -> bytes:
    """Encode a string field in protobuf format."""
    encoded = s.encode("utf-8")
    return bytes([field_num << 3 | 2]) + encode_varint(len(encoded)) + encoded


def encode_label(label: Label) -> bytes:
    """Encode a Label message."""
    return encode_string(1, label.name) + encode_string(2, label.value)


def encode_sample(sample: Sample) -> bytes:
    """Encode a Sample message."""
    # Field 1: value (double) - wire type 1 (64-bit)
    value_bytes = bytes([1 << 3 | 1]) + struct.pack("<d", sample.value)
    # Field 2: timestamp (int64) - wire type 0 (varint)
    ts_bytes = bytes([2 << 3 | 0]) + encode_varint(sample.timestamp_ms)
    return value_bytes + ts_bytes


def encode_timeseries(ts: TimeSeries) -> bytes:
    """Encode a TimeSeries message."""
    result = b""
    # Field 1: labels (repeated Label)
    for label in ts.labels:
        label_bytes = encode_label(label)
        result += bytes([1 << 3 | 2]) + encode_varint(len(label_bytes)) + label_bytes
    # Field 2: samples (repeated Sample)
    for sample in ts.samples:
        sample_bytes = encode_sample(sample)
        result += bytes([2 << 3 | 2]) + encode_varint(len(sample_bytes)) + sample_bytes
    return result


def encode_write_request(timeseries_list: list[TimeSeries]) -> bytes:
    """Encode a WriteRequest message."""
    result = b""
    # Field 1: timeseries (repeated TimeSeries)
    for ts in timeseries_list:
        ts_bytes = encode_timeseries(ts)
        result += bytes([1 << 3 | 2]) + encode_varint(len(ts_bytes)) + ts_bytes
    return result


def make_ts(name: str, value: float, labels: dict[str, str] | None = None) -> TimeSeries:
    """Create a TimeSeries with a single sample at current time."""
    now_ms = int(time.time() * 1000)
    all_labels = [Label("__name__", name)]
    if labels:
        all_labels.extend(Label(k, v) for k, v in sorted(labels.items()))
    return TimeSeries(labels=all_labels, samples=[Sample(now_ms, value)])


# =============================================================================
# Metric Generators (mirrors Fly.io app logic)
# =============================================================================


def generate_payment_api() -> list[TimeSeries]:
    """payment-api: PostgreSQL, Redis, Kubernetes"""
    svc = "payment-api"
    ts_list = []

    # HTTP metrics
    ts_list.append(make_ts("http_requests_in_flight", random.randint(2, 15), {"service": svc}))
    for endpoint in ["/payments", "/checkout", "/refund"]:
        for status in ["200", "201", "400", "500"]:
            count = random.randint(50, 150) if status in ["200", "201"] else random.randint(1, 10)
            ts_list.append(
                make_ts(
                    "http_requests_total",
                    count,
                    {"service": svc, "method": "POST", "endpoint": endpoint, "status": status},
                )
            )

    # PostgreSQL
    ts_list.append(
        make_ts(
            "pg_stat_database_numbackends",
            random.randint(15, 35),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(make_ts("pg_settings_max_connections", 100, {"service": svc}))
    ts_list.append(
        make_ts(
            "pg_stat_database_blks_hit",
            random.randint(90000, 100000),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_blks_read",
            random.randint(1000, 2000),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_activity_count", random.randint(2, 12), {"service": svc, "state": "active"}
        )
    )
    ts_list.append(
        make_ts("pg_stat_activity_count", random.randint(5, 25), {"service": svc, "state": "idle"})
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_xact_commit",
            random.randint(10000, 100000),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_xact_rollback",
            random.randint(10, 200),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_database_size_bytes",
            random.randint(2_000_000_000, 15_000_000_000),
            {"service": svc, "datname": "payments"},
        )
    )
    ts_list.append(
        make_ts("pg_replication_lag_seconds", random.uniform(0.0, 3.0), {"service": svc})
    )

    # Redis
    ts_list.append(make_ts("cache_hits_total", random.randint(8000, 12000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(500, 1500), {"service": svc}))
    ts_list.append(make_ts("redis_connected_clients", random.randint(10, 20), {"service": svc}))
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(100_000_000, 200_000_000), {"service": svc}
        )
    )
    ts_list.append(
        make_ts("redis_db_keys", random.randint(2000, 8000), {"service": svc, "db": "0"})
    )

    # Kubernetes pods
    for i in range(1, 4):
        pod = f"payment-api-{i}"
        ts_list.append(
            make_ts("kube_pod_status_phase", 1, {"service": svc, "pod": pod, "phase": "Running"})
        )
        ts_list.append(
            make_ts(
                "container_memory_working_set_bytes",
                random.randint(200_000_000, 400_000_000),
                {"service": svc, "pod": pod, "container": "payment-api"},
            )
        )

    return ts_list


def generate_checkout_service() -> list[TimeSeries]:
    """checkout-service: MySQL, RabbitMQ, Redis, ECS"""
    svc = "checkout-service"
    ts_list = []

    # HTTP metrics
    ts_list.append(make_ts("http_requests_in_flight", random.randint(1, 10), {"service": svc}))
    for endpoint in ["/cart", "/checkout", "/order"]:
        for status in ["200", "400", "500"]:
            count = random.randint(30, 100) if status == "200" else random.randint(1, 8)
            ts_list.append(
                make_ts(
                    "http_requests_total",
                    count,
                    {"service": svc, "method": "POST", "endpoint": endpoint, "status": status},
                )
            )

    # MySQL
    ts_list.append(
        make_ts("mysql_global_status_threads_connected", random.randint(10, 25), {"service": svc})
    )
    ts_list.append(make_ts("mysql_global_variables_max_connections", 150, {"service": svc}))
    ts_list.append(
        make_ts("mysql_global_status_queries_total", random.randint(5000, 20000), {"service": svc})
    )

    # Redis
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(60_000_000, 120_000_000), {"service": svc}
        )
    )
    ts_list.append(make_ts("redis_connected_clients", random.randint(8, 20), {"service": svc}))
    ts_list.append(make_ts("redis_db_keys", random.randint(800, 3000), {"service": svc, "db": "0"}))
    ts_list.append(make_ts("cache_hits_total", random.randint(8000, 15000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(300, 1000), {"service": svc}))

    # RabbitMQ
    ts_list.append(
        make_ts(
            "rabbitmq_queue_messages",
            random.randint(0, 50),
            {"service": svc, "queue": "order_queue"},
        )
    )
    ts_list.append(make_ts("rabbitmq_queue_consumers", 3, {"service": svc, "queue": "order_queue"}))
    ts_list.append(
        make_ts(
            "rabbitmq_queue_messages_published_total",
            random.randint(500, 2000),
            {"service": svc, "queue": "order_queue"},
        )
    )

    # ECS
    ts_list.append(
        make_ts("ecs_service_running_count", 4, {"service": svc, "cluster": "production"})
    )
    for i in range(1, 5):
        ts_list.append(
            make_ts(
                "ecs_task_cpu_utilization",
                random.uniform(20, 50),
                {"service": svc, "task": f"task-{i}"},
            )
        )
        ts_list.append(
            make_ts(
                "ecs_task_memory_utilization",
                random.uniform(30, 60),
                {"service": svc, "task": f"task-{i}"},
            )
        )

    return ts_list


def generate_notification_worker() -> list[TimeSeries]:
    """notification-worker: Redis, Kafka, Kubernetes"""
    svc = "notification-worker"
    ts_list = []

    # Notification metrics
    ts_list.append(
        make_ts(
            "notifications_sent_total",
            random.randint(1000, 3000),
            {"service": svc, "status": "delivered"},
        )
    )
    ts_list.append(
        make_ts(
            "notifications_sent_total",
            random.randint(50, 150),
            {"service": svc, "status": "failed"},
        )
    )

    # Kafka
    ts_list.append(
        make_ts(
            "kafka_consumer_lag_seconds",
            random.uniform(0.1, 2.0),
            {"service": svc, "topic": "notifications"},
        )
    )
    ts_list.append(
        make_ts(
            "kafka_consumer_records_per_second",
            random.uniform(500, 900),
            {"service": svc, "topic": "notifications"},
        )
    )
    ts_list.append(make_ts("kafka_topic_partitions", 3, {"service": svc, "topic": "notifications"}))

    # Redis
    ts_list.append(make_ts("redis_connected_clients", random.randint(5, 15), {"service": svc}))
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(50_000_000, 100_000_000), {"service": svc}
        )
    )
    ts_list.append(make_ts("cache_hits_total", random.randint(5000, 10000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(200, 800), {"service": svc}))

    # Kubernetes pods
    for i in range(1, 4):
        pod = f"notification-worker-{i}"
        ts_list.append(
            make_ts("kube_pod_status_phase", 1, {"service": svc, "pod": pod, "phase": "Running"})
        )
        ts_list.append(
            make_ts(
                "container_memory_working_set_bytes",
                random.randint(150_000_000, 300_000_000),
                {"service": svc, "pod": pod, "container": "worker"},
            )
        )

    return ts_list


def generate_analytics_stream() -> list[TimeSeries]:
    """analytics-stream: MongoDB, Redis, Kafka, Kubernetes"""
    svc = "analytics-stream"
    ts_list = []

    # Event metrics
    ts_list.append(
        make_ts(
            "events_processed_total",
            random.randint(2000, 5000),
            {"service": svc, "status": "success"},
        )
    )
    ts_list.append(
        make_ts(
            "events_processed_total", random.randint(40, 100), {"service": svc, "status": "error"}
        )
    )
    ts_list.append(
        make_ts("stream_throughput_events_per_second", random.uniform(500, 1500), {"service": svc})
    )

    # MongoDB
    ts_list.append(
        make_ts("mongodb_connections", random.randint(8, 20), {"service": svc, "state": "current"})
    )
    ts_list.append(
        make_ts(
            "mongodb_operations_total",
            random.randint(5000, 20000),
            {"service": svc, "type": "insert"},
        )
    )
    ts_list.append(
        make_ts(
            "mongodb_operations_total",
            random.randint(10000, 40000),
            {"service": svc, "type": "query"},
        )
    )
    ts_list.append(
        make_ts(
            "mongodb_operations_total",
            random.randint(2000, 10000),
            {"service": svc, "type": "update"},
        )
    )

    # Redis
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(80_000_000, 150_000_000), {"service": svc}
        )
    )
    ts_list.append(make_ts("redis_connected_clients", random.randint(5, 12), {"service": svc}))
    ts_list.append(
        make_ts("redis_db_keys", random.randint(1000, 5000), {"service": svc, "db": "0"})
    )
    ts_list.append(make_ts("cache_hits_total", random.randint(10000, 20000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(500, 1500), {"service": svc}))

    # Kafka
    ts_list.append(
        make_ts(
            "kafka_consumer_lag_seconds",
            random.uniform(0.05, 0.5),
            {"service": svc, "topic": "events"},
        )
    )
    ts_list.append(
        make_ts(
            "kafka_consumer_records_per_second",
            random.uniform(800, 1200),
            {"service": svc, "topic": "events"},
        )
    )
    ts_list.append(make_ts("kafka_topic_partitions", 3, {"service": svc, "topic": "events"}))

    # Kubernetes pods
    for i in range(1, 5):
        pod = f"analytics-stream-{i}"
        ts_list.append(
            make_ts("kube_pod_status_phase", 1, {"service": svc, "pod": pod, "phase": "Running"})
        )
        ts_list.append(
            make_ts(
                "container_memory_working_set_bytes",
                random.randint(300_000_000, 600_000_000),
                {"service": svc, "pod": pod, "container": "stream-processor"},
            )
        )

    return ts_list


def generate_identity_service() -> list[TimeSeries]:
    """identity-service: PostgreSQL, Redis, ECS"""
    svc = "identity-service"
    ts_list = []

    # HTTP metrics
    ts_list.append(make_ts("http_requests_in_flight", random.randint(1, 12), {"service": svc}))
    for endpoint in ["/login", "/register", "/verify"]:
        for status in ["200", "401", "500"]:
            count = random.randint(50, 200) if status == "200" else random.randint(5, 30)
            ts_list.append(
                make_ts(
                    "http_requests_total",
                    count,
                    {"service": svc, "method": "POST", "endpoint": endpoint, "status": status},
                )
            )

    # Auth metrics
    ts_list.append(
        make_ts(
            "login_attempts_total",
            random.randint(1000, 3000),
            {"service": svc, "status": "success"},
        )
    )
    ts_list.append(
        make_ts(
            "login_attempts_total", random.randint(100, 500), {"service": svc, "status": "failed"}
        )
    )
    ts_list.append(make_ts("user_registrations_total", random.randint(0, 30), {"service": svc}))
    ts_list.append(make_ts("password_reset_total", random.randint(0, 20), {"service": svc}))

    # PostgreSQL
    ts_list.append(
        make_ts(
            "pg_stat_database_numbackends",
            random.randint(10, 20),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(make_ts("pg_settings_max_connections", 100, {"service": svc}))
    ts_list.append(
        make_ts(
            "pg_stat_database_blks_hit",
            random.randint(80000, 100000),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_blks_read",
            random.randint(1000, 3000),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_activity_count", random.randint(2, 12), {"service": svc, "state": "active"}
        )
    )
    ts_list.append(
        make_ts("pg_stat_activity_count", random.randint(5, 25), {"service": svc, "state": "idle"})
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_xact_commit",
            random.randint(10000, 100000),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_stat_database_xact_rollback",
            random.randint(10, 200),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(
        make_ts(
            "pg_database_size_bytes",
            random.randint(2_000_000_000, 15_000_000_000),
            {"service": svc, "datname": "identity"},
        )
    )
    ts_list.append(
        make_ts("pg_replication_lag_seconds", random.uniform(0.0, 3.0), {"service": svc})
    )

    # Redis
    ts_list.append(
        make_ts("redis_db_keys", random.randint(1000, 5000), {"service": svc, "db": "0"})
    )
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(80_000_000, 150_000_000), {"service": svc}
        )
    )
    ts_list.append(make_ts("redis_connected_clients", random.randint(10, 25), {"service": svc}))
    ts_list.append(make_ts("cache_hits_total", random.randint(6000, 12000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(300, 1200), {"service": svc}))

    # ECS
    ts_list.append(
        make_ts("ecs_service_running_count", 3, {"service": svc, "cluster": "production"})
    )
    for i in range(1, 4):
        ts_list.append(
            make_ts(
                "ecs_task_cpu_utilization",
                random.uniform(15, 40),
                {"service": svc, "task": f"task-{i}"},
            )
        )

    return ts_list


def generate_search_api() -> list[TimeSeries]:
    """search-api: Elasticsearch, Redis, Kubernetes"""
    svc = "search-api"
    ts_list = []

    # HTTP metrics
    ts_list.append(make_ts("http_requests_in_flight", random.randint(2, 20), {"service": svc}))
    for endpoint in ["/search", "/suggest", "/index"]:
        for status in ["200", "400", "500"]:
            count = random.randint(100, 300) if status == "200" else random.randint(5, 30)
            ts_list.append(
                make_ts(
                    "http_requests_total",
                    count,
                    {"service": svc, "method": "GET", "endpoint": endpoint, "status": status},
                )
            )

    # Elasticsearch
    ts_list.append(
        make_ts(
            "elasticsearch_cluster_health_status", 2, {"service": svc, "cluster": "search-cluster"}
        )
    )
    ts_list.append(
        make_ts(
            "elasticsearch_cluster_health_active_shards",
            random.randint(20, 30),
            {"service": svc, "cluster": "search-cluster"},
        )
    )
    ts_list.append(
        make_ts(
            "elasticsearch_cluster_health_relocating_shards",
            random.randint(0, 2),
            {"service": svc, "cluster": "search-cluster"},
        )
    )

    for index in ["products", "users", "content"]:
        ts_list.append(
            make_ts(
                "elasticsearch_indices_search_query_total",
                random.randint(5000, 20000),
                {"service": svc, "index": index},
            )
        )
        ts_list.append(
            make_ts(
                "elasticsearch_indices_indexing_index_total",
                random.randint(1000, 5000),
                {"service": svc, "index": index},
            )
        )
        ts_list.append(
            make_ts(
                "elasticsearch_indices_store_size_bytes",
                random.randint(500_000_000, 5_000_000_000),
                {"service": svc, "index": index},
            )
        )
        ts_list.append(
            make_ts(
                "elasticsearch_indices_docs",
                random.randint(100_000, 10_000_000),
                {"service": svc, "index": index},
            )
        )

    # Redis
    ts_list.append(
        make_ts(
            "redis_memory_used_bytes", random.randint(100_000_000, 300_000_000), {"service": svc}
        )
    )
    ts_list.append(make_ts("redis_connected_clients", random.randint(10, 30), {"service": svc}))
    ts_list.append(
        make_ts("redis_db_keys", random.randint(50000, 200000), {"service": svc, "db": "0"})
    )
    ts_list.append(make_ts("cache_hits_total", random.randint(20000, 50000), {"service": svc}))
    ts_list.append(make_ts("cache_misses_total", random.randint(2000, 8000), {"service": svc}))

    # Kubernetes pods
    for i in range(1, 4):
        pod = f"search-api-{i}"
        ts_list.append(
            make_ts("kube_pod_status_phase", 1, {"service": svc, "pod": pod, "phase": "Running"})
        )
        ts_list.append(
            make_ts(
                "container_memory_working_set_bytes",
                random.randint(400_000_000, 800_000_000),
                {"service": svc, "pod": pod, "container": "search-api"},
            )
        )

    return ts_list


def push_metrics(url: str, user: str, key: str) -> None:
    """Generate and push all demo metrics to Grafana Cloud."""
    # Generate all metrics
    timeseries: list[TimeSeries] = []
    timeseries.extend(generate_payment_api())
    timeseries.extend(generate_checkout_service())
    timeseries.extend(generate_notification_worker())
    timeseries.extend(generate_analytics_stream())
    timeseries.extend(generate_identity_service())
    timeseries.extend(generate_search_api())

    print(f"Generated {len(timeseries)} time series for 6 demo services")

    # Encode as protobuf
    write_request = encode_write_request(timeseries)

    # Compress with snappy
    compressed = snappy.compress(write_request)
    print(
        f"Payload size: {len(write_request)} bytes -> {len(compressed)} bytes (snappy compressed)"
    )

    # Push to Grafana Cloud
    response = requests.post(
        url,
        data=compressed,
        headers={
            "Content-Type": "application/x-protobuf",
            "Content-Encoding": "snappy",
            "X-Prometheus-Remote-Write-Version": "0.1.0",
        },
        auth=(user, key),
        timeout=30,
    )

    if response.status_code in (200, 204):
        print(f"Successfully pushed metrics to Grafana Cloud (HTTP {response.status_code})")
    else:
        print(f"Failed to push metrics: HTTP {response.status_code}")
        print(f"Response: {response.text}")
        raise SystemExit(1)


def main() -> None:
    """Main entry point."""
    url = os.environ.get("GRAFANA_REMOTE_WRITE_URL")
    user = os.environ.get("GRAFANA_CLOUD_USER")
    key = os.environ.get("GRAFANA_CLOUD_KEY")

    if not all([url, user, key]):
        print("Error: Missing required environment variables:")
        print("  GRAFANA_REMOTE_WRITE_URL - Grafana Cloud remote write endpoint")
        print("  GRAFANA_CLOUD_USER - Grafana Cloud instance ID")
        print("  GRAFANA_CLOUD_KEY - Grafana Cloud API key")
        raise SystemExit(1)

    push_metrics(url, user, key)


if __name__ == "__main__":
    main()
