"""Tests for error budget policy configuration."""

from __future__ import annotations

import pytest

from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds, ErrorBudgetGate


class TestBudgetPolicy:
    def test_default_thresholds(self) -> None:
        policy = BudgetPolicy()
        assert policy.thresholds.warning == 0.20
        assert policy.thresholds.critical == 0.10

    def test_custom_thresholds(self) -> None:
        policy = BudgetPolicy(
            thresholds=BudgetThresholds(warning=0.30, critical=0.15),
        )
        assert policy.thresholds.warning == 0.30
        assert policy.thresholds.critical == 0.15

    def test_default_window(self) -> None:
        policy = BudgetPolicy()
        assert policy.window == "30d"

    def test_on_exhausted_defaults(self) -> None:
        policy = BudgetPolicy()
        assert policy.on_exhausted == []

    def test_on_exhausted_custom(self) -> None:
        policy = BudgetPolicy(
            on_exhausted=["freeze_deploys", "notify"],
        )
        assert "freeze_deploys" in policy.on_exhausted
        assert "notify" in policy.on_exhausted

    def test_valid_on_exhausted_values(self) -> None:
        valid = ["freeze_deploys", "require_approval", "notify"]
        policy = BudgetPolicy(on_exhausted=valid)
        assert policy.on_exhausted == valid


class TestErrorBudgetGateWithPolicy:
    def test_error_budget_gate_default_no_policy(self) -> None:
        gate = ErrorBudgetGate()
        assert gate.policy is None

    def test_error_budget_gate_with_policy(self) -> None:
        gate = ErrorBudgetGate(
            policy=BudgetPolicy(
                window="7d",
                thresholds=BudgetThresholds(warning=0.25, critical=0.10),
                on_exhausted=["freeze_deploys"],
            ),
        )
        assert gate.policy is not None
        assert gate.policy.window == "7d"
        assert gate.policy.on_exhausted == ["freeze_deploys"]
