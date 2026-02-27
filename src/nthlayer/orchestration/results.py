"""Result types for service orchestration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ApplyResult:
    """Result of applying a service configuration."""

    service_name: str
    resources_created: Dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    output_dir: Path = Path(".")
    errors: List[str] = field(default_factory=list)

    @property
    def total_resources(self) -> int:
        """Total number of resources created."""
        return sum(self.resources_created.values())

    @property
    def success(self) -> bool:
        """Whether apply succeeded without errors."""
        return len(self.errors) == 0


@dataclass
class PlanResult:
    """Result of planning (dry-run) a service configuration."""

    service_name: str
    service_yaml: Path
    resources: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def total_resources(self) -> int:
        """Total number of resources that would be created."""
        return sum(len(items) for items in self.resources.values())

    @property
    def success(self) -> bool:
        """Whether plan succeeded without errors."""
        return len(self.errors) == 0


class ResultCollector:
    """Aggregates resource generation results during execution."""

    def __init__(self, service_name: str, output_dir: Path) -> None:
        self._result = ApplyResult(service_name=service_name, output_dir=output_dir)

    def record(self, resource_type: str, count: int) -> None:
        """Record a successful resource generation."""
        self._result.resources_created[resource_type] = count

    def record_error(self, display_name: str, error: Exception) -> None:
        """Record a generation failure."""
        self._result.errors.append(f"{display_name.capitalize()} generation failed: {error}")

    def finalize(self, duration: float) -> ApplyResult:
        """Return the final result with duration set."""
        self._result.duration_seconds = duration
        return self._result
