from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from nthlayer.config import Settings, get_settings

logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)


class JWTValidator:
    """Validates JWT tokens from AWS Cognito or custom JWKS."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks: dict[str, Any] | None = None

    async def _get_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from configured URL."""
        if self._jwks:
            return self._jwks

        if not self.settings.jwt_jwks_url:
            if self.settings.cognito_user_pool_id and self.settings.cognito_region:
                jwks_url = (
                    f"https://cognito-idp.{self.settings.cognito_region}.amazonaws.com/"
                    f"{self.settings.cognito_user_pool_id}/.well-known/jwks.json"
                )
            else:
                raise ValueError("No JWKS URL or Cognito configuration provided")
        else:
            jwks_url = str(self.settings.jwt_jwks_url)

        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            self._jwks = response.json()
            return self._jwks

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return claims."""
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            jwks = await self._get_jwks()
            key = None
            for jwk in jwks.get("keys", []):
                if jwk.get("kid") == kid:
                    key = jwk
                    break

            if not key:
                raise JWTError("Public key not found in JWKS")

            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.cognito_audience,
                issuer=self.settings.jwt_issuer,
            )
            return claims

        except JWTError as exc:
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
    """Extract and validate JWT token from request."""
    if not settings.cognito_user_pool_id and not settings.jwt_jwks_url:
        logger.warning("auth_disabled", reason="No JWT configuration")
        return {"sub": "anonymous", "username": "anonymous"}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    validator = JWTValidator(settings)
    claims = await validator.validate_token(credentials.credentials)
    return claims
