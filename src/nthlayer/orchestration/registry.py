"""Resource handler protocol and registry for orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class OrchestratorContext:
    """Shared context passed to all resource handlers."""

    service_yaml: Path
    service_def: Dict[str, Any]
    service_name: str
    output_dir: Path
    env: Optional[str]
    detector: Any  # ResourceDetector — Any to avoid circular import at runtime
    prometheus_url: Optional[str] = None
    push_to_grafana: bool = False


@runtime_checkable
class ResourceHandler(Protocol):
    """Protocol for resource handlers that can plan and generate."""

    @property
    def name(self) -> str:
        """Resource type identifier (e.g. 'slos', 'alerts')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for log messages."""
        ...

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        """Return a preview of what would be generated."""
        ...

    def generate(self, ctx: OrchestratorContext) -> int:
        """Generate resources, return count of items created."""
        ...


class ResourceRegistry:
    """In-memory registry for resource handlers."""

    def __init__(self) -> None:
        self._handlers: Dict[str, ResourceHandler] = {}

    def register(self, handler: ResourceHandler) -> None:
        """Register a handler by its name."""
        self._handlers[handler.name] = handler

    def get(self, name: str) -> Optional[ResourceHandler]:
        """Get a handler by resource type name."""
        return self._handlers.get(name)

    def list(self) -> List[str]:
        """List all registered handler names."""
        return list(self._handlers.keys())
