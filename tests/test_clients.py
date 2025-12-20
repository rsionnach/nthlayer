import pytest
import respx
from httpx import Response
from nthlayer.clients.base import PermanentHTTPError
from nthlayer.clients.cortex import CortexClient
from nthlayer.clients.pagerduty import PagerDutyClient


@pytest.mark.asyncio
async def test_cortex_client_success():
    client = CortexClient("https://cortex.example.com", "test-token")

    with respx.mock:
        respx.get("https://cortex.example.com/api/teams/team-123").mock(
            return_value=Response(200, json={"id": "team-123", "name": "Team"})
        )

        team = await client.get_team("team-123")
        assert team["id"] == "team-123"
        assert team["name"] == "Team"


@pytest.mark.asyncio
async def test_cortex_client_retry_on_503():
    client = CortexClient("https://cortex.example.com", "test-token", max_retries=2)

    with respx.mock:
        route = respx.get("https://cortex.example.com/api/teams/team-123")
        route.side_effect = [
            Response(503),
            Response(200, json={"id": "team-123"}),
        ]

        team = await client.get_team("team-123")
        assert team["id"] == "team-123"
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_pagerduty_client_set_members_with_idempotency():
    client = PagerDutyClient("test-token")

    with respx.mock:
        route = respx.post("https://api.pagerduty.com/teams/team-123/users")
        route.mock(return_value=Response(200, json={}))

        await client.set_team_members(
            "team-123",
            [{"user": {"id": "user-1"}, "role": "manager"}],
            idempotency_key="test-key",
        )

        request = route.calls.last.request
        assert request.headers["Idempotency-Key"] == "test-key"


@pytest.mark.asyncio
async def test_client_permanent_error_no_retry():
    client = CortexClient("https://cortex.example.com", "test-token")

    with respx.mock:
        route = respx.get("https://cortex.example.com/api/teams/team-123")
        route.mock(return_value=Response(404))

        with pytest.raises(PermanentHTTPError):
            await client.get_team("team-123")

        assert route.call_count == 1
