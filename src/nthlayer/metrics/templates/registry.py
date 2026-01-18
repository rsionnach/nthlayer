"""
Template registry for service type metric templates.

Provides lookup and resolution of metric templates by service type,
including inheritance resolution for templates that extend others.
"""

from __future__ import annotations

from nthlayer.metrics.models import MetricDefinition, ServiceTypeTemplate

from .api import API_TEMPLATE
from .cache import CACHE_TEMPLATE
from .database_client import DATABASE_CLIENT_TEMPLATE
from .gateway import GATEWAY_TEMPLATE
from .grpc import GRPC_TEMPLATE
from .queue_consumer import QUEUE_CONSUMER_TEMPLATE
from .worker import WORKER_TEMPLATE

# Registry of all service type templates
_TEMPLATES: dict[str, ServiceTypeTemplate] = {
    "api": API_TEMPLATE,
    "grpc": GRPC_TEMPLATE,
    "worker": WORKER_TEMPLATE,
    "queue-consumer": QUEUE_CONSUMER_TEMPLATE,
    "database-client": DATABASE_CLIENT_TEMPLATE,
    "gateway": GATEWAY_TEMPLATE,
    "cache": CACHE_TEMPLATE,
    # Aliases for common alternative names
    "web": API_TEMPLATE,
    "http": API_TEMPLATE,
    "rest": API_TEMPLATE,
    "background-job": WORKER_TEMPLATE,
    "job": WORKER_TEMPLATE,
    "consumer": QUEUE_CONSUMER_TEMPLATE,
    "queue": QUEUE_CONSUMER_TEMPLATE,
    "db": DATABASE_CLIENT_TEMPLATE,
    "database": DATABASE_CLIENT_TEMPLATE,
    "proxy": GATEWAY_TEMPLATE,
    "lb": GATEWAY_TEMPLATE,
    "redis": CACHE_TEMPLATE,
    "memcached": CACHE_TEMPLATE,
}


def get_template(service_type: str) -> ServiceTypeTemplate | None:
    """
    Get the metric template for a service type.

    Args:
        service_type: Service type name (e.g., 'api', 'worker')

    Returns:
        ServiceTypeTemplate if found, None otherwise
    """
    return _TEMPLATES.get(service_type.lower())


def get_template_names() -> list[str]:
    """
    Get all registered template names (excluding aliases).

    Returns:
        List of unique template names
    """
    seen = set()
    names = []
    for template in _TEMPLATES.values():
        if template.name not in seen:
            names.append(template.name)
            seen.add(template.name)
    return sorted(names)


def resolve_template_metrics(
    template: ServiceTypeTemplate,
    level: str = "required",
) -> list[MetricDefinition]:
    """
    Resolve all metrics for a template, including inherited metrics.

    Handles template inheritance (e.g., gateway extends api).

    Args:
        template: The service type template
        level: Which metrics to include ('required', 'recommended', or 'all')

    Returns:
        List of MetricDefinition including inherited metrics
    """
    metrics: list[MetricDefinition] = []

    # First resolve parent template if this extends another
    if template.extends:
        parent = get_template(template.extends)
        if parent:
            metrics.extend(resolve_template_metrics(parent, level))

    # Add this template's metrics
    if level in ("required", "all"):
        metrics.extend(template.required)
    if level in ("recommended", "all"):
        metrics.extend(template.recommended)

    # Deduplicate by metric name (child overrides parent)
    seen_names: set[str] = set()
    unique_metrics: list[MetricDefinition] = []
    for metric in reversed(metrics):  # Process in reverse to keep child overrides
        if metric.name not in seen_names:
            unique_metrics.append(metric)
            seen_names.add(metric.name)

    return list(reversed(unique_metrics))  # Restore original order
