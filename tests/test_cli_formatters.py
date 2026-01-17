"""Tests for CLI output formatters.

Tests for json, sarif, junit, and markdown formatters
used in NthLayer CI/CD integration.
"""

import json
import xml.etree.ElementTree as ET

import pytest

from nthlayer.cli.formatters import (
    CheckResult,
    CheckStatus,
    OutputFormat,
    ReliabilityReport,
    SARIF_RULES,
    format_report,
)
from nthlayer.cli.formatters.json_fmt import format_json
from nthlayer.cli.formatters.junit import format_junit
from nthlayer.cli.formatters.markdown import format_markdown
from nthlayer.cli.formatters.sarif import format_sarif


@pytest.fixture
def passing_report():
    """Create a report with all passing checks."""
    return ReliabilityReport(
        service="test-service",
        command="plan",
        checks=[
            CheckResult(
                name="SLO Definition",
                status=CheckStatus.PASS,
                message="3 SLOs defined",
                details={"slo_count": 3},
            ),
            CheckResult(
                name="Alert Generation",
                status=CheckStatus.PASS,
                message="15 alerts generated",
                details={"alert_count": 15},
            ),
        ],
        summary={"total_resources": 18},
        metadata={"service_yaml": "test-service.yaml"},
    )


@pytest.fixture
def failing_report():
    """Create a report with failing checks."""
    return ReliabilityReport(
        service="failing-service",
        command="validate-slo",
        checks=[
            CheckResult(
                name="SLO Feasibility",
                status=CheckStatus.FAIL,
                message="Target 99.99% exceeds ceiling 99.84%",
                details={
                    "target": 99.99,
                    "ceiling": 99.84,
                    "recommendation": "Lower SLO target or improve dependencies",
                },
                rule_id="NTHLAYER001",
                location="service.yaml",
                line=15,
            ),
            CheckResult(
                name="Metric Missing",
                status=CheckStatus.FAIL,
                message="Required metric http_requests_total not found",
                rule_id="NTHLAYER003",
                location="service.yaml",
                line=22,
            ),
        ],
        summary={"errors": 2},
    )


@pytest.fixture
def warning_report():
    """Create a report with warning checks."""
    return ReliabilityReport(
        service="warning-service",
        command="drift",
        checks=[
            CheckResult(
                name="Drift Detection",
                status=CheckStatus.WARN,
                message="Error budget projected to exhaust in 23 days",
                details={
                    "days_remaining": 23,
                    "burn_rate": 1.3,
                    "budget_remaining": 0.45,
                },
                rule_id="NTHLAYER002",
            ),
            CheckResult(
                name="Budget Status",
                status=CheckStatus.PASS,
                message="45% budget remaining",
            ),
        ],
    )


@pytest.fixture
def mixed_report():
    """Create a report with mixed check statuses."""
    return ReliabilityReport(
        service="mixed-service",
        command="blast-radius",
        checks=[
            CheckResult(
                name="Blast Radius",
                status=CheckStatus.WARN,
                message="Change affects 3 critical downstream services",
                details={
                    "affected_services": [
                        {"name": "payment-api", "tier": "critical"},
                        {"name": "checkout-api", "tier": "critical"},
                        {"name": "order-api", "tier": "critical"},
                    ]
                },
                rule_id="NTHLAYER005",
            ),
            CheckResult(
                name="Tier Mismatch",
                status=CheckStatus.WARN,
                message="Standard tier service depended on by critical tier",
                rule_id="NTHLAYER006",
            ),
            CheckResult(
                name="Ownership",
                status=CheckStatus.SKIP,
                message="Skipped - no ownership data available",
            ),
            CheckResult(
                name="SLO Check",
                status=CheckStatus.PASS,
                message="SLO targets achievable",
            ),
        ],
    )


class TestReliabilityReport:
    """Tests for ReliabilityReport model."""

    def test_status_with_failures(self, failing_report):
        """Test that status is FAIL when there are failures."""
        assert failing_report.status == CheckStatus.FAIL

    def test_status_with_warnings(self, warning_report):
        """Test that status is WARN when there are only warnings."""
        assert warning_report.status == CheckStatus.WARN

    def test_status_with_passes(self, passing_report):
        """Test that status is PASS when all checks pass."""
        assert passing_report.status == CheckStatus.PASS

    def test_errors_count(self, failing_report):
        """Test error count."""
        assert failing_report.errors == 2

    def test_warnings_count(self, warning_report):
        """Test warning count."""
        assert warning_report.warnings == 1

    def test_passed_count(self, passing_report):
        """Test passed count."""
        assert passing_report.passed == 2

    def test_mixed_counts(self, mixed_report):
        """Test counts with mixed statuses."""
        assert mixed_report.errors == 0
        assert mixed_report.warnings == 2
        assert mixed_report.passed == 1


class TestFormatReport:
    """Tests for format_report dispatcher."""

    def test_format_table(self, passing_report):
        """Test table format output."""
        output = format_report(passing_report, OutputFormat.TABLE)
        assert "test-service" in output
        assert "SLO Definition" in output
        assert "PASS" in output

    def test_format_json(self, passing_report):
        """Test JSON format output."""
        output = format_report(passing_report, OutputFormat.JSON)
        data = json.loads(output)
        assert data["service"] == "test-service"

    def test_format_sarif(self, failing_report):
        """Test SARIF format output."""
        output = format_report(failing_report, OutputFormat.SARIF)
        data = json.loads(output)
        assert data["version"] == "2.1.0"

    def test_format_junit(self, passing_report):
        """Test JUnit format output."""
        output = format_report(passing_report, OutputFormat.JUNIT)
        assert '<?xml version="1.0"' in output
        assert "testsuite" in output

    def test_format_markdown(self, passing_report):
        """Test Markdown format output."""
        output = format_report(passing_report, OutputFormat.MARKDOWN)
        assert "## " in output
        assert "test-service" in output

    def test_format_string_input(self, passing_report):
        """Test format_report with string format."""
        output = format_report(passing_report, "json")
        data = json.loads(output)
        assert data["service"] == "test-service"

    def test_format_output_to_file(self, passing_report, tmp_path):
        """Test writing output to file."""
        output_file = tmp_path / "output.json"
        format_report(passing_report, OutputFormat.JSON, output_file=output_file)
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["service"] == "test-service"


class TestJsonFormatter:
    """Tests for JSON formatter."""

    def test_json_structure(self, passing_report):
        """Test JSON output has correct structure."""
        output = format_json(passing_report)
        data = json.loads(output)

        assert "version" in data
        assert "timestamp" in data
        assert "service" in data
        assert "command" in data
        assert "checks" in data
        assert "summary" in data

    def test_json_service_info(self, passing_report):
        """Test JSON contains service info."""
        output = format_json(passing_report)
        data = json.loads(output)

        assert data["service"] == "test-service"
        assert data["command"] == "plan"

    def test_json_checks(self, passing_report):
        """Test JSON contains check results."""
        output = format_json(passing_report)
        data = json.loads(output)

        assert "slo_definition" in data["checks"]
        assert data["checks"]["slo_definition"]["status"] == "pass"
        assert data["checks"]["slo_definition"]["slo_count"] == 3

    def test_json_summary(self, passing_report):
        """Test JSON contains summary."""
        output = format_json(passing_report)
        data = json.loads(output)

        assert data["summary"]["status"] == "pass"
        assert data["summary"]["passed"] == 2
        assert data["summary"]["total_resources"] == 18

    def test_json_metadata(self, passing_report):
        """Test JSON contains metadata."""
        output = format_json(passing_report)
        data = json.loads(output)

        assert "metadata" in data
        assert data["metadata"]["service_yaml"] == "test-service.yaml"


class TestSarifFormatter:
    """Tests for SARIF formatter."""

    def test_sarif_schema(self, failing_report):
        """Test SARIF output has correct schema."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        assert "$schema" in data
        assert "sarif-schema-2.1.0" in data["$schema"]
        assert data["version"] == "2.1.0"

    def test_sarif_tool_info(self, failing_report):
        """Test SARIF contains tool information."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        driver = data["runs"][0]["tool"]["driver"]
        assert driver["name"] == "NthLayer"
        assert "version" in driver
        assert driver["informationUri"] == "https://github.com/rsionnach/nthlayer"

    def test_sarif_rules(self, failing_report):
        """Test SARIF contains rules for used rule IDs."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        rules = data["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = [r["id"] for r in rules]
        assert "NTHLAYER001" in rule_ids
        assert "NTHLAYER003" in rule_ids

    def test_sarif_results(self, failing_report):
        """Test SARIF contains results for failures."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        results = data["runs"][0]["results"]
        assert len(results) == 2

        # Check first result
        result = results[0]
        assert result["ruleId"] == "NTHLAYER001"
        assert result["level"] == "error"
        assert "99.99%" in result["message"]["text"]

    def test_sarif_locations(self, failing_report):
        """Test SARIF results have locations."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        result = data["runs"][0]["results"][0]
        assert "locations" in result
        location = result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "service.yaml"
        assert location["region"]["startLine"] == 15

    def test_sarif_skips_passing_checks(self, passing_report):
        """Test SARIF doesn't include passing checks."""
        output = format_sarif(passing_report)
        data = json.loads(output)

        results = data["runs"][0]["results"]
        assert len(results) == 0

    def test_sarif_invocation_success(self, passing_report):
        """Test SARIF invocation shows success for passing report."""
        output = format_sarif(passing_report)
        data = json.loads(output)

        invocation = data["runs"][0]["invocations"][0]
        assert invocation["executionSuccessful"] is True

    def test_sarif_invocation_failure(self, failing_report):
        """Test SARIF invocation shows failure for failing report."""
        output = format_sarif(failing_report)
        data = json.loads(output)

        invocation = data["runs"][0]["invocations"][0]
        assert invocation["executionSuccessful"] is False

    def test_sarif_warning_level(self, warning_report):
        """Test SARIF uses warning level for warnings."""
        output = format_sarif(warning_report)
        data = json.loads(output)

        results = data["runs"][0]["results"]
        assert len(results) == 1
        assert results[0]["level"] == "warning"

    def test_sarif_rule_inference(self):
        """Test SARIF infers rule IDs from check names."""
        report = ReliabilityReport(
            service="test",
            command="test",
            checks=[
                CheckResult(
                    name="Budget Exhausted",
                    status=CheckStatus.FAIL,
                    message="Budget depleted",
                ),
                CheckResult(
                    name="Owner Missing",
                    status=CheckStatus.WARN,
                    message="No owner defined",
                ),
                CheckResult(
                    name="Runbook Missing",
                    status=CheckStatus.WARN,
                    message="No runbook URL",
                ),
            ],
        )
        output = format_sarif(report)
        data = json.loads(output)

        results = data["runs"][0]["results"]
        rule_ids = [r["ruleId"] for r in results]
        assert "NTHLAYER004" in rule_ids  # BudgetExhausted
        assert "NTHLAYER007" in rule_ids  # OwnershipMissing
        assert "NTHLAYER008" in rule_ids  # RunbookMissing


class TestJunitFormatter:
    """Tests for JUnit formatter."""

    def test_junit_xml_valid(self, passing_report):
        """Test JUnit output is valid XML."""
        output = format_junit(passing_report)
        # Should not raise
        ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

    def test_junit_structure(self, passing_report):
        """Test JUnit has correct structure."""
        output = format_junit(passing_report)
        assert '<?xml version="1.0"' in output
        assert "<testsuites" in output
        assert "<testsuite" in output
        assert "<testcase" in output

    def test_junit_counts(self, passing_report):
        """Test JUnit has correct test counts."""
        output = format_junit(passing_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        assert root.get("tests") == "2"
        assert root.get("failures") == "0"

    def test_junit_testcase_names(self, passing_report):
        """Test JUnit testcases have correct names."""
        output = format_junit(passing_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        testcases = root.findall(".//testcase")
        names = [tc.get("name") for tc in testcases]
        assert "SLO Definition" in names
        assert "Alert Generation" in names

    def test_junit_failure_element(self, failing_report):
        """Test JUnit has failure elements for failed checks."""
        output = format_junit(failing_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        failures = root.findall(".//failure")
        assert len(failures) == 2
        assert "99.99%" in failures[0].get("message")

    def test_junit_warning_in_system_out(self, warning_report):
        """Test JUnit puts warnings in system-out."""
        output = format_junit(warning_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        system_outs = root.findall(".//system-out")
        assert len(system_outs) == 1
        assert "WARNING" in system_outs[0].text

    def test_junit_skipped_element(self, mixed_report):
        """Test JUnit has skipped elements for skipped checks."""
        output = format_junit(mixed_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        skipped = root.findall(".//skipped")
        assert len(skipped) == 1

    def test_junit_classname(self, passing_report):
        """Test JUnit testcases have correct classname."""
        output = format_junit(passing_report)
        root = ET.fromstring(output.replace('<?xml version="1.0" encoding="UTF-8"?>\n', ""))

        testcase = root.find(".//testcase")
        assert testcase.get("classname") == "test-service.plan"


class TestMarkdownFormatter:
    """Tests for Markdown formatter."""

    def test_markdown_header(self, passing_report):
        """Test Markdown has header."""
        output = format_markdown(passing_report)
        assert "## " in output
        assert "NthLayer" in output
        assert "test-service" in output

    def test_markdown_comment_marker(self, passing_report):
        """Test Markdown has comment marker for updates."""
        output = format_markdown(passing_report)
        assert "<!-- nthlayer -->" in output

    def test_markdown_table(self, passing_report):
        """Test Markdown has results table."""
        output = format_markdown(passing_report)
        assert "| Check | Status | Details |" in output
        assert "|-------|--------|---------|" in output
        assert "SLO Definition" in output

    def test_markdown_pass_icon(self, passing_report):
        """Test Markdown uses pass icon."""
        output = format_markdown(passing_report)
        assert "✅" in output
        assert "Pass" in output

    def test_markdown_fail_icon(self, failing_report):
        """Test Markdown uses fail icon."""
        output = format_markdown(failing_report)
        assert "❌" in output
        assert "Fail" in output

    def test_markdown_warn_icon(self, warning_report):
        """Test Markdown uses warning icon."""
        output = format_markdown(warning_report)
        assert "⚠️" in output
        assert "Warning" in output

    def test_markdown_skip_icon(self, mixed_report):
        """Test Markdown uses skip icon."""
        output = format_markdown(mixed_report)
        assert "⏭️" in output
        assert "Skipped" in output

    def test_markdown_collapsible_details(self, failing_report):
        """Test Markdown has collapsible details for failures."""
        output = format_markdown(failing_report)
        assert "<details>" in output
        assert "<summary>" in output
        assert "</details>" in output

    def test_markdown_details_content(self, failing_report):
        """Test Markdown details contain check information."""
        output = format_markdown(failing_report)
        assert "99.99%" in output
        assert "99.84%" in output

    def test_markdown_nested_dict_details(self, failing_report):
        """Test Markdown formats nested dict details."""
        output = format_markdown(failing_report)
        # Should contain formatted key-value pairs
        assert "Target" in output or "target" in output

    def test_markdown_list_details(self, mixed_report):
        """Test Markdown formats list details as table."""
        output = format_markdown(mixed_report)
        # Should contain table for affected_services list
        assert "payment-api" in output

    def test_markdown_footer(self, passing_report):
        """Test Markdown has footer with links."""
        output = format_markdown(passing_report)
        assert "---" in output
        assert "NthLayer" in output
        assert "github.com" in output or "rsionnach" in output

    def test_markdown_check_emoji(self, failing_report):
        """Test Markdown uses appropriate emoji for check types."""
        report = ReliabilityReport(
            service="test",
            command="test",
            checks=[
                CheckResult(name="SLO Feasibility", status=CheckStatus.FAIL, message="Test"),
                CheckResult(name="Drift Detection", status=CheckStatus.WARN, message="Test"),
                CheckResult(name="Budget Status", status=CheckStatus.WARN, message="Test"),
                CheckResult(name="Blast Radius", status=CheckStatus.WARN, message="Test"),
                CheckResult(name="Dependency Check", status=CheckStatus.WARN, message="Test"),
                CheckResult(name="Owner Missing", status=CheckStatus.WARN, message="Test"),
            ],
        )
        output = format_markdown(report)
        # Check that emojis are present (specific emojis depend on check names)
        assert (
            "📊" in output
            or "📈" in output
            or "💰" in output
            or "💥" in output
            or "🔗" in output
            or "👤" in output
        )


class TestSarifRules:
    """Tests for SARIF rule definitions."""

    def test_all_rules_have_required_fields(self):
        """Test all SARIF rules have required fields."""
        required_fields = [
            "id",
            "name",
            "shortDescription",
            "fullDescription",
            "helpUri",
            "defaultConfiguration",
        ]
        for rule_id, rule in SARIF_RULES.items():
            for field in required_fields:
                assert field in rule, f"Rule {rule_id} missing field {field}"

    def test_rule_ids_match(self):
        """Test rule IDs match dictionary keys."""
        for rule_id, rule in SARIF_RULES.items():
            assert rule["id"] == rule_id

    def test_all_rules_have_level(self):
        """Test all rules have a default level."""
        valid_levels = {"error", "warning", "note", "none"}
        for rule_id, rule in SARIF_RULES.items():
            level = rule["defaultConfiguration"]["level"]
            assert level in valid_levels, f"Rule {rule_id} has invalid level {level}"
