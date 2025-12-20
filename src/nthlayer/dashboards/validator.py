"""
Dashboard validation logic.

Validates dashboard intents against available metrics from Prometheus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nthlayer.dashboards.intents import ALL_INTENTS, get_intents_for_technology
from nthlayer.dashboards.resolver import ResolutionStatus, create_resolver


@dataclass
class IntentResult:
    """Result of resolving a single intent."""

    name: str
    status: ResolutionStatus
    metric_name: str | None = None
    message: str | None = None
    synthesis_expr: str | None = None


@dataclass
class ValidationResult:
    """Result of validating dashboard intents."""

    resolved: list[IntentResult] = field(default_factory=list)
    fallback: list[IntentResult] = field(default_factory=list)
    unresolved: list[IntentResult] = field(default_factory=list)
    custom: list[IntentResult] = field(default_factory=list)
    synthesized: list[IntentResult] = field(default_factory=list)
    discovery_count: int = 0
    discovery_error: str | None = None

    @property
    def total(self) -> int:
        """Total number of intents validated."""
        return (
            len(self.resolved)
            + len(self.fallback)
            + len(self.unresolved)
            + len(self.custom)
            + len(self.synthesized)
        )

    @property
    def resolved_count(self) -> int:
        """Count of resolved intents (including synthesized)."""
        return len(self.resolved) + len(self.synthesized)

    @property
    def has_unresolved(self) -> bool:
        """Whether any intents failed to resolve."""
        return len(self.unresolved) > 0

    def get_exit_code(self, has_prometheus: bool) -> int:
        """Get exit code based on validation results."""
        if self.has_unresolved and has_prometheus:
            return 2  # Warning - some intents unresolved
        return 0


class DashboardValidator:
    """Validates dashboard intents against available Prometheus metrics."""

    def __init__(self, prometheus_url: str | None = None):
        """Initialize validator.

        Args:
            prometheus_url: Optional Prometheus URL for metric discovery
        """
        self.prometheus_url = prometheus_url

    def validate(
        self,
        service_name: str,
        technologies: set[str],
        custom_overrides: dict[str, Any] | None = None,
        validate_all: bool = False,
    ) -> ValidationResult:
        """Validate dashboard intents for a service.

        Args:
            service_name: Name of the service
            technologies: Set of technologies to validate (postgresql, redis, etc.)
            custom_overrides: Custom metric overrides from service spec
            validate_all: If True, validate all intents regardless of technologies

        Returns:
            ValidationResult with resolved/unresolved intents
        """
        result = ValidationResult()

        # Create resolver
        resolver = create_resolver(
            prometheus_url=self.prometheus_url,
            custom_overrides=custom_overrides or {},
        )

        # Discover metrics if Prometheus URL provided
        if self.prometheus_url:
            try:
                result.discovery_count = resolver.discover_for_service(service_name)
            except (ConnectionError, TimeoutError, ValueError, OSError) as e:
                result.discovery_error = str(e)

        # Collect intents to validate
        intents_to_check = self._get_intents_to_check(technologies, validate_all)

        # Resolve each intent
        for intent_name in sorted(intents_to_check):
            intent_result = self._resolve_intent(resolver, intent_name)
            self._categorize_result(result, intent_result)

        return result

    def _get_intents_to_check(self, technologies: set[str], validate_all: bool) -> list[str]:
        """Get list of intent names to validate."""
        if validate_all:
            return list(ALL_INTENTS.keys())

        intents: list[str] = []
        for tech in technologies:
            tech_intents = get_intents_for_technology(tech)
            intents.extend(tech_intents.keys())
        return intents

    def _resolve_intent(self, resolver: Any, intent_name: str) -> IntentResult:
        """Resolve a single intent."""
        resolution = resolver.resolve(intent_name)
        return IntentResult(
            name=intent_name,
            status=resolution.status,
            metric_name=resolution.metric_name,
            message=resolution.message,
            synthesis_expr=getattr(resolution, "synthesis_expr", None),
        )

    def _categorize_result(self, result: ValidationResult, intent: IntentResult) -> None:
        """Categorize an intent result into the appropriate list."""
        if intent.status == ResolutionStatus.RESOLVED:
            result.resolved.append(intent)
        elif intent.status == ResolutionStatus.CUSTOM:
            result.custom.append(intent)
        elif intent.status == ResolutionStatus.FALLBACK:
            result.fallback.append(intent)
        elif intent.status == ResolutionStatus.SYNTHESIZED:
            result.synthesized.append(intent)
        else:
            result.unresolved.append(intent)


def extract_technologies(context: Any, resources: list[Any]) -> set[str]:
    """Extract technologies from service context and resources.

    Args:
        context: ServiceContext from parsed service file
        resources: List of resources from parsed service file

    Returns:
        Set of technology names (postgresql, redis, http, etc.)
    """
    technologies = set()

    # Extract from Dependencies resources
    dependencies = [r for r in resources if r.kind == "Dependencies"]
    for dep in dependencies:
        spec = dep.spec if hasattr(dep, "spec") else {}
        if not isinstance(spec, dict):
            continue

        databases = spec.get("databases", [])
        caches = spec.get("caches", [])

        for db in databases:
            db_type = db.get("type", "") if isinstance(db, dict) else getattr(db, "type", "")
            if db_type:
                technologies.add(db_type)

        for cache in caches:
            cache_type = (
                cache.get("type", "redis")
                if isinstance(cache, dict)
                else getattr(cache, "type", "redis")
            )
            technologies.add(cache_type)

    # Always include HTTP for API services
    if context.type in ("api", "service", "web"):
        technologies.add("http")

    return technologies


def extract_custom_overrides(resources: list[Any]) -> dict[str, Any]:
    """Extract custom metric overrides from resources.

    Args:
        resources: List of resources from parsed service file

    Returns:
        Dictionary of custom metric overrides
    """
    overrides = {}
    for resource in resources:
        if hasattr(resource, "spec") and isinstance(resource.spec, dict):
            metrics = resource.spec.get("metrics", {})
            if isinstance(metrics, dict):
                overrides.update(metrics)
    return overrides
