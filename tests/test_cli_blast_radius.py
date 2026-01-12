"""Tests for blast-radius CLI command."""

import json

from nthlayer.cli.blast_radius import blast_radius_command, handle_blast_radius_command


class TestBlastRadiusCommand:
    """Tests for blast-radius command."""

    def test_demo_mode(self, capsys, tmp_path):
        """Test demo mode output."""
        # Create a temporary service file
        service_file = tmp_path / "service.yaml"
        service_file.write_text(
            """
name: test-service
tier: standard
"""
        )

        exit_code = blast_radius_command(
            service_file=str(service_file),
            demo=True,
        )

        # Demo returns exit code based on risk level (critical = 2)
        assert exit_code in [0, 1, 2]
        captured = capsys.readouterr()

        # Check output contains expected content
        assert "Blast Radius: payment-api" in captured.out
        assert "Risk Assessment" in captured.out
        assert "Impact Summary" in captured.out
        assert "Direct dependents" in captured.out
        assert "Recommendation" in captured.out

    def test_demo_mode_json(self, capsys, tmp_path):
        """Test demo mode with JSON output."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(
            """
name: test-service
tier: standard
"""
        )

        exit_code = blast_radius_command(
            service_file=str(service_file),
            output_format="json",
            demo=True,
        )

        # Exit code depends on risk level
        assert exit_code in [0, 1, 2]
        captured = capsys.readouterr()

        # Parse JSON output
        data = json.loads(captured.out)
        assert data["service"] == "payment-api"
        assert "risk_level" in data
        assert "direct_downstream_count" in data
        assert "total_services_affected" in data
        assert "recommendation" in data

    def test_demo_mode_with_depth(self, capsys, tmp_path):
        """Test demo mode with custom depth."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        exit_code = blast_radius_command(
            service_file=str(service_file),
            depth=2,
            demo=True,
        )

        assert exit_code in [0, 1, 2]
        captured = capsys.readouterr()
        assert "Blast Radius" in captured.out

    def test_no_prometheus_url(self, capsys, tmp_path, monkeypatch):
        """Test error when Prometheus provider is selected but no URL provided."""
        # Clear env var
        monkeypatch.delenv("NTHLAYER_PROMETHEUS_URL", raising=False)

        service_file = tmp_path / "service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: platform
  tier: standard
  type: api
"""
        )

        exit_code = blast_radius_command(
            service_file=str(service_file),
            prometheus_url=None,
            demo=False,
            provider="prometheus",  # Explicitly require prometheus
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "No Prometheus URL" in captured.out

    def test_invalid_service_file(self, capsys, tmp_path):
        """Test error with invalid service file."""
        service_file = tmp_path / "nonexistent.yaml"

        exit_code = blast_radius_command(
            service_file=str(service_file),
            prometheus_url="http://localhost:9090",
            demo=False,
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error parsing service file" in captured.out

    def test_risk_levels(self):
        """Test risk level to exit code mapping."""
        from nthlayer.cli.blast_radius import _risk_to_exit_code

        assert _risk_to_exit_code("low") == 0
        assert _risk_to_exit_code("medium") == 1
        assert _risk_to_exit_code("high") == 2
        assert _risk_to_exit_code("critical") == 2


class TestHandleBlastRadiusCommand:
    """Tests for CLI argument handling."""

    def test_handle_command(self, tmp_path, capsys):
        """Test handle_blast_radius_command with args namespace."""
        import argparse

        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        args = argparse.Namespace(
            service_file=str(service_file),
            prometheus_url=None,
            environment=None,
            depth=10,
            output_format="table",
            demo=True,
        )

        exit_code = handle_blast_radius_command(args)
        assert exit_code in [0, 1, 2]

        captured = capsys.readouterr()
        assert "Blast Radius" in captured.out
