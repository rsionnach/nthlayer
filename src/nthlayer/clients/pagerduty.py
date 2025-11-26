from __future__ import annotations

from typing import Any, Iterable, Sequence

from nthlayer.providers.pagerduty import PagerDutyProvider


class PagerDutyClient:
    """Backward-compatible wrapper around the PagerDuty provider."""

    def __init__(
        self,
        token: str | None,
        *,
        base_url: str = "https://api.pagerduty.com",
        timeout: float = 30.0,
        max_retries: int = 3,  # noqa: ARG002 - maintained for compatibility
        backoff_factor: float = 2.0,  # noqa: ARG002 - maintained for compatibility
    ) -> None:
        self._provider = PagerDutyProvider(
            token,
            base_url=base_url,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._provider.aclose()

    async def get_team(self, team_id: str) -> dict[str, Any]:
        return await self._provider.get_team(team_id)

    async def get_team_members(self, team_id: str) -> Sequence[dict[str, Any]]:
        return await self._provider.get_team_members(team_id)

    async def set_team_members(
        self,
        team_id: str,
        members: Iterable[dict[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> None:
        await self._provider.set_team_members(
            team_id,
            list(members),
            idempotency_key=idempotency_key,
        )
