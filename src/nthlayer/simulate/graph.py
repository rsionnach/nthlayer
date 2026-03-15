"""Build simulation models from OpenSRM manifests."""

from __future__ import annotations

from nthlayer.simulate.models import (
    DependencyModel,
    ServiceFailureModel,
    derive_failure_model,
)
from nthlayer.specs.manifest import ReliabilityManifest


def _normalize_availability(target: float) -> float:
    """Normalize availability target to a 0-1 ratio.
    Values > 1 are treated as percentages (e.g., 99.9 → 0.999).
    Values <= 1 are treated as ratios (e.g., 0.999).
    """
    if target > 1.0:
        return target / 100.0
    return target


def _get_availability_target(manifest: ReliabilityManifest) -> float:
    """Extract and normalize availability target from manifest."""
    for slo in manifest.slos:
        if slo.name == "availability":
            return _normalize_availability(slo.target)
    raise ValueError(
        f"Service '{manifest.name}' has no availability SLO — " f"required for simulation"
    )


def build_failure_models(
    manifests: list[ReliabilityManifest],
    default_mttr_hours: float = 1.0,
) -> list[ServiceFailureModel]:
    """Build failure models from manifests."""
    models: list[ServiceFailureModel] = []
    for manifest in manifests:
        avail = _get_availability_target(manifest)
        model = derive_failure_model(
            name=manifest.name,
            availability_target=avail,
            mttr_hours=default_mttr_hours,
        )
        models.append(model)
    return models


def build_dependency_models(
    manifests: list[ReliabilityManifest],
) -> list[DependencyModel]:
    """Build dependency models from manifests."""
    dep_models: list[DependencyModel] = []
    for manifest in manifests:
        for dep in manifest.dependencies:
            dep_models.append(
                DependencyModel(
                    from_service=manifest.name,
                    to_service=dep.name,
                    critical=dep.critical,
                )
            )
    return dep_models
