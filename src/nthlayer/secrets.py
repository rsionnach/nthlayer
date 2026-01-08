from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import aioboto3
import structlog

logger = structlog.get_logger()


def _sanitize_secret_id(secret_id: str) -> str:
    """Sanitize secret ID for logging - hide sensitive details."""
    if not secret_id or len(secret_id) < 4:
        return "***"
    parts = secret_id.split("/")
    if len(parts) > 1:
        return f"{parts[0]}/***"
    return f"{secret_id[:2]}***"


class SecretsManager:
    """AWS Secrets Manager client for loading secrets at runtime."""

    def __init__(self, region: str = "eu-west-1") -> None:
        self._region = region
        self._cache: dict[str, Any] = {}

    async def get_secret(self, secret_id: str) -> dict[str, Any]:
        if secret_id in self._cache:
            return self._cache[secret_id]

        session = aioboto3.Session(region_name=self._region)
        try:
            async with session.client("secretsmanager") as client:
                response = await client.get_secret_value(SecretId=secret_id)
                secret_string = response.get("SecretString")
                if not secret_string:
                    logger.warning("secret_not_found", secret_id=_sanitize_secret_id(secret_id))
                    return {}
                secret_data = json.loads(secret_string)
                self._cache[secret_id] = secret_data
                return secret_data
        except Exception as exc:
            logger.error("failed_to_load_secret", error=type(exc).__name__)
            return {}

    async def get_secret_value(self, secret_id: str, key: str) -> str | None:
        secret_data = await self.get_secret(secret_id)
        return secret_data.get(key)


@lru_cache
def get_secrets_manager(region: str = "eu-west-1") -> SecretsManager:
    return SecretsManager(region)
