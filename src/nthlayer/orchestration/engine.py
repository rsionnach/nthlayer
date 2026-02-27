"""Execution engine for resource generation."""

from typing import List

from nthlayer.orchestration.registry import OrchestratorContext, ResourceRegistry
from nthlayer.orchestration.results import ResultCollector


class ExecutionEngine:
    """Runs generation loop over registered handlers."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        ctx: OrchestratorContext,
        resource_types: List[str],
        verbose: bool = False,
    ) -> ResultCollector:
        """Execute generation for each resource type, collecting results."""
        collector = ResultCollector(
            service_name=ctx.service_name,
            output_dir=ctx.output_dir,
        )
        total_steps = len(resource_types)

        for step, rtype in enumerate(resource_types, 1):
            handler = self._registry.get(rtype)
            if handler is None:
                continue

            if verbose:
                print(f"[{step}/{total_steps}] Generating {handler.display_name}...")

            try:
                count = handler.generate(ctx)
                collector.record(rtype, count)
                if verbose:
                    _log_success(rtype, count, handler.display_name, ctx.push_to_grafana)
            except Exception as e:
                collector.record_error(handler.display_name, e)

        return collector


def _log_success(resource_type: str, count: int, display_name: str, push_to_grafana: bool) -> None:
    """Log success message for a generated resource."""
    if resource_type == "dashboard":
        if push_to_grafana:
            print("✅ Dashboard created and pushed to Grafana")
        else:
            print("✅ Dashboard created")
    elif resource_type == "pagerduty":
        print("✅ PagerDuty service created")
    else:
        print(f"✅ {count} {display_name} created")
