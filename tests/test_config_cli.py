"""Tests for config/cli.py.

Tests for configuration and secrets management CLI commands.
"""

from unittest.mock import MagicMock, patch

from nthlayer.config.cli import (
    REQUIRED_SECRETS,
    _set_alerting_config,
    _set_grafana_config,
    _set_prometheus_config,
    config_init_command,
    config_set_command,
    config_show_command,
    secrets_get_command,
    secrets_list_command,
    secrets_migrate_command,
    secrets_set_command,
    secrets_verify_command,
)
from nthlayer.config.integrations import (
    GrafanaProfile,
    GrafanaType,
    IntegrationConfig,
    PrometheusProfile,
    PrometheusType,
)
from nthlayer.config.secrets import SecretBackend


class TestConfigShowCommand:
    """Tests for config_show_command."""

    def test_shows_default_config(self, capsys, tmp_path, monkeypatch):
        """Shows configuration with defaults."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config") as mock_load:
                mock_load.return_value = IntegrationConfig.default()
                result = config_show_command()

        captured = capsys.readouterr()
        assert result == 0
        assert "NthLayer Configuration" in captured.out
        assert "(using defaults)" in captured.out
        assert "Prometheus:" in captured.out
        assert "Grafana:" in captured.out
        assert "Alerting:" in captured.out

    def test_shows_config_file_path(self, capsys, tmp_path, monkeypatch):
        """Shows config file path when present."""
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".nthlayer" / "config.yaml"

        with patch("nthlayer.config.cli.get_config_path", return_value=config_path):
            with patch("nthlayer.config.cli.load_config") as mock_load:
                mock_load.return_value = IntegrationConfig.default()
                result = config_show_command()

        captured = capsys.readouterr()
        assert result == 0
        assert str(config_path) in captured.out

    def test_shows_prometheus_profile_details(self, capsys, tmp_path, monkeypatch):
        """Shows prometheus profile details."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()
        config.prometheus.default = "production"
        config.prometheus.profiles["production"] = PrometheusProfile(
            name="production",
            type=PrometheusType.MIMIR,
            url="https://mimir.example.com",
            username="admin",
            password_secret="prometheus/password",
        )

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config", return_value=config):
                result = config_show_command(reveal_secrets=False)

        captured = capsys.readouterr()
        assert result == 0
        assert "[production]" in captured.out
        assert "mimir" in captured.out.lower()
        assert "https://mimir.example.com" in captured.out
        assert "admin" in captured.out
        assert "****" in captured.out

    def test_reveals_prometheus_password(self, capsys, tmp_path, monkeypatch):
        """Reveals prometheus password when requested."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()
        config.prometheus.default = "local"
        config.prometheus.profiles["local"] = PrometheusProfile(
            name="local",
            url="http://localhost:9090",
            password_secret="prometheus/password",
        )

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config", return_value=config):
                with patch.object(
                    PrometheusProfile, "get_password", return_value="secretpassword123"
                ):
                    result = config_show_command(reveal_secrets=True)

        captured = capsys.readouterr()
        assert result == 0
        # Password is displayed as first 4 chars...last 4 chars
        assert "secr...d123" in captured.out

    def test_shows_grafana_profile_details(self, capsys, tmp_path, monkeypatch):
        """Shows grafana profile details."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()
        config.grafana.default = "cloud"
        config.grafana.profiles["cloud"] = GrafanaProfile(
            name="cloud",
            type=GrafanaType.GRAFANA_CLOUD,
            url="https://grafana.example.com",
            org_id=42,
            api_key_secret="grafana/api_key",
        )

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config", return_value=config):
                result = config_show_command()

        captured = capsys.readouterr()
        assert result == 0
        assert "[cloud]" in captured.out
        assert "Org ID: 42" in captured.out
        assert "API Key: ****" in captured.out

    def test_reveals_grafana_api_key(self, capsys, tmp_path, monkeypatch):
        """Reveals grafana API key when requested."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()
        config.grafana.profiles["default"] = GrafanaProfile(
            name="default",
            url="http://localhost:3000",
            api_key_secret="grafana/api_key",
        )

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config", return_value=config):
                with patch.object(
                    GrafanaProfile, "get_api_key", return_value="glsa_secretkey123456"
                ):
                    result = config_show_command(reveal_secrets=True)

        captured = capsys.readouterr()
        assert result == 0
        assert "glsa_sec...3456" in captured.out

    def test_shows_alerting_config(self, capsys, tmp_path, monkeypatch):
        """Shows alerting configuration."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()
        config.alerting.pagerduty.enabled = True
        config.alerting.pagerduty.default_escalation_policy = "platform-oncall"
        config.alerting.slack.enabled = True
        config.alerting.slack.default_channel = "#alerts"

        with patch("nthlayer.config.cli.get_config_path", return_value=None):
            with patch("nthlayer.config.cli.load_config", return_value=config):
                result = config_show_command()

        captured = capsys.readouterr()
        assert result == 0
        assert "PagerDuty: enabled" in captured.out
        assert "platform-oncall" in captured.out
        assert "Slack: enabled" in captured.out
        assert "#alerts" in captured.out


class TestConfigSetCommand:
    """Tests for config_set_command."""

    def test_invalid_key_format(self, capsys):
        """Returns error for invalid key format."""
        result = config_set_command("invalid")

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid key format" in captured.out

    def test_unknown_section(self, capsys):
        """Returns error for unknown section."""
        with patch("nthlayer.config.cli.load_config") as mock_load:
            mock_load.return_value = IntegrationConfig.default()
            result = config_set_command("unknown.key", "value")

        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown section" in captured.out

    def test_set_prometheus_default(self, capsys, tmp_path, monkeypatch):
        """Sets prometheus default profile."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()

        with patch("nthlayer.config.cli.load_config", return_value=config):
            with patch("nthlayer.config.cli.save_config") as mock_save:
                result = config_set_command("prometheus.default", "production")

        assert result == 0
        mock_save.assert_called_once()
        assert config.prometheus.default == "production"

    def test_set_grafana_url(self, capsys, tmp_path, monkeypatch):
        """Sets grafana profile URL."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()

        with patch("nthlayer.config.cli.load_config", return_value=config):
            with patch("nthlayer.config.cli.save_config") as mock_save:
                result = config_set_command("grafana.profiles.cloud.url", "https://grafana.cloud")

        assert result == 0
        mock_save.assert_called_once()
        assert config.grafana.profiles["cloud"].url == "https://grafana.cloud"

    def test_set_alerting_pagerduty_enabled(self, capsys, tmp_path, monkeypatch):
        """Sets alerting pagerduty enabled."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()

        with patch("nthlayer.config.cli.load_config", return_value=config):
            with patch("nthlayer.config.cli.save_config"):
                result = config_set_command("alerting.pagerduty.enabled", "true")

        assert result == 0
        assert config.alerting.pagerduty.enabled is True

    def test_secret_prompts_for_value(self, capsys, tmp_path, monkeypatch):
        """Prompts for value when secret flag is set."""
        monkeypatch.chdir(tmp_path)
        config = IntegrationConfig.default()

        with patch("nthlayer.config.cli.load_config", return_value=config):
            with patch("nthlayer.config.cli.save_config"):
                with patch("nthlayer.config.cli.getpass.getpass", return_value="secret-value"):
                    result = config_set_command(
                        "grafana.profiles.default.api_key", None, secret=True
                    )

        assert result == 0
        assert config.grafana.profiles["default"].api_key_secret == "secret-value"


class TestSetPrometheusConfig:
    """Tests for _set_prometheus_config helper."""

    def test_set_default(self):
        """Sets default prometheus profile."""
        config = IntegrationConfig.default()
        _set_prometheus_config(config, "default", "staging")
        assert config.prometheus.default == "staging"

    def test_set_profile_url(self):
        """Sets profile URL."""
        config = IntegrationConfig.default()
        _set_prometheus_config(config, "profiles.prod.url", "https://prometheus.prod.com")
        assert config.prometheus.profiles["prod"].url == "https://prometheus.prod.com"

    def test_set_profile_type(self):
        """Sets profile type."""
        config = IntegrationConfig.default()
        _set_prometheus_config(config, "profiles.prod.type", "mimir")
        assert config.prometheus.profiles["prod"].type == PrometheusType.MIMIR

    def test_set_profile_username(self):
        """Sets profile username."""
        config = IntegrationConfig.default()
        _set_prometheus_config(config, "profiles.prod.username", "admin")
        assert config.prometheus.profiles["prod"].username == "admin"

    def test_set_profile_password(self):
        """Sets profile password secret."""
        config = IntegrationConfig.default()
        _set_prometheus_config(config, "profiles.prod.password", "prometheus/secret")
        assert config.prometheus.profiles["prod"].password_secret == "prometheus/secret"


class TestSetGrafanaConfig:
    """Tests for _set_grafana_config helper."""

    def test_set_default(self):
        """Sets default grafana profile."""
        config = IntegrationConfig.default()
        _set_grafana_config(config, "default", "staging")
        assert config.grafana.default == "staging"

    def test_set_profile_url(self):
        """Sets profile URL."""
        config = IntegrationConfig.default()
        _set_grafana_config(config, "profiles.prod.url", "https://grafana.prod.com")
        assert config.grafana.profiles["prod"].url == "https://grafana.prod.com"

    def test_set_profile_type(self):
        """Sets profile type."""
        config = IntegrationConfig.default()
        _set_grafana_config(config, "profiles.prod.type", "grafana-cloud")
        assert config.grafana.profiles["prod"].type == GrafanaType.GRAFANA_CLOUD

    def test_set_profile_api_key(self):
        """Sets profile API key secret."""
        config = IntegrationConfig.default()
        _set_grafana_config(config, "profiles.prod.api_key", "grafana/api_key")
        assert config.grafana.profiles["prod"].api_key_secret == "grafana/api_key"

    def test_set_profile_org_id(self):
        """Sets profile org ID."""
        config = IntegrationConfig.default()
        _set_grafana_config(config, "profiles.prod.org_id", "42")
        assert config.grafana.profiles["prod"].org_id == 42


class TestSetAlertingConfig:
    """Tests for _set_alerting_config helper."""

    def test_set_pagerduty_enabled(self):
        """Sets pagerduty enabled."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "pagerduty.enabled", "true")
        assert config.alerting.pagerduty.enabled is True

    def test_set_pagerduty_api_key(self):
        """Sets pagerduty API key secret."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "pagerduty.api_key", "pagerduty/key")
        assert config.alerting.pagerduty.api_key_secret == "pagerduty/key"

    def test_set_pagerduty_escalation_policy(self):
        """Sets pagerduty escalation policy."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "pagerduty.escalation_policy", "platform-oncall")
        assert config.alerting.pagerduty.default_escalation_policy == "platform-oncall"

    def test_set_slack_enabled(self):
        """Sets slack enabled."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "slack.enabled", "yes")
        assert config.alerting.slack.enabled is True

    def test_set_slack_webhook(self):
        """Sets slack webhook secret."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "slack.webhook_url", "slack/webhook")
        assert config.alerting.slack.webhook_url_secret == "slack/webhook"

    def test_set_slack_channel(self):
        """Sets slack default channel."""
        config = IntegrationConfig.default()
        _set_alerting_config(config, "slack.channel", "#engineering")
        assert config.alerting.slack.default_channel == "#engineering"


class TestConfigInitCommand:
    """Tests for config_init_command."""

    def test_init_with_defaults(self, capsys, tmp_path, monkeypatch):
        """Interactive init with default values."""
        monkeypatch.chdir(tmp_path)

        # Simulate user inputs - all defaults
        inputs = iter(
            [
                "",  # Backend choice (default: 1 = env)
                "",  # Grafana type (default: grafana)
                "",  # Grafana URL (default: localhost:3000)
                "n",  # Configure API key? No
                "",  # Prometheus type (default: prometheus)
                "",  # Prometheus URL (default: localhost:9090)
                "n",  # Configure PagerDuty? No
                "n",  # Configure Slack? No
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config") as mock_save:
                result = config_init_command()

        assert result == 0
        mock_save.assert_called_once()
        captured = capsys.readouterr()
        assert "Configuration saved" in captured.out

    def test_init_with_vault_backend(self, capsys, tmp_path, monkeypatch):
        """Interactive init with Vault backend."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "3",  # Backend: vault
                "https://vault.example.com",  # Vault address
                "kubernetes",  # Auth method
                "nthlayer-role",  # Role
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config"):
                result = config_init_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "Vault configured" in captured.out

    def test_init_with_aws_backend(self, capsys, tmp_path, monkeypatch):
        """Interactive init with AWS backend."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "4",  # Backend: aws
                "us-west-2",  # Region
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config"):
                result = config_init_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "AWS Secrets Manager configured" in captured.out

    def test_init_with_grafana_api_key(self, capsys, tmp_path, monkeypatch):
        """Interactive init with Grafana API key."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "",  # Backend
                "",  # Grafana type
                "",  # Grafana URL
                "y",  # Configure API key? Yes
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.getpass.getpass", return_value="glsa_apikey"):
                with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
                    mock_instance = MagicMock()
                    mock_resolver.return_value = mock_instance
                    with patch("nthlayer.config.cli.save_config"):
                        result = config_init_command()

        assert result == 0
        mock_instance.set_secret.assert_called_with("grafana/api_key", "glsa_apikey")

    def test_init_with_pagerduty(self, capsys, tmp_path, monkeypatch):
        """Interactive init with PagerDuty."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "",  # Backend
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # Grafana API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "y",  # Configure PagerDuty? Yes
                "platform-ep",  # Escalation policy
                "y",  # Configure API key? Yes
                "n",  # Configure Slack? No
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.getpass.getpass", return_value="pd_apikey"):
                with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
                    mock_instance = MagicMock()
                    mock_resolver.return_value = mock_instance
                    with patch("nthlayer.config.cli.save_config"):
                        result = config_init_command()

        assert result == 0
        mock_instance.set_secret.assert_called_with("pagerduty/api_key", "pd_apikey")

    def test_init_with_azure_backend(self, capsys, tmp_path, monkeypatch):
        """Interactive init with Azure Key Vault backend."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "5",  # Backend: azure
                "https://myvault.vault.azure.net",  # Vault URL
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config"):
                result = config_init_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "Azure Key Vault configured" in captured.out

    def test_init_with_gcp_backend(self, capsys, tmp_path, monkeypatch):
        """Interactive init with GCP Secret Manager backend."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "6",  # Backend: gcp
                "my-gcp-project",  # Project ID
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config"):
                result = config_init_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "GCP Secret Manager configured" in captured.out

    def test_init_with_doppler_backend(self, capsys, tmp_path, monkeypatch):
        """Interactive init with Doppler backend."""
        monkeypatch.chdir(tmp_path)

        inputs = iter(
            [
                "7",  # Backend: doppler
                "myproj",  # Project
                "stg",  # Config
                "",  # Grafana type
                "",  # Grafana URL
                "n",  # API key
                "",  # Prometheus type
                "",  # Prometheus URL
                "n",  # PagerDuty
                "n",  # Slack
            ]
        )

        with patch("builtins.input", lambda prompt: next(inputs)):
            with patch("nthlayer.config.cli.save_config"):
                result = config_init_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "Doppler configured: myproj/stg" in captured.out


class TestSecretsListCommand:
    """Tests for secrets_list_command."""

    def test_no_secrets(self, capsys):
        """Lists no secrets when none exist."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.list_secrets.return_value = {}
            mock_resolver.return_value = mock_instance

            result = secrets_list_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "No secrets found" in captured.out

    def test_lists_secrets_by_backend(self, capsys):
        """Lists secrets grouped by backend."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.list_secrets.return_value = {
                "env": ["grafana/api_key", "prometheus/password"],
                "file": ["pagerduty/api_key"],
            }
            mock_resolver.return_value = mock_instance

            result = secrets_list_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "[env]" in captured.out
        assert "grafana/api_key" in captured.out
        assert "[file]" in captured.out
        assert "pagerduty/api_key" in captured.out


class TestSecretsVerifyCommand:
    """Tests for secrets_verify_command."""

    def test_all_secrets_found(self, capsys):
        """Returns 0 when all secrets found."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.verify_secrets.return_value = {
                "grafana/api_key": (True, "env"),
                "prometheus/password": (True, "file"),
            }
            mock_resolver.return_value = mock_instance

            result = secrets_verify_command(secrets=["grafana/api_key", "prometheus/password"])

        assert result == 0
        captured = capsys.readouterr()
        assert "grafana/api_key: found (env)" in captured.out
        assert "All required secrets are available" in captured.out

    def test_missing_secrets(self, capsys):
        """Returns 1 when secrets missing."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.verify_secrets.return_value = {
                "grafana/api_key": (True, "env"),
                "pagerduty/api_key": (False, None),
            }
            mock_resolver.return_value = mock_instance

            result = secrets_verify_command(secrets=["grafana/api_key", "pagerduty/api_key"])

        assert result == 1
        captured = capsys.readouterr()
        assert "pagerduty/api_key: NOT FOUND" in captured.out
        assert "Some secrets are missing" in captured.out

    def test_uses_default_required_secrets(self, capsys):
        """Uses REQUIRED_SECRETS when none specified."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.verify_secrets.return_value = {
                secret: (False, None) for secret in REQUIRED_SECRETS
            }
            mock_resolver.return_value = mock_instance

            result = secrets_verify_command()

        mock_instance.verify_secrets.assert_called_once_with(REQUIRED_SECRETS)


class TestSecretsSetCommand:
    """Tests for secrets_set_command."""

    def test_set_secret_with_value(self, capsys):
        """Sets secret with provided value."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.set_secret.return_value = True
            mock_resolver.return_value = mock_instance

            result = secrets_set_command("grafana/api_key", "secret-value")

        assert result == 0
        mock_instance.set_secret.assert_called_once_with("grafana/api_key", "secret-value", None)

    def test_prompts_for_value(self, capsys):
        """Prompts for value when not provided."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.set_secret.return_value = True
            mock_resolver.return_value = mock_instance

            with patch("nthlayer.config.cli.getpass.getpass", return_value="prompted-value"):
                result = secrets_set_command("grafana/api_key", None)

        assert result == 0
        mock_instance.set_secret.assert_called_once_with("grafana/api_key", "prompted-value", None)

    def test_set_with_backend(self, capsys):
        """Sets secret with specific backend."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.set_secret.return_value = True
            mock_resolver.return_value = mock_instance

            result = secrets_set_command("grafana/api_key", "value", backend="file")

        assert result == 0
        mock_instance.set_secret.assert_called_once_with(
            "grafana/api_key", "value", SecretBackend.FILE
        )

    def test_invalid_backend(self, capsys):
        """Returns 1 for invalid backend."""
        result = secrets_set_command("grafana/api_key", "value", backend="invalid")

        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown backend" in captured.out

    def test_set_fails(self, capsys):
        """Returns 1 when set fails."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.set_secret.return_value = False
            mock_resolver.return_value = mock_instance

            result = secrets_set_command("grafana/api_key", "value")

        assert result == 1
        captured = capsys.readouterr()
        assert "Failed to store secret" in captured.out


class TestSecretsGetCommand:
    """Tests for secrets_get_command."""

    def test_secret_not_found(self, capsys):
        """Returns 1 when secret not found."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.resolve.return_value = None
            mock_resolver.return_value = mock_instance

            result = secrets_get_command("nonexistent/secret")

        assert result == 1
        captured = capsys.readouterr()
        assert "Secret not found" in captured.out

    def test_shows_masked_value(self, capsys):
        """Shows masked value by default."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.resolve.return_value = "secretvalue123456"
            mock_resolver.return_value = mock_instance

            result = secrets_get_command("grafana/api_key", reveal=False)

        assert result == 0
        captured = capsys.readouterr()
        assert "secr...3456" in captured.out
        assert "secretvalue123456" not in captured.out

    def test_reveals_value(self, capsys):
        """Reveals full value when requested."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.resolve.return_value = "secretvalue123456"
            mock_resolver.return_value = mock_instance

            result = secrets_get_command("grafana/api_key", reveal=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "secretvalue123456" in captured.out

    def test_short_value_masked(self, capsys):
        """Short values are fully masked."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance.resolve.return_value = "short"
            mock_resolver.return_value = mock_instance

            result = secrets_get_command("grafana/api_key", reveal=False)

        assert result == 0
        captured = capsys.readouterr()
        assert "****" in captured.out


class TestSecretsMigrateCommand:
    """Tests for secrets_migrate_command."""

    def test_invalid_source_backend(self, capsys):
        """Returns 1 for invalid source backend."""
        result = secrets_migrate_command("invalid", "file")

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid backend" in captured.out

    def test_invalid_target_backend(self, capsys):
        """Returns 1 for invalid target backend."""
        result = secrets_migrate_command("env", "invalid")

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid backend" in captured.out

    def test_source_backend_not_available(self, capsys):
        """Returns 1 when source backend not available."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_instance._backends = {}
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 1
        captured = capsys.readouterr()
        assert "Source backend not available" in captured.out

    def test_target_backend_not_available(self, capsys):
        """Returns 1 when target backend not available."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_instance._backends = {SecretBackend.ENV: mock_source}
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 1
        captured = capsys.readouterr()
        assert "Target backend not available" in captured.out

    def test_target_does_not_support_write(self, capsys):
        """Returns 1 when target backend doesn't support write."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_target = MagicMock()
            mock_target.supports_write.return_value = False
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 1
        captured = capsys.readouterr()
        assert "does not support writing" in captured.out

    def test_no_secrets_to_migrate(self, capsys):
        """Returns 0 when no secrets to migrate."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.list_secrets.return_value = []
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 0
        captured = capsys.readouterr()
        assert "No secrets found" in captured.out

    def test_dry_run(self, capsys):
        """Dry run shows what would be migrated."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.list_secrets.return_value = ["grafana/api_key", "missing/secret"]
            mock_source.get_secret.side_effect = (
                lambda p: "value" if p == "grafana/api_key" else None
            )
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file", dry_run=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "grafana/api_key (found)" in captured.out
        assert "missing/secret (NOT FOUND)" in captured.out
        mock_target.set_secret.assert_not_called()

    def test_successful_migration(self, capsys):
        """Successfully migrates secrets."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.list_secrets.return_value = ["grafana/api_key"]
            mock_source.get_secret.return_value = "secret-value"
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            mock_target.set_secret.return_value = True
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 0
        mock_target.set_secret.assert_called_once_with("grafana/api_key", "secret-value")
        captured = capsys.readouterr()
        assert "OK   grafana/api_key" in captured.out
        assert "1 migrated, 0 failed" in captured.out

    def test_migration_with_failures(self, capsys):
        """Returns 1 when some migrations fail."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.list_secrets.return_value = ["secret1", "secret2"]
            mock_source.get_secret.return_value = "value"
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            # First succeeds, second fails
            mock_target.set_secret.side_effect = [True, False]
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 1
        captured = capsys.readouterr()
        assert "1 migrated, 1 failed" in captured.out

    def test_migrate_specific_secrets(self, capsys):
        """Migrates only specified secrets."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.get_secret.return_value = "value"
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            mock_target.set_secret.return_value = True
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file", secrets=["grafana/api_key"])

        assert result == 0
        mock_source.list_secrets.assert_not_called()
        mock_target.set_secret.assert_called_once_with("grafana/api_key", "value")

    def test_skip_not_found_in_source(self, capsys):
        """Skips secrets not found in source."""
        with patch("nthlayer.config.cli.get_secret_resolver") as mock_resolver:
            mock_instance = MagicMock()
            mock_source = MagicMock()
            mock_source.list_secrets.return_value = ["missing/secret"]
            mock_source.get_secret.return_value = None
            mock_target = MagicMock()
            mock_target.supports_write.return_value = True
            mock_instance._backends = {
                SecretBackend.ENV: mock_source,
                SecretBackend.FILE: mock_target,
            }
            mock_resolver.return_value = mock_instance

            result = secrets_migrate_command("env", "file")

        assert result == 0
        mock_target.set_secret.assert_not_called()
        captured = capsys.readouterr()
        assert "SKIP missing/secret (not found in source)" in captured.out
