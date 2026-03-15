"""
Monte Carlo SLO simulation engine.

Predicts the probability of meeting SLAs from OpenSRM manifests
and dependency graphs. Pure transport — no model calls.
"""

from __future__ import annotations

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
    "DependencyModel",
    "FailureEvent",
    "PercentileResult",
    "ServiceFailureModel",
    "ServiceSimulationResult",
    "SimulationResult",
    "WhatIfResult",
    "derive_failure_model",
]
