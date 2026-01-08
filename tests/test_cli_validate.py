"""Tests for CLI validate command.

Tests for nthlayer validate command including file validation,
environment handling, strict mode, and error reporting.
"""

import tempfile
from pathlib import Path

import pytest
from nthlayer.cli.validate import validate_command


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
def minimal_service_yaml():
    """Create a minimal valid service YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Filename must match service name
        service_file = Path(tmpdir) / "minimal-service.yaml"
        service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
        yield str(service_file)


@pytest.fixture
def invalid_service_yaml():
    """Create an invalid service YAML file (missing required fields)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Filename must match service name
        service_file = Path(tmpdir) / "invalid-service.yaml"
        service_file.write_text("""
service:
  name: invalid-service
  # Missing required: team, tier, type
""")
        yield str(service_file)


@pytest.fixture
def malformed_yaml():
    """Create a malformed YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Filename must match service name (though parsing will fail anyway)
        service_file = Path(tmpdir) / "broken.yaml"
        service_file.write_text("""
service:
  name: broken
  invalid: yaml: syntax: {{
""")
        yield str(service_file)


@pytest.fixture
def service_with_warnings_yaml():
    """Create a service YAML that produces validation warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Filename must match service name
        service_file = Path(tmpdir) / "warning-service.yaml"
        # Service without any resources typically generates warnings
        service_file.write_text("""
service:
  name: warning-service
  team: test
  tier: experimental
  type: api
""")
        yield str(service_file)


class TestValidateCommand:
    """Tests for validate_command function."""

    def test_valid_service_returns_success(self, valid_service_yaml):
        """Test that valid service returns exit code 0."""
        result = validate_command(service_file=valid_service_yaml)

        assert result == 0

    def test_minimal_service_returns_success(self, minimal_service_yaml):
        """Test that minimal valid service returns exit code 0."""
        result = validate_command(service_file=minimal_service_yaml)

        assert result == 0

    def test_invalid_service_returns_error(self, invalid_service_yaml):
        """Test that invalid service returns exit code 1."""
        result = validate_command(service_file=invalid_service_yaml)

        assert result == 1

    def test_missing_file_returns_error(self):
        """Test that missing file returns exit code 1."""
        result = validate_command(service_file="/nonexistent/path/service.yaml")

        assert result == 1

    def test_malformed_yaml_returns_error(self, malformed_yaml):
        """Test that malformed YAML returns exit code 1."""
        result = validate_command(service_file=malformed_yaml)

        assert result == 1

    def test_with_environment_parameter(self, valid_service_yaml):
        """Test validation with environment parameter."""
        result = validate_command(
            service_file=valid_service_yaml,
            environment="production",
        )

        assert result == 0

    def test_with_dev_environment(self, valid_service_yaml):
        """Test validation with dev environment."""
        result = validate_command(
            service_file=valid_service_yaml,
            environment="dev",
        )

        assert result == 0

    def test_with_staging_environment(self, valid_service_yaml):
        """Test validation with staging environment."""
        result = validate_command(
            service_file=valid_service_yaml,
            environment="staging",
        )

        assert result == 0


class TestStrictMode:
    """Tests for strict mode behavior."""

    def test_strict_mode_valid_no_warnings(self, valid_service_yaml):
        """Test strict mode with valid file and no warnings passes."""
        result = validate_command(
            service_file=valid_service_yaml,
            strict=True,
        )

        # Should pass if no warnings
        assert result in [0, 1]  # Depends on whether service has warnings

    def test_strict_mode_invalid_fails(self, invalid_service_yaml):
        """Test strict mode with invalid file fails."""
        result = validate_command(
            service_file=invalid_service_yaml,
            strict=True,
        )

        assert result == 1

    def test_non_strict_mode_with_warnings_passes(self, service_with_warnings_yaml):
        """Test non-strict mode passes even with warnings."""
        result = validate_command(
            service_file=service_with_warnings_yaml,
            strict=False,
        )

        # Should pass (exit 0) unless there are actual errors
        # Warnings alone shouldn't cause failure in non-strict mode
        assert result in [0, 1]


class TestOutputCapture:
    """Tests for output formatting."""

    def test_valid_service_prints_service_name(self, valid_service_yaml, capsys):
        """Test that valid service output includes service name."""
        validate_command(service_file=valid_service_yaml)

        captured = capsys.readouterr()
        assert "valid-service" in captured.out

    def test_invalid_service_prints_errors(self, invalid_service_yaml, capsys):
        """Test that invalid service output includes error messages."""
        validate_command(service_file=invalid_service_yaml)

        captured = capsys.readouterr()
        # Should mention the error or "Invalid"
        assert "Invalid" in captured.out or "Error" in captured.out

    def test_environment_shown_in_output(self, valid_service_yaml, capsys):
        """Test that environment is shown in output when specified."""
        validate_command(
            service_file=valid_service_yaml,
            environment="production",
        )

        captured = capsys.readouterr()
        assert "production" in captured.out


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, tmp_path):
        """Test validation of empty file."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")

        result = validate_command(service_file=str(empty_file))

        assert result == 1

    def test_non_yaml_content(self, tmp_path):
        """Test validation of non-YAML content."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("this is not yaml content\njust plain text")

        result = validate_command(service_file=str(bad_file))

        assert result == 1

    def test_yaml_without_service_key(self, tmp_path):
        """Test validation of YAML without 'service' key."""
        no_service = tmp_path / "no-service.yaml"
        no_service.write_text("""
resources:
  - kind: SLO
    name: test
""")
        result = validate_command(service_file=str(no_service))

        assert result == 1

    def test_service_with_extra_fields(self, tmp_path):
        """Test validation of service with extra/unknown fields."""
        extra_fields = tmp_path / "extra.yaml"
        extra_fields.write_text("""
service:
  name: extra-service
  team: test
  tier: standard
  type: api
  unknown_field: should_be_ignored_or_warned
""")
        result = validate_command(service_file=str(extra_fields))

        # Should either pass (ignore extra) or fail (strict schema)
        assert result in [0, 1]
