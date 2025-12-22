"""
Exporter guidance for missing metrics.

Provides helpful suggestions when verify detects missing exporter metrics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExporterInfo:
    """Information about a Prometheus exporter."""

    name: str
    helm_chart: str
    helm_repo: str
    docs_url: str
    metric_prefixes: tuple[str, ...]
    mixin_url: str | None = None


# Known exporters and their metric prefixes
EXPORTERS: dict[str, ExporterInfo] = {
    "postgresql": ExporterInfo(
        name="PostgreSQL Exporter",
        helm_chart="prometheus-postgres-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/prometheus-community/postgres_exporter",
        metric_prefixes=("pg_", "postgres_"),
        mixin_url="https://monitoring.mixins.dev/postgres-exporter/",
    ),
    "redis": ExporterInfo(
        name="Redis Exporter",
        helm_chart="prometheus-redis-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/oliver006/redis_exporter",
        metric_prefixes=("redis_",),
        mixin_url="https://monitoring.mixins.dev/redis/",
    ),
    "elasticsearch": ExporterInfo(
        name="Elasticsearch Exporter",
        helm_chart="prometheus-elasticsearch-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/prometheus-community/elasticsearch_exporter",
        metric_prefixes=("elasticsearch_", "es_"),
        mixin_url="https://monitoring.mixins.dev/elasticsearch/",
    ),
    "mongodb": ExporterInfo(
        name="MongoDB Exporter",
        helm_chart="prometheus-mongodb-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/percona/mongodb_exporter",
        metric_prefixes=("mongodb_", "mongo_"),
        mixin_url="https://monitoring.mixins.dev/mongodb/",
    ),
    "mysql": ExporterInfo(
        name="MySQL Exporter",
        helm_chart="prometheus-mysql-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/prometheus/mysqld_exporter",
        metric_prefixes=("mysql_", "mysqld_"),
        mixin_url="https://monitoring.mixins.dev/mysql/",
    ),
    "kafka": ExporterInfo(
        name="Kafka Exporter",
        helm_chart="prometheus-kafka-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/danielqsj/kafka-exporter",
        metric_prefixes=("kafka_",),
        mixin_url="https://monitoring.mixins.dev/kafka/",
    ),
    "rabbitmq": ExporterInfo(
        name="RabbitMQ Exporter",
        helm_chart="prometheus-rabbitmq-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/kbudde/rabbitmq_exporter",
        metric_prefixes=("rabbitmq_",),
        mixin_url="https://monitoring.mixins.dev/rabbitmq/",
    ),
    "nginx": ExporterInfo(
        name="NGINX Exporter",
        helm_chart="prometheus-nginx-exporter",
        helm_repo="prometheus-community",
        docs_url="https://github.com/nginxinc/nginx-prometheus-exporter",
        metric_prefixes=("nginx_", "nginxexporter_"),
        mixin_url="https://monitoring.mixins.dev/nginx/",
    ),
}


def detect_missing_exporters(missing_metric_names: list[str]) -> dict[str, list[str]]:
    """
    Detect which exporters might be missing based on metric prefixes.

    Args:
        missing_metric_names: List of metric names that are missing

    Returns:
        Dict mapping exporter type to list of missing metrics for that exporter
    """
    missing_by_exporter: dict[str, list[str]] = {}

    for metric_name in missing_metric_names:
        metric_lower = metric_name.lower()
        for exporter_type, info in EXPORTERS.items():
            if any(metric_lower.startswith(prefix) for prefix in info.metric_prefixes):
                if exporter_type not in missing_by_exporter:
                    missing_by_exporter[exporter_type] = []
                missing_by_exporter[exporter_type].append(metric_name)
                break

    return missing_by_exporter


def get_exporter_guidance(exporter_type: str) -> list[str]:
    """
    Get guidance for installing a specific exporter.

    Args:
        exporter_type: Type of exporter (postgresql, redis, etc.)

    Returns:
        List of guidance strings
    """
    info = EXPORTERS.get(exporter_type)
    if not info:
        return []

    return [
        f"Install {info.name}:",
        f"  helm repo add {info.helm_repo} https://prometheus-community.github.io/helm-charts",
        f"  helm install {exporter_type}-exporter {info.helm_repo}/{info.helm_chart}",
        f"  Docs: {info.docs_url}",
    ]


def format_exporter_guidance(missing_by_exporter: dict[str, list[str]]) -> list[str]:
    """
    Format guidance for all missing exporters.

    Args:
        missing_by_exporter: Dict from detect_missing_exporters()

    Returns:
        List of formatted guidance lines
    """
    if not missing_by_exporter:
        return []

    lines = ["[bold]Missing Exporters Detected:[/bold]", ""]

    for exporter_type, metrics in missing_by_exporter.items():
        info = EXPORTERS.get(exporter_type)
        if not info:
            continue

        lines.append(f"[cyan]{info.name}[/cyan] ({len(metrics)} metrics)")
        lines.append(f"  [muted]Missing:[/muted] {', '.join(metrics[:3])}")
        if len(metrics) > 3:
            lines.append(f"           ... and {len(metrics) - 3} more")
        lines.append("")
        lines.append(
            f"  [green]helm repo add[/green] {info.helm_repo} https://prometheus-community.github.io/helm-charts"
        )
        lines.append(
            f"  [green]helm install[/green] {exporter_type}-exporter {info.helm_repo}/{info.helm_chart}"
        )
        lines.append(f"  [muted]Docs:[/muted] {info.docs_url}")
        if info.mixin_url:
            lines.append(f"  [muted]Mixin:[/muted] {info.mixin_url}")
        lines.append("")

    return lines
