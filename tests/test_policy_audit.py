"""Tests for policy audit logging.

Tests for PolicyAuditRecorder, PolicyAuditRepository,
policy override API, and DeploymentGate audit integration.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.policies.audit import PolicyEvaluation, PolicyOverride, PolicyViolation
from nthlayer.policies.recorder import PolicyAuditRecorder
from nthlayer.policies.repository import PolicyAuditRepository
from nthlayer.slos.gates import DeploymentGate, DeploymentGateCheck, GatePolicy, GateResult

# -- Fixtures --


@pytest.fixture
def mock_repository():
    """Create a mock PolicyAuditRepository."""
    repo = MagicMock(spec=PolicyAuditRepository)
    repo.record_evaluation = AsyncMock()
    repo.record_violation = AsyncMock()
    repo.record_override = AsyncMock()
    repo.get_evaluations = AsyncMock(return_value=[])
    repo.get_violations = AsyncMock(return_value=[])
    repo.get_overrides = AsyncMock(return_value=[])
    repo.get_active_override = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def recorder(mock_repository):
    """Create a PolicyAuditRecorder with mock repo."""
    return PolicyAuditRecorder(mock_repository)


@pytest.fixture
def approved_gate_check():
    """Create an approved DeploymentGateCheck."""
    return DeploymentGateCheck(
        service="payment-api",
        tier="critical",
        result=GateResult.APPROVED,
        budget_total_minutes=1440,
        budget_consumed_minutes=50,
        budget_remaining_minutes=1390,
        budget_remaining_percentage=96.5,
        warning_threshold=20.0,
        blocking_threshold=10.0,
        downstream_services=["user-api"],
        high_criticality_downstream=[],
        message="Deployment APPROVED",
        recommendations=["Continue monitoring"],
    )


@pytest.fixture
def blocked_gate_check():
    """Create a blocked DeploymentGateCheck."""
    return DeploymentGateCheck(
        service="payment-api",
        tier="critical",
        result=GateResult.BLOCKED,
        budget_total_minutes=1440,
        budget_consumed_minutes=1400,
        budget_remaining_minutes=40,
        budget_remaining_percentage=2.8,
        warning_threshold=20.0,
        blocking_threshold=10.0,
        downstream_services=["user-api", "billing-api"],
        high_criticality_downstream=["billing-api"],
        message="Deployment BLOCKED: Error budget critically low",
        recommendations=["Wait for recovery"],
    )


@pytest.fixture
def warning_gate_check():
    """Create a warning DeploymentGateCheck."""
    return DeploymentGateCheck(
        service="payment-api",
        tier="critical",
        result=GateResult.WARNING,
        budget_total_minutes=1440,
        budget_consumed_minutes=1200,
        budget_remaining_minutes=240,
        budget_remaining_percentage=16.7,
        warning_threshold=20.0,
        blocking_threshold=10.0,
        downstream_services=[],
        high_criticality_downstream=[],
        message="Deployment WARNING: Error budget low",
        recommendations=["Proceed with caution"],
    )


@pytest.fixture
def mock_context():
    """Create a mock PolicyContext."""
    ctx = MagicMock()
    ctx.to_dict.return_value = {
        "budget_remaining": 96.5,
        "tier": "critical",
        "environment": "prod",
    }
    return ctx


# -- TestPolicyAuditRecorder --


class TestPolicyAuditRecorder:
    """Test PolicyAuditRecorder orchestration."""

    @pytest.mark.asyncio
    async def test_record_gate_check_approved(
        self, recorder, mock_repository, approved_gate_check, mock_context
    ):
        """Approved gate check records evaluation, no violation."""
        result = await recorder.record_gate_check(
            gate_check=approved_gate_check,
            context=mock_context,
            actor="payments-team",
        )

        assert result is not None
        assert result.action == "evaluate"
        assert result.result == "approved"
        assert result.service == "payment-api"
        assert result.actor == "payments-team"

        mock_repository.record_evaluation.assert_awaited_once()
        mock_repository.record_violation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_record_gate_check_blocked(
        self, recorder, mock_repository, blocked_gate_check, mock_context
    ):
        """Blocked gate check records both evaluation and violation."""
        result = await recorder.record_gate_check(
            gate_check=blocked_gate_check,
            context=mock_context,
            deployment_id="deploy-123",
        )

        assert result is not None
        assert result.result == "blocked"

        mock_repository.record_evaluation.assert_awaited_once()
        mock_repository.record_violation.assert_awaited_once()

        violation_arg = mock_repository.record_violation.call_args[0][0]
        assert violation_arg.violation_type == "blocked"
        assert violation_arg.deployment_id == "deploy-123"
        assert violation_arg.budget_remaining_pct == 2.8

    @pytest.mark.asyncio
    async def test_record_gate_check_warning(
        self, recorder, mock_repository, warning_gate_check, mock_context
    ):
        """Warning gate check records both evaluation and violation."""
        result = await recorder.record_gate_check(
            gate_check=warning_gate_check,
            context=mock_context,
        )

        assert result is not None
        assert result.result == "warning"

        mock_repository.record_evaluation.assert_awaited_once()
        mock_repository.record_violation.assert_awaited_once()

        violation_arg = mock_repository.record_violation.call_args[0][0]
        assert violation_arg.violation_type == "warning"

    @pytest.mark.asyncio
    async def test_record_override(self, recorder, mock_repository):
        """Override records both override and evaluation."""
        result = await recorder.record_override(
            service="payment-api",
            policy_name="deployment-gate",
            approved_by="oncall@example.com",
            reason="Emergency hotfix",
            override_type="emergency_bypass",
        )

        assert result is not None
        assert result.approved_by == "oncall@example.com"
        assert result.override_type == "emergency_bypass"
        assert result.reason == "Emergency hotfix"

        mock_repository.record_override.assert_awaited_once()
        mock_repository.record_evaluation.assert_awaited_once()

        eval_arg = mock_repository.record_evaluation.call_args[0][0]
        assert eval_arg.action == "override"
        assert eval_arg.result == "approved"

    @pytest.mark.asyncio
    async def test_fail_open_on_db_error(
        self, recorder, mock_repository, approved_gate_check, mock_context
    ):
        """DB errors are swallowed — recorder returns None, no exception."""
        mock_repository.record_evaluation = AsyncMock(side_effect=Exception("DB connection lost"))

        result = await recorder.record_gate_check(
            gate_check=approved_gate_check,
            context=mock_context,
        )

        assert result is None  # Fail open

    @pytest.mark.asyncio
    async def test_fail_open_on_override_db_error(self, recorder, mock_repository):
        """Override DB errors are swallowed — returns None."""
        mock_repository.record_override = AsyncMock(side_effect=Exception("DB timeout"))

        result = await recorder.record_override(
            service="payment-api",
            policy_name="deployment-gate",
            approved_by="admin",
            reason="Test",
        )

        assert result is None


# -- TestPolicyAuditRepository --


class TestPolicyAuditRepository:
    """Test PolicyAuditRepository DB operations."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_record_evaluation_roundtrip(self, mock_session):
        """Record evaluation calls session.add and flush."""
        repo = PolicyAuditRepository(mock_session)

        evaluation = PolicyEvaluation(
            id="eval-001",
            timestamp=datetime(2025, 6, 1, 12, 0),
            service="payment-api",
            policy_name="deployment-gate",
            actor="team-lead",
            action="evaluate",
            result="approved",
            context_snapshot={"budget_remaining": 96.5},
            matched_condition=None,
            gate_check={"message": "approved"},
        )

        await repo.record_evaluation(evaluation)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_violation_roundtrip(self, mock_session):
        """Record violation calls session.add and flush."""
        repo = PolicyAuditRepository(mock_session)

        violation = PolicyViolation(
            id="viol-001",
            timestamp=datetime(2025, 6, 1, 12, 0),
            service="payment-api",
            policy_name="deployment-gate",
            deployment_id="deploy-123",
            violation_type="blocked",
            reason="Budget exhausted",
            budget_remaining_pct=2.8,
            threshold_pct=10.0,
            downstream_services=["billing-api"],
        )

        await repo.record_violation(violation)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_override_roundtrip(self, mock_session):
        """Record override calls session.add and flush."""
        repo = PolicyAuditRepository(mock_session)

        override = PolicyOverride(
            id="over-001",
            timestamp=datetime(2025, 6, 1, 12, 0),
            service="payment-api",
            policy_name="deployment-gate",
            deployment_id=None,
            approved_by="oncall@example.com",
            reason="Emergency fix",
            override_type="emergency_bypass",
        )

        await repo.record_override(override)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_evaluations_time_window(self, mock_session):
        """get_evaluations queries with time window filter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = PolicyAuditRepository(mock_session)
        results = await repo.get_evaluations("payment-api", hours=48)

        assert results == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_active_override_not_expired(self, mock_session):
        """Active override with future expiry is returned."""
        future = datetime.utcnow() + timedelta(hours=24)
        mock_model = MagicMock()
        mock_model.id = "over-001"
        mock_model.timestamp = datetime.utcnow()
        mock_model.service = "payment-api"
        mock_model.policy_name = "deployment-gate"
        mock_model.deployment_id = None
        mock_model.approved_by = "admin"
        mock_model.reason = "Approved"
        mock_model.override_type = "manual_approval"
        mock_model.expires_at = future
        mock_model.extra_data = {}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = PolicyAuditRepository(mock_session)
        result = await repo.get_active_override("payment-api", "deployment-gate")

        assert result is not None
        assert result.id == "over-001"

    @pytest.mark.asyncio
    async def test_get_active_override_expired(self, mock_session):
        """Expired override returns None."""
        past = datetime.utcnow() - timedelta(hours=24)
        mock_model = MagicMock()
        mock_model.id = "over-001"
        mock_model.timestamp = datetime.utcnow() - timedelta(hours=48)
        mock_model.service = "payment-api"
        mock_model.policy_name = "deployment-gate"
        mock_model.deployment_id = None
        mock_model.approved_by = "admin"
        mock_model.reason = "Approved"
        mock_model.override_type = "manual_approval"
        mock_model.expires_at = past
        mock_model.extra_data = {}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = PolicyAuditRepository(mock_session)
        result = await repo.get_active_override("payment-api", "deployment-gate")

        assert result is None


# -- TestPolicyOverrideAPI --


class TestPolicyOverrideAPI:
    """Test policy override API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from nthlayer.api.routes.policies import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        return TestClient(app)

    @pytest.mark.asyncio
    async def test_create_override_success(self, client):
        """POST /policies/{service}/override returns 201."""
        mock_override = PolicyOverride(
            id="over-001",
            timestamp=datetime.utcnow(),
            service="payment-api",
            policy_name="deployment-gate",
            deployment_id=None,
            approved_by="oncall@example.com",
            reason="Emergency hotfix",
            override_type="manual_approval",
        )

        with (
            patch("nthlayer.api.routes.policies.PolicyAuditRecorder") as MockRecorder,
            patch("nthlayer.api.routes.policies.PolicyAuditRepository"),
            patch("nthlayer.api.routes.policies.session_dependency") as mock_dep,
        ):
            mock_session = AsyncMock()
            mock_dep.return_value = mock_session

            mock_instance = MockRecorder.return_value
            mock_instance.record_override = AsyncMock(return_value=mock_override)

            response = client.post(
                "/api/v1/policies/payment-api/override",
                json={
                    "approved_by": "oncall@example.com",
                    "reason": "Emergency hotfix",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["service"] == "payment-api"
        assert data["approved_by"] == "oncall@example.com"

    def test_create_override_missing_fields(self, client):
        """POST /policies/{service}/override with missing fields returns 422."""
        response = client.post(
            "/api/v1/policies/payment-api/override",
            json={"reason": "Missing approved_by"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_audit_trail(self, client):
        """GET /policies/{service}/audit returns audit data."""
        with (
            patch("nthlayer.api.routes.policies.PolicyAuditRepository") as MockRepo,
            patch("nthlayer.api.routes.policies.session_dependency") as mock_dep,
        ):
            mock_session = AsyncMock()
            mock_dep.return_value = mock_session

            mock_instance = MockRepo.return_value
            mock_instance.get_evaluations = AsyncMock(return_value=[])
            mock_instance.get_violations = AsyncMock(return_value=[])
            mock_instance.get_overrides = AsyncMock(return_value=[])

            response = client.get("/api/v1/policies/payment-api/audit")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "payment-api"
        assert data["evaluations"] == []
        assert data["violations"] == []
        assert data["overrides"] == []

    @pytest.mark.asyncio
    async def test_get_audit_trail_empty(self, client):
        """GET /policies/{service}/audit with no data returns empty lists."""
        with (
            patch("nthlayer.api.routes.policies.PolicyAuditRepository") as MockRepo,
            patch("nthlayer.api.routes.policies.session_dependency") as mock_dep,
        ):
            mock_session = AsyncMock()
            mock_dep.return_value = mock_session

            mock_instance = MockRepo.return_value
            mock_instance.get_evaluations = AsyncMock(return_value=[])
            mock_instance.get_violations = AsyncMock(return_value=[])
            mock_instance.get_overrides = AsyncMock(return_value=[])

            response = client.get("/api/v1/policies/nonexistent-service/audit?hours=168")

        assert response.status_code == 200
        data = response.json()
        assert len(data["evaluations"]) == 0


# -- TestDeploymentGateWithAudit --


class TestDeploymentGateWithAudit:
    """Test DeploymentGate integration with audit recorder."""

    def test_gate_accepts_audit_recorder(self):
        """Gate accepts optional audit_recorder parameter."""
        mock_recorder = MagicMock()
        gate = DeploymentGate(audit_recorder=mock_recorder)

        assert gate.audit_recorder is mock_recorder

    def test_gate_works_without_audit_recorder(self):
        """Gate works identically when no audit_recorder is provided."""
        gate = DeploymentGate()

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
        )

        assert result.result == GateResult.APPROVED
        assert gate.audit_recorder is None

    def test_gate_continues_on_audit_failure(self):
        """Gate still returns correct result even if audit would fail."""
        # Ensure the gate's core logic is unaffected by audit_recorder presence
        mock_recorder = MagicMock()
        gate = DeploymentGate(audit_recorder=mock_recorder)

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=1400,
        )

        # Gate result should be BLOCKED regardless of audit_recorder state
        assert result.result == GateResult.BLOCKED
        assert result.is_blocked


# -- TestGateWiring --


class TestGateWiring:
    """Test that GatePolicy.from_spec is correctly wired."""

    def test_gate_uses_policy_from_spec(self):
        """GatePolicy.from_spec correctly creates policy from resource spec."""
        spec = {
            "thresholds": {"warning": 25.0, "blocking": 5.0},
            "conditions": [],
            "exceptions": [],
        }
        policy = GatePolicy.from_spec(spec)
        gate = DeploymentGate(policy=policy)

        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1000,
            budget_consumed_minutes=940,  # 6% remaining — between 5% and 25%
        )

        # 6% remaining is above 5% blocking but below 25% warning
        assert result.result == GateResult.WARNING

    def test_gate_default_when_no_resource(self):
        """Gate uses tier defaults when no DeploymentGate resource exists."""
        gate = DeploymentGate(policy=None)

        result = gate.check_deployment(
            service="payment-api",
            tier="standard",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
        )

        assert result.result == GateResult.APPROVED


# -- TestAuditConfig --


class TestAuditConfig:
    """Test OpenSRM audit config parsing."""

    def test_audit_config_defaults(self):
        from nthlayer.specs.manifest import AuditConfig

        config = AuditConfig()
        assert config.enabled is True
        assert config.retention_days == 90

    def test_deployment_config_with_audit(self):
        from nthlayer.specs.manifest import AuditConfig, DeploymentConfig

        config = DeploymentConfig(
            environments=["prod"],
            audit=AuditConfig(enabled=True, retention_days=30),
        )
        assert config.audit is not None
        assert config.audit.retention_days == 30

    def test_parse_opensrm_audit_section(self):
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "test", "tier": "standard"},
            "spec": {
                "type": "api",
                "deployment": {
                    "environments": ["prod"],
                    "audit": {"enabled": True, "retention_days": 60},
                },
            },
        }

        manifest = parse_opensrm(data)
        assert manifest.deployment is not None
        assert manifest.deployment.audit is not None
        assert manifest.deployment.audit.enabled is True
        assert manifest.deployment.audit.retention_days == 60

    def test_parse_opensrm_no_audit_section(self):
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "test", "tier": "standard"},
            "spec": {
                "type": "api",
                "deployment": {"environments": ["prod"]},
            },
        }

        manifest = parse_opensrm(data)
        assert manifest.deployment is not None
        assert manifest.deployment.audit is None
