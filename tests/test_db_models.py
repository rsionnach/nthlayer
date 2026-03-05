"""Tests for nthlayer.db.models — SQLAlchemy ORM models."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nthlayer.db.models import (
    Base,
    DeploymentModel,
    ErrorBudgetModel,
    Finding,
    IdempotencyKey,
    IncidentModel,
    PolicyEvaluationModel,
    PolicyOverrideModel,
    PolicyViolationModel,
    Run,
    SLOModel,
)
from nthlayer.domain.models import RunStatus


@pytest.fixture
def engine():
    """Create a SQLite in-memory engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """Create a session for testing."""
    with Session(engine) as session:
        yield session


class TestSchemaCreation:
    """Verify all tables and columns are created."""

    def test_all_tables_created(self, engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected = {
            "idempotency_keys",
            "runs",
            "findings",
            "slos",
            "error_budgets",
            "slo_history",
            "deployments",
            "incidents",
            "policy_evaluations",
            "policy_violations",
            "policy_overrides",
        }
        assert expected.issubset(set(tables))


class TestIdempotencyKey:
    def test_create(self, session):
        key = IdempotencyKey(team_id="team1", idem_key="key1")
        session.add(key)
        session.commit()
        assert key.id is not None
        assert key.created_at is not None

    def test_unique_constraint(self, session):
        """team_id + idem_key must be unique."""
        session.add(IdempotencyKey(team_id="team1", idem_key="key1"))
        session.commit()
        session.add(IdempotencyKey(team_id="team1", idem_key="key1"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_same_key_different_team(self, session):
        """Same key for different teams is allowed."""
        session.add(IdempotencyKey(team_id="team1", idem_key="key1"))
        session.add(IdempotencyKey(team_id="team2", idem_key="key1"))
        session.commit()  # Should not raise


class TestRunModel:
    def test_create(self, session):
        run = Run(
            job_id="j1",
            type="validate",
            status=RunStatus.queued.value,
        )
        session.add(run)
        session.commit()
        assert run.id is not None
        assert run.status == "queued"

    def test_status_values(self, session):
        for status in RunStatus:
            run = Run(job_id=f"j-{status.value}", type="test", status=status.value)
            session.add(run)
        session.commit()

    def test_unique_job_id(self, session):
        session.add(Run(job_id="j1", type="test", status="queued"))
        session.commit()
        session.add(Run(job_id="j1", type="test", status="queued"))
        with pytest.raises(IntegrityError):
            session.commit()


class TestFindingModel:
    def test_create(self, session):
        finding = Finding(
            run_id="r1",
            entity_ref="svc:checkout",
            action="create",
            api_calls=[],
        )
        session.add(finding)
        session.commit()
        assert finding.id is not None

    def test_with_json_fields(self, session):
        finding = Finding(
            run_id="r1",
            entity_ref="svc:checkout",
            before_state={"status": "ok"},
            after_state={"status": "degraded"},
            action="update",
            api_calls=[{"method": "PUT"}],
            outcome="applied",
        )
        session.add(finding)
        session.commit()

        # Re-query to verify JSON round-trip
        session.expire_all()
        loaded = session.get(Finding, finding.id)
        assert loaded.before_state == {"status": "ok"}
        assert loaded.api_calls == [{"method": "PUT"}]


class TestSLOModel:
    def test_create(self, session):
        slo = SLOModel(
            id="slo-1",
            service="checkout",
            name="Availability",
            target=0.999,
            time_window_duration="30d",
            time_window_type="rolling",
            query="sum(rate(http_requests_total{code!~'5..'}[5m]))",
        )
        session.add(slo)
        session.commit()
        assert slo.created_at is not None


class TestErrorBudgetModel:
    def test_create(self, session):
        # Need SLO first (foreign key)
        slo = SLOModel(
            id="slo-1",
            service="checkout",
            name="Avail",
            target=0.999,
            time_window_duration="30d",
            time_window_type="rolling",
            query="test",
        )
        session.add(slo)
        session.commit()

        budget = ErrorBudgetModel(
            slo_id="slo-1",
            service="checkout",
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 31),
            total_budget_minutes=43.2,
            remaining_minutes=30.0,
        )
        session.add(budget)
        session.commit()
        assert budget.id is not None
        assert budget.burned_minutes == 0.0


class TestDeploymentModel:
    def test_create(self, session):
        deploy = DeploymentModel(
            id="dep-1",
            service="checkout",
            environment="production",
            deployed_at=datetime(2026, 3, 5),
            source="github",
            commit_sha="abc123",
        )
        session.add(deploy)
        session.commit()
        assert deploy.created_at is not None


class TestIncidentModel:
    def test_create(self, session):
        incident = IncidentModel(
            id="inc-1",
            service="checkout",
            title="High error rate",
            severity="critical",
            started_at=datetime(2026, 3, 5),
        )
        session.add(incident)
        session.commit()
        assert incident.source == "pagerduty"


class TestPolicyModels:
    def test_policy_evaluation(self, session):
        ev = PolicyEvaluationModel(
            id="ev-1",
            timestamp=datetime(2026, 3, 5),
            service="checkout",
            policy_name="error-budget-gate",
            action="deploy",
            result="allowed",
        )
        session.add(ev)
        session.commit()

    def test_policy_violation(self, session):
        viol = PolicyViolationModel(
            id="viol-1",
            timestamp=datetime(2026, 3, 5),
            service="checkout",
            policy_name="error-budget-gate",
            violation_type="blocked",
            reason="Budget exhausted",
            budget_remaining_pct=5.0,
            threshold_pct=10.0,
        )
        session.add(viol)
        session.commit()

    def test_policy_override(self, session):
        override = PolicyOverrideModel(
            id="ov-1",
            timestamp=datetime(2026, 3, 5),
            service="checkout",
            policy_name="error-budget-gate",
            approved_by="alice",
            reason="Emergency hotfix",
            override_type="emergency",
        )
        session.add(override)
        session.commit()
