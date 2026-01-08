"""Tests for cli/lint.py.

Tests for Prometheus alert linting CLI command.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.lint import _print_result, lint_command


@pytest.fixture
def sample_alerts_yaml():
    """Create sample alerts YAML content."""
    return """
groups:
  - name: test-alerts
    rules:
      - alert: HighErrorRate
        expr: error_rate > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: High error rate detected
"""


@pytest.fixture
def mock_lint_result_passed():
    """Create mock LintResult that passed."""
    result = MagicMock()
    result.passed = True
    result.file_path = "/path/to/alerts.yaml"
    result.issues = []
    result.error_count = 0
    result.warning_count = 0
    result.raw_output = ""
    return result


@pytest.fixture
def mock_lint_result_failed():
    """Create mock LintResult that failed."""
    result = MagicMock()
    result.passed = False
    result.file_path = "/path/to/alerts.yaml"

    issue = MagicMock()
    issue.is_error = True
    issue.is_warning = False
    issue.line = 10
    issue.rule_name = "promql/syntax"
    issue.check = "syntax"
    issue.message = "Invalid PromQL expression"

    result.issues = [issue]
    result.error_count = 1
    result.warning_count = 0
    result.raw_output = "syntax error at line 10"
    return result


class TestLintCommand:
    """Tests for lint_command function."""

    @patch("nthlayer.cli.lint.is_pint_available")
    def test_pint_not_available(self, mock_available):
        """Test when pint is not installed."""
        mock_available.return_value = False

        result = lint_command("/any/path.yaml")

        assert result == 1

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_single_file_passed(
        self, mock_linter_class, mock_available, sample_alerts_yaml, mock_lint_result_passed
    ):
        """Test linting single file that passes."""
        mock_available.return_value = True
        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_lint_result_passed
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(sample_alerts_yaml)

            result = lint_command(str(alerts_file))

        assert result == 0
        mock_linter.lint_file.assert_called_once()

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_single_file_failed(
        self, mock_linter_class, mock_available, sample_alerts_yaml, mock_lint_result_failed
    ):
        """Test linting single file that fails."""
        mock_available.return_value = True
        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_lint_result_failed
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(sample_alerts_yaml)

            result = lint_command(str(alerts_file))

        assert result == 1

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_directory(self, mock_linter_class, mock_available, mock_lint_result_passed):
        """Test linting a directory of files."""
        mock_available.return_value = True
        mock_linter = MagicMock()
        mock_linter.lint_directory.return_value = [mock_lint_result_passed, mock_lint_result_passed]
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            result = lint_command(tmpdir)

        assert result == 0
        mock_linter.lint_directory.assert_called_once()

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_directory_some_failed(
        self, mock_linter_class, mock_available, mock_lint_result_passed, mock_lint_result_failed
    ):
        """Test linting directory where some files fail."""
        mock_available.return_value = True
        mock_linter = MagicMock()
        mock_linter.lint_directory.return_value = [mock_lint_result_passed, mock_lint_result_failed]
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            result = lint_command(tmpdir)

        assert result == 1

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_with_config(self, mock_linter_class, mock_available, mock_lint_result_passed):
        """Test linting with custom config file."""
        mock_available.return_value = True
        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_lint_result_passed
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text("groups: []")

            config_file = Path(tmpdir) / ".pint.hcl"
            config_file.write_text("# pint config")

            result = lint_command(str(alerts_file), config=str(config_file))

        assert result == 0
        mock_linter_class.assert_called_once_with(config_path=config_file)

    @patch("nthlayer.cli.lint.is_pint_available")
    @patch("nthlayer.cli.lint.PintLinter")
    def test_lint_verbose(self, mock_linter_class, mock_available, mock_lint_result_passed):
        """Test linting with verbose output."""
        mock_available.return_value = True
        mock_lint_result_passed.raw_output = "Detailed pint output\nLine 2"
        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_lint_result_passed
        mock_linter_class.return_value = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text("groups: []")

            result = lint_command(str(alerts_file), verbose=True)

        assert result == 0


class TestPrintResult:
    """Tests for _print_result helper function."""

    def test_print_passed_result(self, mock_lint_result_passed):
        """Test printing passed result."""
        # Should not raise
        _print_result(mock_lint_result_passed, verbose=False)

    def test_print_failed_result(self, mock_lint_result_failed):
        """Test printing failed result with issues."""
        # Should not raise
        _print_result(mock_lint_result_failed, verbose=False)

    def test_print_result_with_warning(self):
        """Test printing result with warning issue."""
        result = MagicMock()
        result.passed = True
        result.file_path = "/test/file.yaml"

        issue = MagicMock()
        issue.is_error = False
        issue.is_warning = True
        issue.line = 5
        issue.rule_name = "naming"
        issue.check = "naming"
        issue.message = "Consider renaming"

        result.issues = [issue]
        result.raw_output = ""

        _print_result(result, verbose=False)

    def test_print_result_with_info(self):
        """Test printing result with info issue."""
        result = MagicMock()
        result.passed = True
        result.file_path = "/test/file.yaml"

        issue = MagicMock()
        issue.is_error = False
        issue.is_warning = False
        issue.line = None
        issue.rule_name = None
        issue.check = "info"
        issue.message = "Just a note"

        result.issues = [issue]
        result.raw_output = ""

        _print_result(result, verbose=False)

    def test_print_result_verbose_with_raw_output(self, mock_lint_result_passed):
        """Test printing with verbose and raw output."""
        mock_lint_result_passed.raw_output = "Raw output line 1\nRaw output line 2"

        _print_result(mock_lint_result_passed, verbose=True)
