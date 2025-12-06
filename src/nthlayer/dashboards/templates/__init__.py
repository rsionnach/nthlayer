"""Technology-specific dashboard templates.

Pre-built panel templates for common technologies using the intent-based system.
"""

from typing import Dict, Type

from nthlayer.dashboards.templates.base import TechnologyTemplate
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate

# Intent-based templates (hybrid model) - primary implementation
from nthlayer.dashboards.templates.consul_intent import ConsulIntentTemplate
from nthlayer.dashboards.templates.elasticsearch_intent import ElasticsearchIntentTemplate
from nthlayer.dashboards.templates.etcd_intent import EtcdIntentTemplate
from nthlayer.dashboards.templates.haproxy_intent import HaproxyIntentTemplate
from nthlayer.dashboards.templates.http_intent import HTTPIntentTemplate
from nthlayer.dashboards.templates.kafka_intent import KafkaIntentTemplate
from nthlayer.dashboards.templates.kubernetes import KubernetesTemplate  # No intent version yet
from nthlayer.dashboards.templates.mongodb_intent import MongoDBIntentTemplate
from nthlayer.dashboards.templates.mysql_intent import MySQLIntentTemplate
from nthlayer.dashboards.templates.nats_intent import NatsIntentTemplate
from nthlayer.dashboards.templates.nginx_intent import NginxIntentTemplate
from nthlayer.dashboards.templates.postgresql_intent import PostgreSQLIntentTemplate
from nthlayer.dashboards.templates.pulsar_intent import PulsarIntentTemplate
from nthlayer.dashboards.templates.rabbitmq_intent import RabbitmqIntentTemplate
from nthlayer.dashboards.templates.redis_intent import RedisIntentTemplate
from nthlayer.dashboards.templates.stream_intent import StreamIntentTemplate
from nthlayer.dashboards.templates.traefik_intent import TraefikIntentTemplate
from nthlayer.dashboards.templates.worker_intent import WorkerIntentTemplate

# Aliases for backwards compatibility
PostgreSQLTemplate = PostgreSQLIntentTemplate
RedisTemplate = RedisIntentTemplate
HTTPAPITemplate = HTTPIntentTemplate
MongoDBTemplate = MongoDBIntentTemplate
KafkaTemplate = KafkaIntentTemplate
ElasticsearchTemplate = ElasticsearchIntentTemplate

# Registry of available templates
TECHNOLOGY_TEMPLATES: Dict[str, Type[TechnologyTemplate]] = {
    "postgres": PostgreSQLIntentTemplate,
    "postgresql": PostgreSQLIntentTemplate,
    "mysql": MySQLIntentTemplate,
    "mariadb": MySQLIntentTemplate,
    "redis": RedisIntentTemplate,
    "kubernetes": KubernetesTemplate,
    "k8s": KubernetesTemplate,
    "http": HTTPIntentTemplate,
    "api": HTTPIntentTemplate,
    "mongodb": MongoDBIntentTemplate,
    "mongo": MongoDBIntentTemplate,
    "kafka": KafkaIntentTemplate,
    "elasticsearch": ElasticsearchIntentTemplate,
    "elastic": ElasticsearchIntentTemplate,
    "rabbitmq": RabbitmqIntentTemplate,
    "rabbit": RabbitmqIntentTemplate,
    "nginx": NginxIntentTemplate,
    "nats": NatsIntentTemplate,
    "pulsar": PulsarIntentTemplate,
    "haproxy": HaproxyIntentTemplate,
    "traefik": TraefikIntentTemplate,
    "etcd": EtcdIntentTemplate,
    "consul": ConsulIntentTemplate,
}


def get_template(technology: str) -> TechnologyTemplate:
    """Get template for a technology.

    Args:
        technology: Technology name (postgres, redis, etc.)

    Returns:
        TechnologyTemplate instance

    Raises:
        KeyError: If technology not found
    """
    tech_lower = technology.lower()
    template_class = TECHNOLOGY_TEMPLATES.get(tech_lower)

    if not template_class:
        raise KeyError(f"No template found for technology: {technology}")

    return template_class()


def get_available_technologies() -> list[str]:
    """Get list of technologies with templates.

    Returns:
        List of technology names
    """
    return sorted(set(TECHNOLOGY_TEMPLATES.keys()))


__all__ = [
    # Base classes
    "TechnologyTemplate",
    "IntentBasedTemplate",
    # Intent-based templates (primary implementation)
    "HTTPIntentTemplate",
    "WorkerIntentTemplate",
    "StreamIntentTemplate",
    "PostgreSQLIntentTemplate",
    "RedisIntentTemplate",
    "MySQLIntentTemplate",
    "MongoDBIntentTemplate",
    "KafkaIntentTemplate",
    "ElasticsearchIntentTemplate",
    "RabbitmqIntentTemplate",
    "NginxIntentTemplate",
    "NatsIntentTemplate",
    "PulsarIntentTemplate",
    "HaproxyIntentTemplate",
    "TraefikIntentTemplate",
    "EtcdIntentTemplate",
    "ConsulIntentTemplate",
    "KubernetesTemplate",  # No intent version yet
    # Backwards compatibility aliases
    "PostgreSQLTemplate",
    "RedisTemplate",
    "HTTPAPITemplate",
    "MongoDBTemplate",
    "KafkaTemplate",
    "ElasticsearchTemplate",
    # Functions
    "get_template",
    "get_available_technologies",
]
