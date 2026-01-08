"""Tests for CLI dashboard generation command."""

import json
from unittest.mock import MagicMock, patch

from nthlayer.cli.dashboard import generate_dashboard_command

MINIMAL_SERVICE_YAML = """
service:
  name: test-api
  team: platform
  tier: standard
  type: api
"""

FULL_SERVICE_YAML = """
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
  - kind: Dependencies
    name: databases
    spec:
      databases:
        - type: postgres
          instance: payments-db
"""


class TestGenerateDashboardCommand:
    """Tests for generate_dashboard_command."""

    def test_basic_dashboard_generation(self, tmp_path):
        """Test successful dashboard generation."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
        )

        assert result == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "dashboard" in data

    def test_dry_run_mode(self, tmp_path, capsys):
        """Test dry run mode prints JSON and doesn't write file."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
            dry_run=True,
        )

        assert result == 0
        assert not output_file.exists()  # Dry run doesn't write file

        # Check output contains dashboard JSON
        captured = capsys.readouterr()
        assert "Dashboard JSON (dry run):" in captured.out
        # The JSON is printed to stdout
        assert '"dashboard"' in captured.out or "dashboard" in captured.out

    def test_full_panels_mode(self, tmp_path):
        """Test full panels mode includes all template panels."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(FULL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
            full_panels=True,
        )

        assert result == 0
        assert output_file.exists()

    def test_default_output_path(self, tmp_path, monkeypatch):
        """Test default output path when output not specified."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        # Change to tmp_path so generated/ is created there
        monkeypatch.chdir(tmp_path)

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=None,  # Use default
        )

        assert result == 0
        # Default path is generated/dashboards/{service}.json
        default_output = tmp_path / "generated" / "dashboards" / "test-api.json"
        assert default_output.exists()

    def test_quiet_mode(self, tmp_path, capsys):
        """Test quiet mode suppresses output."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
            quiet=True,
        )

        assert result == 0
        captured = capsys.readouterr()
        # Quiet mode should have minimal/no output
        assert "Generate Grafana Dashboard" not in captured.out

    def test_with_environment(self, tmp_path):
        """Test dashboard generation with environment parameter."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        # Create environments directory
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "prod.yaml").write_text("""
environment: prod
service:
  tier: critical
""")

        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
            environment="prod",
        )

        assert result == 0

    def test_file_not_found_error(self, tmp_path, capsys):
        """Test error handling when service file doesn't exist."""
        # FileNotFoundError happens when build_dashboard encounters missing file
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        with patch(
            "nthlayer.cli.dashboard.build_dashboard",
            side_effect=FileNotFoundError("Template file not found"),
        ):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(tmp_path / "dashboard.json"),
            )

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_yaml_error_during_build(self, tmp_path, capsys):
        """Test error handling for YAML error during build."""
        import yaml

        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        with patch(
            "nthlayer.cli.dashboard.build_dashboard",
            side_effect=yaml.YAMLError("Invalid YAML in template"),
        ):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(tmp_path / "dashboard.json"),
            )

        assert result == 1

    def test_missing_required_fields_error(self, tmp_path, capsys):
        """Test error handling for missing required fields during build."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        with patch(
            "nthlayer.cli.dashboard.build_dashboard",
            side_effect=KeyError("required_field"),
        ):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(tmp_path / "dashboard.json"),
            )

        assert result == 1

    def test_legacy_dashboard_object(self, tmp_path):
        """Test handling of legacy dashboard object format."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        # Mock build_dashboard to return a legacy object with to_grafana_payload
        mock_dashboard = MagicMock()
        mock_dashboard.title = "Test Dashboard"
        mock_dashboard.uid = "test-uid"
        mock_dashboard.panels = [MagicMock(), MagicMock()]
        mock_dashboard.rows = []
        mock_dashboard.to_grafana_payload.return_value = {
            "dashboard": {"title": "Test Dashboard", "uid": "test-uid", "panels": []},
            "overwrite": True,
        }

        with patch("nthlayer.cli.dashboard.build_dashboard", return_value=mock_dashboard):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(output_file),
            )

        assert result == 0
        mock_dashboard.to_grafana_payload.assert_called_once()

    def test_legacy_dashboard_with_rows(self, tmp_path):
        """Test handling legacy dashboard with rows."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        # Create mock row with panels
        mock_row = MagicMock()
        mock_row.panels = [MagicMock(), MagicMock(), MagicMock()]

        mock_dashboard = MagicMock()
        mock_dashboard.title = "Test Dashboard"
        mock_dashboard.uid = "test-uid"
        mock_dashboard.panels = [MagicMock()]
        mock_dashboard.rows = [mock_row]
        mock_dashboard.to_grafana_payload.return_value = {
            "dashboard": {"title": "Test Dashboard", "panels": []},
            "overwrite": True,
        }

        with patch("nthlayer.cli.dashboard.build_dashboard", return_value=mock_dashboard):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(output_file),
            )

        assert result == 0

    def test_oserror_handling(self, tmp_path):
        """Test handling of OSError during file operations."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        # Use a directory that doesn't exist and can't be created
        with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output="/root/forbidden/dashboard.json",
            )

        assert result == 1

    def test_value_error_handling(self, tmp_path):
        """Test handling of ValueError during processing."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        with patch(
            "nthlayer.cli.dashboard.build_dashboard",
            side_effect=ValueError("Invalid service type"),
        ):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(tmp_path / "dashboard.json"),
            )

        assert result == 1

    def test_type_error_handling(self, tmp_path):
        """Test handling of TypeError during processing."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        with patch(
            "nthlayer.cli.dashboard.build_dashboard",
            side_effect=TypeError("Invalid type"),
        ):
            result = generate_dashboard_command(
                service_file=str(service_file),
                output=str(tmp_path / "dashboard.json"),
            )

        assert result == 1

    def test_with_slos_and_dependencies(self, tmp_path):
        """Test dashboard generation with SLOs and dependencies."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(FULL_SERVICE_YAML)
        output_file = tmp_path / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
        )

        assert result == 0
        data = json.loads(output_file.read_text())
        assert "dashboard" in data

    def test_output_directory_creation(self, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text(MINIMAL_SERVICE_YAML)

        # Nested output path
        output_file = tmp_path / "deep" / "nested" / "path" / "dashboard.json"

        result = generate_dashboard_command(
            service_file=str(service_file),
            output=str(output_file),
        )

        assert result == 0
        assert output_file.exists()
