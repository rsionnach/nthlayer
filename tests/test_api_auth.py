"""Tests for API authentication module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from nthlayer.api.auth import ALLOW_ANONYMOUS_ENV, JWTValidator, get_current_user
from nthlayer.config.settings import Settings


class TestJWTValidator:
    """Tests for JWTValidator class."""

    @pytest.mark.asyncio
    async def test_get_jwks_returns_cached(self):
        """_get_jwks returns cached JWKS if available."""
        settings = Settings(jwt_jwks_url="https://example.com/jwks")
        validator = JWTValidator(settings)
        cached_jwks = {"keys": [{"kid": "test-key"}]}
        validator._jwks = cached_jwks

        result = await validator._get_jwks()

        assert result == cached_jwks

    @pytest.mark.asyncio
    async def test_get_jwks_fetches_from_url(self):
        """_get_jwks fetches from jwt_jwks_url."""
        settings = Settings(jwt_jwks_url="https://example.com/jwks")
        validator = JWTValidator(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kid": "fetched-key"}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validator._get_jwks()

        assert result == {"keys": [{"kid": "fetched-key"}]}
        mock_instance.get.assert_called_once_with("https://example.com/jwks")

    @pytest.mark.asyncio
    async def test_get_jwks_constructs_cognito_url(self):
        """_get_jwks constructs Cognito JWKS URL when no jwt_jwks_url."""
        settings = Settings(
            cognito_user_pool_id="us-east-1_abc123",
            cognito_region="us-east-1",
        )
        validator = JWTValidator(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kid": "cognito-key"}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validator._get_jwks()

        expected_url = (
            "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123/.well-known/jwks.json"
        )
        mock_instance.get.assert_called_once_with(expected_url)
        assert result == {"keys": [{"kid": "cognito-key"}]}

    @pytest.mark.asyncio
    async def test_get_jwks_raises_when_no_config(self):
        """_get_jwks raises ValueError when no JWKS config."""
        settings = Settings()
        validator = JWTValidator(settings)

        with pytest.raises(ValueError, match="No JWKS URL or Cognito configuration"):
            await validator._get_jwks()

    @pytest.mark.asyncio
    async def test_validate_token_success(self):
        """validate_token returns claims for valid token."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
            cognito_audience="test-audience",
        )
        validator = JWTValidator(settings)

        # Mock the JWKS
        mock_jwks = {"keys": [{"kid": "test-kid", "kty": "RSA", "n": "xxx", "e": "AQAB"}]}
        validator._jwks = mock_jwks

        # Mock jwt functions
        with patch.object(jwt, "get_unverified_header") as mock_header:
            with patch.object(jwt, "decode") as mock_decode:
                mock_header.return_value = {"kid": "test-kid"}
                mock_decode.return_value = {"sub": "user123", "email": "user@example.com"}

                result = await validator.validate_token("valid-token")

        assert result["sub"] == "user123"
        assert result["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_validate_token_key_not_found(self):
        """validate_token raises 401 when key not in JWKS."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
        )
        validator = JWTValidator(settings)

        # Mock JWKS with different key
        mock_jwks = {"keys": [{"kid": "different-kid"}]}
        validator._jwks = mock_jwks

        with patch.object(jwt, "get_unverified_header") as mock_header:
            mock_header.return_value = {"kid": "unknown-kid"}

            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_token("token-with-unknown-key")

        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_validate_token_jwt_error(self):
        """validate_token raises 401 on JWTError."""
        settings = Settings(
            jwt_jwks_url="https://example.com/jwks",
            jwt_issuer="https://issuer",
        )
        validator = JWTValidator(settings)
        validator._jwks = {"keys": [{"kid": "test-kid"}]}

        with patch.object(jwt, "get_unverified_header") as mock_header:
            with patch.object(jwt, "decode") as mock_decode:
                from jose import JWTError

                mock_header.return_value = {"kid": "test-kid"}
                mock_decode.side_effect = JWTError("Token expired")

                with pytest.raises(HTTPException) as exc_info:
                    await validator.validate_token("expired-token")

        assert exc_info.value.status_code == 401

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
