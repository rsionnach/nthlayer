"""
Tests for deployment gates.
"""

from unittest.mock import MagicMock, patch

from nthlayer.slos.gates import DeploymentGate, GatePolicy, GateResult


class TestDeploymentGate:
    """Test deployment gate checks."""

    def test_approved_healthy_budget(self):
        """Test approval with healthy budget."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,  # 24 hours
            budget_consumed_minutes=50,  # ~3% consumed, 97% remaining
        )

        assert result.result == GateResult.APPROVED
        assert result.is_approved
        assert not result.is_warning
        assert not result.is_blocked
        assert result.budget_remaining_percentage > 90

    def test_warning_low_budget(self):
        """Test warning with low budget (between warning and blocking)."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=1200,  # 83% consumed, 17% remaining
        )

        assert result.result == GateResult.WARNING
        assert result.is_warning
        assert not result.is_approved
        assert not result.is_blocked
        assert result.budget_remaining_percentage < 20
        assert result.budget_remaining_percentage > 10

    def test_blocked_critical_budget(self):
        """Test blocking with critical budget."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=1350,  # 94% consumed, 6% remaining
        )

        assert result.result == GateResult.BLOCKED
        assert result.is_blocked
        assert not result.is_approved
        assert not result.is_warning
        assert result.budget_remaining_percentage < 10

    def test_standard_tier_no_blocking(self):
        """Test that standard tier doesn't block, only warns."""
        gate = DeploymentGate()

        # Even with very low budget, standard tier only warns
        result = gate.check_deployment(
            service="search-api",
            tier="standard",
            budget_total_minutes=1440,
            budget_consumed_minutes=1400,  # 97% consumed, 3% remaining
        )

        # Should warn but not block (standard tier has no blocking threshold)
        assert result.result == GateResult.WARNING
        assert result.blocking_threshold is None

    def test_low_tier_advisory_only(self):
        """Test that low tier is advisory only."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="test-service",
            tier="low",
            budget_total_minutes=1440,
            budget_consumed_minutes=950,  # 66% consumed, 34% remaining
        )

        # Low tier has higher warning threshold (30%)
        # 34% remaining should be approved (above 30% threshold)
        assert result.result == GateResult.APPROVED
        assert result.blocking_threshold is None

    def test_blast_radius_tracking(self):
        """Test blast radius is tracked."""
        gate = DeploymentGate()

        downstream = [
            {"name": "checkout-service", "criticality": "critical"},
            {"name": "analytics-service", "criticality": "low"},
            {"name": "email-service", "criticality": "high"},
        ]

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
            downstream_services=downstream,
        )

        assert len(result.downstream_services) == 3
        assert len(result.high_criticality_downstream) == 2
        assert "checkout-service" in result.high_criticality_downstream
        assert "email-service" in result.high_criticality_downstream
        assert "analytics-service" not in result.high_criticality_downstream

    def test_thresholds_per_tier(self):
        """Test that thresholds are correctly set per tier."""
        gate = DeploymentGate()

        critical_result = gate.check_deployment("svc1", "critical", 1440, 50)
        assert critical_result.warning_threshold == 20.0
        assert critical_result.blocking_threshold == 10.0

        standard_result = gate.check_deployment("svc2", "standard", 1440, 50)
        assert standard_result.warning_threshold == 20.0
        assert standard_result.blocking_threshold is None

        low_result = gate.check_deployment("svc3", "low", 1440, 50)
        assert low_result.warning_threshold == 30.0
        assert low_result.blocking_threshold is None

    def test_recommendations_include_blast_radius(self):
        """Test that recommendations mention blast radius."""
        gate = DeploymentGate()

        downstream = [
            {"name": "checkout-service", "criticality": "critical"},
        ]

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
            downstream_services=downstream,
        )

        # Should mention blast radius in recommendations
        blast_radius_mentioned = any(
            "Blast radius" in rec or "downstream" in rec for rec in result.recommendations
        )
        assert blast_radius_mentioned


class TestGatePolicy:
    """Tests for GatePolicy class."""

    def test_from_spec_with_thresholds(self):
        """Test creating GatePolicy from spec with thresholds."""
        spec = {
            "thresholds": {
                "warning": 30.0,
                "blocking": 15.0,
            },
            "conditions": [],
            "exceptions": [],
        }

        policy = GatePolicy.from_spec(spec)

        assert policy.warning == 30.0
        assert policy.blocking == 15.0
        assert policy.conditions == []
        assert policy.exceptions == []

    def test_from_spec_with_conditions_and_exceptions(self):
        """Test creating GatePolicy with conditions and exceptions."""
        spec = {
            "thresholds": {"warning": 25.0},
            "conditions": [{"when": "budget_remaining < 5", "blocking": 5.0}],
            "exceptions": [{"team": "sre-team", "allow": "always"}],
        }

        policy = GatePolicy.from_spec(spec)

        assert policy.warning == 25.0
        assert policy.blocking is None
        assert len(policy.conditions) == 1
        assert len(policy.exceptions) == 1

    def test_from_spec_empty(self):
        """Test creating GatePolicy from empty spec."""
        policy = GatePolicy.from_spec({})

        assert policy.warning is None
        assert policy.blocking is None
        assert policy.conditions == []
        assert policy.exceptions == []


class TestDeploymentGateWithPolicy:
    """Tests for deployment gates with custom policies."""

    def test_custom_warning_threshold(self):
        """Test custom warning threshold from policy."""
        policy = GatePolicy(warning=40.0, blocking=None)
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="standard",
            budget_total_minutes=100,
            budget_consumed_minutes=65,  # 35% remaining < 40% warning
        )

        assert result.result == GateResult.WARNING
        assert result.warning_threshold == 40.0

    def test_custom_blocking_threshold(self):
        """Test custom blocking threshold from policy."""
        policy = GatePolicy(warning=30.0, blocking=20.0)
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="standard",  # normally no blocking
            budget_total_minutes=100,
            budget_consumed_minutes=85,  # 15% remaining < 20% blocking
        )

        assert result.result == GateResult.BLOCKED
        assert result.blocking_threshold == 20.0

    def test_team_exception_bypasses_gate(self):
        """Test that team exception allows bypass."""
        policy = GatePolicy(
            warning=50.0,
            blocking=30.0,
            exceptions=[{"team": "platform-team", "allow": "always"}],
        )
        gate = DeploymentGate(policy=policy)

        # Budget is critically low but team has exception
        result = gate.check_deployment(
            service="test-api",
            tier="critical",
            budget_total_minutes=100,
            budget_consumed_minutes=95,  # 5% remaining - would be blocked
            team="platform-team",
        )

        assert result.result == GateResult.APPROVED
        assert "bypass" in result.message.lower()

    def test_team_exception_wrong_team(self):
        """Test that wrong team doesn't get bypass."""
        policy = GatePolicy(
            warning=50.0,
            blocking=30.0,
            exceptions=[{"team": "platform-team", "allow": "always"}],
        )
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="critical",
            budget_total_minutes=100,
            budget_consumed_minutes=95,
            team="other-team",
        )

        # Should still be blocked
        assert result.result == GateResult.BLOCKED

    def test_team_exception_not_always(self):
        """Test that non-always exception doesn't bypass."""
        policy = GatePolicy(
            exceptions=[{"team": "platform-team", "allow": "conditional"}],
        )
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="critical",
            budget_total_minutes=100,
            budget_consumed_minutes=95,
            team="platform-team",
        )

        # Should still be blocked (allow != "always")
        assert result.result == GateResult.BLOCKED

    def test_condition_evaluation(self):
        """Test condition-based threshold adjustment."""
        policy = GatePolicy(
            warning=20.0,
            blocking=None,
            conditions=[{"when": "budget_remaining < 10", "blocking": 5.0}],
        )
        gate = DeploymentGate(policy=policy)

        # Mock the evaluator at the source module (lazy import)
        with patch("nthlayer.policies.evaluator.ConditionEvaluator") as mock_evaluator_class:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_all.return_value = (
                True,
                {"when": "budget_remaining < 10", "blocking": 5.0},
            )
            mock_evaluator_class.return_value = mock_evaluator

            result = gate.check_deployment(
                service="test-api",
                tier="standard",
                budget_total_minutes=100,
                budget_consumed_minutes=92,  # 8% remaining
            )

            # Should have blocking threshold from condition
            assert result.blocking_threshold == 5.0

    def test_condition_no_match(self):
        """Test when no condition matches."""
        policy = GatePolicy(
            warning=20.0,
            blocking=10.0,
            conditions=[{"when": "never_true", "blocking": 1.0}],
        )
        gate = DeploymentGate(policy=policy)

        with patch("nthlayer.policies.evaluator.ConditionEvaluator") as mock_evaluator_class:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_all.return_value = (False, None)
            mock_evaluator_class.return_value = mock_evaluator

            result = gate.check_deployment(
                service="test-api",
                tier="standard",
                budget_total_minutes=100,
                budget_consumed_minutes=50,
            )

            # Should use policy thresholds, not condition
            assert result.blocking_threshold == 10.0


class TestDeploymentGateEdgeCases:
    """Additional edge case tests for deployment gates."""

    def test_zero_total_budget(self):
        """Test handling of zero total budget."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="test-api",
            tier="standard",
            budget_total_minutes=0,
            budget_consumed_minutes=0,
        )

        # Should default to 100% remaining
        assert result.budget_remaining_percentage == 100.0
        assert result.result == GateResult.APPROVED

    def test_non_high_criticality_downstream_only(self):
        """Test blast radius with only non-high-criticality downstream."""
        gate = DeploymentGate()

        downstream = [
            {"name": "analytics-service", "criticality": "low"},
            {"name": "logging-service", "criticality": "medium"},
        ]

        result = gate.check_deployment(
            service="test-api",
            tier="standard",
            budget_total_minutes=100,
            budget_consumed_minutes=10,
            downstream_services=downstream,
        )

        assert len(result.downstream_services) == 2
        assert len(result.high_criticality_downstream) == 0
        # Should mention downstream count in recommendations
        downstream_mentioned = any("downstream" in rec.lower() for rec in result.recommendations)
        assert downstream_mentioned

    def test_get_threshold_for_tier(self):
        """Test getting default thresholds for tier."""
        gate = DeploymentGate()

        critical = gate.get_threshold_for_tier("critical")
        assert critical["warning"] == 20.0
        assert critical["blocking"] == 10.0

        standard = gate.get_threshold_for_tier("standard")
        assert standard["warning"] == 20.0
        assert standard["blocking"] is None

        # Unknown tier should fall back to standard
        unknown = gate.get_threshold_for_tier("unknown")
        assert unknown["warning"] == 20.0

    def test_no_team_no_exception(self):
        """Test that no team provided doesn't trigger exception."""
        policy = GatePolicy(
            exceptions=[{"team": "platform-team", "allow": "always"}],
        )
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="critical",
            budget_total_minutes=100,
            budget_consumed_minutes=95,
            team=None,  # No team
        )

        assert result.result == GateResult.BLOCKED

    def test_empty_exceptions_list(self):
        """Test that empty exceptions list doesn't cause issues."""
        policy = GatePolicy(exceptions=[])
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="test-api",
            tier="critical",
            budget_total_minutes=100,
            budget_consumed_minutes=95,
            team="any-team",
        )

        assert result.result == GateResult.BLOCKED
