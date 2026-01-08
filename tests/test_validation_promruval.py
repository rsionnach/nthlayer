"""Tests for validation/promruval.py.

Tests for promruval binary integration including version checking,
file validation, and output parsing.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from nthlayer.validation.metadata import Severity
from nthlayer.validation.promruval import (
    PromruvalConfig,
    PromruvalLinter,
    is_promruval_available,
    validate_with_promruval,
)


class TestPromruvalConfig:
    """Tests for PromruvalConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PromruvalConfig()

        assert config.config_path is None
        assert config.enabled_validators == []
        assert config.disabled_validators == []
        assert config.output_format == "json"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PromruvalConfig(
            config_path=Path("/path/to/config.yaml"),
            enabled_validators=["hasLabels", "hasAnnotations"],
            disabled_validators=["expressionDoesNotUseOlderDataThan"],
            output_format="text",
        )

        assert config.config_path == Path("/path/to/config.yaml")
        assert config.enabled_validators == ["hasLabels", "hasAnnotations"]
        assert config.disabled_validators == ["expressionDoesNotUseOlderDataThan"]
        assert config.output_format == "text"


class TestPromruvalLinter:
    """Tests for PromruvalLinter class."""

    @patch("shutil.which")
    def test_is_available_true(self, mock_which):
        """Test is_available when promruval is installed."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        assert linter.is_available is True

    @patch("shutil.which")
    def test_is_available_false(self, mock_which):
        """Test is_available when promruval is not installed."""
        mock_which.return_value = None
        linter = PromruvalLinter()

        assert linter.is_available is False

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_version(self, mock_which, mock_run):
        """Test getting promruval version."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(stdout="promruval v1.2.3\n", stderr="")

        linter = PromruvalLinter()
        version = linter.get_version()

        assert version == "1.2.3"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_version_no_match(self, mock_which, mock_run):
        """Test getting version when format doesn't match regex."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(stdout="unknown format", stderr="")

        linter = PromruvalLinter()
        version = linter.get_version()

        assert version == "unknown format"

    @patch("shutil.which")
    def test_get_version_not_available(self, mock_which):
        """Test get_version when promruval not installed."""
        mock_which.return_value = None
        linter = PromruvalLinter()

        assert linter.get_version() is None

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_version_timeout(self, mock_which, mock_run):
        """Test get_version handles timeout."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.side_effect = subprocess.TimeoutExpired("promruval", 10)

        linter = PromruvalLinter()
        version = linter.get_version()

        assert version is None

    @patch("shutil.which")
    def test_validate_file_not_available(self, mock_which):
        """Test validate_file when promruval not installed."""
        mock_which.return_value = None
        linter = PromruvalLinter()

        result = linter.validate_file("rules.yaml")

        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.INFO
        assert "not installed" in result.issues[0].message

    @patch("shutil.which")
    def test_validate_file_not_found(self, mock_which):
        """Test validate_file with non-existent file."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        result = linter.validate_file("/nonexistent/rules.yaml")

        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.ERROR
        assert "File not found" in result.issues[0].message

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validate_file_success_json(self, mock_which, mock_run):
        """Test successful validation with JSON output."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                [
                    {
                        "severity": "warning",
                        "rule": "HighLatency",
                        "validator": "hasAnnotations",
                        "message": "Missing runbook annotation",
                    }
                ]
            ),
            stderr="",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("groups: []")
            f.flush()

            linter = PromruvalLinter()
            result = linter.validate_file(f.name)

        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING
        assert result.issues[0].rule_name == "HighLatency"
        assert "hasAnnotations" in result.issues[0].validator

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validate_file_with_config(self, mock_which, mock_run):
        """Test validation with custom config path."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(stdout="[]", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "rules.yaml"
            rules_file.write_text("groups: []")

            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("validators: []")

            config = PromruvalConfig(config_path=config_file)
            linter = PromruvalLinter(config=config)
            linter.validate_file(rules_file)

            # Verify config was passed
            call_args = mock_run.call_args[0][0]
            assert "--config" in call_args
            assert str(config_file) in call_args

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validate_file_timeout(self, mock_which, mock_run):
        """Test validation handles timeout."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.side_effect = subprocess.TimeoutExpired("promruval", 60)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("groups: []")
            f.flush()

            linter = PromruvalLinter()
            result = linter.validate_file(f.name)

        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.ERROR
        assert "timed out" in result.issues[0].message

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validate_file_subprocess_error(self, mock_which, mock_run):
        """Test validation handles subprocess error."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.side_effect = subprocess.SubprocessError("Command failed")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("groups: []")
            f.flush()

            linter = PromruvalLinter()
            result = linter.validate_file(f.name)

        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.ERROR
        assert "failed" in result.issues[0].message

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validate_file_text_output(self, mock_which, mock_run):
        """Test validation with text output format."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(
            stdout="error: missing label 'severity'\nwarning: consider adding runbook",
            stderr="",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("groups: []")
            f.flush()

            config = PromruvalConfig(output_format="text")
            linter = PromruvalLinter(config=config)
            result = linter.validate_file(f.name)

        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.ERROR  # Contains "error"
        assert result.issues[1].severity == Severity.WARNING  # Default


class TestParseJsonOutput:
    """Tests for _parse_json_output method."""

    @patch("shutil.which")
    def test_empty_output(self, mock_which):
        """Test parsing empty JSON output."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_json_output("", "")

        assert issues == []

    @patch("shutil.which")
    def test_list_format(self, mock_which):
        """Test parsing JSON list format."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        output = json.dumps(
            [
                {"severity": "error", "rule": "Test", "message": "Error 1"},
                {"severity": "warning", "rule": "Test2", "message": "Warning 1"},
            ]
        )

        issues = linter._parse_json_output(output, "")

        assert len(issues) == 2
        assert issues[0].severity == Severity.ERROR
        assert issues[1].severity == Severity.WARNING

    @patch("shutil.which")
    def test_dict_format_with_errors_and_warnings(self, mock_which):
        """Test parsing JSON dict format with errors and warnings."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        output = json.dumps(
            {
                "errors": [{"rule": "Test", "message": "Error"}],
                "warnings": [{"rule": "Test2", "message": "Warning"}],
            }
        )

        issues = linter._parse_json_output(output, "")

        assert len(issues) == 2

    @patch("shutil.which")
    def test_invalid_json_falls_back_to_text(self, mock_which):
        """Test invalid JSON falls back to text parsing."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_json_output("not json\nerror: something wrong", "")

        assert len(issues) == 2  # Two lines of text
        assert issues[0].severity == Severity.WARNING  # "not json" - no error keywords
        assert issues[1].severity == Severity.ERROR  # "error: something wrong"


class TestItemToIssue:
    """Tests for _item_to_issue method."""

    @patch("shutil.which")
    def test_error_severity(self, mock_which):
        """Test error severity mapping."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        for severity in ["error", "fatal", "bug"]:
            issue = linter._item_to_issue({"severity": severity, "message": "test"})
            assert issue.severity == Severity.ERROR

    @patch("shutil.which")
    def test_warning_severity(self, mock_which):
        """Test warning severity mapping."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"severity": "warning", "message": "test"})
        assert issue.severity == Severity.WARNING

    @patch("shutil.which")
    def test_info_severity_default(self, mock_which):
        """Test info severity as default."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"severity": "info", "message": "test"})
        assert issue.severity == Severity.INFO

    @patch("shutil.which")
    def test_uses_level_field(self, mock_which):
        """Test using 'level' field when 'severity' missing."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"level": "error", "message": "test"})
        assert issue.severity == Severity.ERROR

    @patch("shutil.which")
    def test_uses_alert_field(self, mock_which):
        """Test using 'alert' field when 'rule' missing."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"alert": "HighCPU", "message": "test"})
        assert issue.rule_name == "HighCPU"

    @patch("shutil.which")
    def test_uses_error_field(self, mock_which):
        """Test using 'error' field when 'message' missing."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"error": "Something failed"})
        assert issue.message == "Something failed"

    @patch("shutil.which")
    def test_line_number(self, mock_which):
        """Test line number is extracted."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issue = linter._item_to_issue({"message": "test", "line": 42})
        assert issue.line == 42


class TestParseTextOutput:
    """Tests for _parse_text_output method."""

    @patch("shutil.which")
    def test_empty_output(self, mock_which):
        """Test parsing empty text output."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_text_output("")

        assert issues == []

    @patch("shutil.which")
    def test_error_detection(self, mock_which):
        """Test error keyword detection."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_text_output("error: something broke")

        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR

    @patch("shutil.which")
    def test_fatal_detection(self, mock_which):
        """Test fatal keyword detection."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_text_output("fatal: crash")

        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR

    @patch("shutil.which")
    def test_invalid_detection(self, mock_which):
        """Test invalid keyword detection."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_text_output("invalid syntax at line 5")

        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR

    @patch("shutil.which")
    def test_default_warning(self, mock_which):
        """Test default severity is warning."""
        mock_which.return_value = "/usr/local/bin/promruval"
        linter = PromruvalLinter()

        issues = linter._parse_text_output("consider adding a label")

        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING


class TestListValidators:
    """Tests for list_validators method."""

    @patch("shutil.which")
    def test_not_available(self, mock_which):
        """Test list_validators when promruval not available."""
        mock_which.return_value = None
        linter = PromruvalLinter()

        validators = linter.list_validators()

        assert validators == []

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_parses_list_items(self, mock_which, mock_run):
        """Test parsing validator list from output."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.return_value = MagicMock(
            stdout="- hasLabels description\n- hasAnnotations description\n* customValidator more info",
            stderr="",
        )

        linter = PromruvalLinter()
        validators = linter.list_validators()

        assert "hasLabels" in validators
        assert "hasAnnotations" in validators
        assert "customValidator" in validators

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_handles_timeout(self, mock_which, mock_run):
        """Test handles timeout when listing validators."""
        mock_which.return_value = "/usr/local/bin/promruval"
        mock_run.side_effect = subprocess.TimeoutExpired("promruval", 10)

        linter = PromruvalLinter()
        validators = linter.list_validators()

        assert validators == []


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @patch("shutil.which")
    def test_is_promruval_available_true(self, mock_which):
        """Test is_promruval_available returns True."""
        mock_which.return_value = "/usr/local/bin/promruval"

        assert is_promruval_available() is True

    @patch("shutil.which")
    def test_is_promruval_available_false(self, mock_which):
        """Test is_promruval_available returns False."""
        mock_which.return_value = None

        assert is_promruval_available() is False

    @patch("shutil.which")
    def test_validate_with_promruval_no_config(self, mock_which):
        """Test validate_with_promruval without config."""
        mock_which.return_value = None  # Not installed

        result = validate_with_promruval("rules.yaml")

        assert len(result.issues) == 1
        assert "not installed" in result.issues[0].message

    @patch("shutil.which")
    def test_validate_with_promruval_with_config(self, mock_which):
        """Test validate_with_promruval with config path."""
        mock_which.return_value = None  # Not installed

        result = validate_with_promruval("rules.yaml", config_path="/path/to/config.yaml")

        assert len(result.issues) == 1
