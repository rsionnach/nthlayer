"""
Service type metric templates.

Provides pre-defined metric templates based on OpenTelemetry Semantic
Conventions for different service types (api, grpc, worker, etc.).
"""

from nthlayer.metrics.templates.registry import (
    get_template,
    get_template_names,
    resolve_template_metrics,
)

__all__ = ["get_template", "get_template_names", "resolve_template_metrics"]
