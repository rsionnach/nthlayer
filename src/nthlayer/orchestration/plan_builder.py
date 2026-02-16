"""Unified plan builder using resource handler registry."""

from typing import List

from nthlayer.orchestration.registry import OrchestratorContext, ResourceRegistry
from nthlayer.orchestration.results import PlanResult


class PlanBuilder:
    """Builds a plan by delegating to registered handlers."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry

    def build(self, ctx: OrchestratorContext, resource_types: List[str]) -> PlanResult:
        """Build a plan for detected resource types."""
        result = PlanResult(service_name=ctx.service_name, service_yaml=ctx.service_yaml)

        if not resource_types:
            result.warnings.append(
                "No resources detected. Service YAML may be missing SLO, "
                "Dependencies, Observability, or PagerDuty resources."
            )

        try:
            for rtype in resource_types:
                handler = self._registry.get(rtype)
                if handler is not None:
                    result.resources[rtype] = handler.plan(ctx)
        except Exception as e:
            result.errors.append(f"Planning failed: {e}")

        return result
