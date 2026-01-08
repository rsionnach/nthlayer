"""Tests for CLI validate-spec command.

Tests for nthlayer validate-spec command including OPA policy validation,
file/directory handling, and error reporting.
"""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.validate_spec import (
    _print_result,
    handle_validate_spec_command,
    register_validate_spec_parser,
    validate_spec_command,
)
from nthlayer.validation.metadata import Severity, ValidationIssue, ValidationResult


@pytest.fixture
def valid_service_yaml():
    """Create a valid service YAML file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "valid-service.yaml"
        service_file.write_text("""
service:
  name: valid-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability
""")
        yield str(service_file)


@pytest.fixture
def invalid_service_yaml():
    """Create an invalid service YAML file (missing required fields)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "invalid-service.yaml"
        service_file.write_text("""
service:
  name: invalid-service
  # Missing required: team, tier, type

resources:
  - kind: SLO
    name: test
""")
        yield str(service_file)


@pytest.fixture
def service_dir_with_files():
    """Create a directory with multiple service YAML files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Valid service file
        valid = Path(tmpdir) / "valid.yaml"
        valid.write_text("""
service:
  name: valid
  team: test
  tier: standard
  type: api

resources:
  - kind: SLO
    name: test
    spec:
      objective: 99.9
""")
        # Another valid service file
        another = Path(tmpdir) / "another.yml"
        another.write_text("""
service:
  name: another
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: main
    spec:
      objective: 99.95
""")
        # Non-service YAML (should be skipped)
        non_service = Path(tmpdir) / "config.yaml"
        non_service.write_text("""
database:
  host: localhost
  port: 5432
""")
        yield tmpdir


@pytest.fixture
def empty_dir():
    """Create an empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def successful_result(tmp_path):
    """Create a successful ValidationResult."""
    return ValidationResult(
        file_path=tmp_path / "test.yaml",
        issues=[],
        rules_checked=1,
    )


@pytest.fixture
def warning_result(tmp_path):
    """Create a ValidationResult with warnings."""
    return ValidationResult(
        file_path=tmp_path / "test.yaml",
        issues=[
            ValidationIssue(
                severity=Severity.WARNING,
                rule_name="service.tier.valid",
                validator="native",
                message="service.tier 'custom' is not a standard tier",
            ),
        ],
        rules_checked=1,
    )


@pytest.fixture
def error_result(tmp_path):
    """Create a ValidationResult with errors."""
    return ValidationResult(
        file_path=tmp_path / "test.yaml",
        issues=[
            ValidationIssue(
                severity=Severity.ERROR,
                rule_name="service.team",
                validator="native",
                message="service.team is required",
            ),
            ValidationIssue(
                severity=Severity.WARNING,
                rule_name="resources.required",
                validator="native",
                message="resources section is empty",
            ),
        ],
        rules_checked=1,
    )


class TestValidateSpecCommand:
    """Tests for validate_spec_command function."""

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_valid_file_returns_success(self, mock_validator_class, valid_service_yaml, tmp_path):
        """Test that valid file returns exit code 0."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_spec_command(file_path=valid_service_yaml)

        assert result == 0
        mock_validator.validate_file.assert_called_once()

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_warnings_return_exit_code_1(self, mock_validator_class, valid_service_yaml):
        """Test that warnings return exit code 1."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="test",
                    validator="native",
                    message="This is a warning",
                ),
            ],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_spec_command(file_path=valid_service_yaml)

        assert result == 1

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_errors_return_exit_code_2(self, mock_validator_class, valid_service_yaml):
        """Test that errors return exit code 2."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="test",
                    validator="native",
                    message="This is an error",
                ),
            ],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_spec_command(file_path=valid_service_yaml)

        assert result == 2

    def test_missing_file_returns_exit_code_2(self):
        """Test that missing file returns exit code 2."""
        result = validate_spec_command(file_path="/nonexistent/path/service.yaml")

        assert result == 2

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_empty_directory_returns_success(self, mock_validator_class, empty_dir):
        """Test that empty directory returns exit code 0."""
        result = validate_spec_command(file_path=empty_dir)

        assert result == 0
        # Validator should not be called for empty dir
        mock_validator_class.return_value.validate_file.assert_not_called()

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_directory_validates_service_files(self, mock_validator_class, service_dir_with_files):
        """Test that directory validates service files and skips non-service files."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(service_dir_with_files) / "valid.yaml",
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_spec_command(file_path=service_dir_with_files)

        assert result == 0
        # Should be called twice (valid.yaml and another.yml, not config.yaml)
        assert mock_validator.validate_file.call_count == 2

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_custom_policy_dir(self, mock_validator_class, valid_service_yaml, tmp_path):
        """Test that custom policy_dir is passed to validator."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        policy_dir = str(tmp_path / "custom-policies")

        result = validate_spec_command(
            file_path=valid_service_yaml,
            policy_dir=policy_dir,
        )

        assert result == 0
        mock_validator_class.assert_called_once_with(policy_dir=policy_dir)

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_verbose_mode(self, mock_validator_class, valid_service_yaml, capsys):
        """Test that verbose mode shows additional output."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="test",
                    validator="native",
                    message="This is a warning",
                    suggestion="Fix it this way",
                ),
            ],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_spec_command(
            file_path=valid_service_yaml,
            verbose=True,
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "Fix it this way" in captured.out

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_shows_conftest_mode_when_available(
        self, mock_validator_class, valid_service_yaml, capsys
    ):
        """Test that conftest mode is shown when available."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        with patch("nthlayer.cli.validate_spec.is_conftest_available", return_value=True):
            validate_spec_command(file_path=valid_service_yaml)

        captured = capsys.readouterr()
        assert "conftest" in captured.out

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_shows_native_mode_when_conftest_unavailable(
        self, mock_validator_class, valid_service_yaml, capsys
    ):
        """Test that native mode is shown when conftest unavailable."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(valid_service_yaml),
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        with patch("nthlayer.cli.validate_spec.is_conftest_available", return_value=False):
            validate_spec_command(file_path=valid_service_yaml)

        captured = capsys.readouterr()
        assert "native" in captured.out

    @patch("nthlayer.cli.validate_spec.ConftestValidator")
    def test_shows_file_count(self, mock_validator_class, service_dir_with_files, capsys):
        """Test that file count is shown."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            file_path=Path(service_dir_with_files) / "test.yaml",
            issues=[],
            rules_checked=1,
        )
        mock_validator_class.return_value = mock_validator

        validate_spec_command(file_path=service_dir_with_files)

        captured = capsys.readouterr()
        # Should show "Files to validate: 2"
        assert "Files to validate" in captured.out
        assert "2" in captured.out


class TestPrintResult:
    """Tests for _print_result helper function."""

    def test_passed_no_issues(self, successful_result, capsys):
        """Test printing passed result with no issues."""
        _print_result(successful_result, verbose=False)

        captured = capsys.readouterr()
        assert "✓" in captured.out or "test.yaml" in captured.out

    def test_passed_with_warnings(self, warning_result, capsys):
        """Test printing passed result with warnings."""
        _print_result(warning_result, verbose=False)

        captured = capsys.readouterr()
        assert "⚠" in captured.out

    def test_failed_with_errors(self, error_result, capsys):
        """Test printing failed result with errors."""
        _print_result(error_result, verbose=False)

        captured = capsys.readouterr()
        assert "✗" in captured.out

    def test_verbose_shows_suggestions(self, capsys, tmp_path):
        """Test that verbose mode shows suggestions."""
        result = ValidationResult(
            file_path=tmp_path / "test.yaml",
            issues=[
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="test",
                    validator="native",
                    message="Test warning",
                    suggestion="Try doing this instead",
                ),
            ],
            rules_checked=1,
        )

        _print_result(result, verbose=True)

        captured = capsys.readouterr()
        assert "Try doing this instead" in captured.out

    def test_non_verbose_hides_suggestions(self, capsys, tmp_path):
        """Test that non-verbose mode hides suggestions."""
        result = ValidationResult(
            file_path=tmp_path / "test.yaml",
            issues=[
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="test",
                    validator="native",
                    message="Test warning",
                    suggestion="Try doing this instead",
                ),
            ],
            rules_checked=1,
        )

        _print_result(result, verbose=False)

        captured = capsys.readouterr()
        assert "Try doing this instead" not in captured.out

    def test_info_severity_icon(self, capsys, tmp_path):
        """Test that INFO severity uses info icon."""
        result = ValidationResult(
            file_path=tmp_path / "test.yaml",
            issues=[
                ValidationIssue(
                    severity=Severity.INFO,
                    rule_name="test",
                    validator="native",
                    message="Info message",
                ),
            ],
            rules_checked=1,
        )

        _print_result(result, verbose=False)

        captured = capsys.readouterr()
        assert "ℹ" in captured.out


class TestRegisterValidateSpecParser:
    """Tests for register_validate_spec_parser function."""

    def test_registers_subparser(self):
        """Test that validate-spec subparser is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_validate_spec_parser(subparsers)

        # Should be able to parse validate-spec command
        args = parser.parse_args(["validate-spec", "test.yaml"])
        assert args.file_path == "test.yaml"

    def test_accepts_policy_dir_option(self):
        """Test that --policy-dir option is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_validate_spec_parser(subparsers)

        args = parser.parse_args(["validate-spec", "test.yaml", "--policy-dir", "/custom/policies"])
        assert args.policy_dir == "/custom/policies"

    def test_accepts_verbose_flag(self):
        """Test that --verbose/-v flag is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_validate_spec_parser(subparsers)

        args = parser.parse_args(["validate-spec", "test.yaml", "-v"])
        assert args.verbose is True


class TestHandleValidateSpecCommand:
    """Tests for handle_validate_spec_command function."""

    @patch("nthlayer.cli.validate_spec.validate_spec_command")
    def test_passes_args_correctly(self, mock_command):
        """Test that args are passed correctly to command."""
        mock_command.return_value = 0

        args = argparse.Namespace(
            file_path="test.yaml",
            policy_dir="/custom/policies",
            verbose=True,
        )

        result = handle_validate_spec_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            file_path="test.yaml",
            policy_dir="/custom/policies",
            verbose=True,
        )

    @patch("nthlayer.cli.validate_spec.validate_spec_command")
    def test_handles_missing_optional_args(self, mock_command):
        """Test that missing optional args are handled."""
        mock_command.return_value = 0

        # Create args without policy_dir and verbose
        args = argparse.Namespace(file_path="test.yaml")

        result = handle_validate_spec_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            file_path="test.yaml",
            policy_dir=None,
            verbose=False,
        )


class TestIntegration:
    """Integration tests for validate-spec command."""

    def test_real_validation_with_valid_file(self, valid_service_yaml):
        """Test real validation with valid service file."""
        # This runs actual validation without mocks
        result = validate_spec_command(file_path=valid_service_yaml)

        # Should pass (exit code 0 or 1 for warnings depending on policies)
        assert result in [0, 1]

    def test_real_validation_with_invalid_file(self, invalid_service_yaml):
        """Test real validation with invalid service file."""
        # This runs actual validation without mocks
        result = validate_spec_command(file_path=invalid_service_yaml)

        # Should fail with errors (exit code 2)
        assert result == 2
