import pytest
from nthlayer.providers.pagerduty import (
    PagerDutyProvider,
    PagerDutyProviderError,
    PagerDutyTeamMembershipResource,
)


@pytest.mark.asyncio
async def test_health_check_healthy(monkeypatch):
    calls = []

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        calls.append((method, path, kwargs))
        if method == "get" and path == "/users/me":
            return {"user": {"id": "me"}}
        raise AssertionError("unexpected path")

    provider = PagerDutyProvider("token")
    monkeypatch.setattr(PagerDutyProvider, "_request", fake_request, raising=False)
    health = await provider.health_check()
    assert health.status == "healthy"
    assert calls and calls[0][1] == "/users/me"


@pytest.mark.asyncio
async def test_health_check_unreachable(monkeypatch):
    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        raise PagerDutyProviderError("boom")

    provider = PagerDutyProvider("token")
    monkeypatch.setattr(PagerDutyProvider, "_request", fake_request, raising=False)
    health = await provider.health_check()
    assert health.status == "unreachable"
    assert "boom" in (health.details or "")


@pytest.mark.asyncio
async def test_team_membership_plan_add_and_remove(monkeypatch):
    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        if method == "get" and path.endswith("/members"):
            return {
                "members": [
                    {"user": {"id": "user-a"}},
                    {"user": {"id": "user-c"}},
                ]
            }
        raise AssertionError("unexpected path")

    provider = PagerDutyProvider("token")
    monkeypatch.setattr(PagerDutyProvider, "_request", fake_request, raising=False)
    resource = PagerDutyTeamMembershipResource(provider, team_id="team-123")

    # Desired has A and B; current has A and C ⇒ create B, delete C
    plan = await resource.plan({"manager_ids": ["user-a", "user-b"]})
    assert plan.has_changes
    actions = [c.action for c in plan.changes]
    assert actions.count("create") == 1
    assert actions.count("delete") == 1


@pytest.mark.asyncio
async def test_team_membership_apply_sets_memberships(monkeypatch):
    recorded = {"calls": []}

    async def fake_request(self, method, path, **kwargs):  # noqa: ANN001
        recorded["calls"].append((method, path, kwargs))
        return {}

    provider = PagerDutyProvider("token")
    monkeypatch.setattr(PagerDutyProvider, "_request", fake_request, raising=False)
    resource = PagerDutyTeamMembershipResource(provider, team_id="team-123")

    await resource.apply(
        {"manager_ids": ["user-a", "user-b"]},
        idempotency_key="idem-123",
    )

    assert recorded["calls"], "Expected a POST to set memberships"
    method, path, kwargs = recorded["calls"][0]
    assert method == "post"
    assert path.endswith("/teams/team-123/users")
    headers = kwargs.get("headers") or {}
    assert headers.get("Idempotency-Key") == "idem-123"
    body = kwargs.get("json") or {}
    memberships = body.get("memberships")
    assert {m["user"]["id"] for m in memberships} == {"user-a", "user-b"}
