"""Tests for policy condition evaluator.

Tests for nthlayer policies evaluator including condition parsing,
operator evaluation, boolean logic, and built-in functions.
"""

from datetime import datetime

import pytest
from nthlayer.policies.evaluator import (
    ConditionEvaluator,
    EvaluationResult,
    PolicyContext,
)


class TestPolicyContext:
    """Tests for PolicyContext dataclass."""

    def test_default_values(self):
        """Test PolicyContext has sensible defaults."""
        ctx = PolicyContext()

        assert ctx.budget_remaining == 100.0
        assert ctx.budget_consumed == 0.0
        assert ctx.burn_rate == 1.0
        assert ctx.tier == "standard"
        assert ctx.environment == "prod"
        assert ctx.downstream_count == 0
        assert ctx.now is None

    def test_custom_values(self):
        """Test PolicyContext with custom values."""
        now = datetime(2024, 6, 15, 14, 30)
        ctx = PolicyContext(
            budget_remaining=50.0,
            budget_consumed=50.0,
            burn_rate=2.5,
            tier="critical",
            environment="staging",
            service="payment-api",
            team="platform",
            downstream_count=10,
            high_criticality_downstream=3,
            now=now,
        )

        assert ctx.budget_remaining == 50.0
        assert ctx.tier == "critical"
        assert ctx.environment == "staging"
        assert ctx.service == "payment-api"
        assert ctx.now == now

    def test_to_dict_basic(self):
        """Test to_dict returns expected keys."""
        ctx = PolicyContext()
        d = ctx.to_dict()

        expected_keys = [
            "hour",
            "minute",
            "weekday",
            "day_of_week",
            "date",
            "month",
            "day",
            "year",
            "budget_remaining",
            "budget_consumed",
            "burn_rate",
            "tier",
            "environment",
            "env",
            "service",
            "team",
            "downstream_count",
            "high_criticality_downstream",
        ]
        for key in expected_keys:
            assert key in d

    def test_to_dict_with_custom_time(self):
        """Test to_dict with custom datetime."""
        # Wednesday, June 12, 2024, 10:30 AM
        now = datetime(2024, 6, 12, 10, 30)
        ctx = PolicyContext(now=now)
        d = ctx.to_dict()

        assert d["hour"] == 10
        assert d["minute"] == 30
        assert d["weekday"] is True  # Wednesday is weekday
        assert d["day_of_week"] == 2  # Wednesday
        assert d["date"] == "2024-06-12"
        assert d["month"] == 6
        assert d["day"] == 12
        assert d["year"] == 2024

    def test_to_dict_weekend(self):
        """Test to_dict correctly identifies weekend."""
        # Saturday, June 15, 2024
        now = datetime(2024, 6, 15, 10, 0)
        ctx = PolicyContext(now=now)
        d = ctx.to_dict()

        assert d["weekday"] is False
        assert d["day_of_week"] == 5  # Saturday

    def test_env_alias(self):
        """Test that 'env' is an alias for 'environment'."""
        ctx = PolicyContext(environment="staging")
        d = ctx.to_dict()

        assert d["environment"] == "staging"
        assert d["env"] == "staging"


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_basic_result(self):
        """Test creating basic evaluation result."""
        result = EvaluationResult(
            condition="hour >= 9",
            result=True,
        )

        assert result.condition == "hour >= 9"
        assert result.result is True
        assert result.matched_rule is None
        assert result.context_snapshot == {}

    def test_full_result(self):
        """Test creating evaluation result with all fields."""
        result = EvaluationResult(
            condition="budget_remaining < 20",
            result=True,
            matched_rule="low_budget",
            context_snapshot={"budget_remaining": 15.0},
        )

        assert result.condition == "budget_remaining < 20"
        assert result.result is True
        assert result.matched_rule == "low_budget"
        assert result.context_snapshot == {"budget_remaining": 15.0}


class TestConditionEvaluatorInit:
    """Tests for ConditionEvaluator initialization."""

    def test_init_with_none(self):
        """Test initialization with no context."""
        evaluator = ConditionEvaluator()
        assert evaluator.context == {}

    def test_init_with_dict(self):
        """Test initialization with dict context."""
        ctx = {"hour": 10, "tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.context == ctx

    def test_init_with_policy_context(self):
        """Test initialization with PolicyContext."""
        ctx = PolicyContext(tier="critical", budget_remaining=50.0)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.context["tier"] == "critical"
        assert evaluator.context["budget_remaining"] == 50.0


class TestComparisonOperators:
    """Tests for comparison operators."""

    def test_equals_string(self):
        """Test == operator with strings."""
        ctx = {"tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier == 'critical'") is True
        assert evaluator.evaluate("tier == 'standard'") is False

    def test_equals_number(self):
        """Test == operator with numbers."""
        ctx = {"hour": 10}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour == 10") is True
        assert evaluator.evaluate("hour == 11") is False

    def test_not_equals(self):
        """Test != operator."""
        ctx = {"tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier != 'standard'") is True
        assert evaluator.evaluate("tier != 'critical'") is False

    def test_greater_than(self):
        """Test > operator."""
        ctx = {"hour": 10}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour > 9") is True
        assert evaluator.evaluate("hour > 10") is False
        assert evaluator.evaluate("hour > 11") is False

    def test_greater_than_or_equal(self):
        """Test >= operator."""
        ctx = {"hour": 10}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour >= 9") is True
        assert evaluator.evaluate("hour >= 10") is True
        assert evaluator.evaluate("hour >= 11") is False

    def test_less_than(self):
        """Test < operator."""
        ctx = {"budget_remaining": 15.0}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("budget_remaining < 20") is True
        assert evaluator.evaluate("budget_remaining < 15") is False
        assert evaluator.evaluate("budget_remaining < 10") is False

    def test_less_than_or_equal(self):
        """Test <= operator."""
        ctx = {"budget_remaining": 15.0}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("budget_remaining <= 20") is True
        assert evaluator.evaluate("budget_remaining <= 15") is True
        assert evaluator.evaluate("budget_remaining <= 10") is False

    def test_float_comparison(self):
        """Test comparison with floats."""
        ctx = {"burn_rate": 2.5}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("burn_rate > 2.0") is True
        assert evaluator.evaluate("burn_rate <= 2.5") is True


class TestBooleanOperators:
    """Tests for boolean operators (AND, OR, NOT)."""

    def test_and_both_true(self):
        """Test AND when both conditions true."""
        ctx = {"hour": 10, "weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour >= 9 AND weekday") is True

    def test_and_one_false(self):
        """Test AND when one condition false."""
        ctx = {"hour": 10, "weekday": False}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour >= 9 AND weekday") is False

    def test_and_case_insensitive(self):
        """Test AND is case insensitive."""
        ctx = {"hour": 10, "weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour >= 9 and weekday") is True
        assert evaluator.evaluate("hour >= 9 And weekday") is True

    def test_or_one_true(self):
        """Test OR when one condition true."""
        ctx = {"tier": "critical", "budget_remaining": 50}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier == 'critical' OR budget_remaining < 20") is True

    def test_or_both_false(self):
        """Test OR when both conditions false."""
        ctx = {"tier": "standard", "budget_remaining": 50}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier == 'critical' OR budget_remaining < 20") is False

    def test_or_case_insensitive(self):
        """Test OR is case insensitive."""
        ctx = {"tier": "critical", "weekday": False}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier == 'critical' or weekday") is True

    def test_not_true(self):
        """Test NOT inverts true to false."""
        ctx = {"weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("NOT weekday") is False

    def test_not_false(self):
        """Test NOT inverts false to true."""
        ctx = {"weekday": False}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("NOT weekday") is True

    def test_not_case_insensitive(self):
        """Test NOT is case insensitive."""
        ctx = {"weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("not weekday") is False

    def test_complex_and_or(self):
        """Test complex AND/OR expression."""
        ctx = {"hour": 10, "weekday": True, "tier": "standard"}
        evaluator = ConditionEvaluator(ctx)

        # OR has lower precedence than AND
        assert evaluator.evaluate("tier == 'critical' OR hour >= 9 AND weekday") is True


class TestParentheses:
    """Tests for parentheses grouping."""

    def test_simple_parentheses(self):
        """Test simple parentheses grouping."""
        ctx = {"hour": 10, "weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("(hour >= 9) AND weekday") is True

    def test_parentheses_change_precedence(self):
        """Test parentheses changing evaluation precedence."""
        ctx = {"hour": 10, "weekday": False, "tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        # Without parentheses: tier == 'critical' OR (hour >= 9 AND weekday)
        # -> critical OR False -> True
        assert evaluator.evaluate("tier == 'critical' OR hour >= 9 AND weekday") is True

        # With parentheses: (tier == 'critical' OR hour >= 9) AND weekday
        # -> True AND False -> False
        assert evaluator.evaluate("(tier == 'critical' OR hour >= 9) AND weekday") is False

    def test_nested_parentheses(self):
        """Test nested parentheses."""
        ctx = {"a": True, "b": True, "c": False, "d": True}
        evaluator = ConditionEvaluator(ctx)

        # ((a AND b) OR c) AND d
        assert evaluator.evaluate("((a AND b) OR c) AND d") is True

    def test_multiple_parentheses(self):
        """Test multiple parentheses groups."""
        ctx = {"a": True, "b": False, "c": True, "d": False}
        evaluator = ConditionEvaluator(ctx)

        # (a AND b) OR (c AND d)
        assert evaluator.evaluate("(a AND b) OR (c AND d)") is False

        # (a OR b) AND (c OR d)
        assert evaluator.evaluate("(a OR b) AND (c OR d)") is True


class TestBuiltinFunctions:
    """Tests for built-in functions."""

    def test_business_hours_during(self):
        """Test business_hours() during business hours."""
        # Wednesday 10:30 AM
        now = datetime(2024, 6, 12, 10, 30)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("business_hours()") is True

    def test_business_hours_outside(self):
        """Test business_hours() outside business hours."""
        # Wednesday 8:00 PM
        now = datetime(2024, 6, 12, 20, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("business_hours()") is False

    def test_business_hours_weekend(self):
        """Test business_hours() on weekend."""
        # Saturday 10:30 AM
        now = datetime(2024, 6, 15, 10, 30)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("business_hours()") is False

    def test_weekday_true(self):
        """Test weekday() on a weekday."""
        # Wednesday
        now = datetime(2024, 6, 12, 10, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("weekday()") is True

    def test_weekday_false(self):
        """Test weekday() on a weekend."""
        # Saturday
        now = datetime(2024, 6, 15, 10, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("weekday()") is False

    @pytest.mark.xfail(
        reason="Known bug: parentheses handling evaluates function args as conditions"
    )
    def test_freeze_period_inside(self):
        """Test freeze_period() when inside freeze.

        NOTE: This test documents a bug where functions with arguments fail
        because the parentheses-handling loop incorrectly evaluates function
        arguments as conditions. See issue trellis-evaluator-parens-bug.
        """
        # Dec 25, 2024
        now = datetime(2024, 12, 25, 10, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("freeze_period('2024-12-20', '2025-01-02')") is True

    def test_freeze_period_outside(self):
        """Test freeze_period() when outside freeze.

        NOTE: This test passes but for the wrong reason due to a bug where
        functions with arguments always return False. The freeze_period function
        should return False because we're outside the freeze period, but it
        actually returns False because of the parentheses-handling bug.
        See issue trellis-evaluator-parens-bug.
        """
        # Dec 10, 2024
        now = datetime(2024, 12, 10, 10, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        # This returns False (correct result, wrong reason - see note above)
        assert evaluator.evaluate("freeze_period('2024-12-20', '2025-01-02')") is False

    def test_peak_traffic_during(self):
        """Test peak_traffic() during peak hours."""
        # 11 AM (within default peak hours 10-12)
        now = datetime(2024, 6, 12, 11, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("peak_traffic()") is True

    def test_peak_traffic_outside(self):
        """Test peak_traffic() outside peak hours."""
        # 9 AM (before peak hours)
        now = datetime(2024, 6, 12, 9, 0)
        ctx = PolicyContext(now=now)
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("peak_traffic()") is False

    def test_unknown_function_returns_false(self):
        """Test that unknown function returns False."""
        evaluator = ConditionEvaluator({})

        assert evaluator.evaluate("unknown_function()") is False


class TestValueResolution:
    """Tests for value resolution."""

    def test_string_single_quotes(self):
        """Test string literal with single quotes."""
        ctx = {"tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("tier == 'critical'") is True

    def test_string_double_quotes(self):
        """Test string literal with double quotes."""
        ctx = {"tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate('tier == "critical"') is True

    def test_integer_literal(self):
        """Test integer literal."""
        ctx = {"hour": 10}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour == 10") is True

    def test_float_literal(self):
        """Test float literal."""
        ctx = {"burn_rate": 2.5}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("burn_rate == 2.5") is True

    def test_boolean_true_literal(self):
        """Test boolean true literal."""
        evaluator = ConditionEvaluator({})

        assert evaluator.evaluate("true") is True
        assert evaluator.evaluate("True") is True

    def test_boolean_false_literal(self):
        """Test boolean false literal."""
        evaluator = ConditionEvaluator({})

        assert evaluator.evaluate("false") is False
        assert evaluator.evaluate("False") is False

    def test_missing_variable_returns_false(self):
        """Test that missing variable returns False."""
        evaluator = ConditionEvaluator({})

        assert evaluator.evaluate("unknown_var") is False
        assert evaluator.evaluate("unknown_var == 'value'") is False

    def test_boolean_variable(self):
        """Test boolean variable evaluation."""
        ctx = {"weekday": True}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("weekday") is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_condition_returns_true(self):
        """Test empty condition returns True."""
        evaluator = ConditionEvaluator({})

        assert evaluator.evaluate("") is True
        assert evaluator.evaluate("   ") is True

    def test_whitespace_normalized(self):
        """Test whitespace is normalized."""
        ctx = {"hour": 10}
        evaluator = ConditionEvaluator(ctx)

        assert evaluator.evaluate("hour   >=    9") is True
        assert evaluator.evaluate("  hour >= 9  ") is True

    def test_invalid_syntax_returns_false(self):
        """Test invalid syntax returns False (fail safe)."""
        evaluator = ConditionEvaluator({})

        # Missing operator
        assert evaluator.evaluate("hour 10") is False

    def test_unmatched_parentheses(self):
        """Test unmatched parentheses handled gracefully."""
        evaluator = ConditionEvaluator({"a": True})

        # Should not crash, may return False
        result = evaluator.evaluate("(a AND (b)")
        assert isinstance(result, bool)


class TestEvaluateAll:
    """Tests for evaluate_all method."""

    def test_no_matching_conditions(self):
        """Test when no conditions match."""
        ctx = {"hour": 8}  # Before business hours
        evaluator = ConditionEvaluator(ctx)

        conditions = [
            {"name": "business", "when": "hour >= 9 AND hour <= 17", "blocking": 10},
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is False
        assert matched is None

    def test_single_matching_condition(self):
        """Test single matching condition."""
        ctx = {"hour": 10, "weekday": True}
        evaluator = ConditionEvaluator(ctx)

        conditions = [
            {"name": "business", "when": "hour >= 9 AND weekday", "blocking": 10},
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is True
        assert matched["name"] == "business"

    def test_most_restrictive_wins(self):
        """Test that most restrictive condition wins."""
        ctx = {"hour": 10, "weekday": True, "tier": "critical"}
        evaluator = ConditionEvaluator(ctx)

        conditions = [
            {"name": "business", "when": "weekday", "blocking": 10},
            {"name": "critical", "when": "tier == 'critical'", "blocking": 50},
            {"name": "peak", "when": "hour >= 10", "blocking": 20},
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is True
        assert matched["name"] == "critical"  # Highest blocking value

    def test_empty_when_matches(self):
        """Test condition with empty 'when' clause always matches."""
        evaluator = ConditionEvaluator({})

        conditions = [
            {"name": "default", "when": "", "blocking": 5},
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is True
        assert matched["name"] == "default"

    def test_multiple_conditions_equal_blocking(self):
        """Test with multiple conditions having equal blocking values."""
        ctx = {"a": True, "b": True}
        evaluator = ConditionEvaluator(ctx)

        conditions = [
            {"name": "first", "when": "a", "blocking": 10},
            {"name": "second", "when": "b", "blocking": 10},
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is True
        # First matching condition with equal blocking wins
        assert matched["name"] == "first"


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_complex_policy_expression(self):
        """Test complex real-world policy expression."""
        # Wednesday 2:30 PM, critical tier, low budget
        now = datetime(2024, 6, 12, 14, 30)
        ctx = PolicyContext(
            now=now,
            tier="critical",
            budget_remaining=15.0,
            environment="prod",
        )
        evaluator = ConditionEvaluator(ctx)

        # Block deployment if: during business hours AND (critical tier OR low budget)
        expr = "business_hours() AND (tier == 'critical' OR budget_remaining < 20)"
        assert evaluator.evaluate(expr) is True

    @pytest.mark.xfail(
        reason="Known bug: parentheses handling evaluates function args as conditions"
    )
    def test_freeze_period_with_override(self):
        """Test freeze period with environment override.

        NOTE: This test documents a bug where functions with arguments fail.
        See issue trellis-evaluator-parens-bug.
        """
        # During freeze period
        now = datetime(2024, 12, 25, 10, 0)
        ctx = PolicyContext(now=now, environment="dev")
        evaluator = ConditionEvaluator(ctx)

        # Block unless dev environment
        expr = "freeze_period('2024-12-20', '2025-01-02') AND environment != 'dev'"
        assert evaluator.evaluate(expr) is False  # Dev is allowed

        # Prod should be blocked
        ctx_prod = PolicyContext(now=now, environment="prod")
        evaluator_prod = ConditionEvaluator(ctx_prod)
        assert evaluator_prod.evaluate(expr) is True

    def test_blast_radius_check(self):
        """Test blast radius considerations."""
        ctx = PolicyContext(
            tier="critical",
            downstream_count=15,
            high_criticality_downstream=5,
        )
        evaluator = ConditionEvaluator(ctx)

        # High blast radius check
        expr = "downstream_count > 10 AND high_criticality_downstream >= 3"
        assert evaluator.evaluate(expr) is True

    def test_full_deployment_gate(self):
        """Test full deployment gate evaluation."""
        # Tuesday 11 AM, critical service, healthy budget
        now = datetime(2024, 6, 11, 11, 0)
        ctx = PolicyContext(
            now=now,
            tier="critical",
            budget_remaining=80.0,
            environment="prod",
        )
        evaluator = ConditionEvaluator(ctx)

        conditions = [
            {
                "name": "freeze",
                "when": "freeze_period('2024-12-20', '2025-01-02')",
                "blocking": 100,
            },
            {
                "name": "low_budget",
                "when": "budget_remaining < 20",
                "blocking": 50,
            },
            {
                "name": "peak_hours",
                "when": "peak_traffic() AND tier == 'critical'",
                "blocking": 30,
            },
            {
                "name": "business_hours",
                "when": "business_hours()",
                "blocking": 10,
            },
        ]

        should_apply, matched = evaluator.evaluate_all(conditions)
        assert should_apply is True
        # Peak traffic (11 AM is in 10-12) AND critical tier has blocking=30
        # Business hours also matches with blocking=10
        # Peak should win
        assert matched["name"] == "peak_hours"
