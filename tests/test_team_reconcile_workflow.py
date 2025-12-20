import sys
import types

import pytest
from nthlayer.domain.models import Finding


class _MockCompiledGraph:
    async def ainvoke(self, state):  # pragma: no cover - not used in unit tests
        return state


class _MockStateGraph:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def add_node(self, *_args, **_kwargs) -> None:  # pragma: no cover
        return None

    def set_entry_point(self, *_args, **_kwargs) -> None:  # pragma: no cover
        return None

    def add_edge(self, *_args, **_kwargs) -> None:  # pragma: no cover
        return None

    def add_conditional_edges(self, *_args, **_kwargs) -> None:  # pragma: no cover
        return None

    def compile(self) -> _MockCompiledGraph:
        return _MockCompiledGraph()


sys.modules.setdefault(
    "langgraph.graph", types.SimpleNamespace(END="END", StateGraph=_MockStateGraph)
)

from nthlayer.workflows.team_reconcile import TeamReconcileWorkflow


class StubCortex:
    async def get_team(self, team_id: str):  # pragma: no cover - unused in tests
        return {"id": team_id}


class StubPagerDuty:
    def __init__(self, current_members: list[str]) -> None:
        self.members = [{"user": {"id": member}} for member in current_members]
        self.latest_memberships: list[dict[str, str]] | None = None

    async def get_team(self, team_id: str):  # pragma: no cover - unused in tests
        return {"id": team_id}

    async def get_team_members(self, team_id: str):
        return self.members

    async def set_team_members(
        self, team_id: str, memberships, *, idempotency_key: str | None = None
    ):
        self.latest_memberships = list(memberships)


class StubSlack:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def post_message(self, channel: str, summary: str):  # pragma: no cover - not used yet
        self.messages.append((channel, summary))


class StubRepository:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.session = self

    async def record_finding(self, finding: Finding):
        self.findings.append(finding)

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_apply_diff_replaces_memberships_when_removals_needed():
    repo = StubRepository()
    workflow = TeamReconcileWorkflow(
        cortex=StubCortex(),
        pagerduty=StubPagerDuty(["user-1", "user-2"]),
        slack=StubSlack(),
        repository=repo,
    )

    state = {
        "job_id": "job-1",
        "team_id": "team-1",
        "desired": {"managers": ["user-2"]},
        "pagerduty_team": {"members": [{"user": {"id": "user-1"}}, {"user": {"id": "user-2"}}]},
    }

    state = await workflow._compute_diff(state)
    state = await workflow._apply_diff(state)

    assert state["applied"] is True
    assert workflow.pagerduty.latest_memberships == [{"user": {"id": "user-2"}, "role": "manager"}]
    assert repo.findings and repo.findings[0].after == {"managers": ["user-2"]}


@pytest.mark.asyncio
async def test_apply_diff_is_noop_when_no_changes():
    repo = StubRepository()
    workflow = TeamReconcileWorkflow(
        cortex=StubCortex(),
        pagerduty=StubPagerDuty(["user-1"]),
        slack=StubSlack(),
        repository=repo,
    )

    state = {
        "job_id": "job-1",
        "team_id": "team-1",
        "desired": {"managers": ["user-1"]},
        "pagerduty_team": {"members": [{"user": {"id": "user-1"}}]},
    }

    state = await workflow._compute_diff(state)
    state = await workflow._apply_diff(state)

    assert state["applied"] is False
    assert workflow.pagerduty.latest_memberships is None
    assert not repo.findings
