"""Tests for config/secrets/backends.py.

Tests for cloud secret backends (Vault, AWS, Azure, GCP, Doppler).
"""

from unittest.mock import MagicMock, patch

from nthlayer.config.secrets.backends import (
    AWSSecretBackend,
    AzureSecretBackend,
    DopplerSecretBackend,
    GCPSecretBackend,
    VaultSecretBackend,
    _sanitize_error,
)


class TestSanitizeError:
    """Tests for _sanitize_error helper."""

    def test_returns_exception_type(self):
        """Returns exception type name."""
        exc = ValueError("sensitive details")
        result = _sanitize_error(exc)
        assert result == "ValueError"

    def test_handles_custom_exceptions(self):
        """Handles custom exception types."""

        class CustomError(Exception):
            pass

        exc = CustomError("secret info")
        result = _sanitize_error(exc)
        assert result == "CustomError"


class TestVaultSecretBackend:
    """Tests for VaultSecretBackend."""

    def test_init(self):
        """Initializes with config."""
        config = MagicMock()
        backend = VaultSecretBackend(config)
        assert backend.config == config
        assert backend._client is None

    def test_get_client_with_token_auth(self, monkeypatch):
        """Gets client with token authentication."""
        monkeypatch.setenv("VAULT_TOKEN", "test-token")

        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client

        config = MagicMock()
        config.vault_address = "https://vault.example.com"
        config.vault_namespace = "nthlayer"
        config.vault_auth_method = "token"

        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            backend = VaultSecretBackend(config)
            client = backend._get_client()

        assert client == mock_client
        assert mock_client.token == "test-token"

    def test_get_client_with_kubernetes_auth(self, tmp_path, monkeypatch):
        """Gets client with Kubernetes authentication."""
        jwt_file = (
            tmp_path / "var" / "run" / "secrets" / "kubernetes.io" / "serviceaccount" / "token"
        )
        jwt_file.parent.mkdir(parents=True)
        jwt_file.write_text("k8s-jwt-token")

        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client

        config = MagicMock()
        config.vault_address = "https://vault.example.com"
        config.vault_namespace = None
        config.vault_auth_method = "kubernetes"
        config.vault_role = "nthlayer-role"

        # Patch os.path.exists to use our temp file
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            with patch("os.path.exists", return_value=True):
                with patch(
                    "builtins.open",
                    MagicMock(
                        return_value=MagicMock(
                            __enter__=MagicMock(
                                return_value=MagicMock(read=MagicMock(return_value="k8s-jwt"))
                            ),
                            __exit__=MagicMock(),
                        )
                    ),
                ):
                    backend = VaultSecretBackend(config)
                    client = backend._get_client()

        mock_client.auth.kubernetes.login.assert_called_once_with(
            role="nthlayer-role", jwt="k8s-jwt"
        )

    def test_get_client_with_approle_auth(self, monkeypatch):
        """Gets client with AppRole authentication."""
        monkeypatch.setenv("VAULT_ROLE_ID", "role-123")
        monkeypatch.setenv("VAULT_SECRET_ID", "secret-456")

        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client

        config = MagicMock()
        config.vault_address = "https://vault.example.com"
        config.vault_namespace = None
        config.vault_auth_method = "approle"

        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            backend = VaultSecretBackend(config)
            client = backend._get_client()

        mock_client.auth.approle.login.assert_called_once_with(
            role_id="role-123", secret_id="secret-456"
        )

    def test_get_secret_with_key_in_path(self):
        """Gets secret with key specified in path."""
        config = MagicMock()
        config.vault_path_prefix = "secret/data/nthlayer"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"api_key": "secret-value"}}
        }

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("grafana#api_key")

        assert result == "secret-value"
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once()

    def test_get_secret_without_key_separator(self):
        """Gets secret without hash separator."""
        config = MagicMock()
        config.vault_path_prefix = "secret/data/nthlayer"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"api_key": "value123"}}
        }

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("grafana/api_key")

        assert result == "value123"

    def test_get_secret_returns_none_on_error(self):
        """Returns None when secret not found."""
        config = MagicMock()
        config.vault_path_prefix = "secret"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("not found")

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("nonexistent")

        assert result is None

    def test_set_secret_success(self):
        """Sets secret successfully."""
        config = MagicMock()
        config.vault_path_prefix = "secret/data/nthlayer"

        mock_client = MagicMock()

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.secrets.kv.v2.create_or_update_secret.assert_called_once()

    def test_set_secret_failure(self):
        """Returns False when set fails."""
        config = MagicMock()
        config.vault_path_prefix = "secret"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = Exception("write failed")

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_list_secrets_success(self):
        """Lists secrets successfully."""
        config = MagicMock()
        config.vault_path_prefix = "secret/data/nthlayer"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.list_secrets.return_value = {
            "data": {"keys": ["grafana", "prometheus"]}
        }

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == ["grafana", "prometheus"]

    def test_list_secrets_empty_on_error(self):
        """Returns empty list on error."""
        config = MagicMock()
        config.vault_path_prefix = "secret"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.list_secrets.side_effect = Exception("list failed")

        backend = VaultSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == []

    def test_supports_write(self):
        """Supports write operations."""
        backend = VaultSecretBackend(MagicMock())
        assert backend.supports_write() is True


class TestAWSSecretBackend:
    """Tests for AWSSecretBackend."""

    def test_init(self):
        """Initializes with config."""
        config = MagicMock()
        backend = AWSSecretBackend(config)
        assert backend.config == config
        assert backend._client is None

    def test_get_client(self):
        """Gets boto3 client."""
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        config = MagicMock()
        config.aws_region = "us-east-1"

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            backend = AWSSecretBackend(config)
            client = backend._get_client()

        assert client == mock_client
        mock_boto3.client.assert_called_once_with("secretsmanager", region_name="us-east-1")

    def test_get_secret_with_key(self):
        """Gets secret value with key."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": '{"api_key": "secret123"}'}

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("grafana/api_key")

        assert result == "secret123"
        mock_client.get_secret_value.assert_called_once_with(SecretId="nthlayer/grafana")

    def test_get_secret_without_key(self):
        """Gets entire secret string without key."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "raw-secret-value"}

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("simple_secret")

        assert result == "raw-secret-value"

    def test_get_secret_returns_none_on_error(self):
        """Returns None when secret not found."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = Exception("not found")

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("nonexistent")

        assert result is None

    def test_set_secret_updates_existing(self):
        """Updates existing secret."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": '{"existing": "value"}'}
        mock_client.exceptions = MagicMock()
        mock_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.put_secret_value.assert_called_once()

    def test_set_secret_creates_new(self):
        """Creates new secret when not found."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.exceptions = MagicMock()
        ResourceNotFoundError = type("ResourceNotFoundException", (Exception,), {})
        mock_client.exceptions.ResourceNotFoundException = ResourceNotFoundError
        mock_client.get_secret_value.side_effect = ResourceNotFoundError("not found")
        mock_client.put_secret_value.side_effect = ResourceNotFoundError("not found")

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.create_secret.assert_called_once()

    def test_set_secret_failure(self):
        """Returns False when set fails."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.exceptions = MagicMock()
        mock_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_client.get_secret_value.side_effect = Exception("unexpected error")

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_list_secrets(self):
        """Lists secrets with prefix."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "SecretList": [
                    {"Name": "nthlayer/grafana"},
                    {"Name": "nthlayer/prometheus"},
                    {"Name": "other/secret"},  # Should be filtered out
                ]
            }
        ]
        mock_client.get_paginator.return_value = mock_paginator

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == ["grafana", "prometheus"]

    def test_list_secrets_empty_on_error(self):
        """Returns empty list on error."""
        config = MagicMock()
        config.aws_secret_prefix = "nthlayer/"

        mock_client = MagicMock()
        mock_client.get_paginator.side_effect = Exception("error")

        backend = AWSSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == []

    def test_supports_write(self):
        """Supports write operations."""
        backend = AWSSecretBackend(MagicMock())
        assert backend.supports_write() is True


class TestAzureSecretBackend:
    """Tests for AzureSecretBackend."""

    def test_init(self):
        """Initializes with config."""
        config = MagicMock()
        backend = AzureSecretBackend(config)
        assert backend.config == config
        assert backend._client is None

    def test_path_to_secret_name(self):
        """Converts path to Azure secret name."""
        backend = AzureSecretBackend(MagicMock())
        assert backend._path_to_secret_name("grafana/api_key") == "nthlayer-grafana-api-key"
        assert backend._path_to_secret_name("simple_secret") == "nthlayer-simple-secret"

    def test_get_secret_success(self):
        """Gets secret successfully."""
        config = MagicMock()
        config.azure_vault_url = "https://myvault.vault.azure.net"

        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_secret.value = "secret-value"
        mock_client.get_secret.return_value = mock_secret

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("grafana/api_key")

        assert result == "secret-value"
        mock_client.get_secret.assert_called_once_with("nthlayer-grafana-api-key")

    def test_get_secret_returns_none_on_error(self):
        """Returns None when secret not found."""
        config = MagicMock()

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = Exception("not found")

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("nonexistent")

        assert result is None

    def test_set_secret_success(self):
        """Sets secret successfully."""
        config = MagicMock()

        mock_client = MagicMock()

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.set_secret.assert_called_once_with("nthlayer-grafana-api-key", "new-value")

    def test_set_secret_failure(self):
        """Returns False when set fails."""
        config = MagicMock()

        mock_client = MagicMock()
        mock_client.set_secret.side_effect = Exception("write failed")

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_list_secrets(self):
        """Lists secrets with nthlayer prefix."""
        config = MagicMock()

        mock_client = MagicMock()
        mock_props = [
            MagicMock(name="nthlayer-grafana-api-key"),
            MagicMock(name="nthlayer-prometheus-password"),
            MagicMock(name="other-secret"),  # Should be filtered
        ]
        # Set name attribute properly
        mock_props[0].name = "nthlayer-grafana-api-key"
        mock_props[1].name = "nthlayer-prometheus-password"
        mock_props[2].name = "other-secret"
        mock_client.list_properties_of_secrets.return_value = mock_props

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert "grafana/api/key" in result or len(result) == 2

    def test_list_secrets_empty_on_error(self):
        """Returns empty list on error."""
        config = MagicMock()

        mock_client = MagicMock()
        mock_client.list_properties_of_secrets.side_effect = Exception("error")

        backend = AzureSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == []

    def test_supports_write(self):
        """Supports write operations."""
        backend = AzureSecretBackend(MagicMock())
        assert backend.supports_write() is True


class TestGCPSecretBackend:
    """Tests for GCPSecretBackend."""

    def test_init(self):
        """Initializes with config."""
        config = MagicMock()
        backend = GCPSecretBackend(config)
        assert backend.config == config
        assert backend._client is None

    def test_path_to_secret_name(self):
        """Converts path to GCP secret name."""
        config = MagicMock()
        config.gcp_secret_prefix = "nthlayer-"

        backend = GCPSecretBackend(config)
        assert backend._path_to_secret_name("grafana/api_key") == "nthlayer-grafana-api-key"

    def test_get_secret_success(self):
        """Gets secret successfully."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "secret-value"
        mock_client.access_secret_version.return_value = mock_response

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("grafana/api_key")

        assert result == "secret-value"

    def test_get_secret_returns_none_on_error(self):
        """Returns None when secret not found."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception("not found")

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.get_secret("nonexistent")

        assert result is None

    def test_set_secret_creates_new(self):
        """Creates new secret and version."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = Exception("not found")

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.create_secret.assert_called_once()
        mock_client.add_secret_version.assert_called_once()

    def test_set_secret_updates_existing(self):
        """Adds version to existing secret."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        mock_client.create_secret.assert_not_called()
        mock_client.add_secret_version.assert_called_once()

    def test_set_secret_failure(self):
        """Returns False when set fails."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()
        mock_client.add_secret_version.side_effect = Exception("write failed")

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_list_secrets(self):
        """Lists secrets with prefix."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()

        # Create mock secrets with proper name attribute
        secret1 = MagicMock()
        secret1.name = "projects/my-project/secrets/nthlayer-grafana-api-key"
        secret2 = MagicMock()
        secret2.name = "projects/my-project/secrets/nthlayer-prometheus-password"
        secret3 = MagicMock()
        secret3.name = "projects/my-project/secrets/other-secret"

        mock_client.list_secrets.return_value = [secret1, secret2, secret3]

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert len(result) == 2

    def test_list_secrets_empty_on_error(self):
        """Returns empty list on error."""
        config = MagicMock()
        config.gcp_project_id = "my-project"
        config.gcp_secret_prefix = "nthlayer-"

        mock_client = MagicMock()
        mock_client.list_secrets.side_effect = Exception("error")

        backend = GCPSecretBackend(config)
        backend._client = mock_client

        result = backend.list_secrets()

        assert result == []

    def test_supports_write(self):
        """Supports write operations."""
        backend = GCPSecretBackend(MagicMock())
        assert backend.supports_write() is True


class TestDopplerSecretBackend:
    """Tests for DopplerSecretBackend."""

    def test_init(self):
        """Initializes with config."""
        config = MagicMock()
        backend = DopplerSecretBackend(config)
        assert backend.config == config
        assert backend._secrets_cache is None

    def test_get_token_from_env(self, monkeypatch):
        """Gets token from environment."""
        monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.test-token")
        backend = DopplerSecretBackend(MagicMock())
        assert backend._get_token() == "dp.st.test-token"

    def test_get_token_returns_none_when_not_set(self, monkeypatch):
        """Returns None when token not set."""
        monkeypatch.delenv("DOPPLER_TOKEN", raising=False)
        backend = DopplerSecretBackend(MagicMock())
        assert backend._get_token() is None

    def test_path_to_key(self):
        """Converts path to Doppler key format."""
        backend = DopplerSecretBackend(MagicMock())
        assert backend._path_to_key("grafana/api_key") == "GRAFANA_API_KEY"
        assert backend._path_to_key("prometheus-password") == "PROMETHEUS_PASSWORD"

    def test_fetch_secrets_uses_cache(self, monkeypatch):
        """Uses cached secrets."""
        monkeypatch.setenv("DOPPLER_TOKEN", "token")
        backend = DopplerSecretBackend(MagicMock())
        backend._secrets_cache = {"GRAFANA_API_KEY": "cached-value"}

        result = backend._fetch_secrets()

        assert result == {"GRAFANA_API_KEY": "cached-value"}

    def test_fetch_secrets_no_token(self, monkeypatch):
        """Returns empty dict when no token."""
        monkeypatch.delenv("DOPPLER_TOKEN", raising=False)
        backend = DopplerSecretBackend(MagicMock())

        result = backend._fetch_secrets()

        assert result == {}

    def test_fetch_secrets_from_api(self, monkeypatch):
        """Fetches secrets from Doppler API."""
        monkeypatch.setenv("DOPPLER_TOKEN", "test-token")

        config = MagicMock()
        config.doppler_project = "myproject"
        config.doppler_config = "prd"

        mock_response = MagicMock()
        mock_response.json.return_value = {"GRAFANA_API_KEY": "api-value", "DB_PASSWORD": "db-pass"}
        mock_response.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_response

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            backend = DopplerSecretBackend(config)
            result = backend._fetch_secrets()

        assert result == {"GRAFANA_API_KEY": "api-value", "DB_PASSWORD": "db-pass"}
        assert backend._secrets_cache == result

    def test_fetch_secrets_api_error(self, monkeypatch):
        """Returns empty dict on API error."""
        monkeypatch.setenv("DOPPLER_TOKEN", "test-token")

        config = MagicMock()
        config.doppler_project = "myproject"
        config.doppler_config = "prd"

        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("API error")

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            backend = DopplerSecretBackend(config)
            result = backend._fetch_secrets()

        assert result == {}

    def test_get_secret(self, monkeypatch):
        """Gets secret from cache."""
        backend = DopplerSecretBackend(MagicMock())
        backend._secrets_cache = {"GRAFANA_API_KEY": "secret-value"}

        result = backend.get_secret("grafana/api_key")

        assert result == "secret-value"

    def test_get_secret_not_found(self, monkeypatch):
        """Returns None when secret not in cache."""
        backend = DopplerSecretBackend(MagicMock())
        backend._secrets_cache = {}

        result = backend.get_secret("nonexistent")

        assert result is None

    def test_set_secret_no_token(self, monkeypatch):
        """Returns False when no token."""
        monkeypatch.delenv("DOPPLER_TOKEN", raising=False)
        backend = DopplerSecretBackend(MagicMock())

        result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_set_secret_success(self, monkeypatch):
        """Sets secret via API."""
        monkeypatch.setenv("DOPPLER_TOKEN", "test-token")

        config = MagicMock()
        config.doppler_project = "myproject"
        config.doppler_config = "prd"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_response

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            backend = DopplerSecretBackend(config)
            backend._secrets_cache = {"OLD": "value"}
            result = backend.set_secret("grafana/api_key", "new-value")

        assert result is True
        assert backend._secrets_cache is None  # Cache invalidated

    def test_set_secret_failure(self, monkeypatch):
        """Returns False when API call fails."""
        monkeypatch.setenv("DOPPLER_TOKEN", "test-token")

        config = MagicMock()
        config.doppler_project = "myproject"
        config.doppler_config = "prd"

        mock_httpx = MagicMock()
        mock_httpx.post.side_effect = Exception("API error")

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            backend = DopplerSecretBackend(config)
            result = backend.set_secret("grafana/api_key", "value")

        assert result is False

    def test_list_secrets(self, monkeypatch):
        """Lists secrets from cache."""
        backend = DopplerSecretBackend(MagicMock())
        backend._secrets_cache = {"KEY1": "val1", "KEY2": "val2"}

        result = backend.list_secrets()

        assert sorted(result) == ["KEY1", "KEY2"]

    def test_supports_write(self):
        """Supports write operations."""
        backend = DopplerSecretBackend(MagicMock())
        assert backend.supports_write() is True
