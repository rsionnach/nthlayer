"""Tests for metadata validation."""

import pytest
import yaml
from nthlayer.validation import (
    AlertForDuration,
    HasRequiredAnnotations,
    HasRequiredLabels,
    LabelMatchesPattern,
    MetadataValidator,
    NoEmptyAnnotations,
    NoEmptyLabels,
    RangeQueryMaxDuration,
    RuleContext,
    RuleNamePattern,
    Severity,
    ValidRunbookUrl,
    ValidSeverityLevel,
    validate_metadata,
)


@pytest.fixture
def sample_rule():
    """Create a sample rule for testing."""
    return RuleContext(
        name="TestAlert",
        expr='sum(rate(http_requests_total{status="5xx"}[5m])) > 10',
        labels={
            "severity": "critical",
            "team": "platform",
            "service": "payment-api",
        },
        annotations={
            "summary": "High error rate",
            "description": "Error rate is above threshold",
            "runbook_url": "https://runbooks.example.com/high-error-rate",
        },
        for_duration="5m",
    )


@pytest.fixture
def incomplete_rule():
    """Create a rule missing required fields."""
    return RuleContext(
        name="IncompleteAlert",
        expr="up == 0",
        labels={},
        annotations={},
    )


class TestHasRequiredLabels:
    """Test HasRequiredLabels validator."""

    def test_passes_when_all_labels_present(self, sample_rule):
        validator = HasRequiredLabels(["severity", "team"])
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_fails_when_label_missing(self, sample_rule):
        validator = HasRequiredLabels(["severity", "tier"])  # 'tier' is missing
        issues = validator.validate(sample_rule)
        assert len(issues) == 1
        assert issues[0].is_error
        assert "tier" in issues[0].message

    def test_fails_multiple_missing_labels(self, incomplete_rule):
        validator = HasRequiredLabels(["severity", "team", "service"])
        issues = validator.validate(incomplete_rule)
        assert len(issues) == 3


class TestHasRequiredAnnotations:
    """Test HasRequiredAnnotations validator."""

    def test_passes_when_all_annotations_present(self, sample_rule):
        validator = HasRequiredAnnotations(["summary", "description"])
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_fails_when_annotation_missing(self, incomplete_rule):
        validator = HasRequiredAnnotations(["summary"])
        issues = validator.validate(incomplete_rule)
        assert len(issues) == 1
        assert "summary" in issues[0].message


class TestLabelMatchesPattern:
    """Test LabelMatchesPattern validator."""

    def test_passes_when_pattern_matches(self, sample_rule):
        validator = LabelMatchesPattern({"severity": r"^(critical|warning|info)$"})
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_fails_when_pattern_not_matched(self, sample_rule):
        validator = LabelMatchesPattern({"severity": r"^(low|medium|high)$"})
        issues = validator.validate(sample_rule)
        assert len(issues) == 1
        assert "pattern" in issues[0].message

    def test_skips_missing_labels(self, incomplete_rule):
        validator = LabelMatchesPattern({"severity": r".*"})
        issues = validator.validate(incomplete_rule)
        assert len(issues) == 0  # Don't report missing as pattern mismatch


class TestValidSeverityLevel:
    """Test ValidSeverityLevel validator."""

    def test_passes_valid_severity(self, sample_rule):
        validator = ValidSeverityLevel()
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_fails_invalid_severity(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={"severity": "severe"},  # Invalid
            annotations={},
        )
        validator = ValidSeverityLevel()
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert "Invalid severity" in issues[0].message

    def test_custom_severities(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={"severity": "p1"},
            annotations={},
        )
        validator = ValidSeverityLevel(valid_severities={"p1", "p2", "p3"})
        issues = validator.validate(rule)
        assert len(issues) == 0


class TestValidRunbookUrl:
    """Test ValidRunbookUrl validator."""

    def test_passes_valid_url(self, sample_rule):
        validator = ValidRunbookUrl()
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_passes_no_runbook_url(self, incomplete_rule):
        validator = ValidRunbookUrl()
        issues = validator.validate(incomplete_rule)
        assert len(issues) == 0  # Not required, just validated if present

    def test_fails_missing_scheme(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={},
            annotations={"runbook_url": "example.com/runbook"},
        )
        validator = ValidRunbookUrl()
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert "scheme" in issues[0].message

    def test_fails_missing_host(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={},
            annotations={"runbook_url": "https:///path"},
        )
        validator = ValidRunbookUrl()
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert "host" in issues[0].message


class TestRangeQueryMaxDuration:
    """Test RangeQueryMaxDuration validator."""

    def test_passes_normal_range(self, sample_rule):
        validator = RangeQueryMaxDuration(max_duration="15d")
        issues = validator.validate(sample_rule)
        assert len(issues) == 0  # [5m] is within 15d

    def test_warns_large_range(self):
        rule = RuleContext(
            name="Test",
            expr="avg_over_time(cpu_usage[30d])",  # 30 days
            labels={},
            annotations={},
        )
        validator = RangeQueryMaxDuration(max_duration="15d")
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "exceed data retention" in issues[0].message


class TestAlertForDuration:
    """Test AlertForDuration validator."""

    def test_passes_normal_duration(self, sample_rule):
        validator = AlertForDuration(min_duration="0s", max_duration="1h")
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_warns_very_long_duration(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={},
            annotations={},
            for_duration="2h",  # 2 hours
        )
        validator = AlertForDuration(max_duration="1h")
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert "very long" in issues[0].message


class TestNoEmptyLabels:
    """Test NoEmptyLabels validator."""

    def test_passes_non_empty(self, sample_rule):
        validator = NoEmptyLabels()
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_fails_empty_label(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={"severity": "", "team": "platform"},
            annotations={},
        )
        validator = NoEmptyLabels()
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert "severity" in issues[0].message


class TestNoEmptyAnnotations:
    """Test NoEmptyAnnotations validator."""

    def test_passes_non_empty(self, sample_rule):
        validator = NoEmptyAnnotations()
        issues = validator.validate(sample_rule)
        assert len(issues) == 0

    def test_warns_empty_annotation(self):
        rule = RuleContext(
            name="Test",
            expr="up == 0",
            labels={},
            annotations={"summary": "OK", "description": ""},
        )
        validator = NoEmptyAnnotations()
        issues = validator.validate(rule)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING


class TestRuleNamePattern:
    """Test RuleNamePattern validator."""

    def test_passes_camel_case(self, sample_rule):
        validator = RuleNamePattern()
        issues = validator.validate(sample_rule)
        assert len(issues) == 0  # "TestAlert" matches ^[A-Z][a-zA-Z0-9_]+$

    def test_warns_snake_case(self):
        rule = RuleContext(
            name="test_alert",  # snake_case
            expr="up == 0",
            labels={},
            annotations={},
        )
        validator = RuleNamePattern()
        issues = validator.validate(rule)
        assert len(issues) == 1

    def test_custom_pattern(self):
        rule = RuleContext(
            name="my_custom_alert",
            expr="up == 0",
            labels={},
            annotations={},
        )
        validator = RuleNamePattern(pattern=r"^[a-z_]+$")
        issues = validator.validate(rule)
        assert len(issues) == 0


class TestMetadataValidator:
    """Test MetadataValidator composite."""

    def test_default_validators(self, sample_rule):
        validator = MetadataValidator.default()
        issues = validator.validate_rule(sample_rule)
        assert len(issues) == 0

    def test_strict_validators(self, sample_rule):
        validator = MetadataValidator.strict()
        issues = validator.validate_rule(sample_rule)
        assert len(issues) == 0

    def test_strict_fails_without_runbook(self, incomplete_rule):
        validator = MetadataValidator.strict()
        issues = validator.validate_rule(incomplete_rule)
        assert len(issues) > 0

    def test_add_custom_validator(self, sample_rule):
        validator = MetadataValidator()
        validator.add_validator(HasRequiredLabels(["custom_label"]))
        issues = validator.validate_rule(sample_rule)
        assert len(issues) == 1
        assert "custom_label" in issues[0].message

    def test_validate_file(self, tmp_path):
        """Test validating a real YAML file."""
        rules_content = {
            "groups": [
                {
                    "name": "test-group",
                    "rules": [
                        {
                            "alert": "TestAlert",
                            "expr": "up == 0",
                            "for": "5m",
                            "labels": {"severity": "critical"},
                            "annotations": {
                                "summary": "Test summary",
                                "description": "Test description",
                            },
                        }
                    ],
                }
            ]
        }

        rules_file = tmp_path / "alerts.yaml"
        with open(rules_file, "w") as f:
            yaml.dump(rules_content, f)

        validator = MetadataValidator.default()
        result = validator.validate_file(rules_file)

        assert result.rules_checked == 1
        assert result.passed


class TestValidateMetadataFunction:
    """Test the convenience validate_metadata function."""

    def test_default_validation(self, tmp_path):
        rules_content = {
            "groups": [
                {
                    "name": "test",
                    "rules": [
                        {
                            "alert": "ValidAlert",
                            "expr": "up == 0",
                            "labels": {"severity": "warning"},
                            "annotations": {
                                "summary": "Test",
                                "description": "Test desc",
                            },
                        }
                    ],
                }
            ]
        }

        rules_file = tmp_path / "alerts.yaml"
        with open(rules_file, "w") as f:
            yaml.dump(rules_content, f)

        result = validate_metadata(rules_file)
        assert result.passed

    def test_strict_validation(self, tmp_path):
        # Missing runbook_url in strict mode
        rules_content = {
            "groups": [
                {
                    "name": "test",
                    "rules": [
                        {
                            "alert": "MissingRunbook",
                            "expr": "up == 0",
                            "labels": {
                                "severity": "warning",
                                "team": "platform",
                                "service": "api",
                            },
                            "annotations": {
                                "summary": "Test",
                                "description": "Test desc",
                            },
                        }
                    ],
                }
            ]
        }

        rules_file = tmp_path / "alerts.yaml"
        with open(rules_file, "w") as f:
            yaml.dump(rules_content, f)

        result = validate_metadata(rules_file, strict=True)
        assert not result.passed
        assert any("runbook_url" in issue.message for issue in result.issues)

    def test_file_not_found(self):
        result = validate_metadata("/nonexistent/file.yaml")
        assert not result.passed
        assert "not found" in result.issues[0].message.lower()
