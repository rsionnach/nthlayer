from __future__ import annotations

from typing import Any

from nthlayer.clients.base import BaseHTTPClient


class CortexClient(BaseHTTPClient):
    """Cortex API client with retry logic and circuit breaker."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        super().__init__(
            base_url,
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def get_team(self, team_id: str) -> dict[str, Any]:
        return await self.get(f"/api/teams/{team_id}")
