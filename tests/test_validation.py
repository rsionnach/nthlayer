"""Tests for the validation module (pint integration)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from nthlayer.validation import (
    LintIssue,
    LintResult,
    PintLinter,
    Severity,
    is_pint_available,
    lint_alerts_file,
)


class TestLintIssue:
    """Tests for LintIssue dataclass."""

    def test_is_error_bug(self):
        issue = LintIssue(severity=Severity.ERROR, rule_name="test", check="test", message="test")
        assert issue.is_error is True
        assert issue.is_warning is False

    def test_is_error_fatal(self):
        # Fatal maps to ERROR in the unified Severity enum
        issue = LintIssue(severity=Severity.ERROR, rule_name="test", check="test", message="test")
        assert issue.is_error is True

    def test_is_warning(self):
        issue = LintIssue(severity=Severity.WARNING, rule_name="test", check="test", message="test")
        assert issue.is_error is False
        assert issue.is_warning is True

    def test_is_information(self):
        issue = LintIssue(severity=Severity.INFO, rule_name="test", check="test", message="test")
        assert issue.is_error is False
        assert issue.is_warning is False


class TestLintResult:
    """Tests for LintResult dataclass."""

    def test_passed_no_issues(self):
        result = LintResult(file_path=Path("test.yaml"), issues=[])
        assert result.passed is True
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_passed_with_warnings(self):
        result = LintResult(
            file_path=Path("test.yaml"),
            issues=[LintIssue(severity=Severity.WARNING, rule_name="", check="", message="warn")],
        )
        assert result.passed is True
        assert result.error_count == 0
        assert result.warning_count == 1

    def test_failed_with_error(self):
        result = LintResult(
            file_path=Path("test.yaml"),
            issues=[LintIssue(severity=Severity.ERROR, rule_name="", check="", message="error")],
        )
        assert result.passed is False
        assert result.error_count == 1

    def test_summary_passed(self):
        result = LintResult(file_path=Path("test.yaml"), issues=[])
        assert "No issues found" in result.summary()

    def test_summary_warnings(self):
        result = LintResult(
            file_path=Path("test.yaml"),
            issues=[LintIssue(severity=Severity.WARNING, rule_name="", check="", message="warn")],
        )
        assert "1 warnings" in result.summary()

    def test_summary_errors(self):
        result = LintResult(
            file_path=Path("test.yaml"),
            issues=[
                LintIssue(severity=Severity.ERROR, rule_name="", check="", message="error"),
                LintIssue(severity=Severity.WARNING, rule_name="", check="", message="warn"),
            ],
        )
        assert "1 errors" in result.summary()
        assert "1 warnings" in result.summary()


class TestPintLinter:
    """Tests for PintLinter class."""

    def test_is_available_when_not_installed(self):
        with patch("shutil.which", return_value=None):
            linter = PintLinter()
            assert linter.is_available is False

    def test_is_available_when_installed(self):
        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            linter = PintLinter()
            assert linter.is_available is True

    def test_lint_file_not_available(self):
        with patch("shutil.which", return_value=None):
            linter = PintLinter()
            result = linter.lint_file(Path("test.yaml"))

            assert result.passed is True  # Not an error, just info
            assert len(result.issues) == 1
            assert "not installed" in result.issues[0].message

    def test_lint_file_not_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            linter = PintLinter()
            result = linter.lint_file(Path("/nonexistent/file.yaml"))

            assert result.passed is False
            assert len(result.issues) == 1
            assert "not found" in result.issues[0].message.lower()

    def test_lint_file_success(self, tmp_path):
        # Create a test file
        test_file = tmp_path / "alerts.yaml"
        test_file.write_text("groups: []")

        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

                linter = PintLinter()
                result = linter.lint_file(test_file)

                assert result.passed is True
                assert len(result.issues) == 0
                # Called at least once (may be called twice for version check)
                assert mock_run.call_count >= 1

    def test_lint_file_with_issues(self, tmp_path):
        test_file = tmp_path / "alerts.yaml"
        test_file.write_text("groups: []")

        pint_output = (
            "alerts.yaml:5 Warning: TestAlert (promql/rate) rate() counter\n"
            "alerts.yaml:10 Bug: TestAlert2 (promql/syntax) syntax error"
        )

        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=pint_output, stderr="", returncode=1)

                linter = PintLinter()
                result = linter.lint_file(test_file)

                assert len(result.issues) >= 1

    def test_lint_file_timeout(self, tmp_path):
        test_file = tmp_path / "alerts.yaml"
        test_file.write_text("groups: []")

        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="pint", timeout=60)

                linter = PintLinter()
                result = linter.lint_file(test_file)

                assert result.passed is False
                assert "timed out" in result.issues[0].message.lower()


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_is_pint_available_true(self):
        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            assert is_pint_available() is True

    def test_is_pint_available_false(self):
        with patch("shutil.which", return_value=None):
            assert is_pint_available() is False

    def test_lint_alerts_file(self, tmp_path):
        test_file = tmp_path / "alerts.yaml"
        test_file.write_text("groups: []")

        with patch("shutil.which", return_value="/usr/local/bin/pint"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

                result = lint_alerts_file(test_file)

                assert isinstance(result, LintResult)
                assert result.passed is True
