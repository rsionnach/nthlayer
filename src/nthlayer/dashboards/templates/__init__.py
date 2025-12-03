"""Technology-specific dashboard templates.

Pre-built panel templates for common technologies.
Includes both legacy templates and intent-based templates for the hybrid model.
"""

from typing import Dict, Type

from nthlayer.dashboards.templates.base import TechnologyTemplate

# Intent-based templates (hybrid model)
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate
from nthlayer.dashboards.templates.elasticsearch import ElasticsearchTemplate
from nthlayer.dashboards.templates.elasticsearch_intent import ElasticsearchIntentTemplate
from nthlayer.dashboards.templates.http_api import HTTPAPITemplate
from nthlayer.dashboards.templates.http_intent import HTTPIntentTemplate
from nthlayer.dashboards.templates.kafka import KafkaTemplate
from nthlayer.dashboards.templates.kafka_intent import KafkaIntentTemplate
from nthlayer.dashboards.templates.kubernetes import KubernetesTemplate
from nthlayer.dashboards.templates.mongodb import MongoDBTemplate
from nthlayer.dashboards.templates.mongodb_intent import MongoDBIntentTemplate
from nthlayer.dashboards.templates.mysql_intent import MySQLIntentTemplate
from nthlayer.dashboards.templates.postgresql import PostgreSQLTemplate
from nthlayer.dashboards.templates.postgresql_intent import PostgreSQLIntentTemplate
from nthlayer.dashboards.templates.redis import RedisTemplate
from nthlayer.dashboards.templates.redis_intent import RedisIntentTemplate
from nthlayer.dashboards.templates.stream_intent import StreamIntentTemplate
from nthlayer.dashboards.templates.worker_intent import WorkerIntentTemplate

# Registry of available templates
TECHNOLOGY_TEMPLATES: Dict[str, Type[TechnologyTemplate]] = {
    "postgres": PostgreSQLTemplate,
    "postgresql": PostgreSQLTemplate,
    "redis": RedisTemplate,
    "kubernetes": KubernetesTemplate,
    "k8s": KubernetesTemplate,
    "http": HTTPAPITemplate,
    "api": HTTPAPITemplate,
    "mongodb": MongoDBTemplate,
    "mongo": MongoDBTemplate,
    "kafka": KafkaTemplate,
    "elasticsearch": ElasticsearchTemplate,
    "elastic": ElasticsearchTemplate,
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
    # Legacy templates
    "PostgreSQLTemplate",
    "RedisTemplate",
    "KubernetesTemplate",
    "HTTPAPITemplate",
    "MongoDBTemplate",
    "KafkaTemplate",
    "ElasticsearchTemplate",
    # Intent-based templates (hybrid model)
    "HTTPIntentTemplate",
    "WorkerIntentTemplate",
    "StreamIntentTemplate",
    "PostgreSQLIntentTemplate",
    "RedisIntentTemplate",
    "MySQLIntentTemplate",
    "MongoDBIntentTemplate",
    "KafkaIntentTemplate",
    "ElasticsearchIntentTemplate",
    # Functions
    "get_template",
    "get_available_technologies",
]
