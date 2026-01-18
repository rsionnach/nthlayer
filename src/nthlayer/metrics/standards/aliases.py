"""
Metric name aliasing from common Prometheus names to OTel Semantic Conventions.

Maps framework-specific and legacy metric names to their canonical
OpenTelemetry equivalents for matching during discovery.
"""

from __future__ import annotations

# Maps common Prometheus metric names to OTel Semantic Convention names
METRIC_ALIASES: dict[str, str] = {
    # =========================================================================
    # HTTP Server Metrics → http.server.request.duration
    # =========================================================================
    # Generic Prometheus
    "http_requests_total": "http.server.request.duration",
    "http_request_duration_seconds": "http.server.request.duration",
    "http_request_duration_seconds_bucket": "http.server.request.duration",
    "http_request_duration_seconds_count": "http.server.request.duration",
    "http_request_duration_seconds_sum": "http.server.request.duration",
    "http_request_latency_seconds": "http.server.request.duration",
    "request_latency_seconds": "http.server.request.duration",
    "request_duration_seconds": "http.server.request.duration",
    # Python frameworks
    "flask_http_request_duration_seconds": "http.server.request.duration",
    "fastapi_requests_total": "http.server.request.duration",
    "starlette_requests_total": "http.server.request.duration",
    "django_http_requests_total": "http.server.request.duration",
    # Java/JVM frameworks
    "spring_http_server_requests_seconds": "http.server.request.duration",
    "http_server_requests_seconds": "http.server.request.duration",
    "jetty_requests_seconds": "http.server.request.duration",
    # Node.js frameworks
    "express_http_request_duration_seconds": "http.server.request.duration",
    "nodejs_http_request_duration_seconds": "http.server.request.duration",
    "nestjs_http_request_duration_seconds": "http.server.request.duration",
    # Go frameworks
    "gin_request_duration_seconds": "http.server.request.duration",
    "echo_request_duration_seconds": "http.server.request.duration",
    "chi_request_duration_seconds": "http.server.request.duration",
    # =========================================================================
    # HTTP Client Metrics → http.client.request.duration
    # =========================================================================
    "http_client_requests_total": "http.client.request.duration",
    "http_client_request_duration_seconds": "http.client.request.duration",
    "outbound_http_request_duration_seconds": "http.client.request.duration",
    # =========================================================================
    # gRPC Server Metrics → rpc.server.duration
    # =========================================================================
    "grpc_server_handled_total": "rpc.server.duration",
    "grpc_server_handling_seconds": "rpc.server.duration",
    "grpc_server_msg_received_total": "rpc.server.duration",
    "grpc_server_msg_sent_total": "rpc.server.duration",
    "grpc_server_started_total": "rpc.server.duration",
    # =========================================================================
    # gRPC Client Metrics → rpc.client.duration
    # =========================================================================
    "grpc_client_handled_total": "rpc.client.duration",
    "grpc_client_handling_seconds": "rpc.client.duration",
    "grpc_client_started_total": "rpc.client.duration",
    # =========================================================================
    # Database Metrics → db.client.operation.duration
    # =========================================================================
    "sql_client_duration_seconds": "db.client.operation.duration",
    "db_query_duration_seconds": "db.client.operation.duration",
    # Connection pool metrics → db.client.connections.usage (OTel official)
    "db_client_connections_usage": "db.client.connections.usage",
    "db_client_connections": "db.client.connections.usage",
    "hikaricp_connections": "db.client.connections.usage",
    "hikaricp_connections_active": "db.client.connections.usage",
    "pg_stat_activity_count": "db.client.connections.usage",
    # =========================================================================
    # Messaging/Queue Metrics → messaging.receive.duration
    # =========================================================================
    "kafka_consumer_fetch_latency_avg": "messaging.receive.duration",
    "kafka_consumer_records_consumed_total": "messaging.receive.messages",
    "kafka_consumer_fetch_manager_fetch_latency_avg": "messaging.receive.duration",
    "rabbitmq_message_process_duration": "messaging.receive.duration",
    "rabbitmq_messages_received_total": "messaging.receive.messages",
    "sqs_message_receive_duration_seconds": "messaging.receive.duration",
    "sqs_messages_received_total": "messaging.receive.messages",
    # =========================================================================
    # Cache Metrics → cache.operation.duration
    # =========================================================================
    "redis_command_duration_seconds": "cache.operation.duration",
    "redis_commands_total": "cache.operation.duration",
    "memcached_command_duration_seconds": "cache.operation.duration",
    "cache_hits_total": "cache.hit_ratio",
    "cache_misses_total": "cache.hit_ratio",
    # =========================================================================
    # Worker/Job Metrics → jobs.duration
    # =========================================================================
    "celery_task_runtime_seconds": "jobs.duration",
    "celery_tasks_total": "jobs.total",
    "sidekiq_job_duration_seconds": "jobs.duration",
    "sidekiq_jobs_total": "jobs.total",
    "rq_job_duration_seconds": "jobs.duration",
    "job_duration_seconds": "jobs.duration",
    "background_job_duration_seconds": "jobs.duration",
}

# Reverse mapping: OTel canonical → list of aliases
_REVERSE_ALIASES: dict[str, list[str]] = {}


def _build_reverse_aliases() -> None:
    """Build reverse mapping on first use."""
    if _REVERSE_ALIASES:
        return
    for alias, canonical in METRIC_ALIASES.items():
        if canonical not in _REVERSE_ALIASES:
            _REVERSE_ALIASES[canonical] = []
        _REVERSE_ALIASES[canonical].append(alias)


def get_canonical_name(metric_name: str) -> str | None:
    """
    Get the OTel canonical name for a metric.

    Args:
        metric_name: Prometheus metric name to look up

    Returns:
        OTel canonical name if aliased, None otherwise
    """
    return METRIC_ALIASES.get(metric_name)


def get_aliases_for_canonical(canonical_name: str) -> list[str]:
    """
    Get all known aliases for an OTel canonical metric name.

    Args:
        canonical_name: OTel semantic convention metric name

    Returns:
        List of known Prometheus aliases for this metric
    """
    _build_reverse_aliases()
    return _REVERSE_ALIASES.get(canonical_name, [])
