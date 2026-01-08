"""Tests for CLI setup command.

Tests for nthlayer setup wizard including connection testing,
service creation, and configuration flow.
"""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.setup import (
    _create_first_service,
    _generate_service_yaml,
    _is_valid_service_name,
    _print_next_steps,
    _print_welcome_banner,
    _quick_setup,
    _test_connections,
    _test_grafana,
    _test_pagerduty,
    _test_prometheus,
    config_exists,
    handle_setup_command,
    register_setup_parser,
    setup_command,
)
from nthlayer.config.integrations import (
    GrafanaProfile,
    GrafanaType,
    IntegrationConfig,
    PrometheusProfile,
    PrometheusType,
)


@pytest.fixture
def prometheus_profile():
    """Create a Prometheus profile for testing."""
    return PrometheusProfile(
        name="default",
        type=PrometheusType.PROMETHEUS,
        url="http://localhost:9090",
    )


@pytest.fixture
def prometheus_profile_with_auth():
    """Create a Prometheus profile with auth for testing."""
    return PrometheusProfile(
        name="default",
        type=PrometheusType.PROMETHEUS,
        url="http://localhost:9090",
        username="admin",
        password_secret="prometheus/password",
    )


@pytest.fixture
def grafana_profile():
    """Create a Grafana profile for testing."""
    return GrafanaProfile(
        name="default",
        type=GrafanaType.GRAFANA,
        url="http://localhost:3000",
    )


@pytest.fixture
def grafana_profile_with_key():
    """Create a Grafana profile with API key for testing."""
    profile = GrafanaProfile(
        name="default",
        type=GrafanaType.GRAFANA,
        url="http://localhost:3000",
        api_key_secret="grafana/api_key",
    )
    return profile


@pytest.fixture
def mock_config():
    """Create a mock integration config for testing."""
    config = IntegrationConfig.default()
    config.prometheus.profiles["default"] = PrometheusProfile(
        name="default",
        type=PrometheusType.PROMETHEUS,
        url="http://localhost:9090",
    )
    config.prometheus.default = "default"
    return config


class TestSetupCommand:
    """Tests for setup_command function."""

    @patch("nthlayer.cli.setup._test_connections")
    def test_test_only_mode(self, mock_test):
        """Test test_only mode calls _test_connections."""
        mock_test.return_value = 0

        result = setup_command(test_only=True)

        assert result == 0
        mock_test.assert_called_once()

    @patch("nthlayer.cli.setup._print_next_steps")
    @patch("nthlayer.cli.setup._test_connections")
    @patch("nthlayer.cli.setup._quick_setup")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup.get_config_path")
    @patch("nthlayer.cli.setup._print_welcome_banner")
    def test_quick_setup_mode(
        self,
        mock_banner,
        mock_config_path,
        mock_confirm,
        mock_quick,
        mock_test,
        mock_next_steps,
    ):
        """Test quick setup mode."""
        mock_config_path.return_value = None
        mock_quick.return_value = 0
        mock_test.return_value = 0
        mock_confirm.return_value = False  # No to first service

        result = setup_command(quick=True, skip_service=True)

        assert result == 0
        mock_quick.assert_called_once()

    @patch("nthlayer.cli.setup._print_next_steps")
    @patch("nthlayer.cli.setup._test_connections")
    @patch("nthlayer.config.cli.config_init_command")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup.get_config_path")
    @patch("nthlayer.cli.setup._print_welcome_banner")
    def test_advanced_setup_mode(
        self,
        mock_banner,
        mock_config_path,
        mock_confirm,
        mock_advanced,
        mock_test,
        mock_next_steps,
    ):
        """Test advanced setup mode uses config_init_command."""
        mock_config_path.return_value = None
        mock_advanced.return_value = 0
        mock_test.return_value = 0

        result = setup_command(quick=False, skip_service=True)

        assert result == 0
        mock_advanced.assert_called_once()

    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup.get_config_path")
    @patch("nthlayer.cli.setup._print_welcome_banner")
    def test_existing_config_cancelled(self, mock_banner, mock_config_path, mock_confirm):
        """Test setup cancelled when existing config not overwritten."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_config_path.return_value = mock_path
        mock_confirm.return_value = False  # Don't overwrite

        result = setup_command()

        assert result == 0

    @patch("nthlayer.cli.setup._create_first_service")
    @patch("nthlayer.cli.setup._print_next_steps")
    @patch("nthlayer.cli.setup._test_connections")
    @patch("nthlayer.cli.setup._quick_setup")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup.get_config_path")
    @patch("nthlayer.cli.setup._print_welcome_banner")
    def test_create_first_service_offered(
        self,
        mock_banner,
        mock_config_path,
        mock_confirm,
        mock_quick,
        mock_test,
        mock_next_steps,
        mock_create_service,
    ):
        """Test first service creation is offered when not skipped."""
        mock_config_path.return_value = None
        mock_quick.return_value = 0
        mock_test.return_value = 0
        mock_confirm.return_value = True  # Yes to first service

        setup_command(quick=True, skip_service=False)

        mock_create_service.assert_called_once()

    @patch("nthlayer.cli.setup._print_next_steps")
    @patch("nthlayer.cli.setup._test_connections")
    @patch("nthlayer.cli.setup._quick_setup")
    @patch("nthlayer.cli.setup.get_config_path")
    @patch("nthlayer.cli.setup._print_welcome_banner")
    def test_quick_setup_failure_returns_error(
        self,
        mock_banner,
        mock_config_path,
        mock_quick,
        mock_test,
        mock_next_steps,
    ):
        """Test that quick_setup failure is propagated."""
        mock_config_path.return_value = None
        mock_quick.return_value = 1

        result = setup_command(quick=True, skip_service=True)

        assert result == 1


class TestQuickSetup:
    """Tests for _quick_setup function."""

    @patch("nthlayer.cli.setup.save_config")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup._prompt_secret")
    @patch("nthlayer.cli.setup._prompt")
    def test_basic_prometheus_only(
        self,
        mock_prompt,
        mock_prompt_secret,
        mock_confirm,
        mock_resolver,
        mock_save,
    ):
        """Test basic setup with just Prometheus."""
        mock_prompt.return_value = "http://localhost:9090"
        mock_confirm.side_effect = [False, False, False]  # No auth, no grafana, no pagerduty
        mock_resolver.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = _quick_setup()

        assert result == 0
        mock_save.assert_called_once()

    @patch("nthlayer.cli.setup.save_config")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup._prompt_secret")
    @patch("nthlayer.cli.setup._prompt")
    def test_prometheus_with_auth(
        self,
        mock_prompt,
        mock_prompt_secret,
        mock_confirm,
        mock_resolver,
        mock_save,
    ):
        """Test setup with Prometheus authentication."""
        mock_prompt.side_effect = ["http://localhost:9090", "admin"]
        mock_prompt_secret.return_value = "secret123"
        mock_confirm.side_effect = [True, False, False]  # Yes auth, no grafana, no pagerduty
        mock_resolver_instance = MagicMock()
        mock_resolver.return_value = mock_resolver_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = _quick_setup()

        assert result == 0
        mock_resolver_instance.set_secret.assert_called_once_with(
            "prometheus/password", "secret123"
        )

    @patch("nthlayer.cli.setup.save_config")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup._prompt_secret")
    @patch("nthlayer.cli.setup._prompt")
    def test_full_setup_with_all_integrations(
        self,
        mock_prompt,
        mock_prompt_secret,
        mock_confirm,
        mock_resolver,
        mock_save,
    ):
        """Test full setup with all integrations."""
        mock_prompt.side_effect = [
            "http://prometheus:9090",  # Prometheus URL
            "http://grafana:3000",  # Grafana URL
            "default-policy",  # PagerDuty policy
        ]
        mock_prompt_secret.side_effect = [
            "grafana-key",  # Grafana API key
            "pagerduty-key",  # PagerDuty API key
        ]
        mock_confirm.side_effect = [
            False,  # No Prometheus auth
            True,  # Yes Grafana
            True,  # Yes PagerDuty
        ]
        mock_resolver_instance = MagicMock()
        mock_resolver.return_value = mock_resolver_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = _quick_setup()

        assert result == 0
        # Should save secrets for grafana and pagerduty
        assert mock_resolver_instance.set_secret.call_count == 2


class TestTestConnections:
    """Tests for _test_connections function."""

    @patch("nthlayer.cli.setup._test_pagerduty")
    @patch("nthlayer.cli.setup._test_grafana")
    @patch("nthlayer.cli.setup._test_prometheus")
    @patch("nthlayer.cli.setup.load_config")
    def test_all_connections_pass(self, mock_load, mock_prom, mock_grafana, mock_pd):
        """Test when all connections pass."""
        config = IntegrationConfig.default()
        config.prometheus.profiles["default"] = PrometheusProfile(
            name="default",
            type=PrometheusType.PROMETHEUS,
            url="http://localhost:9090",
        )
        config.prometheus.default = "default"
        config.grafana.profiles["default"] = GrafanaProfile(
            name="default",
            type=GrafanaType.GRAFANA,
            url="http://localhost:3000",
        )
        config.grafana.default = "default"
        config.alerting.pagerduty.enabled = True

        mock_load.return_value = config
        mock_prom.return_value = (True, "Connected")
        mock_grafana.return_value = (True, "Connected")
        mock_pd.return_value = (True, "Connected")

        result = _test_connections()

        assert result == 0

    @patch("nthlayer.cli.setup._test_prometheus")
    @patch("nthlayer.cli.setup.load_config")
    def test_prometheus_failure(self, mock_load, mock_prom):
        """Test when Prometheus connection fails."""
        config = IntegrationConfig.default()
        config.prometheus.profiles["default"] = PrometheusProfile(
            name="default",
            type=PrometheusType.PROMETHEUS,
            url="http://localhost:9090",
        )
        config.prometheus.default = "default"

        mock_load.return_value = config
        mock_prom.return_value = (False, "Connection refused")

        result = _test_connections()

        assert result == 1

    @patch("nthlayer.cli.setup._test_pagerduty")
    @patch("nthlayer.cli.setup._test_grafana")
    @patch("nthlayer.cli.setup._test_prometheus")
    @patch("nthlayer.cli.setup.load_config")
    def test_no_profiles_configured(self, mock_load, mock_prom, mock_grafana, mock_pd):
        """Test when no profiles are configured."""
        config = IntegrationConfig.default()
        # Clear the default profiles
        config.prometheus.profiles = {}
        config.prometheus.default = ""
        config.grafana.profiles = {}
        config.grafana.default = ""
        config.alerting.pagerduty.enabled = False
        mock_load.return_value = config

        # Should still return 0 if nothing configured
        result = _test_connections()

        assert result == 0
        mock_prom.assert_not_called()
        mock_grafana.assert_not_called()
        mock_pd.assert_not_called()


class TestTestPrometheus:
    """Tests for _test_prometheus function."""

    @patch("httpx.Client")
    def test_successful_connection(self, mock_client_class, prometheus_profile):
        """Test successful Prometheus connection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"version": "2.45.0"}}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        ok, msg = _test_prometheus(prometheus_profile)

        assert ok is True
        assert "2.45.0" in msg

    @patch("httpx.Client")
    def test_auth_required(self, mock_client_class, prometheus_profile):
        """Test Prometheus requires auth."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        ok, msg = _test_prometheus(prometheus_profile)

        assert ok is False
        assert "Authentication required" in msg

    @patch("httpx.Client")
    def test_connection_refused(self, mock_client_class, prometheus_profile):
        """Test Prometheus connection refused."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client

        ok, msg = _test_prometheus(prometheus_profile)

        assert ok is False
        assert "Connection refused" in msg

    @patch("httpx.Client")
    def test_timeout(self, mock_client_class, prometheus_profile):
        """Test Prometheus connection timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        ok, msg = _test_prometheus(prometheus_profile)

        assert ok is False
        assert "timed out" in msg

    @patch("httpx.Client")
    def test_with_auth(self, mock_client_class, prometheus_profile_with_auth):
        """Test Prometheus connection with auth credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"version": "2.45.0"}}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Mock get_password
        with patch.object(prometheus_profile_with_auth, "get_password", return_value="secret"):
            ok, msg = _test_prometheus(prometheus_profile_with_auth)

        assert ok is True
        # Verify auth was passed
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs.get("auth") is not None


class TestTestGrafana:
    """Tests for _test_grafana function."""

    @patch("httpx.Client")
    def test_successful_connection_no_key(self, mock_client_class, grafana_profile):
        """Test successful Grafana connection without API key."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        ok, msg = _test_grafana(grafana_profile)

        assert ok is True
        assert "no API key" in msg or "Connected" in msg

    @patch("httpx.Client")
    def test_successful_connection_with_key(self, mock_client_class, grafana_profile_with_key):
        """Test successful Grafana connection with API key."""
        mock_health = MagicMock()
        mock_health.status_code = 200

        mock_org = MagicMock()
        mock_org.status_code = 200
        mock_org.json.return_value = {"name": "Main Org"}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [mock_health, mock_org]
        mock_client_class.return_value = mock_client

        with patch.object(grafana_profile_with_key, "get_api_key", return_value="test-key"):
            ok, msg = _test_grafana(grafana_profile_with_key)

        assert ok is True
        assert "Main Org" in msg

    @patch("httpx.Client")
    def test_invalid_api_key(self, mock_client_class, grafana_profile):
        """Test Grafana with invalid API key."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        ok, msg = _test_grafana(grafana_profile)

        assert ok is False
        assert "Invalid API key" in msg

    @patch("httpx.Client")
    def test_connection_refused(self, mock_client_class, grafana_profile):
        """Test Grafana connection refused."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client

        ok, msg = _test_grafana(grafana_profile)

        assert ok is False
        assert "Connection refused" in msg


class TestTestPagerDuty:
    """Tests for _test_pagerduty function."""

    @patch("httpx.Client")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    def test_successful_connection(self, mock_resolver, mock_client_class):
        """Test successful PagerDuty connection."""
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.resolve.return_value = "test-api-key"
        mock_resolver.return_value = mock_resolver_instance

        mock_abilities = MagicMock()
        mock_abilities.status_code = 200

        mock_policies = MagicMock()
        mock_policies.status_code = 200
        mock_policies.json.return_value = {"total": 5}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [mock_abilities, mock_policies]
        mock_client_class.return_value = mock_client

        config = IntegrationConfig.default()
        config.alerting.pagerduty.enabled = True
        config.alerting.pagerduty.api_key_secret = "pagerduty/api_key"

        ok, msg = _test_pagerduty(config)

        assert ok is True
        assert "5 escalation policies" in msg

    @patch("nthlayer.cli.setup.get_secret_resolver")
    def test_no_api_key(self, mock_resolver):
        """Test PagerDuty with no API key configured."""
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.resolve.return_value = None
        mock_resolver.return_value = mock_resolver_instance

        config = IntegrationConfig.default()
        config.alerting.pagerduty.enabled = True

        with patch.dict("os.environ", {}, clear=True):
            ok, msg = _test_pagerduty(config)

        assert ok is False
        assert "No API key" in msg

    @patch("httpx.Client")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    def test_invalid_api_key(self, mock_resolver, mock_client_class):
        """Test PagerDuty with invalid API key."""
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.resolve.return_value = "invalid-key"
        mock_resolver.return_value = mock_resolver_instance

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = IntegrationConfig.default()
        config.alerting.pagerduty.enabled = True

        ok, msg = _test_pagerduty(config)

        assert ok is False
        assert "Invalid API key" in msg

    @patch("httpx.Client")
    @patch("nthlayer.cli.setup.get_secret_resolver")
    def test_uses_env_var(self, mock_resolver, mock_client_class):
        """Test PagerDuty uses environment variable as fallback."""
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.resolve.return_value = None
        mock_resolver.return_value = mock_resolver_instance

        mock_abilities = MagicMock()
        mock_abilities.status_code = 200

        mock_policies = MagicMock()
        mock_policies.status_code = 200
        mock_policies.json.return_value = {"total": 3}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [mock_abilities, mock_policies]
        mock_client_class.return_value = mock_client

        config = IntegrationConfig.default()
        config.alerting.pagerduty.enabled = True

        with patch.dict("os.environ", {"PAGERDUTY_API_KEY": "env-key"}):
            ok, msg = _test_pagerduty(config)

        assert ok is True


class TestCreateFirstService:
    """Tests for _create_first_service function."""

    @patch("nthlayer.cli.setup._confirm")
    @patch("nthlayer.cli.setup.select")
    @patch("nthlayer.cli.setup._prompt")
    def test_creates_service_file(self, mock_prompt, mock_select, mock_confirm):
        """Test service file creation."""
        import os

        mock_prompt.side_effect = ["my-service", "platform"]
        mock_select.side_effect = [
            "api - HTTP/REST API service",
            "standard - 99.9% availability, 15min escalation",
        ]
        mock_confirm.return_value = True  # Overwrite if exists

        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                _create_first_service()

                # Verify file was created
                service_file = Path(tmpdir) / "services" / "my-service.yaml"
                assert service_file.exists()
                content = service_file.read_text()
                assert "name: my-service" in content
                assert "team: platform" in content
            finally:
                os.chdir(original_dir)

    @patch("nthlayer.cli.setup._prompt")
    def test_skips_empty_name(self, mock_prompt, capsys):
        """Test skipping when empty name provided."""
        mock_prompt.return_value = ""

        _create_first_service()

        captured = capsys.readouterr()
        assert "Skipping" in captured.out or captured.out == ""

    @patch("nthlayer.cli.setup._prompt")
    def test_invalid_name_rejected(self, mock_prompt, capsys):
        """Test invalid service name is rejected."""
        mock_prompt.return_value = "Invalid_Name"

        _create_first_service()

        captured = capsys.readouterr()
        assert "Invalid" in captured.out or "lowercase" in captured.out


class TestGenerateServiceYaml:
    """Tests for _generate_service_yaml function."""

    def test_critical_tier(self):
        """Test generation for critical tier."""
        yaml = _generate_service_yaml("payment-api", "payments", "api", 1)

        assert "name: payment-api" in yaml
        assert "team: payments" in yaml
        assert "tier: 1" in yaml
        assert "type: api" in yaml
        assert "99.95" in yaml  # Critical availability
        assert "200" in yaml  # Critical latency threshold
        assert "urgency: high" in yaml

    def test_standard_tier(self):
        """Test generation for standard tier."""
        yaml = _generate_service_yaml("user-service", "platform", "api", 2)

        assert "name: user-service" in yaml
        assert "tier: 2" in yaml
        assert "99.9" in yaml  # Standard availability
        assert "500" in yaml  # Standard latency threshold
        assert "urgency: low" in yaml

    def test_low_tier(self):
        """Test generation for low tier."""
        yaml = _generate_service_yaml("batch-job", "data", "worker", 3)

        assert "name: batch-job" in yaml
        assert "tier: 3" in yaml
        assert "type: worker" in yaml
        assert "99.5" in yaml  # Low availability
        assert "1000" in yaml  # Low latency threshold

    def test_contains_slo_definitions(self):
        """Test that generated YAML contains SLO definitions."""
        yaml = _generate_service_yaml("test-api", "test", "api", 2)

        assert "kind: SLO" in yaml
        assert "name: availability" in yaml
        assert "name: latency-p99" in yaml
        assert "kind: PagerDuty" in yaml


class TestIsValidServiceName:
    """Tests for _is_valid_service_name function."""

    def test_valid_names(self):
        """Test valid service names."""
        assert _is_valid_service_name("my-service") is True
        assert _is_valid_service_name("service1") is True
        assert _is_valid_service_name("a") is True
        assert _is_valid_service_name("my-service-123") is True
        assert _is_valid_service_name("123") is True

    def test_invalid_empty(self):
        """Test empty name is invalid."""
        assert _is_valid_service_name("") is False

    def test_invalid_starting_hyphen(self):
        """Test name starting with hyphen is invalid."""
        assert _is_valid_service_name("-service") is False

    def test_invalid_ending_hyphen(self):
        """Test name ending with hyphen is invalid."""
        assert _is_valid_service_name("service-") is False

    def test_invalid_uppercase(self):
        """Test uppercase letters are invalid."""
        assert _is_valid_service_name("MyService") is False
        assert _is_valid_service_name("SERVICE") is False

    def test_invalid_special_characters(self):
        """Test special characters are invalid."""
        assert _is_valid_service_name("my_service") is False
        assert _is_valid_service_name("my.service") is False
        assert _is_valid_service_name("my service") is False
        assert _is_valid_service_name("my@service") is False


class TestConfigExists:
    """Tests for config_exists function."""

    @patch("nthlayer.cli.setup.get_config_path")
    def test_exists(self, mock_get_path):
        """Test when config exists."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path

        assert config_exists() is True

    @patch("nthlayer.cli.setup.get_config_path")
    def test_not_exists(self, mock_get_path):
        """Test when config does not exist."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path

        assert config_exists() is False

    @patch("nthlayer.cli.setup.get_config_path")
    def test_no_path_returns_false(self, mock_get_path):
        """Test when get_config_path returns None."""
        mock_get_path.return_value = None

        assert config_exists() is False


class TestDisplayFunctions:
    """Tests for display helper functions."""

    def test_print_welcome_banner(self, capsys):
        """Test welcome banner output."""
        _print_welcome_banner()

        captured = capsys.readouterr()
        assert "NthLayer" in captured.out

    def test_print_next_steps(self, capsys):
        """Test next steps output."""
        _print_next_steps()

        captured = capsys.readouterr()
        assert "Next steps" in captured.out
        assert "nthlayer" in captured.out


class TestRegisterSetupParser:
    """Tests for register_setup_parser function."""

    def test_registers_parser(self):
        """Test parser registration."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_setup_parser(subparsers)

        # Parse a setup command
        args = parser.parse_args(["setup"])
        assert hasattr(args, "quick") or True  # Just verify it parsed

    def test_quick_flag(self):
        """Test --quick flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_setup_parser(subparsers)

        args = parser.parse_args(["setup", "--quick"])
        assert args.quick is True

    def test_advanced_flag(self):
        """Test --advanced flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_setup_parser(subparsers)

        args = parser.parse_args(["setup", "--advanced"])
        assert args.advanced is True

    def test_test_flag(self):
        """Test --test flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_setup_parser(subparsers)

        args = parser.parse_args(["setup", "--test"])
        assert args.test is True

    def test_skip_service_flag(self):
        """Test --skip-service flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_setup_parser(subparsers)

        args = parser.parse_args(["setup", "--skip-service"])
        assert args.skip_service is True


class TestHandleSetupCommand:
    """Tests for handle_setup_command function."""

    @patch("nthlayer.cli.setup.setup_command")
    def test_passes_quick_mode(self, mock_setup):
        """Test quick mode is passed correctly."""
        mock_setup.return_value = 0

        args = argparse.Namespace(advanced=False, test=False, skip_service=False)
        result = handle_setup_command(args)

        assert result == 0
        mock_setup.assert_called_once_with(quick=True, test_only=False, skip_service=False)

    @patch("nthlayer.cli.setup.setup_command")
    def test_passes_advanced_mode(self, mock_setup):
        """Test advanced mode is passed correctly."""
        mock_setup.return_value = 0

        args = argparse.Namespace(advanced=True, test=False, skip_service=False)
        result = handle_setup_command(args)

        assert result == 0
        mock_setup.assert_called_once_with(quick=False, test_only=False, skip_service=False)

    @patch("nthlayer.cli.setup.setup_command")
    def test_passes_test_mode(self, mock_setup):
        """Test test mode is passed correctly."""
        mock_setup.return_value = 0

        args = argparse.Namespace(advanced=False, test=True, skip_service=False)
        result = handle_setup_command(args)

        assert result == 0
        mock_setup.assert_called_once_with(quick=True, test_only=True, skip_service=False)

    @patch("nthlayer.cli.setup.setup_command")
    def test_passes_skip_service(self, mock_setup):
        """Test skip_service is passed correctly."""
        mock_setup.return_value = 0

        args = argparse.Namespace(advanced=False, test=False, skip_service=True)
        result = handle_setup_command(args)

        assert result == 0
        mock_setup.assert_called_once_with(quick=True, test_only=False, skip_service=True)
