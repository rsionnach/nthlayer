"""Service orchestrator for unified apply workflow.

Coordinates generation of all resources (SLOs, alerts, dashboards, etc.)
from a single service definition file.

This module is a facade — all logic lives in nthlayer.orchestration.
Imports are preserved for backward compatibility.
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nthlayer.core.errors import ConfigurationError
from nthlayer.orchestration.engine import ExecutionEngine
from nthlayer.orchestration.handlers import register_default_handlers
from nthlayer.orchestration.plan_builder import PlanBuilder
from nthlayer.orchestration.registry import OrchestratorContext, ResourceRegistry
from nthlayer.orchestration.results import ApplyResult, PlanResult

# Re-export for backward compatibility
__all__ = ["ApplyResult", "PlanResult", "ResourceDetector", "ServiceOrchestrator"]


class ResourceDetector:
    """Detects what resources should be generated from a service definition.

    Uses single-pass indexing to avoid redundant list scans.
    """

    def __init__(self, service_def: Dict[str, Any]):
        self.service_def = service_def
        self._resource_index: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def _build_index(self) -> Dict[str, List[Dict[str, Any]]]:
        """Build single-pass resource index by kind.

        Indexes all resources in one O(N) pass instead of scanning
        multiple times for each resource type check.
        """
        if self._resource_index is not None:
            return self._resource_index

        index: Dict[str, List[Dict[str, Any]]] = {
            "SLO": [],
            "Dependencies": [],
            "Observability": [],
            "PagerDuty": [],
        }

        for resource in self.service_def.get("resources", []):
            kind = resource.get("kind", "")
            if kind in index:
                index[kind].append(resource)

        self._resource_index = index
        return index

    def detect(self) -> List[str]:
        """Returns list of resource types to generate."""
        index = self._build_index()
        resources = []

        # Always generate SLOs if defined
        if index["SLO"]:
            resources.append("slos")
            # Auto-add recording rules if SLOs exist
            resources.append("recording-rules")
            # Auto-add Backstage entity if SLOs exist
            resources.append("backstage")

        # Auto-generate alerts if dependencies defined
        if self._has_dependencies(index):
            resources.append("alerts")

        # Auto-generate dashboard if observability config or dependencies
        if index["Observability"] or self._has_dependencies(index):
            resources.append("dashboard")

        # Generate PagerDuty if resource defined
        if index["PagerDuty"]:
            resources.append("pagerduty")

        return resources

    def _has_dependencies(self, index: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Check if service has dependencies (for alert generation)."""
        deps_resources = index["Dependencies"]
        if not deps_resources:
            return False

        # Check first Dependencies resource for actual dependency content
        spec = deps_resources[0].get("spec", {})
        return bool(spec.get("databases") or spec.get("services") or spec.get("external_apis"))

    def get_resources_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        """Get all resources of a specific kind (cached)."""
        index = self._build_index()
        return index.get(kind, [])


class ServiceOrchestrator:
    """Orchestrates generation of all resources for a service.

    Thin facade that delegates to orchestration components.
    """

    def __init__(
        self,
        service_yaml: Path,
        env: Optional[str] = None,
        push_to_grafana: bool = False,
        prometheus_url: Optional[str] = None,
    ):
        self.service_yaml = service_yaml
        self.env = env
        self.push_to_grafana = push_to_grafana
        self.prometheus_url = prometheus_url
        self.service_def: Optional[Dict[str, Any]] = None
        self.service_name: Optional[str] = None
        self.output_dir: Optional[Path] = None
        self._detector: Optional[ResourceDetector] = None
        self._registry = ResourceRegistry()
        register_default_handlers(self._registry)

    def _load_service(self) -> None:
        """Load and parse service YAML file."""
        if self.service_def is not None:
            return  # Already loaded

        with open(self.service_yaml, "r") as f:
            self.service_def = yaml.safe_load(f)

        # Get service name
        service_section = self.service_def.get("service", {})
        self.service_name = service_section.get("name") or self.service_yaml.stem

        # Set default output directory
        if self.output_dir is None:
            self.output_dir = Path("generated") / self.service_name

    def _get_detector(self) -> ResourceDetector:
        """Get cached resource detector, creating if needed."""
        if self._detector is None:
            self._detector = ResourceDetector(self.service_def or {})
        return self._detector

    def _build_context(self) -> OrchestratorContext:
        """Build the shared context for handlers."""
        if self.service_name is None or self.service_def is None or self.output_dir is None:
            raise ConfigurationError("service must be loaded before building context")
        return OrchestratorContext(
            service_yaml=self.service_yaml,
            service_def=self.service_def,
            service_name=self.service_name,
            output_dir=self.output_dir,
            env=self.env,
            detector=self._get_detector(),
            prometheus_url=self.prometheus_url,
            push_to_grafana=self.push_to_grafana,
        )

    def plan(self) -> PlanResult:
        """Preview what resources would be generated (dry-run)."""
        try:
            self._load_service()
        except Exception as e:
            return PlanResult(
                service_name=self.service_yaml.stem,
                service_yaml=self.service_yaml,
                errors=[f"Failed to load service: {e}"],
            )

        if self.service_name is None or self.service_def is None:
            raise ConfigurationError("service must be loaded before planning")

        # Ensure output_dir is set for context building
        if self.output_dir is None:
            self.output_dir = Path("generated") / self.service_name

        resource_types = self._get_detector().detect()
        ctx = self._build_context()
        builder = PlanBuilder(self._registry)
        return builder.build(ctx, resource_types)

    def apply(
        self,
        skip: Optional[List[str]] = None,
        only: Optional[List[str]] = None,
        force: bool = False,
        verbose: bool = False,
    ) -> ApplyResult:
        """Generate all resources for the service."""
        start = time.time()

        try:
            self._load_service()
        except Exception as e:
            return ApplyResult(
                service_name=self.service_yaml.stem, errors=[f"Failed to load service: {e}"]
            )

        assert self.service_name is not None
        assert self.service_def is not None
        assert self.output_dir is not None

        # Create output directory and verify writability
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.output_dir / ".nthlayer_write_test"
            test_file.touch()
            test_file.unlink()
        except OSError as e:
            return ApplyResult(
                service_name=self.service_name,
                output_dir=self.output_dir,
                errors=[f"Output directory not writable: {e}"],
            )

        resource_types = self._get_filtered_resources(skip, only)
        ctx = self._build_context()
        engine = ExecutionEngine(self._registry)
        collector = engine.execute(ctx, resource_types, verbose=verbose)
        return collector.finalize(time.time() - start)

    def _get_filtered_resources(
        self, skip: Optional[List[str]], only: Optional[List[str]]
    ) -> List[str]:
        """Detect and filter resource types to generate (uses cached detector)."""
        resource_types = self._get_detector().detect()

        if only:
            resource_types = [r for r in resource_types if r in only]
        if skip:
            resource_types = [r for r in resource_types if r not in skip]

        return resource_types
