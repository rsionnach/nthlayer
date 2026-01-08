"""Tests for cli/generate_alerts.py.

Tests for alert generation CLI command.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.generate_alerts import generate_alerts_command


@pytest.fixture
def service_with_dependencies():
    """Create service YAML with dependencies."""
    return """
service:
  name: payment-api
  team: payments-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
        - type: redis
"""


@pytest.fixture
def service_without_dependencies():
    """Create service YAML without dependencies."""
    return """
service:
  name: simple-api
  team: simple-team
  tier: tier-2
  type: api
"""


class TestGenerateAlertsCommand:
    """Tests for generate_alerts_command function."""

    def test_missing_service_file(self):
        """Test with non-existent service file."""
        result = generate_alerts_command("/nonexistent/service.yaml")

        assert result == 1

    def test_dry_run_no_dependencies(self, service_without_dependencies):
        """Test dry run with service without dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_without_dependencies)

            result = generate_alerts_command(
                str(service_file),
                dry_run=True,
            )

        # Should fail because no dependencies to generate alerts for
        assert result == 1

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_dry_run_with_dependencies(self, mock_generate, service_with_dependencies):
        """Test dry run with service with dependencies."""
        # Mock alert generation
        mock_alert = MagicMock()
        mock_alert.name = "PostgresDown"
        mock_alert.severity = "critical"
        mock_alert.technology = "postgres"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(
                str(service_file),
                dry_run=True,
            )

        assert result == 0
        mock_generate.assert_called_once()
        # Check that output_path is None for dry_run
        call_args = mock_generate.call_args
        assert call_args[0][1] is None  # output_path should be None

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_generate_with_output(self, mock_generate, service_with_dependencies):
        """Test generating alerts with specific output."""
        mock_alert = MagicMock()
        mock_alert.name = "RedisDown"
        mock_alert.severity = "warning"
        mock_alert.technology = "redis"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            output_file = Path(tmpdir) / "alerts.yaml"

            result = generate_alerts_command(
                str(service_file),
                output=str(output_file),
            )

        assert result == 0
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args
        assert call_args[0][1] == output_file  # output_path

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_generate_default_output_path(self, mock_generate, service_with_dependencies):
        """Test generating alerts with default output path."""
        mock_alert = MagicMock()
        mock_alert.name = "Alert1"
        mock_alert.severity = "warning"
        mock_alert.technology = "postgres"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "payment-api.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(str(service_file))

        assert result == 0
        call_args = mock_generate.call_args
        # Default output should be based on service name
        assert "payment-api" in str(call_args[0][1])

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_with_environment(self, mock_generate, service_with_dependencies):
        """Test generating alerts with environment specified."""
        mock_alert = MagicMock()
        mock_alert.name = "Alert1"
        mock_alert.severity = "critical"
        mock_alert.technology = "postgres"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(
                str(service_file),
                environment="production",
                dry_run=True,
            )

        assert result == 0
        call_args = mock_generate.call_args
        assert call_args[1]["environment"] == "production"

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_with_runbook_url(self, mock_generate, service_with_dependencies):
        """Test generating alerts with runbook URL."""
        mock_alert = MagicMock()
        mock_alert.name = "Alert1"
        mock_alert.severity = "warning"
        mock_alert.technology = "redis"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(
                str(service_file),
                runbook_url="https://runbooks.example.com",
                dry_run=True,
            )

        assert result == 0
        call_args = mock_generate.call_args
        assert call_args[1]["runbook_url"] == "https://runbooks.example.com"

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_with_notification_channel(self, mock_generate, service_with_dependencies):
        """Test generating alerts with notification channel."""
        mock_alert = MagicMock()
        mock_alert.name = "Alert1"
        mock_alert.severity = "critical"
        mock_alert.technology = "postgres"
        mock_generate.return_value = [mock_alert]

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(
                str(service_file),
                notification_channel="pagerduty",
                dry_run=True,
            )

        assert result == 0
        call_args = mock_generate.call_args
        assert call_args[1]["notification_channel"] == "pagerduty"

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_generate_exception_handling(self, mock_generate, service_with_dependencies):
        """Test handling exceptions during generation."""
        mock_generate.side_effect = ValueError("Invalid configuration")

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(str(service_file), dry_run=True)

        assert result == 1

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_dry_run_multiple_alerts(self, mock_generate, service_with_dependencies):
        """Test dry run output with multiple alerts (more than 5)."""
        # Create 8 mock alerts
        mock_alerts = []
        for i in range(8):
            alert = MagicMock()
            alert.name = f"Alert{i}"
            alert.severity = "warning" if i % 2 == 0 else "critical"
            alert.technology = "postgres" if i % 2 == 0 else "redis"
            mock_alerts.append(alert)

        mock_generate.return_value = mock_alerts

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(str(service_file), dry_run=True)

        assert result == 0

    @patch("nthlayer.cli.generate_alerts.generate_alerts_for_service")
    def test_empty_alerts_returned(self, mock_generate, service_with_dependencies):
        """Test when no alerts are generated."""
        mock_generate.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_alerts_command(str(service_file), dry_run=True)

        # Should return 1 when no alerts generated (prompts user to add deps)
        assert result == 1
