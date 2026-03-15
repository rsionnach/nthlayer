"""
Tests for Monte Carlo SLO simulation data models.
"""

from __future__ import annotations

import pytest

from nthlayer.simulate.models import (
    DependencyModel,
    FailureEvent,
    PercentileResult,
    ServiceFailureModel,
    derive_failure_model,
)


class TestServiceFailureModel:
    """Tests for ServiceFailureModel dataclass."""

    def test_create_with_explicit_values(self):
        """Create a model with explicit values and verify them."""
        model = ServiceFailureModel(
            name="payment-api",
            availability_target=0.999,
            mtbf_hours=999.0,
            mttr_hours=1.0,
        )

        assert model.name == "payment-api"
        assert model.availability_target == pytest.approx(0.999)
        assert model.mtbf_hours == pytest.approx(999.0)
        assert model.mttr_hours == pytest.approx(1.0)

    def test_default_distributions(self):
        """Verify default distribution parameters are set correctly."""
        model = ServiceFailureModel(
            name="checkout",
            availability_target=0.99,
            mtbf_hours=49.5,
            mttr_hours=0.5,
        )

        assert model.mtbf_distribution == "exponential"
        assert model.mttr_distribution == "lognormal"

    def test_default_shapes(self):
        """Verify default shape parameters are set correctly."""
        model = ServiceFailureModel(
            name="auth-service",
            availability_target=0.9999,
            mtbf_hours=9999.0,
            mttr_hours=1.0,
        )

        assert model.mtbf_shape == pytest.approx(1.0)
        assert model.mttr_shape == pytest.approx(0.5)

    def test_override_distributions(self):
        """Verify distribution parameters can be overridden."""
        model = ServiceFailureModel(
            name="custom-service",
            availability_target=0.99,
            mtbf_hours=99.0,
            mttr_hours=1.0,
            mtbf_distribution="weibull",
            mttr_distribution="exponential",
            mtbf_shape=2.0,
            mttr_shape=1.0,
        )

        assert model.mtbf_distribution == "weibull"
        assert model.mttr_distribution == "exponential"
        assert model.mtbf_shape == pytest.approx(2.0)
        assert model.mttr_shape == pytest.approx(1.0)


class TestDeriveFailureModel:
    """Tests for the derive_failure_model function."""

    def test_derive_from_99_9_percent(self):
        """Derive from 99.9% availability with default MTTR=1.0."""
        model = derive_failure_model("payment-api", 0.999)

        assert model.name == "payment-api"
        assert model.availability_target == pytest.approx(0.999)
        assert model.mttr_hours == pytest.approx(1.0)
        # MTBF = 1.0 * 0.999 / (1 - 0.999) = 0.999 / 0.001 = 999.0
        assert model.mtbf_hours == pytest.approx(999.0, rel=1e-3)

    def test_derive_from_99_percent_with_custom_mttr(self):
        """Derive from 99% availability with custom MTTR=0.5."""
        model = derive_failure_model("checkout", 0.99, mttr_hours=0.5)

        assert model.name == "checkout"
        assert model.availability_target == pytest.approx(0.99)
        assert model.mttr_hours == pytest.approx(0.5)
        # MTBF = 0.5 * 0.99 / (1 - 0.99) = 0.495 / 0.01 = 49.5
        assert model.mtbf_hours == pytest.approx(49.5, rel=1e-3)

    def test_derive_with_mttr_2_0(self):
        """Derive from 99.9% availability with MTTR=2.0."""
        model = derive_failure_model("auth-service", 0.999, mttr_hours=2.0)

        assert model.mttr_hours == pytest.approx(2.0)
        # MTBF = 2.0 * 0.999 / (1 - 0.999) = 1.998 / 0.001 = 1998.0
        assert model.mtbf_hours == pytest.approx(1998.0, rel=1e-3)

    def test_derived_model_has_correct_defaults(self):
        """Derived model should have correct distribution defaults."""
        model = derive_failure_model("svc", 0.99)

        assert model.mtbf_distribution == "exponential"
        assert model.mttr_distribution == "lognormal"
        assert model.mtbf_shape == pytest.approx(1.0)
        assert model.mttr_shape == pytest.approx(0.5)


class TestFailureEvent:
    """Tests for FailureEvent dataclass."""

    def test_create_event(self):
        """Create a failure event and verify fields."""
        event = FailureEvent(start_hour=100.0, duration=2.5)

        assert event.start_hour == pytest.approx(100.0)
        assert event.duration == pytest.approx(2.5)

    def test_end_hour_computed_property(self):
        """Verify end_hour is computed as start_hour + duration."""
        event = FailureEvent(start_hour=100.0, duration=2.5)

        assert event.end_hour == pytest.approx(102.5)

    def test_end_hour_at_zero_start(self):
        """Verify end_hour when start_hour is 0."""
        event = FailureEvent(start_hour=0.0, duration=5.0)

        assert event.end_hour == pytest.approx(5.0)

    def test_end_hour_with_large_values(self):
        """Verify end_hour with large hours values."""
        event = FailureEvent(start_hour=8000.0, duration=48.0)

        assert event.end_hour == pytest.approx(8048.0)


class TestDependencyModel:
    """Tests for DependencyModel dataclass."""

    def test_critical_dependency(self):
        """Create a critical dependency and verify fields."""
        dep = DependencyModel(
            from_service="checkout",
            to_service="payment-api",
            critical=True,
        )

        assert dep.from_service == "checkout"
        assert dep.to_service == "payment-api"
        assert dep.critical is True
        # Default degradation factor
        assert dep.degradation_factor == pytest.approx(0.99)

    def test_non_critical_dependency_with_custom_degradation(self):
        """Create a non-critical dependency with custom degradation factor."""
        dep = DependencyModel(
            from_service="analytics",
            to_service="user-service",
            critical=False,
            degradation_factor=0.95,
        )

        assert dep.from_service == "analytics"
        assert dep.to_service == "user-service"
        assert dep.critical is False
        assert dep.degradation_factor == pytest.approx(0.95)

    def test_non_critical_default_degradation(self):
        """Non-critical dependency defaults to 0.99 degradation factor."""
        dep = DependencyModel(
            from_service="svc-a",
            to_service="svc-b",
            critical=False,
        )

        assert dep.degradation_factor == pytest.approx(0.99)
