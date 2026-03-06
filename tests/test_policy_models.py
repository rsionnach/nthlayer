"""Tests for policy engine models."""

from __future__ import annotations

from nthlayer.policies.models import (
    PolicyReport,
    PolicyRule,
    PolicySeverity,
    PolicyViolation,
    RuleType,
)


class TestPolicyRule:
    def test_construction_defaults(self):
        rule = PolicyRule(name="test-rule", type=RuleType.required_fields)
        assert rule.name == "test-rule"
        assert rule.type == RuleType.required_fields
        assert rule.severity == PolicySeverity.error
        assert rule.params == {}
        assert rule.description is None

    def test_construction_all_fields(self):
        rule = PolicyRule(
            name="tier-check",
            type=RuleType.tier_constraint,
            severity=PolicySeverity.warning,
            params={"tier": "critical", "min_slos": 2},
            description="Check tier constraints",
        )
        assert rule.severity == PolicySeverity.warning
        assert rule.params["min_slos"] == 2
        assert rule.description == "Check tier constraints"


class TestPolicyViolation:
    def test_construction(self):
        v = PolicyViolation(
            rule_name="require-ownership",
            rule_type=RuleType.required_fields,
            severity=PolicySeverity.error,
            message="Required field 'ownership.runbook' is missing",
            field_path="ownership.runbook",
        )
        assert v.rule_name == "require-ownership"
        assert v.field_path == "ownership.runbook"

    def test_field_path_optional(self):
        v = PolicyViolation(
            rule_name="test",
            rule_type=RuleType.tier_constraint,
            severity=PolicySeverity.warning,
            message="Some warning",
        )
        assert v.field_path is None


class TestPolicyReport:
    def test_empty_report_passes(self):
        report = PolicyReport(service="test-service")
        assert report.passed is True
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.rules_evaluated == 0

    def test_report_with_errors_fails(self):
        report = PolicyReport(
            service="test-service",
            violations=[
                PolicyViolation(
                    rule_name="r1",
                    rule_type=RuleType.required_fields,
                    severity=PolicySeverity.error,
                    message="Missing field",
                ),
            ],
            rules_evaluated=1,
        )
        assert report.passed is False
        assert report.error_count == 1
        assert report.warning_count == 0

    def test_report_with_only_warnings_passes(self):
        report = PolicyReport(
            service="test-service",
            violations=[
                PolicyViolation(
                    rule_name="r1",
                    rule_type=RuleType.dependency_rule,
                    severity=PolicySeverity.warning,
                    message="Advisory",
                ),
            ],
            rules_evaluated=1,
        )
        assert report.passed is True
        assert report.error_count == 0
        assert report.warning_count == 1

    def test_report_with_mixed_violations(self):
        report = PolicyReport(
            service="test-service",
            violations=[
                PolicyViolation(
                    rule_name="r1",
                    rule_type=RuleType.required_fields,
                    severity=PolicySeverity.error,
                    message="Error",
                ),
                PolicyViolation(
                    rule_name="r2",
                    rule_type=RuleType.tier_constraint,
                    severity=PolicySeverity.warning,
                    message="Warning",
                ),
                PolicyViolation(
                    rule_name="r3",
                    rule_type=RuleType.required_fields,
                    severity=PolicySeverity.error,
                    message="Another error",
                ),
            ],
            rules_evaluated=3,
        )
        assert report.passed is False
        assert report.error_count == 2
        assert report.warning_count == 1


class TestRuleType:
    def test_enum_values(self):
        assert RuleType.required_fields == "required_fields"
        assert RuleType.tier_constraint == "tier_constraint"
        assert RuleType.dependency_rule == "dependency_rule"


class TestPolicySeverity:
    def test_enum_values(self):
        assert PolicySeverity.error == "error"
        assert PolicySeverity.warning == "warning"
