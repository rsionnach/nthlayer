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


class TestBudgetPolicyParsing:
    def test_parse_opensrm_with_budget_policy(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "deployment": {
                    "gates": {
                        "error_budget": {
                            "enabled": True,
                            "policy": {
                                "window": "7d",
                                "thresholds": {
                                    "warning": 0.25,
                                    "critical": 0.15,
                                },
                                "on_exhausted": ["freeze_deploys", "notify"],
                            },
                        },
                    },
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.deployment is not None
        assert manifest.deployment.gates is not None
        assert manifest.deployment.gates.error_budget is not None
        assert manifest.deployment.gates.error_budget.policy is not None
        policy = manifest.deployment.gates.error_budget.policy
        assert policy.window == "7d"
        assert policy.thresholds.warning == 0.25
        assert policy.thresholds.critical == 0.15
        assert policy.on_exhausted == ["freeze_deploys", "notify"]

    def test_parse_opensrm_without_budget_policy(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "deployment": {
                    "gates": {
                        "error_budget": {"enabled": True},
                    },
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.deployment is not None
        assert manifest.deployment.gates is not None
        assert manifest.deployment.gates.error_budget is not None
        assert manifest.deployment.gates.error_budget.policy is None

    def test_parse_budget_policy_partial_thresholds(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "deployment": {
                    "gates": {
                        "error_budget": {
                            "enabled": True,
                            "policy": {
                                "thresholds": {"warning": 0.30},
                            },
                        },
                    },
                },
            },
        }
        manifest = parse_opensrm(data)
        policy = manifest.deployment.gates.error_budget.policy
        assert policy is not None
        assert policy.thresholds.warning == 0.30
        assert policy.thresholds.critical == 0.10  # default
        assert policy.window == "30d"  # default


class TestBudgetPolicyCLIWiring:
    """Test that BudgetPolicy flows from manifest to DeploymentGate via CLI."""

    def test_gate_policy_from_budget_policy(self) -> None:
        """BudgetPolicy from manifest converts to GatePolicy for DeploymentGate."""
        from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds
        from nthlayer.slos.gates import GatePolicy

        budget_policy = BudgetPolicy(
            window="7d",
            thresholds=BudgetThresholds(warning=0.25, critical=0.12),
            on_exhausted=["freeze_deploys", "notify"],
        )

        # Conversion: BudgetPolicy -> GatePolicy
        gate_policy = GatePolicy(
            warning=budget_policy.thresholds.warning * 100,
            blocking=budget_policy.thresholds.critical * 100,
            on_exhausted=budget_policy.on_exhausted,
        )

        assert gate_policy.warning == 25.0
        assert gate_policy.blocking == 12.0
        assert gate_policy.on_exhausted == ["freeze_deploys", "notify"]

    def test_gate_policy_from_budget_policy_defaults(self) -> None:
        """Default BudgetPolicy converts to expected GatePolicy values."""
        from nthlayer.specs.manifest import BudgetPolicy
        from nthlayer.slos.gates import GatePolicy

        budget_policy = BudgetPolicy()

        gate_policy = GatePolicy(
            warning=budget_policy.thresholds.warning * 100,
            blocking=budget_policy.thresholds.critical * 100,
            on_exhausted=budget_policy.on_exhausted,
        )

        assert gate_policy.warning == 20.0
        assert gate_policy.blocking == 10.0
        assert gate_policy.on_exhausted == []
