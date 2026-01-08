"""Tests for slos/alerts.py.

Tests for alert rules, evaluation, and storage.
"""

from datetime import datetime

import pytest
from nthlayer.slos.alerts import (
    AlertEvaluator,
    AlertEvent,
    AlertRule,
    AlertRuleStorage,
    AlertSeverity,
    AlertType,
    get_alert_storage,
)
from nthlayer.slos.models import ErrorBudget, SLOStatus


@pytest.fixture
def sample_budget():
    """Create a sample error budget."""
    return ErrorBudget(
        slo_id="slo-001",
        service="test-service",
        period_start=datetime(2025, 1, 1),
        period_end=datetime(2025, 1, 31),
        total_budget_minutes=43.2,  # 30 days * 1440 min * 0.001
        burned_minutes=21.6,
        remaining_minutes=21.6,
        burn_rate=1.0,
        status=SLOStatus.HEALTHY,
    )


@pytest.fixture
def threshold_rule():
    """Create a budget threshold alert rule."""
    return AlertRule(
        id="rule-001",
        service="test-service",
        slo_id="slo-001",
        alert_type=AlertType.BUDGET_THRESHOLD,
        severity=AlertSeverity.WARNING,
        threshold=0.75,
        slack_webhook="https://hooks.slack.com/test",
    )


@pytest.fixture
def burn_rate_rule():
    """Create a burn rate alert rule."""
    return AlertRule(
        id="rule-002",
        service="test-service",
        slo_id="slo-001",
        alert_type=AlertType.BURN_RATE,
        severity=AlertSeverity.CRITICAL,
        threshold=3.0,
        pagerduty_key="test-key",
    )


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_info_value(self):
        """Test INFO severity value."""
        assert AlertSeverity.INFO.value == "info"

    def test_warning_value(self):
        """Test WARNING severity value."""
        assert AlertSeverity.WARNING.value == "warning"

    def test_critical_value(self):
        """Test CRITICAL severity value."""
        assert AlertSeverity.CRITICAL.value == "critical"


class TestAlertType:
    """Tests for AlertType enum."""

    def test_budget_threshold_value(self):
        """Test BUDGET_THRESHOLD type value."""
        assert AlertType.BUDGET_THRESHOLD.value == "budget_threshold"

    def test_burn_rate_value(self):
        """Test BURN_RATE type value."""
        assert AlertType.BURN_RATE.value == "burn_rate"

    def test_budget_exhaustion_value(self):
        """Test BUDGET_EXHAUSTION type value."""
        assert AlertType.BUDGET_EXHAUSTION.value == "budget_exhaustion"


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_create_minimal_rule(self):
        """Test creating rule with minimal fields."""
        rule = AlertRule(
            id="test-rule",
            service="my-service",
            slo_id="my-slo",
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.WARNING,
            threshold=0.5,
        )

        assert rule.id == "test-rule"
        assert rule.service == "my-service"
        assert rule.slo_id == "my-slo"
        assert rule.threshold == 0.5
        assert rule.enabled is True
        assert rule.slack_webhook is None
        assert rule.pagerduty_key is None

    def test_create_full_rule(self):
        """Test creating rule with all fields."""
        rule = AlertRule(
            id="test-rule",
            service="my-service",
            slo_id="my-slo",
            alert_type=AlertType.BURN_RATE,
            severity=AlertSeverity.CRITICAL,
            threshold=3.0,
            slack_webhook="https://hooks.slack.com/test",
            pagerduty_key="pd-key",
            enabled=False,
        )

        assert rule.enabled is False
        assert rule.slack_webhook == "https://hooks.slack.com/test"
        assert rule.pagerduty_key == "pd-key"

    def test_to_dict(self, threshold_rule):
        """Test converting rule to dictionary."""
        result = threshold_rule.to_dict()

        assert result["id"] == "rule-001"
        assert result["service"] == "test-service"
        assert result["slo_id"] == "slo-001"
        assert result["alert_type"] == "budget_threshold"
        assert result["severity"] == "warning"
        assert result["threshold"] == 0.75
        assert result["slack_webhook"] == "https://hooks.slack.com/test"
        assert result["pagerduty_key"] is None
        assert result["enabled"] is True
        assert "created_at" in result


class TestAlertEvent:
    """Tests for AlertEvent dataclass."""

    def test_create_event(self):
        """Test creating an alert event."""
        event = AlertEvent(
            id="event-001",
            rule_id="rule-001",
            service="test-service",
            slo_id="slo-001",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="Test message",
            details={"key": "value"},
        )

        assert event.id == "event-001"
        assert event.rule_id == "rule-001"
        assert event.title == "Test Alert"
        assert event.details == {"key": "value"}

    def test_to_dict(self):
        """Test converting event to dictionary."""
        triggered_at = datetime(2025, 1, 10, 12, 0, 0)
        event = AlertEvent(
            id="event-001",
            rule_id="rule-001",
            service="test-service",
            slo_id="slo-001",
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="Something is wrong",
            details={"burned_minutes": 10.5},
            triggered_at=triggered_at,
        )

        result = event.to_dict()

        assert result["id"] == "event-001"
        assert result["rule_id"] == "rule-001"
        assert result["service"] == "test-service"
        assert result["severity"] == "critical"
        assert result["title"] == "Critical Alert"
        assert result["details"] == {"burned_minutes": 10.5}
        assert result["triggered_at"] == "2025-01-10T12:00:00"


class TestAlertEvaluator:
    """Tests for AlertEvaluator class."""

    def test_init(self):
        """Test evaluator initialization."""
        evaluator = AlertEvaluator()
        assert evaluator is not None

    def test_evaluate_budget_threshold_not_triggered(self, sample_budget, threshold_rule):
        """Test threshold not triggered when below threshold."""
        # Budget is 50% consumed, threshold is 75%
        evaluator = AlertEvaluator()
        result = evaluator.evaluate_budget_threshold(sample_budget, threshold_rule)

        assert result is None

    def test_evaluate_budget_threshold_triggered(self, sample_budget, threshold_rule):
        """Test threshold triggered when at/above threshold."""
        # Set budget to 80% consumed: burned_minutes = 0.8 * 43.2 = 34.56
        sample_budget.burned_minutes = 34.56

        evaluator = AlertEvaluator()
        result = evaluator.evaluate_budget_threshold(sample_budget, threshold_rule)

        assert result is not None
        assert isinstance(result, AlertEvent)
        assert result.service == "test-service"
        assert result.slo_id == "slo-001"
        assert result.severity == AlertSeverity.WARNING
        assert "Error Budget Alert" in result.title
        assert result.details["budget_consumed_percent"] == 80.0
        assert result.details["threshold_percent"] == 75.0

    def test_evaluate_budget_threshold_exactly_at_threshold(self, sample_budget, threshold_rule):
        """Test threshold triggered when at or just above threshold."""
        # Slightly above 75% to avoid floating point precision issues
        # 75.5% consumed: burned_minutes = 0.755 * 43.2 = 32.616
        sample_budget.burned_minutes = 32.616

        evaluator = AlertEvaluator()
        result = evaluator.evaluate_budget_threshold(sample_budget, threshold_rule)

        assert result is not None

    def test_evaluate_burn_rate_not_triggered(self, sample_budget, burn_rate_rule):
        """Test burn rate not triggered when below threshold."""
        sample_budget.burn_rate = 2.0  # Below 3.0 threshold

        evaluator = AlertEvaluator()
        result = evaluator.evaluate_burn_rate(sample_budget, burn_rate_rule)

        assert result is None

    def test_evaluate_burn_rate_triggered(self, sample_budget, burn_rate_rule):
        """Test burn rate triggered when at/above threshold."""
        sample_budget.burn_rate = 4.0  # Above 3.0 threshold

        evaluator = AlertEvaluator()
        result = evaluator.evaluate_burn_rate(sample_budget, burn_rate_rule)

        assert result is not None
        assert isinstance(result, AlertEvent)
        assert result.severity == AlertSeverity.CRITICAL
        assert "High Burn Rate Alert" in result.title
        assert result.details["burn_rate"] == 4.0
        assert result.details["threshold"] == 3.0

    def test_evaluate_burn_rate_none_value(self, sample_budget, burn_rate_rule):
        """Test burn rate returns None when burn_rate is None."""
        sample_budget.burn_rate = None

        evaluator = AlertEvaluator()
        result = evaluator.evaluate_burn_rate(sample_budget, burn_rate_rule)

        assert result is None

    def test_evaluate_rules_all_triggered(self, sample_budget):
        """Test evaluating multiple rules, all triggered."""
        # 80% consumed: burned_minutes = 0.8 * 43.2 = 34.56
        sample_budget.burned_minutes = 34.56
        sample_budget.burn_rate = 5.0

        threshold_rule = AlertRule(
            id="rule-001",
            service="test-service",
            slo_id="slo-001",
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.WARNING,
            threshold=0.75,
        )
        burn_rule = AlertRule(
            id="rule-002",
            service="test-service",
            slo_id="slo-001",
            alert_type=AlertType.BURN_RATE,
            severity=AlertSeverity.CRITICAL,
            threshold=3.0,
        )

        evaluator = AlertEvaluator()
        events = evaluator.evaluate_rules(sample_budget, [threshold_rule, burn_rule])

        assert len(events) == 2
        assert events[0].rule_id == "rule-001"
        assert events[1].rule_id == "rule-002"

    def test_evaluate_rules_disabled_rule(self, sample_budget, threshold_rule):
        """Test disabled rules are skipped."""
        # 80% consumed: burned_minutes = 0.8 * 43.2 = 34.56
        sample_budget.burned_minutes = 34.56
        threshold_rule.enabled = False

        evaluator = AlertEvaluator()
        events = evaluator.evaluate_rules(sample_budget, [threshold_rule])

        assert len(events) == 0

    def test_evaluate_rules_empty_list(self, sample_budget):
        """Test evaluating empty rules list."""
        evaluator = AlertEvaluator()
        events = evaluator.evaluate_rules(sample_budget, [])

        assert len(events) == 0

    def test_format_threshold_message_critical(self, sample_budget, threshold_rule):
        """Test threshold message formatting for critical level."""
        # 95% consumed: burned_minutes = 0.95 * 43.2 = 41.04
        sample_budget.burned_minutes = 41.04
        threshold_rule.severity = AlertSeverity.CRITICAL

        evaluator = AlertEvaluator()
        message = evaluator._format_threshold_message(sample_budget, threshold_rule)

        assert "Error Budget Alert" in message
        assert "test-service" in message
        assert "95.0%" in message
        assert "CRITICAL" in message

    def test_format_threshold_message_warning_level(self, sample_budget, threshold_rule):
        """Test threshold message formatting for warning level (75-90%)."""
        # 80% consumed: burned_minutes = 0.8 * 43.2 = 34.56
        sample_budget.burned_minutes = 34.56
        threshold_rule.severity = AlertSeverity.WARNING

        evaluator = AlertEvaluator()
        message = evaluator._format_threshold_message(sample_budget, threshold_rule)

        assert "WARNING" in message

    def test_format_threshold_message_info_level(self, sample_budget, threshold_rule):
        """Test threshold message formatting for info level (<75%)."""
        # 60% consumed: burned_minutes = 0.6 * 43.2 = 25.92
        sample_budget.burned_minutes = 25.92
        threshold_rule.severity = AlertSeverity.INFO

        evaluator = AlertEvaluator()
        message = evaluator._format_threshold_message(sample_budget, threshold_rule)

        assert "Monitor closely" in message

    def test_format_burn_rate_message_critical(self, sample_budget, burn_rate_rule):
        """Test burn rate message formatting for critical rate (>=6x)."""
        sample_budget.burn_rate = 7.0

        evaluator = AlertEvaluator()
        message = evaluator._format_burn_rate_message(sample_budget, burn_rate_rule)

        assert "High Burn Rate Alert" in message
        assert "7.00x" in message
        assert "CRITICAL" in message

    def test_format_burn_rate_message_warning(self, sample_budget, burn_rate_rule):
        """Test burn rate message formatting for warning rate (3-6x)."""
        sample_budget.burn_rate = 4.0

        evaluator = AlertEvaluator()
        message = evaluator._format_burn_rate_message(sample_budget, burn_rate_rule)

        assert "Elevated burn rate" in message

    def test_format_burn_rate_message_low(self, sample_budget, burn_rate_rule):
        """Test burn rate message formatting for low rate (<3x)."""
        sample_budget.burn_rate = 2.0

        evaluator = AlertEvaluator()
        message = evaluator._format_burn_rate_message(sample_budget, burn_rate_rule)

        assert "above normal" in message

    def test_format_burn_rate_message_none_rate(self, sample_budget, burn_rate_rule):
        """Test burn rate message formatting when rate is None."""
        sample_budget.burn_rate = None

        evaluator = AlertEvaluator()
        message = evaluator._format_burn_rate_message(sample_budget, burn_rate_rule)

        assert "0.00x" in message


class TestAlertRuleStorage:
    """Tests for AlertRuleStorage class."""

    def test_init_empty(self):
        """Test storage initializes empty."""
        storage = AlertRuleStorage()
        assert storage._rules == {}

    def test_add_rule(self, threshold_rule):
        """Test adding a rule."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)

        rules = storage.get_rules("test-service")
        assert len(rules) == 1
        assert rules[0].id == "rule-001"

    def test_add_rule_replaces_existing(self, threshold_rule):
        """Test adding rule with same ID replaces existing."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)

        # Add another rule with same ID but different threshold
        updated_rule = AlertRule(
            id="rule-001",
            service="test-service",
            slo_id="slo-001",
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.CRITICAL,
            threshold=0.9,
        )
        storage.add_rule(updated_rule)

        rules = storage.get_rules("test-service")
        assert len(rules) == 1
        assert rules[0].threshold == 0.9

    def test_add_multiple_rules(self, threshold_rule, burn_rate_rule):
        """Test adding multiple rules."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)
        storage.add_rule(burn_rate_rule)

        rules = storage.get_rules("test-service")
        assert len(rules) == 2

    def test_get_rules_empty_service(self):
        """Test getting rules for service with no rules."""
        storage = AlertRuleStorage()
        rules = storage.get_rules("nonexistent-service")

        assert rules == []

    def test_get_all_rules(self, threshold_rule, burn_rate_rule):
        """Test getting all rules."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)

        # Add rule for different service
        other_rule = AlertRule(
            id="rule-003",
            service="other-service",
            slo_id="slo-002",
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.INFO,
            threshold=0.5,
        )
        storage.add_rule(other_rule)

        all_rules = storage.get_all_rules()

        assert len(all_rules) == 2
        assert "test-service" in all_rules
        assert "other-service" in all_rules

    def test_delete_rule_success(self, threshold_rule):
        """Test successfully deleting a rule."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)

        result = storage.delete_rule("rule-001", "test-service")

        assert result is True
        assert len(storage.get_rules("test-service")) == 0

    def test_delete_rule_not_found(self):
        """Test deleting nonexistent rule."""
        storage = AlertRuleStorage()

        result = storage.delete_rule("nonexistent", "test-service")

        assert result is False

    def test_delete_rule_wrong_service(self, threshold_rule):
        """Test deleting rule from wrong service."""
        storage = AlertRuleStorage()
        storage.add_rule(threshold_rule)

        result = storage.delete_rule("rule-001", "other-service")

        assert result is False
        # Rule still exists in original service
        assert len(storage.get_rules("test-service")) == 1


class TestGetAlertStorage:
    """Tests for get_alert_storage function."""

    def test_returns_storage_instance(self):
        """Test function returns AlertRuleStorage instance."""
        storage = get_alert_storage()
        assert isinstance(storage, AlertRuleStorage)

    def test_returns_same_instance(self):
        """Test function returns same global instance."""
        storage1 = get_alert_storage()
        storage2 = get_alert_storage()

        assert storage1 is storage2
