"""Tests for API authentication module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jwt.exceptions import InvalidTokenError
from nthlayer.api.auth import ALLOW_ANONYMOUS_ENV, JWTValidator, get_current_user
from nthlayer.config.settings import Settings


class TestJWTValidator:
    """Tests for JWTValidator class."""

    def test_get_jwks_url_from_jwt_jwks_url(self):
        """_get_jwks_url returns jwt_jwks_url when set."""
        settings = Settings(jwt_jwks_url="https://example.com/jwks")
        validator = JWTValidator(settings)

        result = validator._get_jwks_url()

        assert result == "https://example.com/jwks"

    def test_get_jwks_url_constructs_cognito_url(self):
        """_get_jwks_url constructs Cognito JWKS URL when no jwt_jwks_url."""
        settings = Settings(
            cognito_user_pool_id="us-east-1_abc123",
            cognito_region="us-east-1",
        )
        validator = JWTValidator(settings)

        result = validator._get_jwks_url()

        expected_url = (
            "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123/.well-known/jwks.json"
        )
        assert result == expected_url

    def test_get_jwks_url_raises_when_no_config(self):
        """_get_jwks_url raises ValueError when no JWKS config."""
        settings = Settings()
        validator = JWTValidator(settings)

        with pytest.raises(ValueError, match="No JWKS URL or Cognito configuration"):
            validator._get_jwks_url()

    def test_get_jwks_client_creates_client(self):
        """_get_jwks_client creates a PyJWKClient."""
        settings = Settings(jwt_jwks_url="https://example.com/jwks")
        validator = JWTValidator(settings)

        with patch("nthlayer.api.auth.PyJWKClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = validator._get_jwks_client()

        mock_client_class.assert_called_once_with("https://example.com/jwks")
        assert result == mock_client

    def test_get_jwks_client_caches_client(self):
        """_get_jwks_client caches the PyJWKClient."""
        settings = Settings(jwt_jwks_url="https://example.com/jwks")
        validator = JWTValidator(settings)

        with patch("nthlayer.api.auth.PyJWKClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Call twice
            result1 = validator._get_jwks_client()
            result2 = validator._get_jwks_client()

        # Should only create once
        mock_client_class.assert_called_once()
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_validate_token_success(self):
        """validate_token returns claims for valid token."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
            cognito_audience="test-audience",
        )
        validator = JWTValidator(settings)

        # Mock the JWKS client and jwt.decode
        mock_signing_key = MagicMock()
        mock_signing_key.key = "test-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(validator, "_get_jwks_client", return_value=mock_jwks_client):
            with patch("nthlayer.api.auth.jwt.decode") as mock_decode:
                mock_decode.return_value = {"sub": "user123", "email": "user@example.com"}

                result = await validator.validate_token("valid-token")

        assert result["sub"] == "user123"
        assert result["email"] == "user@example.com"
        mock_jwks_client.get_signing_key_from_jwt.assert_called_once_with("valid-token")
        mock_decode.assert_called_once_with(
            "valid-token",
            "test-key",
            algorithms=["RS256"],
            audience="test-audience",
            issuer="https://issuer",
        )

    @pytest.mark.asyncio
    async def test_validate_token_invalid_token_error(self):
        """validate_token raises 401 on InvalidTokenError."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
        )
        validator = JWTValidator(settings)

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.side_effect = InvalidTokenError("Token expired")

        with patch.object(validator, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_token("expired-token")

        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_validate_token_integration_with_get_current_user(self):
        """get_current_user uses JWTValidator for token validation."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
            cognito_audience="test-audience",
        )

        mock_credentials = MagicMock()
        mock_credentials.credentials = "valid-token"

        with patch.object(JWTValidator, "validate_token", new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = {"sub": "user123", "username": "testuser"}

            result = await get_current_user(mock_credentials, settings)

        assert result["sub"] == "user123"
        mock_validate.assert_called_once_with("valid-token")


@pytest.mark.asyncio
async def test_get_current_user_fails_when_auth_not_configured():
    """Without auth config and no anonymous opt-in, should return 503."""
    settings = Settings()

    # Ensure anonymous access is not enabled
    env_backup = os.environ.pop(ALLOW_ANONYMOUS_ENV, None)
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None, settings)

        assert exc_info.value.status_code == 503
        assert "Authentication not configured" in str(exc_info.value.detail)
    finally:
        if env_backup is not None:
            os.environ[ALLOW_ANONYMOUS_ENV] = env_backup


@pytest.mark.asyncio
async def test_get_current_user_allows_anonymous_when_opted_in():
    """With NTHLAYER_ALLOW_ANONYMOUS=true, should return anonymous user."""
    settings = Settings()

    env_backup = os.environ.get(ALLOW_ANONYMOUS_ENV)
    os.environ[ALLOW_ANONYMOUS_ENV] = "true"
    try:
        result = await get_current_user(None, settings)

        assert result["sub"] == "anonymous"
        assert result["username"] == "anonymous"
    finally:
        if env_backup is not None:
            os.environ[ALLOW_ANONYMOUS_ENV] = env_backup
        else:
            os.environ.pop(ALLOW_ANONYMOUS_ENV, None)


@pytest.mark.asyncio
async def test_get_current_user_requires_credentials_when_configured():
    """With auth configured but no credentials, should return 401."""
    settings = Settings(
        jwt_jwks_url="https://example.com/.well-known/jwks.json",
        jwt_issuer="https://issuer",
        cognito_audience="aud",
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(None, settings)

    assert exc_info.value.status_code == 401
    assert "Missing authentication credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_anonymous_opt_in_case_insensitive():
    """NTHLAYER_ALLOW_ANONYMOUS should be case-insensitive."""
    settings = Settings()

    for value in ["true", "True", "TRUE", "TrUe"]:
        env_backup = os.environ.get(ALLOW_ANONYMOUS_ENV)
        os.environ[ALLOW_ANONYMOUS_ENV] = value
        try:
            result = await get_current_user(None, settings)
            assert result["sub"] == "anonymous", f"Failed for value: {value}"
        finally:
            if env_backup is not None:
                os.environ[ALLOW_ANONYMOUS_ENV] = env_backup
            else:
                os.environ.pop(ALLOW_ANONYMOUS_ENV, None)


@pytest.mark.asyncio
async def test_anonymous_opt_in_requires_exact_true():
    """Only 'true' (case-insensitive) should enable anonymous access."""
    settings = Settings()

    for value in ["yes", "1", "on", "enabled", ""]:
        env_backup = os.environ.get(ALLOW_ANONYMOUS_ENV)
        os.environ[ALLOW_ANONYMOUS_ENV] = value
        try:
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(None, settings)
            assert exc_info.value.status_code == 503, f"Should reject for value: {value}"
        finally:
            if env_backup is not None:
                os.environ[ALLOW_ANONYMOUS_ENV] = env_backup
            else:
                os.environ.pop(ALLOW_ANONYMOUS_ENV, None)
