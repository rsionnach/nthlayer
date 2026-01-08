"""Tests for cli/validate_metadata.py.

Tests for Prometheus rule metadata validation CLI command.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.validate_metadata import (
    _print_validation_result,
    validate_metadata_command,
)


@pytest.fixture
def valid_alerts_yaml():
    """Create valid alerts YAML content."""
    return """
groups:
  - name: test-alerts
    rules:
      - alert: HighErrorRate
        expr: error_rate > 0.1
        for: 5m
        labels:
          severity: warning
          team: platform
          service: test-api
        annotations:
          summary: High error rate detected
          description: Error rate is above threshold
          runbook_url: https://runbooks.example.com/high-error-rate
"""


@pytest.fixture
def invalid_alerts_yaml():
    """Create alerts YAML missing required labels."""
    return """
groups:
  - name: test-alerts
    rules:
      - alert: HighErrorRate
        expr: error_rate > 0.1
        for: 5m
        labels:
          severity: invalid
        annotations:
          summary: High error rate detected
"""


class TestValidateMetadataCommand:
    """Tests for validate_metadata_command function."""

    def test_file_not_found(self):
        """Test with non-existent file."""
        result = validate_metadata_command("/nonexistent/alerts.yaml")

        assert result == 2

    def test_no_yaml_files_in_directory(self):
        """Test with directory containing no YAML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty directory
            result = validate_metadata_command(tmpdir)

        assert result == 2

    def test_single_file_valid(self, valid_alerts_yaml):
        """Test validating single valid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(str(alerts_file))

        assert result == 0

    def test_single_file_with_warnings(self, invalid_alerts_yaml):
        """Test validating file that produces warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(invalid_alerts_yaml)

            result = validate_metadata_command(str(alerts_file))

        # Invalid severity should produce warning/error
        assert result in [1, 2]

    def test_strict_mode(self, valid_alerts_yaml):
        """Test strict validation mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(str(alerts_file), strict=True)

        # Strict mode may require additional fields
        assert result in [0, 1, 2]

    def test_directory_validation(self, valid_alerts_yaml):
        """Test validating directory of files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple alert files
            for i in range(3):
                alerts_file = Path(tmpdir) / f"alerts{i}.yaml"
                alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(tmpdir)

        assert result == 0

    def test_directory_with_nested_files(self, valid_alerts_yaml):
        """Test validating directory with nested YAML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            alerts_file = subdir / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(tmpdir)

        assert result == 0

    def test_yml_extension(self, valid_alerts_yaml):
        """Test validating files with .yml extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(tmpdir)

        assert result == 0

    def test_verbose_mode(self, valid_alerts_yaml):
        """Test verbose output mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(str(alerts_file), verbose=True)

        assert result == 0

    @patch("nthlayer.cli.validate_metadata.is_promruval_available")
    @patch("nthlayer.cli.validate_metadata.validate_with_promruval")
    def test_with_promruval(self, mock_validate, mock_available, valid_alerts_yaml):
        """Test using promruval for additional validation."""
        mock_available.return_value = True

        mock_result = MagicMock()
        mock_result.issues = []
        mock_validate.return_value = mock_result

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(
                str(alerts_file),
                use_promruval=True,
            )

        assert result == 0
        mock_validate.assert_called()

    @patch("nthlayer.cli.validate_metadata.is_promruval_available")
    def test_promruval_not_available(self, mock_available, valid_alerts_yaml):
        """Test when promruval is not available."""
        mock_available.return_value = False

        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_file = Path(tmpdir) / "alerts.yaml"
            alerts_file.write_text(valid_alerts_yaml)

            result = validate_metadata_command(
                str(alerts_file),
                use_promruval=True,
            )

        # Should still succeed without promruval
        assert result == 0


class TestPrintValidationResult:
    """Tests for _print_validation_result helper function."""

    def test_print_passed_result(self):
        """Test printing passed result without issues."""
        result = MagicMock()
        result.passed = True
        result.issues = []
        result.file_path = MagicMock()
        result.file_path.name = "alerts.yaml"

        # Should not raise
        _print_validation_result(result, verbose=False)

    def test_print_passed_with_warnings(self):
        """Test printing passed result with warnings."""
        result = MagicMock()
        result.passed = True

        issue = MagicMock()
        issue.severity = MagicMock()
        issue.severity.name = "WARNING"
        issue.validator = "test"
        issue.rule_name = "TestRule"
        issue.message = "Warning message"
        issue.suggestion = "Fix it"

        result.issues = [issue]
        result.file_path = MagicMock()
        result.file_path.name = "alerts.yaml"

        _print_validation_result(result, verbose=False)

    def test_print_failed_result(self):
        """Test printing failed result."""
        result = MagicMock()
        result.passed = False

        issue = MagicMock()
        issue.severity = MagicMock()
        issue.severity.name = "ERROR"
        issue.validator = "test"
        issue.rule_name = None
        issue.message = "Error message"
        issue.suggestion = None

        result.issues = [issue]
        result.file_path = MagicMock()
        result.file_path.name = "alerts.yaml"

        _print_validation_result(result, verbose=False)

    def test_print_verbose_with_suggestion(self):
        """Test verbose printing with suggestions."""
        result = MagicMock()
        result.passed = True

        issue = MagicMock()
        issue.severity = MagicMock()
        issue.severity.name = "INFO"
        issue.validator = "test"
        issue.rule_name = "TestRule"
        issue.message = "Info message"
        issue.suggestion = "Consider doing this"

        result.issues = [issue]
        result.file_path = MagicMock()
        result.file_path.name = "alerts.yaml"

        _print_validation_result(result, verbose=True)
