from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from nthlayer.api.deps import get_job_enqueuer, session_dependency
from nthlayer.api.main import create_app


class DummyResult:
    def __init__(self, rowcount: int = 1) -> None:
        self.rowcount = rowcount


class DummySession:
    def __init__(self) -> None:
        self.queries: list[tuple[Any, dict[str, Any] | None]] = []
        self.added_objects: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj: Any) -> None:
        """Mock add method for ORM objects"""
        self.added_objects.append(obj)

    async def execute(self, query: Any, params: dict[str, Any] | None = None) -> DummyResult:
        self.queries.append((query, params))
        return DummyResult()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class StubEnqueuer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def enqueue(self, message: Any) -> str:
        payload = message.to_message_body() if hasattr(message, "to_message_body") else message
        self.messages.append({"raw": message, "payload": payload})
        return "msg-id"


class ErrorEnqueuer:
    async def enqueue(self, message: Any) -> str:
        raise RuntimeError("queue offline")


SESSION_INSTANCES: list[DummySession] = []


async def dummy_session_dependency() -> AsyncIterator[DummySession]:
    session = DummySession()
    SESSION_INSTANCES.append(session)
    yield session


@pytest.mark.asyncio
async def test_team_reconcile_enqueues_job() -> None:
    app = create_app()
    stub_enqueuer = StubEnqueuer()

    SESSION_INSTANCES.clear()

    app.dependency_overrides[session_dependency] = dummy_session_dependency
    app.dependency_overrides[get_job_enqueuer] = lambda: stub_enqueuer

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/teams/reconcile",
            json={"team_id": "team-123", "desired": {"id": "team-123", "name": "Team"}},
            headers={"X-Principal-Id": "user-1"},
        )

    assert response.status_code == 202
    body = response.json()
    UUID(body["job_id"])
    assert stub_enqueuer.messages, "message was enqueued"


@pytest.mark.asyncio
async def test_team_reconcile_rolls_back_on_enqueue_failure() -> None:
    app = create_app()
    SESSION_INSTANCES.clear()

    app.dependency_overrides[session_dependency] = dummy_session_dependency
    app.dependency_overrides[get_job_enqueuer] = lambda: ErrorEnqueuer()

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/teams/reconcile",
            json={"team_id": "team-123", "desired": {"id": "team-123", "name": "Team"}},
            headers={"X-Principal-Id": "user-1"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue reconciliation job"
    assert SESSION_INSTANCES, "session should have been created"
    session = SESSION_INSTANCES[-1]
    assert session.rollbacks == 1
    assert session.commits == 0
