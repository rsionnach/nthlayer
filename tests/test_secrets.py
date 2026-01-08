"""Tests for secrets.py.

Tests for AWS Secrets Manager client.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.secrets import (
    SecretsManager,
    _sanitize_secret_id,
    get_secrets_manager,
)


class TestSanitizeSecretId:
    """Tests for _sanitize_secret_id function."""

    def test_empty_string(self):
        """Test sanitizing empty string."""
        assert _sanitize_secret_id("") == "***"

    def test_short_string(self):
        """Test sanitizing short string."""
        assert _sanitize_secret_id("abc") == "***"

    def test_simple_string(self):
        """Test sanitizing simple string."""
        result = _sanitize_secret_id("my-secret")
        assert result == "my***"

    def test_path_string(self):
        """Test sanitizing path-style secret ID."""
        result = _sanitize_secret_id("prod/database/password")
        assert result == "prod/***"

    def test_single_part(self):
        """Test sanitizing single-part string."""
        result = _sanitize_secret_id("simple")
        assert result == "si***"


class TestSecretsManager:
    """Tests for SecretsManager class."""

    def test_init_default_region(self):
        """Test initialization with default region."""
        manager = SecretsManager()
        assert manager._region == "eu-west-1"

    def test_init_custom_region(self):
        """Test initialization with custom region."""
        manager = SecretsManager(region="us-east-1")
        assert manager._region == "us-east-1"

    def test_init_empty_cache(self):
        """Test initialization creates empty cache."""
        manager = SecretsManager()
        assert manager._cache == {}

    @pytest.mark.asyncio
    async def test_get_secret_from_cache(self):
        """Test getting secret from cache."""
        manager = SecretsManager()
        manager._cache["my-secret"] = {"password": "cached-value"}

        result = await manager.get_secret("my-secret")

        assert result == {"password": "cached-value"}

    @pytest.mark.asyncio
    @patch("nthlayer.secrets.aioboto3.Session")
    async def test_get_secret_success(self, mock_session_class):
        """Test successfully getting a secret from AWS."""
        mock_client = AsyncMock()
        mock_client.get_secret_value = AsyncMock(
            return_value={
                "SecretString": json.dumps({"username": "admin", "password": "secret123"})
            }
        )

        mock_session = MagicMock()
        mock_session.client = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        mock_session_class.return_value = mock_session

        manager = SecretsManager()
        result = await manager.get_secret("my-secret")

        assert result == {"username": "admin", "password": "secret123"}
        assert manager._cache["my-secret"] == result

    @pytest.mark.asyncio
    @patch("nthlayer.secrets.aioboto3.Session")
    async def test_get_secret_empty_string(self, mock_session_class):
        """Test getting secret with empty SecretString."""
        mock_client = AsyncMock()
        mock_client.get_secret_value = AsyncMock(return_value={"SecretString": None})

        mock_session = MagicMock()
        mock_session.client = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        mock_session_class.return_value = mock_session

        manager = SecretsManager()
        result = await manager.get_secret("empty-secret")

        assert result == {}

    @pytest.mark.asyncio
    @patch("nthlayer.secrets.aioboto3.Session")
    async def test_get_secret_exception(self, mock_session_class):
        """Test getting secret with exception."""
        mock_client = AsyncMock()
        mock_client.get_secret_value = AsyncMock(side_effect=Exception("AccessDenied"))

        mock_session = MagicMock()
        mock_session.client = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        mock_session_class.return_value = mock_session

        manager = SecretsManager()
        result = await manager.get_secret("forbidden-secret")

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_secret_value_found(self):
        """Test getting a specific key from secret."""
        manager = SecretsManager()
        manager._cache["db-creds"] = {"username": "admin", "password": "secret"}

        result = await manager.get_secret_value("db-creds", "password")

        assert result == "secret"

    @pytest.mark.asyncio
    async def test_get_secret_value_not_found(self):
        """Test getting non-existent key from secret."""
        manager = SecretsManager()
        manager._cache["db-creds"] = {"username": "admin"}

        result = await manager.get_secret_value("db-creds", "password")

        assert result is None


class TestGetSecretsManager:
    """Tests for get_secrets_manager function."""

    def test_returns_secrets_manager(self):
        """Test function returns SecretsManager instance."""
        # Clear cache first
        get_secrets_manager.cache_clear()

        manager = get_secrets_manager()
        assert isinstance(manager, SecretsManager)

    def test_caches_instance(self):
        """Test function caches the instance."""
        get_secrets_manager.cache_clear()

        manager1 = get_secrets_manager()
        manager2 = get_secrets_manager()

        assert manager1 is manager2

    def test_different_regions_different_instances(self):
        """Test different regions return different cached instances."""
        get_secrets_manager.cache_clear()

        manager1 = get_secrets_manager("us-east-1")
        manager2 = get_secrets_manager("eu-west-1")

        assert manager1 is not manager2
        assert manager1._region == "us-east-1"
        assert manager2._region == "eu-west-1"
