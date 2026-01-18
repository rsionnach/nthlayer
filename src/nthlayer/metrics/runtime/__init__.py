"""
Runtime-specific metric templates.

Provides recommended metrics for different language runtimes
(Python, JVM, Go, Node.js) based on OpenTelemetry runtime conventions.
"""

from __future__ import annotations

from nthlayer.metrics.models import MetricDefinition

from .go import GO_METRICS
from .jvm import JVM_METRICS
from .nodejs import NODEJS_METRICS
from .python import PYTHON_METRICS

# Registry mapping runtime names to their metrics
_RUNTIME_METRICS: dict[str, list[MetricDefinition]] = {
    "python": PYTHON_METRICS,
    "jvm": JVM_METRICS,
    "go": GO_METRICS,
    "golang": GO_METRICS,
    "nodejs": NODEJS_METRICS,
    "node": NODEJS_METRICS,
    "javascript": NODEJS_METRICS,
    "typescript": NODEJS_METRICS,
    # JVM language aliases
    "java": JVM_METRICS,
    "kotlin": JVM_METRICS,
    "scala": JVM_METRICS,
    "groovy": JVM_METRICS,
    "clojure": JVM_METRICS,
}


def get_runtime_metrics(runtime: str | None) -> list[MetricDefinition]:
    """
    Get recommended metrics for a runtime/language.

    Args:
        runtime: Runtime or language name (e.g., 'python', 'java', 'go')

    Returns:
        List of MetricDefinition for the runtime, empty list if unknown
    """
    if not runtime:
        return []
    return _RUNTIME_METRICS.get(runtime.lower(), [])


def get_supported_runtimes() -> list[str]:
    """
    Get list of supported runtime names (excluding aliases).

    Returns:
        List of canonical runtime names
    """
    return ["python", "jvm", "go", "nodejs"]


__all__ = ["get_runtime_metrics", "get_supported_runtimes"]
