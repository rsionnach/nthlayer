from __future__ import annotations

import asyncio
from typing import Any

import httpx

from nthlayer.providers.base import (
    PlanChange,
    PlanResult,
    Provider,
    ProviderHealth,
    ProviderResource,
    ProviderResourceSchema,
)
from nthlayer.providers.registry import register_provider

DEFAULT_USER_AGENT = "nthlayer-provider-grafana/0.1.0"


class GrafanaProviderError(RuntimeError):
    pass


class GrafanaProvider(Provider):
    name = "grafana"

    def __init__(
        self,
        url: str,
        token: str | None,
        *,
        timeout: float = 30.0,
        org_id: int | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._org_id = org_id
        self._user_agent = user_agent

    async def aclose(self) -> None:  # for symmetry with other providers
        return None

    async def health_check(self) -> ProviderHealth:
        try:
            await self._request("GET", "/api/health")
            return ProviderHealth(status="healthy")
        except GrafanaProviderError as exc:
            return ProviderHealth(status="unreachable", details=str(exc))

    async def resources(self) -> list[ProviderResourceSchema]:
        return [
            GrafanaFolderResource.schema(),
            GrafanaDashboardResource.schema(),
            GrafanaDatasourceResource.schema(),
        ]

    def folder(self, uid: str) -> "GrafanaFolderResource":
        return GrafanaFolderResource(self, uid)

    def dashboard(self, uid: str) -> "GrafanaDashboardResource":
        return GrafanaDashboardResource(self, uid)

    def datasource(self, name: str) -> "GrafanaDatasourceResource":
        return GrafanaDatasourceResource(self, name)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        if self._token:
            headers.setdefault("Authorization", f"Bearer {self._token}")
        if self._org_id is not None:
            headers.setdefault("X-Grafana-Org-Id", str(self._org_id))
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("User-Agent", self._user_agent)

        def _call() -> dict[str, Any]:  # Regular function, not async
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.request(method, url, headers=headers, **kwargs)
                    resp.raise_for_status()
                    return resp.json() if resp.content else {}
            except httpx.HTTPError as exc:  # pragma: no cover - error path asserted by tests
                raise GrafanaProviderError(str(exc)) from exc

        return await asyncio.to_thread(_call)


class GrafanaFolderResource(ProviderResource):
    RESOURCE = "grafana_folder"

    def __init__(self, provider: GrafanaProvider, uid: str) -> None:
        self._p = provider
        self._uid = uid

    @staticmethod
    def schema() -> ProviderResourceSchema:
        return ProviderResourceSchema(
            name=GrafanaFolderResource.RESOURCE,
            description="Grafana folder by UID",
            attributes={"uid": "Folder UID", "title": "Folder title"},
        )

    async def plan(self, desired_state: dict[str, Any]) -> PlanResult:
        title = desired_state.get("title")
        try:
            data = await self._p._request("GET", f"/api/folders/uid/{self._uid}")
            current_title = data.get("title")
            if current_title != title:
                return PlanResult([PlanChange("update", {"title": title})])
            return PlanResult([])
        except Exception:  # pragma: no cover - surfaced via tests
            return PlanResult([PlanChange("create", {"title": title})])

    async def drift(self, desired_state: dict[str, Any]) -> PlanResult:
        return await self.plan(desired_state)

    async def apply(self, desired_state: dict[str, Any], *, idempotency_key: str | None = None) -> None:
        title = desired_state.get("title")
        try:
            await self._p._request("GET", f"/api/folders/uid/{self._uid}")
            await self._p._request("PUT", f"/api/folders/{self._uid}", json={"title": title})
        except GrafanaProviderError:
            await self._p._request("POST", "/api/folders", json={"uid": self._uid, "title": title})


class GrafanaDashboardResource(ProviderResource):
    RESOURCE = "grafana_dashboard"

    def __init__(self, provider: GrafanaProvider, uid: str) -> None:
        self._p = provider
        self._uid = uid

    @staticmethod
    def schema() -> ProviderResourceSchema:
        return ProviderResourceSchema(
            name=GrafanaDashboardResource.RESOURCE,
            description="Grafana dashboard by UID",
            attributes={
                "uid": "Dashboard UID",
                "title": "Dashboard title",
                "folderUid": "Folder UID",
                "dashboard": "Full dashboard JSON (without ids/version)",
            },
        )

    async def plan(self, desired_state: dict[str, Any]) -> PlanResult:
        desired_title = desired_state.get("title")
        desired_folder = desired_state.get("folderUid")
        try:
            data = await self._p._request("GET", f"/api/dashboards/uid/{self._uid}")
            meta = data.get("meta", {})
            current_title = data.get("dashboard", {}).get("title")
            current_folder = meta.get("folderUid")
            changes: list[PlanChange] = []
            if current_title != desired_title:
                changes.append(PlanChange("update", {"field": "title"}))
            if desired_folder and current_folder != desired_folder:
                changes.append(PlanChange("update", {"field": "folderUid"}))
            return PlanResult(changes)
        except Exception:  # pragma: no cover
            return PlanResult([PlanChange("create", {"uid": self._uid})])

    async def drift(self, desired_state: dict[str, Any]) -> PlanResult:
        return await self.plan(desired_state)

    async def apply(self, desired_state: dict[str, Any], *, idempotency_key: str | None = None) -> None:
        dashboard = desired_state.get("dashboard") or {
            "uid": self._uid,
            "title": desired_state.get("title"),
        }
        payload = {
            "dashboard": dashboard,
            "folderUid": desired_state.get("folderUid"),
            "overwrite": True,
        }
        await self._p._request("POST", "/api/dashboards/db", json=payload)


class GrafanaDatasourceResource(ProviderResource):
    RESOURCE = "grafana_datasource"

    def __init__(self, provider: GrafanaProvider, name: str) -> None:
        self._p = provider
        self._name = name

    @staticmethod
    def schema() -> ProviderResourceSchema:
        return ProviderResourceSchema(
            name=GrafanaDatasourceResource.RESOURCE,
            description="Grafana datasource by name",
            attributes={
                "name": "Datasource name",
                "type": "Datasource type",
                "url": "Target URL",
                "isDefault": "Whether to set as default",
            },
        )

    async def plan(self, desired_state: dict[str, Any]) -> PlanResult:
        try:
            ds = await self._p._request("GET", f"/api/datasources/name/{self._name}")
            changes: list[PlanChange] = []
            for field in ("type", "url", "isDefault"):
                if field in desired_state and ds.get(field) != desired_state.get(field):
                    changes.append(PlanChange("update", {"field": field}))
            return PlanResult(changes)
        except Exception:  # pragma: no cover
            return PlanResult([PlanChange("create", {"name": self._name})])

    async def drift(self, desired_state: dict[str, Any]) -> PlanResult:
        return await self.plan(desired_state)

    async def apply(self, desired_state: dict[str, Any], *, idempotency_key: str | None = None) -> None:
        try:
            ds = await self._p._request("GET", f"/api/datasources/name/{self._name}")
            ds_id = ds.get("id")
            await self._p._request("PUT", f"/api/datasources/{ds_id}", json=desired_state)
        except GrafanaProviderError:
            payload = {"name": self._name} | {k: v for k, v in desired_state.items() if k != "name"}
            await self._p._request("POST", "/api/datasources", json=payload)


def _factory(**kwargs: Any) -> GrafanaProvider:
    return GrafanaProvider(**kwargs)


register_provider(
    GrafanaProvider.name,
    _factory,
    version="httpx",  # We use raw HTTP; version pin can reflect SDK if later adopted
    description="Grafana provider (folders, dashboards, datasources)",
)

__all__ = [
    "GrafanaProvider",
    "GrafanaProviderError",
    "GrafanaFolderResource",
    "GrafanaDashboardResource",
    "GrafanaDatasourceResource",
]
