"""Tests for deps CLI command."""

import json

from nthlayer.cli.deps import deps_command, handle_deps_command


class TestDepsCommand:
    """Tests for deps command."""

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

        exit_code = deps_command(
            service_file=str(service_file),
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        # Check output contains expected content
        assert "Dependencies: payment-api" in captured.out
        assert "Upstream" in captured.out
        assert "Downstream" in captured.out
        assert "user-service" in captured.out
        assert "postgresql" in captured.out
        assert "checkout-api" in captured.out

    def test_demo_mode_json(self, capsys, tmp_path):
        """Test demo mode with JSON output."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(
            """
name: test-service
tier: standard
"""
        )

        exit_code = deps_command(
            service_file=str(service_file),
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        # Parse JSON output
        data = json.loads(captured.out)
        assert data["service"] == "payment-api"
        assert "upstream" in data
        assert "downstream" in data
        assert len(data["upstream"]) > 0
        assert len(data["downstream"]) > 0

    def test_demo_mode_upstream_only(self, capsys, tmp_path):
        """Test demo mode with upstream only."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        exit_code = deps_command(
            service_file=str(service_file),
            direction="upstream",
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "upstream" in data
        assert "downstream" not in data

    def test_demo_mode_downstream_only(self, capsys, tmp_path):
        """Test demo mode with downstream only."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        exit_code = deps_command(
            service_file=str(service_file),
            direction="downstream",
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "downstream" in data
        assert "upstream" not in data

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

        exit_code = deps_command(
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

        exit_code = deps_command(
            service_file=str(service_file),
            prometheus_url="http://localhost:9090",
            demo=False,
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error parsing service file" in captured.out


class TestHandleDepsCommand:
    """Tests for CLI argument handling."""

    def test_handle_command(self, tmp_path, capsys):
        """Test handle_deps_command with args namespace."""
        import argparse

        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        args = argparse.Namespace(
            service_file=str(service_file),
            prometheus_url=None,
            environment=None,
            direction="both",
            output_format="table",
            demo=True,
        )

        exit_code = handle_deps_command(args)
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Dependencies" in captured.out
