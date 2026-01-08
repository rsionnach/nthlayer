"""Tests for config/loader.py.

Tests for configuration file loading, validation, and merging.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from nthlayer.config.integrations import IntegrationConfig
from nthlayer.config.loader import (
    ConfigLoader,
    ConfigValidationError,
    PathTraversalError,
    _validate_path_safe,
    get_config_path,
    get_credentials_path,
    load_config,
    load_secrets_config,
    save_config,
    validate_environment_name,
    validate_url,
)
from nthlayer.config.secrets import SecretBackend, SecretConfig


class TestConfigValidationError:
    """Tests for ConfigValidationError exception."""

    def test_is_value_error(self):
        """Test ConfigValidationError is a ValueError."""
        with pytest.raises(ValueError):
            raise ConfigValidationError("test error")

    def test_message(self):
        """Test error message is preserved."""
        try:
            raise ConfigValidationError("custom message")
        except ConfigValidationError as e:
            assert str(e) == "custom message"


class TestPathTraversalError:
    """Tests for PathTraversalError exception."""

    def test_is_value_error(self):
        """Test PathTraversalError is a ValueError."""
        with pytest.raises(ValueError):
            raise PathTraversalError("test error")

    def test_message(self):
        """Test error message is preserved."""
        try:
            raise PathTraversalError("path error")
        except PathTraversalError as e:
            assert str(e) == "path error"


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        result = validate_url("http://localhost:9090")
        assert result == "http://localhost:9090"

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        result = validate_url("https://prometheus.example.com")
        assert result == "https://prometheus.example.com"

    def test_valid_url_with_path(self):
        """Test valid URL with path."""
        result = validate_url("http://localhost:9090/api/v1")
        assert result == "http://localhost:9090/api/v1"

    def test_empty_url_raises(self):
        """Test empty URL raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("")
        assert "cannot be empty" in str(exc.value)

    def test_empty_url_with_custom_field_name(self):
        """Test empty URL with custom field name."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("", field_name="prometheus_url")
        assert "prometheus_url cannot be empty" in str(exc.value)

    def test_invalid_scheme_raises(self):
        """Test invalid scheme raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("ftp://example.com")
        assert "must use http or https" in str(exc.value)

    def test_no_scheme_raises(self):
        """Test URL without scheme raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("localhost:9090")
        assert "must use http or https" in str(exc.value)

    def test_no_host_raises(self):
        """Test URL without host raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("http://")
        assert "must have a host" in str(exc.value)

    def test_invalid_url_raises(self):
        """Test completely invalid URL raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_url("not a url at all!!!")
        # Should fail due to missing scheme
        assert "http or https" in str(exc.value)


class TestValidateEnvironmentName:
    """Tests for validate_environment_name function."""

    def test_valid_simple_name(self):
        """Test valid simple environment name."""
        result = validate_environment_name("production")
        assert result == "production"

    def test_valid_with_dash(self):
        """Test valid name with dash."""
        result = validate_environment_name("prod-us-east-1")
        assert result == "prod-us-east-1"

    def test_valid_with_underscore(self):
        """Test valid name with underscore."""
        result = validate_environment_name("staging_v2")
        assert result == "staging_v2"

    def test_valid_with_numbers(self):
        """Test valid name with numbers."""
        result = validate_environment_name("env123")
        assert result == "env123"

    def test_empty_name_raises(self):
        """Test empty name raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name("")
        assert "cannot be empty" in str(exc.value)

    def test_starts_with_number_raises(self):
        """Test name starting with number raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name("123prod")
        assert "must start with a letter" in str(exc.value)

    def test_starts_with_dash_raises(self):
        """Test name starting with dash raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name("-production")
        assert "must start with a letter" in str(exc.value)

    def test_special_characters_raises(self):
        """Test name with special characters raises error."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name("prod@env")
        assert "must start with a letter" in str(exc.value)

    def test_too_long_raises(self):
        """Test name too long raises error."""
        long_name = "a" * 65
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name(long_name)
        assert "64 characters or less" in str(exc.value)

    def test_max_length_allowed(self):
        """Test max length name is allowed."""
        name = "a" * 64
        result = validate_environment_name(name)
        assert result == name

    def test_custom_field_name(self):
        """Test custom field name in error message."""
        with pytest.raises(ConfigValidationError) as exc:
            validate_environment_name("", field_name="target_env")
        assert "target_env" in str(exc.value)


class TestValidatePathSafe:
    """Tests for _validate_path_safe function."""

    def test_valid_absolute_path(self, tmp_path):
        """Test valid absolute path."""
        test_file = tmp_path / "config.yaml"
        test_file.touch()

        result = _validate_path_safe(test_file)
        assert result == test_file.resolve()

    def test_traversal_sequence_raises(self, tmp_path):
        """Test path with .. raises error."""
        with pytest.raises(PathTraversalError) as exc:
            _validate_path_safe(tmp_path / ".." / "etc" / "passwd")
        assert "traversal sequence" in str(exc.value)

    def test_double_dot_in_path_raises(self):
        """Test double dot in any part of path raises."""
        with pytest.raises(PathTraversalError):
            _validate_path_safe(Path("/some/path/../other"))

    def test_with_allowed_roots(self, tmp_path):
        """Test path within allowed root."""
        test_file = tmp_path / "subdir" / "config.yaml"
        test_file.parent.mkdir()
        test_file.touch()

        result = _validate_path_safe(test_file, allowed_roots=[tmp_path])
        assert result == test_file.resolve()

    def test_escapes_allowed_roots_raises(self, tmp_path):
        """Test path escaping allowed roots raises error."""
        other_dir = tmp_path.parent
        with pytest.raises(PathTraversalError) as exc:
            _validate_path_safe(other_dir / "file", allowed_roots=[tmp_path])
        assert "escapes allowed directories" in str(exc.value)

    def test_multiple_allowed_roots(self, tmp_path):
        """Test path within one of multiple allowed roots."""
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        root1.mkdir()
        root2.mkdir()
        test_file = root2 / "file.yaml"
        test_file.touch()

        result = _validate_path_safe(test_file, allowed_roots=[root1, root2])
        assert result == test_file.resolve()


class TestGetConfigPath:
    """Tests for get_config_path function."""

    def test_explicit_path_exists(self, tmp_path):
        """Test explicit path that exists."""
        config_file = tmp_path / "config.yaml"
        config_file.touch()

        result = get_config_path(str(config_file))
        assert result == config_file

    def test_explicit_path_not_exists(self, tmp_path):
        """Test explicit path that doesn't exist."""
        result = get_config_path(str(tmp_path / "nonexistent.yaml"))
        assert result is None

    def test_explicit_path_with_traversal_raises(self):
        """Test explicit path with traversal raises error."""
        with pytest.raises(PathTraversalError):
            get_config_path("/some/../path/config.yaml")

    def test_cwd_config_found(self, tmp_path, monkeypatch):
        """Test config found in current directory."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".nthlayer"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.touch()

        result = get_config_path()
        assert result == config_file

    def test_home_config_found(self, tmp_path, monkeypatch):
        """Test config found in home directory."""
        monkeypatch.chdir(tmp_path)  # cwd has no config

        with patch("nthlayer.config.loader.Path.home") as mock_home:
            mock_home.return_value = tmp_path / "home"
            home_config = tmp_path / "home" / ".nthlayer" / "config.yaml"
            home_config.parent.mkdir(parents=True)
            home_config.touch()

            result = get_config_path()
            assert result == home_config

    def test_no_config_found(self, tmp_path, monkeypatch):
        """Test no config found anywhere."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.config.loader.Path.home") as mock_home:
            mock_home.return_value = tmp_path / "home"
            (tmp_path / "home").mkdir()

            result = get_config_path()
            assert result is None

    def test_explicit_path_takes_precedence(self, tmp_path, monkeypatch):
        """Test explicit path takes precedence over search."""
        monkeypatch.chdir(tmp_path)

        # Create cwd config
        cwd_config = tmp_path / ".nthlayer" / "config.yaml"
        cwd_config.parent.mkdir()
        cwd_config.touch()

        # Create explicit config
        explicit_config = tmp_path / "custom.yaml"
        explicit_config.touch()

        result = get_config_path(str(explicit_config))
        assert result == explicit_config


class TestGetCredentialsPath:
    """Tests for get_credentials_path function."""

    def test_returns_home_credentials_path(self):
        """Test returns credentials path in home directory."""
        result = get_credentials_path()
        assert result == Path.home() / ".nthlayer" / "credentials.yaml"


class TestConfigLoader:
    """Tests for ConfigLoader class."""

    def test_init_with_path(self, tmp_path):
        """Test initialization with explicit path."""
        config_file = tmp_path / "config.yaml"
        loader = ConfigLoader(config_file)

        assert loader.config_path == config_file

    def test_init_without_path(self, monkeypatch, tmp_path):
        """Test initialization without path searches for config."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".nthlayer"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.touch()

        loader = ConfigLoader()
        assert loader.config_path == config_file

    def test_load_returns_default_when_no_file(self, tmp_path):
        """Test load returns default config when no file exists."""
        loader = ConfigLoader(tmp_path / "nonexistent.yaml")
        config = loader.load()

        assert isinstance(config, IntegrationConfig)
        assert config.prometheus.default == "local"

    def test_load_from_file(self, tmp_path):
        """Test loading config from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "version": 1,
            "prometheus": {
                "default": "prod",
                "profiles": {
                    "prod": {
                        "type": "mimir",
                        "url": "http://mimir:9009",
                    }
                },
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        config = loader.load()

        assert config.prometheus.default == "prod"
        assert config.prometheus.profiles["prod"].url == "http://mimir:9009"

    def test_load_handles_invalid_yaml(self, tmp_path):
        """Test load handles invalid YAML gracefully."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: {{")

        loader = ConfigLoader(config_file)
        config = loader.load()

        # Returns default config on error
        assert isinstance(config, IntegrationConfig)

    def test_load_handles_empty_file(self, tmp_path):
        """Test load handles empty file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        loader = ConfigLoader(config_file)
        config = loader.load()

        assert isinstance(config, IntegrationConfig)

    def test_load_secrets_config(self, tmp_path):
        """Test loading secrets configuration."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "secrets": {
                "backend": "vault",
                "strict": True,
                "fallback": ["env", "file"],
                "vault": {
                    "address": "http://vault:8200",
                    "namespace": "prod",
                    "auth_method": "kubernetes",
                    "role": "nthlayer",
                    "path_prefix": "secret/data/myapp",
                },
                "aws": {
                    "region": "us-west-2",
                    "secret_prefix": "myapp/",
                },
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.backend == SecretBackend.VAULT
        assert secrets.strict is True
        assert SecretBackend.ENV in secrets.fallback
        assert SecretBackend.FILE in secrets.fallback
        assert secrets.vault_address == "http://vault:8200"
        assert secrets.vault_namespace == "prod"
        assert secrets.vault_auth_method == "kubernetes"
        assert secrets.vault_role == "nthlayer"
        assert secrets.vault_path_prefix == "secret/data/myapp"
        assert secrets.aws_region == "us-west-2"
        assert secrets.aws_secret_prefix == "myapp/"

    def test_load_secrets_config_no_file(self, tmp_path):
        """Test loading secrets when no config file exists."""
        loader = ConfigLoader(tmp_path / "nonexistent.yaml")
        secrets = loader.load_secrets_config()

        assert isinstance(secrets, SecretConfig)
        assert secrets.backend == SecretBackend.ENV

    def test_load_secrets_config_invalid_backend(self, tmp_path):
        """Test loading secrets with invalid backend falls back to env."""
        config_file = tmp_path / "config.yaml"
        config_data = {"secrets": {"backend": "invalid_backend"}}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.backend == SecretBackend.ENV

    def test_load_secrets_config_invalid_fallback(self, tmp_path):
        """Test loading secrets with invalid fallback entries."""
        config_file = tmp_path / "config.yaml"
        config_data = {"secrets": {"fallback": ["env", "invalid", "file"]}}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        # Invalid entries are skipped
        assert SecretBackend.ENV in secrets.fallback
        assert SecretBackend.FILE in secrets.fallback
        assert len(secrets.fallback) == 2

    def test_load_secrets_config_with_credentials_file(self, tmp_path):
        """Test loading secrets with custom credentials file."""
        config_file = tmp_path / "config.yaml"
        creds_file = Path.home() / ".nthlayer" / "custom-creds.yaml"
        config_data = {"secrets": {"credentials_file": str(creds_file)}}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.credentials_file == creds_file

    def test_load_secrets_config_error_handling(self, tmp_path):
        """Test secrets config handles errors gracefully."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: {{")

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        # Returns default on error
        assert isinstance(secrets, SecretConfig)

    def test_save_config(self, tmp_path):
        """Test saving configuration to file."""
        config = IntegrationConfig.default()
        target_path = tmp_path / "saved-config.yaml"

        loader = ConfigLoader()
        loader.save(config, target_path)

        assert target_path.exists()
        # File contains YAML content (may include Python tags for enums)
        content = target_path.read_text()
        assert "version" in content
        assert "prometheus" in content

    def test_save_creates_parent_dirs(self, tmp_path):
        """Test save creates parent directories."""
        config = IntegrationConfig.default()
        target_path = tmp_path / "nested" / "dir" / "config.yaml"

        loader = ConfigLoader()
        loader.save(config, target_path)

        assert target_path.exists()

    def test_save_to_default_path(self, tmp_path, monkeypatch):
        """Test save to default path when none specified."""
        # Change to tmp_path to avoid finding project config
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.config.loader.Path.home") as mock_home:
            mock_home.return_value = tmp_path

            config = IntegrationConfig.default()
            # Create loader after patch is active, with no config found
            loader = ConfigLoader(None)
            loader.config_path = None  # Force to use default path
            loader.save(config)

            expected_path = tmp_path / ".nthlayer" / "config.yaml"
            assert expected_path.exists()


class TestLoadConfig:
    """Tests for load_config convenience function."""

    def test_load_config_with_path(self, tmp_path):
        """Test load_config with explicit path."""
        config_file = tmp_path / "config.yaml"
        config_data = {"version": 2}
        config_file.write_text(yaml.dump(config_data))

        config = load_config(str(config_file))

        assert config.version == 2

    def test_load_config_without_path(self, tmp_path, monkeypatch):
        """Test load_config searches for config."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".nthlayer"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_data = {"version": 3}
        config_file.write_text(yaml.dump(config_data))

        config = load_config()

        assert config.version == 3

    def test_load_config_returns_default(self, tmp_path, monkeypatch):
        """Test load_config returns default when no file found."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.config.loader.Path.home") as mock_home:
            mock_home.return_value = tmp_path / "home"
            (tmp_path / "home").mkdir()

            config = load_config()

            assert isinstance(config, IntegrationConfig)


class TestLoadSecretsConfig:
    """Tests for load_secrets_config convenience function."""

    def test_load_secrets_config_with_path(self, tmp_path):
        """Test load_secrets_config with explicit path."""
        config_file = tmp_path / "config.yaml"
        config_data = {"secrets": {"backend": "aws"}}
        config_file.write_text(yaml.dump(config_data))

        secrets = load_secrets_config(str(config_file))

        assert secrets.backend == SecretBackend.AWS

    def test_load_secrets_config_without_path(self, tmp_path, monkeypatch):
        """Test load_secrets_config searches for config."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".nthlayer"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_data = {"secrets": {"backend": "gcp"}}
        config_file.write_text(yaml.dump(config_data))

        secrets = load_secrets_config()

        assert secrets.backend == SecretBackend.GCP


class TestSaveConfig:
    """Tests for save_config convenience function."""

    def test_save_config_with_path(self, tmp_path):
        """Test save_config with explicit path."""
        config = IntegrationConfig.default()
        target_path = tmp_path / "config.yaml"

        save_config(config, str(target_path))

        assert target_path.exists()

    def test_save_config_without_path(self, tmp_path, monkeypatch):
        """Test save_config to default location."""
        # Change to tmp_path to avoid finding project config
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.config.loader.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            with patch("nthlayer.config.loader.get_config_path", return_value=None):
                config = IntegrationConfig.default()
                save_config(config)

                expected_path = tmp_path / ".nthlayer" / "config.yaml"
                assert expected_path.exists()


class TestParseSecretsConfigAllProviders:
    """Tests for parsing all provider-specific secrets config."""

    def test_azure_config(self, tmp_path):
        """Test Azure secrets config parsing."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "secrets": {
                "backend": "azure",
                "azure": {"vault_url": "https://myvault.vault.azure.net"},
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.backend == SecretBackend.AZURE
        assert secrets.azure_vault_url == "https://myvault.vault.azure.net"

    def test_gcp_config(self, tmp_path):
        """Test GCP secrets config parsing."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "secrets": {
                "backend": "gcp",
                "gcp": {"project_id": "my-project", "secret_prefix": "myapp-"},
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.backend == SecretBackend.GCP
        assert secrets.gcp_project_id == "my-project"
        assert secrets.gcp_secret_prefix == "myapp-"

    def test_doppler_config(self, tmp_path):
        """Test Doppler secrets config parsing."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "secrets": {
                "backend": "doppler",
                "doppler": {"project": "my-doppler-project", "config": "production"},
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        assert secrets.backend == SecretBackend.DOPPLER
        assert secrets.doppler_project == "my-doppler-project"
        assert secrets.doppler_config == "production"

    def test_all_defaults(self, tmp_path):
        """Test all provider defaults are applied."""
        config_file = tmp_path / "config.yaml"
        config_data = {"secrets": {}}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        secrets = loader.load_secrets_config()

        # Check defaults
        assert secrets.backend == SecretBackend.ENV
        assert secrets.strict is False
        assert secrets.vault_auth_method == "token"
        assert secrets.vault_path_prefix == "secret/data/nthlayer"
        assert secrets.aws_region == "us-east-1"
        assert secrets.aws_secret_prefix == "nthlayer/"
        assert secrets.gcp_secret_prefix == "nthlayer-"
