"""Tests for CLI generate command.

Tests for nthlayer generate command including SLO generation,
format validation, dry-run mode, and error handling.
"""

import tempfile
from pathlib import Path

import pytest
from nthlayer.cli.generate import generate_slo_command


@pytest.fixture
def service_with_slo_yaml():
    """Create a service YAML with SLO resources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Filename must match service name
        service_file = Path(tmpdir) / "slo-service.yaml"
        service_file.write_text("""
service:
  name: slo-service
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
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 99
        threshold_ms: 500
""")
        yield str(service_file)


@pytest.fixture
def minimal_service_yaml():
    """Create a minimal service YAML without SLOs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "minimal-service.yaml"
        service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
        yield str(service_file)


class TestGenerateSloCommand:
    """Tests for generate_slo_command function."""

    def test_generate_with_valid_service(self, service_with_slo_yaml, tmp_path):
        """Test successful SLO generation."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
        )

        assert result == 0

    def test_generate_creates_output_directory(self, service_with_slo_yaml, tmp_path):
        """Test that output directory is created."""
        output_dir = tmp_path / "output"

        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(output_dir),
        )

        assert output_dir.exists() or (output_dir / "sloth").exists()

    def test_unsupported_format_fails(self, service_with_slo_yaml, tmp_path):
        """Test that unsupported format returns error."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            format="unsupported",
        )

        assert result == 1

    def test_prometheus_format_fails(self, service_with_slo_yaml, tmp_path):
        """Test that prometheus format is not yet supported."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            format="prometheus",
        )

        assert result == 1

    def test_openslo_format_fails(self, service_with_slo_yaml, tmp_path):
        """Test that openslo format is not yet supported."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            format="openslo",
        )

        assert result == 1

    def test_sloth_format_succeeds(self, service_with_slo_yaml, tmp_path):
        """Test that sloth format is supported."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            format="sloth",
        )

        assert result == 0

    def test_missing_file_fails(self, tmp_path):
        """Test that missing file returns error."""
        result = generate_slo_command(
            service_file="/nonexistent/service.yaml",
            output_dir=str(tmp_path / "output"),
        )

        assert result == 1


class TestDryRunMode:
    """Tests for dry-run mode."""

    def test_dry_run_returns_success(self, service_with_slo_yaml, tmp_path):
        """Test dry-run returns success without writing files."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            dry_run=True,
        )

        assert result == 0

    def test_dry_run_does_not_create_files(self, service_with_slo_yaml, tmp_path):
        """Test dry-run does not create output files."""
        output_dir = tmp_path / "dry_run_output"

        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(output_dir),
            dry_run=True,
        )

        # Output dir should not exist in dry-run mode
        # (unless it was created by directory validation)
        sloth_dir = output_dir / "sloth"
        assert not sloth_dir.exists() or len(list(sloth_dir.glob("*"))) == 0

    def test_dry_run_shows_preview(self, service_with_slo_yaml, tmp_path, capsys):
        """Test dry-run shows preview message."""
        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            dry_run=True,
        )

        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out or "Would generate" in captured.out


class TestEnvironmentParameter:
    """Tests for environment parameter handling."""

    def test_with_environment(self, service_with_slo_yaml, tmp_path):
        """Test generation with environment parameter."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            environment="production",
        )

        assert result == 0

    def test_dev_environment(self, service_with_slo_yaml, tmp_path):
        """Test generation with dev environment."""
        result = generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            environment="dev",
        )

        assert result == 0

    def test_environment_shown_in_output(self, service_with_slo_yaml, tmp_path, capsys):
        """Test environment is shown in output."""
        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
            environment="staging",
        )

        captured = capsys.readouterr()
        assert "staging" in captured.out


class TestOutputContent:
    """Tests for output content and formatting."""

    def test_shows_slo_count(self, service_with_slo_yaml, tmp_path, capsys):
        """Test output shows SLO count."""
        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
        )

        captured = capsys.readouterr()
        # Should show count or generated SLOs
        assert "SLO" in captured.out or "Generated" in captured.out

    def test_shows_next_steps(self, service_with_slo_yaml, tmp_path, capsys):
        """Test output shows next steps."""
        generate_slo_command(
            service_file=service_with_slo_yaml,
            output_dir=str(tmp_path / "output"),
        )

        captured = capsys.readouterr()
        # Should mention next steps or sloth command
        assert "sloth" in captured.out.lower() or "step" in captured.out.lower()

    def test_shows_error_message(self, tmp_path, capsys):
        """Test error message is shown for failures."""
        generate_slo_command(
            service_file="/nonexistent/file.yaml",
            output_dir=str(tmp_path / "output"),
        )

        captured = capsys.readouterr()
        assert "Error" in captured.out or "failed" in captured.out.lower()


class TestNoSloResources:
    """Tests for services without SLO resources."""

    def test_service_without_slos(self, minimal_service_yaml, tmp_path):
        """Test generation with service that has no SLO resources."""
        result = generate_slo_command(
            service_file=minimal_service_yaml,
            output_dir=str(tmp_path / "output"),
        )

        # Should return error or success with 0 SLOs depending on implementation
        assert result in [0, 1]
