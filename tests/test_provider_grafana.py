import pytest
from nthlayer.providers.grafana import (
    GrafanaDashboardResource,
    GrafanaDatasourceResource,
    GrafanaFolderResource,
    GrafanaProvider,
)


@pytest.mark.asyncio
async def test_health_check(monkeypatch):
    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        assert method == "GET" and path == "/api/health"
        return {"database": "ok"}

    p = GrafanaProvider("https://grafana.example.com", "token")
    monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)
    health = await p.health_check()
    assert health.status == "healthy"


@pytest.mark.asyncio
async def test_folder_plan_create_and_update(monkeypatch):
    calls = {"get": 0}

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        if method == "GET" and path.startswith("/api/folders/uid/"):
            calls["get"] += 1
            if calls["get"] == 1:
                raise RuntimeError("simulate 404")
            return {"title": "Old"}
        return {}

    p = GrafanaProvider("https://grafana.example.com", "token")
    monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)
    r = GrafanaFolderResource(p, uid="folder-1")

    plan_create = await r.plan({"title": "New"})
    assert plan_create.has_changes and plan_create.changes[0].action == "create"

    # Now second call simulates exists with different title
    plan_update = await r.plan({"title": "New"})
    assert plan_update.has_changes and plan_update.changes[0].action == "update"


@pytest.mark.asyncio
async def test_dashboard_plan_create_and_apply(monkeypatch):
    recorded = []

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        if method == "GET" and path.startswith("/api/dashboards/uid/"):
            raise RuntimeError("simulate 404")
        recorded.append((method, path, kwargs))
        return {}

    p = GrafanaProvider("https://grafana.example.com", "token")
    monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)
    r = GrafanaDashboardResource(p, uid="db-1")

    plan = await r.plan({"title": "T", "folderUid": "f-1"})
    assert plan.has_changes and plan.changes[0].action == "create"

    await r.apply({"title": "T", "folderUid": "f-1"})
    assert recorded and recorded[0][1] == "/api/dashboards/db"


@pytest.mark.asyncio
async def test_datasource_plan_create_update(monkeypatch):
    calls = {"phase": 0}

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        if method == "GET" and path.startswith("/api/datasources/name/"):
            if calls["phase"] == 0:
                raise RuntimeError("404")
            return {"id": 100, "name": "prometheus", "type": "prometheus", "url": "http://old"}
        return {}

    p = GrafanaProvider("https://grafana.example.com", "token")
    monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)
    r = GrafanaDatasourceResource(p, name="prometheus")

    plan_create = await r.plan({"name": "prometheus", "type": "prometheus", "url": "http://new"})
    assert plan_create.has_changes and plan_create.changes[0].action == "create"

    calls["phase"] = 1
    plan_update = await r.plan({"name": "prometheus", "type": "prometheus", "url": "http://new"})
    assert plan_update.has_changes and plan_update.changes[0].action == "update"
