"""Technology-specific dashboard templates.

Pre-built panel templates for common technologies.
"""

from typing import Dict, Type
from nthlayer.dashboards.templates.base import TechnologyTemplate
from nthlayer.dashboards.templates.postgresql import PostgreSQLTemplate
from nthlayer.dashboards.templates.redis import RedisTemplate
from nthlayer.dashboards.templates.kubernetes import KubernetesTemplate
from nthlayer.dashboards.templates.http_api import HTTPAPITemplate


# Registry of available templates
TECHNOLOGY_TEMPLATES: Dict[str, Type[TechnologyTemplate]] = {
    "postgres": PostgreSQLTemplate,
    "postgresql": PostgreSQLTemplate,
    "redis": RedisTemplate,
    "kubernetes": KubernetesTemplate,
    "k8s": KubernetesTemplate,
    "http": HTTPAPITemplate,
    "api": HTTPAPITemplate,
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
    "TechnologyTemplate",
    "PostgreSQLTemplate",
    "RedisTemplate",
    "KubernetesTemplate",
    "HTTPAPITemplate",
    "get_template",
    "get_available_technologies",
]
