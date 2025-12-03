import pytest
from nthlayer.alerts.models import AlertRule
from nthlayer.demo import build_prometheus_alerts_demo, run_grafana_demo
from nthlayer.providers.grafana import GrafanaProvider, GrafanaProviderError


@pytest.mark.asyncio
async def test_run_grafana_demo_returns_changes(monkeypatch):
    provider = GrafanaProvider("https://grafana.example.com", "token", org_id=1)

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        if method == "GET" and path == "/api/folders/uid/nthlayer-demo":
            return {"title": "Legacy"}
        if method == "PUT" and path == "/api/folders/nthlayer-demo":
            return {}
        if method == "GET" and path == "/api/dashboards/uid/nthlayer-demo-dashboard":
            return {"dashboard": {"title": "Old"}, "meta": {"folderUid": "legacy"}}
        if method == "POST" and path == "/api/dashboards/db":
            return {}
        if method == "GET" and path == "/api/datasources/name/prometheus-demo":
            return {"id": 7, "type": "prometheus", "url": "http://old", "isDefault": False}
        if method == "PUT" and path == "/api/datasources/7":
            return {}
        raise AssertionError(f"unexpected call: {method} {path}")

    monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)

    result = await run_grafana_demo(provider)

    assert result["folder"]["applied"] is True
    assert any(change["action"] == "update" for change in result["folder"]["changes"])
    assert result["dashboard"]["applied"] is True
    assert result["datasource"]["applied"] is True


@pytest.mark.asyncio
async def test_run_grafana_demo_handles_errors(monkeypatch):
    provider = GrafanaProvider("https://grafana.example.com", None)

    async def failing_request(self, method, path, **kwargs):  # noqa: ANN001
        raise GrafanaProviderError("connection failed")

    monkeypatch.setattr(GrafanaProvider, "_request", failing_request, raising=False)

    result = await run_grafana_demo(provider)

    assert result["folder"]["applied"] is False
    assert "connection failed" in (result["folder"]["error"] or "")


def test_build_prometheus_alerts_demo_uses_limit(monkeypatch):
    samples = [
        AlertRule(name="A", expr="up == 0"),
        AlertRule(name="B", expr="up == 1"),
    ]

    class StubLoader:
        def __init__(self):
            self.calls = 0

        def load_technology(self, technology: str):
            self.calls += 1
            return samples

    monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

    result = build_prometheus_alerts_demo("postgres", limit=1)

    assert len(result) == 1
    assert result[0]["name"] == "A"
    assert result[0]["prometheus"]["alert"] == "A"
