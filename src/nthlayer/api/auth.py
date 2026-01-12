from __future__ import annotations

import os
from typing import Any

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from nthlayer.config import Settings, get_settings

logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)

# Environment variable to explicitly allow anonymous access (for development only)
ALLOW_ANONYMOUS_ENV = "NTHLAYER_ALLOW_ANONYMOUS"


class JWTValidator:
    """Validates JWT tokens from AWS Cognito or custom JWKS."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks_client: PyJWKClient | None = None

    def _get_jwks_url(self) -> str:
        """Get JWKS URL from settings."""
        if self.settings.jwt_jwks_url:
            return str(self.settings.jwt_jwks_url)

        if self.settings.cognito_user_pool_id and self.settings.cognito_region:
            return (
                f"https://cognito-idp.{self.settings.cognito_region}.amazonaws.com/"
                f"{self.settings.cognito_user_pool_id}/.well-known/jwks.json"
            )

        raise ValueError("No JWKS URL or Cognito configuration provided")

    def _get_jwks_client(self) -> PyJWKClient:
        """Get or create JWKS client."""
        if self._jwks_client is None:
            jwks_url = self._get_jwks_url()
            self._jwks_client = PyJWKClient(jwks_url)
        return self._jwks_client

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return claims."""
        try:
            jwks_client = self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.settings.cognito_audience,
                issuer=self.settings.jwt_issuer,
            )
            return claims

        except InvalidTokenError as exc:
            logger.warning("jwt_validation_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Extract and validate JWT token from request.

    When authentication is not configured (no JWT/Cognito settings):
    - By default, returns 503 Service Unavailable (fail-closed security)
    - If NTHLAYER_ALLOW_ANONYMOUS=true, allows anonymous access (for development)

    Raises:
        HTTPException: 503 if auth not configured, 401 if credentials missing/invalid
    """
    if not settings.cognito_user_pool_id and not settings.jwt_jwks_url:
        # Check for explicit anonymous access opt-in
        allow_anonymous = os.environ.get(ALLOW_ANONYMOUS_ENV, "").lower() == "true"
        if allow_anonymous:
            logger.warning(
                "auth_anonymous_access",
                reason=f"{ALLOW_ANONYMOUS_ENV}=true",
                warning="Anonymous access enabled - do not use in production",
            )
            return {"sub": "anonymous", "username": "anonymous"}

        # Default: fail-closed - reject requests when auth not configured
        logger.error("auth_not_configured", reason="No JWT/Cognito configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured. Set JWT_JWKS_URL or Cognito settings.",
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    validator = JWTValidator(settings)
    claims = await validator.validate_token(credentials.credentials)
    return claims
