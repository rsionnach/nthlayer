"""Tests for Monte Carlo simulation engine."""

from __future__ import annotations

import random

import pytest

from nthlayer.simulate.engine import (
    generate_failure_timeline,
    simulate_run,
    run_simulation,
    _topological_sort,
)
from nthlayer.simulate.models import (
    DependencyModel,
    derive_failure_model,
)


class TestGenerateFailureTimeline:
    def test_returns_list_of_failure_events(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        events = generate_failure_timeline(model, horizon_hours=720.0)
        assert isinstance(events, list)
        assert len(events) > 0

    def test_events_within_horizon(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        horizon = 720.0
        events = generate_failure_timeline(model, horizon_hours=horizon)
        for event in events:
            assert event.start_hour < horizon
            assert event.start_hour + event.duration <= horizon + 0.001

    def test_events_non_overlapping(self):
        model = derive_failure_model("svc", availability_target=0.99)
        random.seed(42)
        events = generate_failure_timeline(model, horizon_hours=720.0)
        for i in range(len(events) - 1):
            assert events[i].end_hour <= events[i + 1].start_hour + 0.001

    def test_high_availability_fewer_failures(self):
        low_avail = derive_failure_model("low", availability_target=0.95)
        high_avail = derive_failure_model("high", availability_target=0.9999)
        random.seed(42)
        low_events = generate_failure_timeline(low_avail, horizon_hours=2160.0)
        random.seed(42)
        high_events = generate_failure_timeline(high_avail, horizon_hours=2160.0)
        assert len(high_events) < len(low_events)


class TestTopologicalSort:
    def test_cycle_detection_raises(self):
        """Cycles in the dependency graph should raise ValueError."""
        a = derive_failure_model("a", availability_target=0.999)
        b = derive_failure_model("b", availability_target=0.999)
        deps = [
            DependencyModel(from_service="a", to_service="b", critical=True),
            DependencyModel(from_service="b", to_service="a", critical=True),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort([a, b], deps)

    def test_standalone_service_converges_to_target(self):
        """A standalone service should converge to its availability target."""
        model = derive_failure_model("svc", availability_target=0.999)
        random.seed(42)
        horizon = 2160.0  # 90 days
        availabilities = []
        for _ in range(1000):
            result = simulate_run([model], [], horizon)
            availabilities.append(result["svc"])
        mean_avail = sum(availabilities) / len(availabilities)
        # Should converge to ~0.999 within ±0.005
        assert mean_avail == pytest.approx(0.999, abs=0.005)


class TestSimulateRun:
    def test_two_independent_services(self):
        svc_a = derive_failure_model("a", availability_target=0.999)
        svc_b = derive_failure_model("b", availability_target=0.995)
        random.seed(42)
        result = simulate_run([svc_a, svc_b], [], 2160.0)
        assert "a" in result
        assert "b" in result
        assert 0.0 <= result["a"] <= 1.0
        assert 0.0 <= result["b"] <= 1.0

    def test_critical_dependency_reduces_availability(self):
        parent = derive_failure_model("parent", availability_target=0.999)
        child = derive_failure_model("child", availability_target=0.999)
        dep = DependencyModel(from_service="child", to_service="parent", critical=True)
        random.seed(42)
        child_avails = []
        for _ in range(500):
            result = simulate_run([parent, child], [dep], 2160.0)
            child_avails.append(result["child"])
        mean_child = sum(child_avails) / len(child_avails)
        assert mean_child < 0.999


class TestRunSimulation:
    def test_returns_simulation_result(self):
        models = [derive_failure_model("svc", availability_target=0.999)]
        result = run_simulation(models, [], num_runs=100, horizon_days=90, seed=42)
        assert result.target_service == "svc"
        assert result.num_runs == 100
        assert 0.0 <= result.p_meeting_sla <= 1.0

    def test_analytical_two_services_in_series(self):
        """
        Analytical verification: two critical deps in series.
        A at 99.9%, B at 99.5% → composite ~99.4%
        """
        svc_a = derive_failure_model("a", availability_target=0.999)
        svc_b = derive_failure_model("b", availability_target=0.995)
        svc_c = derive_failure_model("c", availability_target=0.9999)
        deps = [
            DependencyModel(from_service="c", to_service="a", critical=True),
            DependencyModel(from_service="c", to_service="b", critical=True),
        ]
        result = run_simulation(
            [svc_a, svc_b, svc_c],
            deps,
            num_runs=5000,
            horizon_days=90,
            seed=42,
        )
        c_result = result.services["c"]
        assert c_result.availability_p50 == pytest.approx(0.994, abs=0.01)
