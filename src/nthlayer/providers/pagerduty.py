from __future__ import annotations

import asyncio
from typing import Any, Callable, Iterable

import httpx
import pagerduty
from pagerduty import RestApiV2Client

from nthlayer.providers.base import (
    PlanChange,
    PlanResult,
    Provider,
    ProviderHealth,
    ProviderResource,
    ProviderResourceSchema,
)
from nthlayer.providers.registry import register_provider

DEFAULT_USER_AGENT = "nthlayer-provider-pagerduty/0.1.0"


class PagerDutyProviderError(RuntimeError):
    """Raised when the PagerDuty provider encounters an error."""


class PagerDutyProvider(Provider):
    """PagerDuty provider backed by the official python-pagerduty client."""

    name = "pagerduty"

    def __init__(
        self,
        api_token: str | None,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        default_from: str | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        client_factory: Callable[..., RestApiV2Client] | None = None,
    ) -> None:
        self._timeout = timeout
        self._user_agent = user_agent
        factory = client_factory or RestApiV2Client
        token = api_token or "nthlayer-placeholder-token"
        self._client = factory(token, default_from=default_from or "nthlayer@example.com")
        if base_url:
            # RestApiV2Client stores the base URL on the protected attribute.
            self._client._base_url = base_url.rstrip("/")  # type: ignore[attr-defined,assignment]

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)

    async def get_team(self, team_id: str) -> dict[str, Any]:
        data = await self._request("get", f"/teams/{team_id}")
        return data.get("team", data)

    async def get_team_members(self, team_id: str) -> list[dict[str, Any]]:
        data = await self._request("get", f"/teams/{team_id}/members")
        members = data.get("members") or data.get("team_memberships") or []
        return members

    async def set_team_members(
        self,
        team_id: str,
        memberships: list[dict[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> None:
        headers = {"X-User-Agent": self._user_agent}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        await self._request(
            "post",
            f"/teams/{team_id}/users",
            json={"memberships": memberships},
            headers=headers,
        )

    async def health_check(self) -> ProviderHealth:
        try:
            await self._request("get", "/users/me")
        except PagerDutyProviderError as exc:
            return ProviderHealth(status="unreachable", details=str(exc))
        return ProviderHealth(status="healthy")

    async def resources(self) -> list[ProviderResourceSchema]:
        return [PagerDutyTeamMembershipResource.schema()]  # type: ignore[arg-type]

    def team_membership_resource(self, team_id: str) -> "PagerDutyTeamMembershipResource":
        return PagerDutyTeamMembershipResource(self, team_id)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Accept", "application/vnd.pagerduty+json;version=2")
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("User-Agent", self._user_agent)

        def _call() -> dict[str, Any]:
            try:
                response: httpx.Response = getattr(self._client, method)(
                    path,
                    timeout=self._timeout,
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
            except (pagerduty.HttpError, pagerduty.ServerHttpError, httpx.HTTPError) as exc:
                raise PagerDutyProviderError(str(exc)) from exc
            try:
                return response.json()
            except ValueError as exc:  # pragma: no cover - unexpected
                raise PagerDutyProviderError("PagerDuty response did not contain JSON") from exc

        return await asyncio.to_thread(_call)


class PagerDutyTeamMembershipResource(ProviderResource):
    """Resource responsible for team membership reconciliation."""

    RESOURCE_NAME = "pagerduty_team_membership"

    def __init__(self, provider: PagerDutyProvider, team_id: str) -> None:
        self._provider = provider
        self._team_id = team_id

    @staticmethod
    def schema() -> ProviderResourceSchema:
        return ProviderResourceSchema(
            name=PagerDutyTeamMembershipResource.RESOURCE_NAME,
            description="Ensures PagerDuty team membership matches desired state",
            attributes={
                "team_id": "PagerDuty team identifier",
                "manager_ids": "List of desired manager user IDs",
            },
        )

    def _membership_payload(self, manager_ids: Iterable[str]) -> list[dict[str, Any]]:
        return [
            {"user": {"id": identifier}, "role": "manager"}
            for identifier in sorted({str(identifier) for identifier in manager_ids})
        ]

    async def plan(self, desired_state: dict[str, Any]) -> PlanResult:
        desired_ids = sorted({str(i) for i in desired_state.get("manager_ids", [])})
        memberships = await self._provider.get_team_members(self._team_id)
        current_ids = sorted({member["user"]["id"] for member in memberships if member.get("user")})

        additions = [PlanChange("create", {"user_id": user_id}) for user_id in desired_ids if user_id not in current_ids]
        removals = [PlanChange("delete", {"user_id": user_id}) for user_id in current_ids if user_id not in desired_ids]
        metadata = {
            "current_ids": current_ids,
            "desired_ids": desired_ids,
        }
        return PlanResult(changes=additions + removals, metadata=metadata)

    async def drift(self, desired_state: dict[str, Any]) -> PlanResult:
        return await self.plan(desired_state)

    async def apply(
        self,
        desired_state: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> None:
        memberships = self._membership_payload(desired_state.get("manager_ids", []))
        await self._provider.set_team_members(
            self._team_id,
            memberships,
            idempotency_key=idempotency_key,
        )


def _factory(**kwargs: Any) -> PagerDutyProvider:
    return PagerDutyProvider(**kwargs)


register_provider(
    PagerDutyProvider.name,
    _factory,
    version=pagerduty.__version__,
    description="PagerDuty REST API v2 provider",
)

__all__ = ["PagerDutyProvider", "PagerDutyProviderError"]
