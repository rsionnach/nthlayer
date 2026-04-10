"""
Re-export shim — canonical source is nthlayer_common.slo_models.

This shim maintains backward compatibility during the ecosystem migration.
All consumers within nthlayer can continue to import from nthlayer.slos.models.
"""

from nthlayer_common.slo_models import (  # noqa: F401
    SLO,
    ErrorBudget,
    Incident,
    SLOStatus,
    TimeWindow,
    TimeWindowType,
)

__all__ = [
    "SLO",
    "ErrorBudget",
    "SLOStatus",
    "TimeWindow",
    "TimeWindowType",
    "Incident",
]
