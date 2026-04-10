"""Tests for building simulation models from manifests."""

from __future__ import annotations

import pytest

from nthlayer.simulate.graph import (
    build_dependency_models,
    build_failure_models,
)
from nthlayer.specs.manifest import (
    Dependency,
    ReliabilityManifest,
    SLODefinition,
)


def _make_manifest(
    name: str,
    avail_target: float = 99.9,
    deps: list[Dependency] | None = None,
) -> ReliabilityManifest:
    return ReliabilityManifest(
        name=name,
        team="test",
        tier="standard",
        type="api",
        slos=[SLODefinition(name="availability", target=avail_target, window="30d")],
        dependencies=deps or [],
    )


class TestBuildFailureModels:
    def test_single_manifest(self):
        manifest = _make_manifest("svc-a", avail_target=99.9)
        models = build_failure_models([manifest])
        assert len(models) == 1
        assert models[0].name == "svc-a"
        assert models[0].availability_target == pytest.approx(0.999)

    def test_availability_as_percentage_vs_ratio(self):
        manifest = _make_manifest("svc", avail_target=99.95)
        models = build_failure_models([manifest])
        assert models[0].availability_target == pytest.approx(0.9995)

    def test_availability_as_ratio(self):
        manifest = _make_manifest("svc", avail_target=0.999)
        models = build_failure_models([manifest])
        assert models[0].availability_target == pytest.approx(0.999)

    def test_no_availability_slo_raises(self):
        manifest = ReliabilityManifest(name="svc", team="t", tier="standard", type="api", slos=[])
        with pytest.raises(ValueError, match="availability"):
            build_failure_models([manifest])


class TestBuildDependencyModels:
    def test_critical_dependency(self):
        deps = [Dependency(name="db", type="database", critical=True)]
        manifest = _make_manifest("svc", deps=deps)
        dep_models = build_dependency_models([manifest])
        assert len(dep_models) == 1
        assert dep_models[0].from_service == "svc"
        assert dep_models[0].to_service == "db"
        assert dep_models[0].critical is True

    def test_non_critical_dependency(self):
        deps = [Dependency(name="cache", type="cache", critical=False)]
        manifest = _make_manifest("svc", deps=deps)
        dep_models = build_dependency_models([manifest])
        assert dep_models[0].critical is False

    def test_multiple_manifests(self):
        m1 = _make_manifest("a", deps=[Dependency(name="b", type="api", critical=True)])
        m2 = _make_manifest("b")
        dep_models = build_dependency_models([m1, m2])
        assert len(dep_models) == 1
