"""Tests for nthlayer.domain.models — pure data models."""

from nthlayer.domain.models import (
    Finding,
    Run,
    RunStatus,
    Service,
    Team,
    TeamSource,
)


class TestRunStatus:
    def test_enum_values(self):
        assert RunStatus.queued == "queued"
        assert RunStatus.running == "running"
        assert RunStatus.succeeded == "succeeded"
        assert RunStatus.failed == "failed"

    def test_string_coercion(self):
        assert str(RunStatus.queued) == "queued"
        assert f"{RunStatus.failed}" == "failed"

    def test_membership(self):
        assert "queued" in RunStatus.__members__
        assert "invalid" not in RunStatus.__members__


class TestTeamSource:
    def test_defaults_to_none(self):
        ts = TeamSource()
        assert ts.cortex_id is None
        assert ts.pagerduty_id is None

    def test_with_values(self):
        ts = TeamSource(cortex_id="C1", pagerduty_id="P1")
        assert ts.cortex_id == "C1"
        assert ts.pagerduty_id == "P1"

    def test_model_dump_roundtrip(self):
        ts = TeamSource(cortex_id="C1")
        dumped = ts.model_dump()
        restored = TeamSource.model_validate(dumped)
        assert restored == ts


class TestTeam:
    def test_minimal(self):
        t = Team(id="t1", name="Platform")
        assert t.managers == []
        assert t.sources.cortex_id is None
        assert t.metadata == {}

    def test_full(self):
        t = Team(
            id="t1",
            name="Platform",
            managers=["alice"],
            sources=TeamSource(cortex_id="C1"),
            metadata={"region": "eu"},
        )
        assert t.metadata["region"] == "eu"
        assert t.sources.cortex_id == "C1"

    def test_immutable_defaults(self):
        t1, t2 = Team(id="a", name="A"), Team(id="b", name="B")
        assert t1.managers is not t2.managers

    def test_model_dump_roundtrip(self):
        t = Team(id="t1", name="Platform", managers=["alice"])
        dumped = t.model_dump()
        restored = Team.model_validate(dumped)
        assert restored.id == t.id
        assert list(restored.managers) == list(t.managers)


class TestService:
    def test_minimal(self):
        s = Service(id="s1", name="checkout", owner_team_id="t1")
        assert s.tier is None
        assert s.dependencies == []

    def test_with_deps(self):
        s = Service(
            id="s1",
            name="checkout",
            owner_team_id="t1",
            dependencies=["payment", "inventory"],
        )
        assert len(s.dependencies) == 2

    def test_with_tier(self):
        s = Service(id="s1", name="checkout", owner_team_id="t1", tier="critical")
        assert s.tier == "critical"

    def test_model_dump_roundtrip(self):
        s = Service(id="s1", name="checkout", owner_team_id="t1", dependencies=["a"])
        dumped = s.model_dump()
        restored = Service.model_validate(dumped)
        assert restored.id == s.id
        assert list(restored.dependencies) == list(s.dependencies)


class TestRun:
    def test_defaults(self):
        r = Run(job_id="j1", type="validate")
        assert r.status == RunStatus.queued
        assert r.started_at is None
        assert r.finished_at is None
        assert r.requested_by is None
        assert r.idempotency_key is None

    def test_status_transition(self):
        r = Run(job_id="j1", type="validate", status=RunStatus.running)
        assert r.status == RunStatus.running

    def test_with_timestamps(self):
        r = Run(
            job_id="j1",
            type="validate",
            started_at=1000.0,
            finished_at=2000.0,
        )
        assert r.finished_at - r.started_at == 1000.0

    def test_model_dump_roundtrip(self):
        r = Run(job_id="j1", type="validate", status=RunStatus.succeeded)
        dumped = r.model_dump()
        restored = Run.model_validate(dumped)
        assert restored.status == RunStatus.succeeded


class TestFinding:
    def test_minimal(self):
        f = Finding(run_id="r1", entity_ref="svc:checkout", action="create")
        assert f.before is None
        assert f.after is None
        assert f.outcome is None
        assert list(f.api_calls) == []

    def test_full(self):
        f = Finding(
            run_id="r1",
            entity_ref="svc:checkout",
            before={"status": "ok"},
            after={"status": "degraded"},
            action="update",
            api_calls=[{"method": "PUT", "url": "/svc"}],
            outcome="applied",
        )
        assert f.before["status"] == "ok"
        assert f.after["status"] == "degraded"
        assert f.outcome == "applied"
        calls = list(f.api_calls)
        assert len(calls) == 1

    def test_model_dump_roundtrip(self):
        f = Finding(run_id="r1", entity_ref="svc:x", action="create")
        dumped = f.model_dump()
        restored = Finding.model_validate(dumped)
        assert restored.run_id == f.run_id
        assert restored.action == f.action
