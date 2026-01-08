"""Tests for cli/pagerduty.py.

Tests for PagerDuty setup CLI command.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.pagerduty import setup_pagerduty_command


@pytest.fixture
def service_with_pagerduty():
    """Create service YAML with PagerDuty resource."""
    return """
service:
  name: payment-api
  team: payments-team
  tier: tier-1
  type: api
resources:
  - kind: PagerDuty
    name: primary
    spec:
      escalation_policy: platform-oncall
      urgency: high
"""


@pytest.fixture
def service_without_pagerduty():
    """Create service YAML without PagerDuty resource."""
    return """
service:
  name: simple-api
  team: simple-team
  tier: tier-2
  type: api
"""


@pytest.fixture
def service_with_full_pagerduty():
    """Create service YAML with full PagerDuty config."""
    return """
service:
  name: critical-api
  team: platform-team
  tier: tier-1
  type: api
resources:
  - kind: PagerDuty
    name: primary
    spec:
      escalation_policy: platform-oncall
      urgency: high
      auto_resolve_timeout: 14400
      create_escalation_policy:
        name: auto-created-policy
        users:
          - user@example.com
"""


class TestSetupPagerDutyCommand:
    """Tests for setup_pagerduty_command function."""

    def test_missing_api_key(self, service_with_pagerduty):
        """Test when no API key is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            # Clear env var if set
            with patch.dict("os.environ", {}, clear=True):
                result = setup_pagerduty_command(str(service_file))

        assert result == 1

    def test_api_key_from_env(self, service_with_pagerduty):
        """Test API key from environment variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            with patch.dict("os.environ", {"PAGERDUTY_API_KEY": "test-key"}):
                with patch("nthlayer.cli.pagerduty.PagerDutyClient") as mock_client:
                    mock_instance = MagicMock()
                    mock_result = MagicMock()
                    mock_result.success = True
                    mock_result.created_service = True
                    mock_result.service_id = "PSERVICE1"
                    mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
                    mock_result.created_escalation_policy = False
                    mock_result.escalation_policy_id = None
                    mock_result.team_id = None
                    mock_result.created_team = False
                    mock_result.warnings = []
                    mock_instance.setup_service.return_value = mock_result
                    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                    mock_instance.__exit__ = MagicMock(return_value=False)
                    mock_client.return_value = mock_instance

                    result = setup_pagerduty_command(str(service_file))

        assert result == 0

    def test_missing_service_file(self):
        """Test with non-existent service file."""
        result = setup_pagerduty_command(
            "/nonexistent/service.yaml",
            api_key="test-key",
        )

        assert result == 1

    def test_invalid_yaml(self):
        """Test with invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.yaml"
            bad_file.write_text("not: valid: yaml: {{")

            result = setup_pagerduty_command(str(bad_file), api_key="test-key")

        assert result == 1

    def test_no_pagerduty_resource(self, service_without_pagerduty):
        """Test with service that has no PagerDuty resource."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_without_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 1

    def test_dry_run(self, service_with_pagerduty):
        """Test dry run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(
                str(service_file),
                api_key="test-key",
                dry_run=True,
            )

        assert result == 0

    def test_dry_run_with_environment(self, service_with_pagerduty):
        """Test dry run mode with environment specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(
                str(service_file),
                api_key="test-key",
                environment="production",
                dry_run=True,
            )

        assert result == 0

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_successful_setup_new_service(self, mock_client, service_with_pagerduty):
        """Test successful setup creating new service."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = True
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = False
        mock_result.escalation_policy_id = None
        mock_result.team_id = None
        mock_result.created_team = False
        mock_result.warnings = []
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 0
        mock_instance.setup_service.assert_called_once()

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_successful_setup_existing_service(self, mock_client, service_with_pagerduty):
        """Test successful setup with existing service."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = False  # Already existed
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = False
        mock_result.escalation_policy_id = None
        mock_result.team_id = "PTEAM1"
        mock_result.created_team = False
        mock_result.warnings = []
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 0

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_setup_creates_escalation_policy(self, mock_client, service_with_full_pagerduty):
        """Test setup that creates escalation policy."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = True
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = True
        mock_result.escalation_policy_id = "PPOLICY1"
        mock_result.team_id = "PTEAM1"
        mock_result.created_team = True
        mock_result.warnings = []
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_full_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 0
        call_args = mock_instance.setup_service.call_args
        assert call_args[1]["create_escalation_policy_config"] is not None

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_setup_failure(self, mock_client, service_with_pagerduty):
        """Test setup that fails."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Escalation policy not found"
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 1

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_setup_with_warnings(self, mock_client, service_with_pagerduty):
        """Test setup that succeeds with warnings."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = True
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = False
        mock_result.escalation_policy_id = None
        mock_result.team_id = None
        mock_result.created_team = False
        mock_result.warnings = ["Team not found, using default", "Integration key reused"]
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 0

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_unexpected_exception(self, mock_client, service_with_pagerduty):
        """Test handling of unexpected exceptions."""
        mock_client.side_effect = RuntimeError("Connection failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 1

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_setup_with_environment(self, mock_client, service_with_pagerduty):
        """Test setup with environment parameter."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = True
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = False
        mock_result.escalation_policy_id = None
        mock_result.team_id = None
        mock_result.created_team = False
        mock_result.warnings = []
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(
                str(service_file),
                api_key="test-key",
                environment="staging",
            )

        assert result == 0

    @patch("nthlayer.cli.pagerduty.PagerDutyClient")
    def test_setup_creates_team(self, mock_client, service_with_pagerduty):
        """Test setup that creates a new team."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.created_service = True
        mock_result.service_id = "PSERVICE1"
        mock_result.service_url = "https://pd.example.com/services/PSERVICE1"
        mock_result.created_escalation_policy = False
        mock_result.escalation_policy_id = None
        mock_result.team_id = "PTEAM1"
        mock_result.created_team = True  # New team created
        mock_result.warnings = []
        mock_instance.setup_service.return_value = mock_result
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_pagerduty)

            result = setup_pagerduty_command(str(service_file), api_key="test-key")

        assert result == 0
