"""Tests for what-if scenario parsing and execution."""

from __future__ import annotations

import pytest

from nthlayer.simulate.models import DependencyModel, derive_failure_model
from nthlayer.simulate.what_if import apply_scenario, parse_what_if


class TestParseWhatIf:
    def test_redundant(self):
        scenario = parse_what_if("redundant:payment-api")
        assert scenario["type"] == "redundant"
        assert scenario["service"] == "payment-api"

    def test_improve(self):
        scenario = parse_what_if("improve:db:availability:0.9999")
        assert scenario["type"] == "improve"
        assert scenario["service"] == "db"
        assert scenario["value"] == pytest.approx(0.9999)

    def test_remove(self):
        scenario = parse_what_if("remove:cache")
        assert scenario["type"] == "remove"
        assert scenario["service"] == "cache"

    def test_degrade(self):
        scenario = parse_what_if("degrade:db:0.95")
        assert scenario["type"] == "degrade"
        assert scenario["service"] == "db"
        assert scenario["factor"] == pytest.approx(0.95)

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unknown"):
            parse_what_if("unknown:foo")


class TestApplyScenario:
    def test_redundant_squares_failure_probability(self):
        services = [derive_failure_model("a", 0.99)]
        deps: list[DependencyModel] = []
        scenario = parse_what_if("redundant:a")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        a_model = next(s for s in new_services if s.name == "a")
        assert a_model.availability_target > 0.99

    def test_remove_dependency(self):
        services = [
            derive_failure_model("parent", 0.999),
            derive_failure_model("child", 0.999),
        ]
        deps = [DependencyModel(from_service="child", to_service="parent", critical=True)]
        scenario = parse_what_if("remove:parent")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        assert len(new_deps) == 0

    def test_improve_availability(self):
        services = [derive_failure_model("svc", 0.99)]
        deps: list[DependencyModel] = []
        scenario = parse_what_if("improve:svc:availability:0.9999")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        svc = next(s for s in new_services if s.name == "svc")
        assert svc.availability_target == pytest.approx(0.9999)

    def test_degrade_critical_to_non_critical(self):
        services = [
            derive_failure_model("parent", 0.999),
            derive_failure_model("child", 0.999),
        ]
        deps = [DependencyModel(from_service="child", to_service="parent", critical=True)]
        scenario = parse_what_if("degrade:parent:0.95")
        new_services, new_deps = apply_scenario(services, deps, scenario)
        assert new_deps[0].critical is False
        assert new_deps[0].degradation_factor == pytest.approx(0.95)
