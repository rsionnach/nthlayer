"""Shared helpers for working with ReliabilityManifest.

Provides utility functions used across multiple generators.
"""

from __future__ import annotations

import structlog

from nthlayer.specs.manifest import ReliabilityManifest

logger = structlog.get_logger()

# Shared technology keywords for name-based inference
TECH_KEYWORDS: dict[str, str] = {
    "redis": "redis",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "mongo": "mongodb",
    "mongodb": "mongodb",
    "kafka": "kafka",
    "rabbit": "rabbitmq",
    "rabbitmq": "rabbitmq",
    "nginx": "nginx",
    "haproxy": "haproxy",
    "elasticsearch": "elasticsearch",
    "elastic": "elasticsearch",
    "memcache": "memcached",
    "memcached": "memcached",
    "sqs": "sqs",
}


def infer_technology_from_name(name: str) -> str | None:
    """Infer technology from a service/dependency name using keyword matching."""
    name_lower = name.lower()
    for keyword, tech in TECH_KEYWORDS.items():
        if keyword in name_lower:
            return tech
    return None


def extract_dependency_technologies(manifest: ReliabilityManifest) -> list[str]:
    """Extract technology names from manifest dependencies.

    Consolidates dependency extraction logic previously duplicated in
    generators/alerts.py and loki/generator.py.

    Args:
        manifest: ReliabilityManifest instance

    Returns:
        Deduplicated list of technology names (e.g., ["postgresql", "redis"])
    """
    technologies = []

    for dep in manifest.dependencies:
        if dep.type == "database" and dep.database_type:
            technologies.append(dep.database_type.lower())
        elif dep.type == "cache":
            # Use name-based inference for cache type
            name_lower = dep.name.lower()
            if "redis" in name_lower:
                technologies.append("redis")
            elif "memcache" in name_lower or "memcached" in name_lower:
                technologies.append("memcached")
            else:
                logger.warning(
                    "Could not infer cache technology for dependency '%s', "
                    "defaulting to redis. Set database_type explicitly.",
                    dep.name,
                )
                technologies.append("redis")
        elif dep.type == "queue":
            name_lower = dep.name.lower()
            if "kafka" in name_lower:
                technologies.append("kafka")
            elif "rabbit" in name_lower:
                technologies.append("rabbitmq")
            elif "sqs" in name_lower:
                technologies.append("sqs")
            else:
                logger.warning(
                    "Could not infer queue technology for dependency '%s', "
                    "defaulting to kafka. Set database_type explicitly.",
                    dep.name,
                )
                technologies.append("kafka")
        elif dep.type == "api":
            # API dependencies don't map to a technology for alert templates
            pass

    return list(set(technologies))
