"""
Monte Carlo SLO simulation engine.

Predicts the probability of meeting SLAs from OpenSRM manifests
and dependency graphs. Pure transport — no model calls.
"""

from __future__ import annotations

from nthlayer.simulate.graph import (
    build_dependency_models,
    build_failure_models,
)
from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    PercentileResult,
    ServiceFailureModel,
    ServiceSimulationResult,
    SimulationResult,
    WhatIfResult,
    derive_failure_model,
)

__all__ = [
    "build_dependency_models",
    "build_failure_models",
    "DependencyModel",
    "FailureEvent",
    "PercentileResult",
    "ServiceFailureModel",
    "ServiceSimulationResult",
    "SimulationResult",
    "WhatIfResult",
    "derive_failure_model",
]
