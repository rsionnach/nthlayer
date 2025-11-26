from __future__ import annotations

from typing import Any

from nthlayer.clients.base import BaseHTTPClient


class SlackNotifier(BaseHTTPClient):
    """Slack API client with retry logic and circuit breaker."""

    def __init__(
        self,
        token: str | None,
        *,
        base_url: str = "https://slack.com/api",
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
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def post_message(self, channel: str, text: str, **blocks: Any) -> None:
        if not self._token:
            return
        payload = {"channel": channel, "text": text} | blocks
        await self.post("/chat.postMessage", json=payload)
