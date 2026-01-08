"""Tests for SLO storage repository.

Tests for database operations including SLO CRUD,
error budget storage, and deployment tracking.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from nthlayer.slos.models import (
    SLO,
    ErrorBudget,
    SLOStatus,
    TimeWindow,
    TimeWindowType,
)
from nthlayer.slos.storage import SLORepository


@pytest.fixture
def sample_slo():
    """Create a sample SLO for testing."""
    return SLO(
        id="slo-availability-001",
        service="payment-api",
        name="availability",
        description="Service availability SLO",
        target=99.95,
        time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
        query="sum(rate(http_requests_total{status!~'5..'}[5m])) / sum(rate(http_requests_total[5m]))",
        owner="platform-team",
        labels={"tier": "critical", "team": "payments"},
    )


@pytest.fixture
def sample_error_budget():
    """Create a sample error budget for testing."""
    return ErrorBudget(
        slo_id="slo-availability-001",
        service="payment-api",
        period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        total_budget_minutes=43.2,  # 0.05% of 30 days
        burned_minutes=10.5,
        remaining_minutes=32.7,
        incident_burn_minutes=5.0,
        deployment_burn_minutes=3.5,
        slo_breach_burn_minutes=2.0,
        status=SLOStatus.WARNING,
        burn_rate=0.35,
    )


@pytest.fixture
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_slo_model():
    """Create a mock SLO model from database."""
    model = MagicMock()
    model.id = "slo-test-001"
    model.service = "test-service"
    model.name = "availability"
    model.description = "Test SLO"
    model.target = 99.9
    model.time_window_duration = "30d"
    model.time_window_type = "rolling"
    model.query = "up{service='test'}"
    model.owner = "test-team"
    model.labels = {"tier": "standard"}
    model.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    model.updated_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    return model


@pytest.fixture
def mock_error_budget_model():
    """Create a mock error budget model from database."""
    model = MagicMock()
    model.slo_id = "slo-test-001"
    model.service = "test-service"
    model.period_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    model.period_end = datetime(2024, 1, 31, tzinfo=timezone.utc)
    model.total_budget_minutes = 43.2
    model.burned_minutes = 10.5
    model.remaining_minutes = 32.7
    model.incident_burn_minutes = 5.0
    model.deployment_burn_minutes = 3.5
    model.slo_breach_burn_minutes = 2.0
    model.status = "warning"
    model.burn_rate = 0.35
    model.updated_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    return model


class TestSLORepositoryInit:
    """Tests for SLORepository initialization."""

    def test_init_with_session(self, mock_session):
        """Test repository initialization with session."""
        repo = SLORepository(mock_session)
        assert repo.session == mock_session


class TestCreateSLO:
    """Tests for SLO creation."""

    @pytest.mark.asyncio
    async def test_create_slo_adds_to_session(self, mock_session, sample_slo):
        """Test that creating an SLO adds it to the session."""
        repo = SLORepository(mock_session)
        await repo.create_slo(sample_slo)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_slo_model_has_correct_id(self, mock_session, sample_slo):
        """Test that the created model has correct ID."""
        repo = SLORepository(mock_session)
        await repo.create_slo(sample_slo)

        added_model = mock_session.add.call_args[0][0]
        assert added_model.id == sample_slo.id
        assert added_model.service == sample_slo.service
        assert added_model.name == sample_slo.name


class TestGetSLO:
    """Tests for getting SLO by ID."""

    @pytest.mark.asyncio
    async def test_get_slo_found(self, mock_session, mock_slo_model):
        """Test getting an existing SLO."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_slo_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        slo = await repo.get_slo("slo-test-001")

        assert slo is not None
        assert slo.id == "slo-test-001"
        assert slo.service == "test-service"

    @pytest.mark.asyncio
    async def test_get_slo_not_found(self, mock_session):
        """Test getting a non-existent SLO."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        slo = await repo.get_slo("nonexistent")

        assert slo is None


class TestGetSLOsByService:
    """Tests for getting SLOs by service."""

    @pytest.mark.asyncio
    async def test_get_slos_by_service_found(self, mock_session, mock_slo_model):
        """Test getting SLOs for a service."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_slo_model]
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        slos = await repo.get_slos_by_service("test-service")

        assert len(slos) == 1
        assert slos[0].service == "test-service"

    @pytest.mark.asyncio
    async def test_get_slos_by_service_empty(self, mock_session):
        """Test getting SLOs for a service with no SLOs."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        slos = await repo.get_slos_by_service("unknown-service")

        assert slos == []


class TestUpdateSLO:
    """Tests for updating SLOs."""

    @pytest.mark.asyncio
    async def test_update_slo_success(self, mock_session, mock_slo_model, sample_slo):
        """Test successful SLO update."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_slo_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.update_slo(sample_slo)

        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_slo_not_found(self, mock_session, sample_slo):
        """Test updating a non-existent SLO."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)

        with pytest.raises(ValueError, match="SLO not found"):
            await repo.update_slo(sample_slo)


class TestDeleteSLO:
    """Tests for deleting SLOs."""

    @pytest.mark.asyncio
    async def test_delete_slo_exists(self, mock_session, mock_slo_model):
        """Test deleting an existing SLO."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_slo_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.delete_slo("slo-test-001")

        mock_session.delete.assert_called_once_with(mock_slo_model)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_slo_not_found(self, mock_session):
        """Test deleting a non-existent SLO does nothing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.delete_slo("nonexistent")

        mock_session.delete.assert_not_called()


class TestErrorBudget:
    """Tests for error budget operations."""

    @pytest.mark.asyncio
    async def test_create_error_budget(self, mock_session, sample_error_budget):
        """Test creating a new error budget."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Budget doesn't exist
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.create_or_update_error_budget(sample_error_budget)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_error_budget(
        self, mock_session, sample_error_budget, mock_error_budget_model
    ):
        """Test updating an existing error budget."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_error_budget_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.create_or_update_error_budget(sample_error_budget)

        # Should not call add for existing budget
        mock_session.add.assert_not_called()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_error_budget_found(self, mock_session, mock_error_budget_model):
        """Test getting current error budget."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_error_budget_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        budget = await repo.get_current_error_budget("slo-test-001")

        assert budget is not None
        assert budget.slo_id == "slo-test-001"
        assert budget.burned_minutes == 10.5

    @pytest.mark.asyncio
    async def test_get_current_error_budget_not_found(self, mock_session):
        """Test getting non-existent error budget."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        budget = await repo.get_current_error_budget("nonexistent")

        assert budget is None


class TestSLOMeasurement:
    """Tests for SLO measurement recording."""

    @pytest.mark.asyncio
    async def test_record_slo_measurement(self, mock_session):
        """Test recording an SLO measurement."""
        repo = SLORepository(mock_session)

        await repo.record_slo_measurement(
            slo_id="slo-test-001",
            service="test-service",
            timestamp=datetime.utcnow(),
            sli_value=99.95,
            target_value=99.9,
            compliant=True,
            budget_burn_minutes=0.5,
            extra_data={"window": "5m"},
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_slo_history(self, mock_session):
        """Test getting SLO measurement history."""
        mock_history_model = MagicMock()
        mock_history_model.timestamp = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        mock_history_model.sli_value = 99.95
        mock_history_model.target_value = 99.9
        mock_history_model.compliant = True
        mock_history_model.budget_burn_minutes = 0.5
        mock_history_model.extra_data = {"window": "5m"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_history_model]
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        history = await repo.get_slo_history(
            slo_id="slo-test-001",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )

        assert len(history) == 1
        assert history[0]["sli_value"] == 99.95
        assert history[0]["compliant"] is True


class TestDeployment:
    """Tests for deployment operations."""

    @pytest.mark.asyncio
    async def test_record_deployment(self, mock_session):
        """Test recording a deployment."""
        repo = SLORepository(mock_session)

        await repo.record_deployment(
            deployment_id="deploy-001",
            service="test-service",
            deployed_at=datetime.utcnow(),
            commit_sha="abc123",
            author="developer@example.com",
            pr_number="PR-42",
            source="github-actions",
            extra_data={"branch": "main"},
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_deployment(self, mock_session):
        """Test creating a deployment record."""
        from nthlayer.slos.deployment import Deployment

        deployment = Deployment(
            id="deploy-002",
            service="test-service",
            environment="production",
            deployed_at=datetime.utcnow(),
            commit_sha="def456",
            author="developer@example.com",
        )

        repo = SLORepository(mock_session)
        await repo.create_deployment(deployment)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_deployment_found(self, mock_session):
        """Test getting an existing deployment."""
        mock_model = MagicMock()
        mock_model.id = "deploy-001"
        mock_model.service = "test-service"
        mock_model.environment = "production"
        mock_model.deployed_at = datetime.utcnow()
        mock_model.commit_sha = "abc123"
        mock_model.author = "developer@example.com"
        mock_model.pr_number = None
        mock_model.source = "argocd"
        mock_model.extra_data = {}
        mock_model.correlated_burn_minutes = None
        mock_model.correlation_confidence = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        deployment = await repo.get_deployment("deploy-001")

        assert deployment is not None
        assert deployment.id == "deploy-001"
        assert deployment.service == "test-service"

    @pytest.mark.asyncio
    async def test_get_deployment_not_found(self, mock_session):
        """Test getting a non-existent deployment."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        deployment = await repo.get_deployment("nonexistent")

        assert deployment is None

    @pytest.mark.asyncio
    async def test_get_recent_deployments(self, mock_session):
        """Test getting recent deployments."""
        mock_model = MagicMock()
        mock_model.id = "deploy-001"
        mock_model.service = "test-service"
        mock_model.environment = "production"
        mock_model.deployed_at = datetime.utcnow()
        mock_model.commit_sha = "abc123"
        mock_model.author = "developer@example.com"
        mock_model.pr_number = None
        mock_model.source = "argocd"
        mock_model.extra_data = {}
        mock_model.correlated_burn_minutes = 5.0
        mock_model.correlation_confidence = 0.8

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        deployments = await repo.get_recent_deployments(
            service="test-service",
            hours=24,
            environment="production",
        )

        assert len(deployments) == 1
        assert deployments[0].id == "deploy-001"

    @pytest.mark.asyncio
    async def test_update_deployment_correlation(self, mock_session):
        """Test updating deployment correlation."""
        mock_model = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.update_deployment_correlation(
            deployment_id="deploy-001",
            burn_minutes=10.5,
            confidence=0.85,
        )

        assert mock_model.correlated_burn_minutes == 10.5
        assert mock_model.correlation_confidence == 0.85
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_deployment_correlation_not_found(self, mock_session):
        """Test updating non-existent deployment does nothing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        await repo.update_deployment_correlation(
            deployment_id="nonexistent",
            burn_minutes=10.5,
            confidence=0.85,
        )

        mock_session.flush.assert_not_called()


class TestIncident:
    """Tests for incident operations."""

    @pytest.mark.asyncio
    async def test_record_incident(self, mock_session):
        """Test recording an incident."""
        repo = SLORepository(mock_session)

        await repo.record_incident(
            incident_id="inc-001",
            service="test-service",
            started_at=datetime.utcnow(),
            title="High Error Rate",
            severity="critical",
            resolved_at=datetime.utcnow(),
            duration_minutes=45.5,
            budget_burn_minutes=12.0,
            source="pagerduty",
            extra_data={"urgency": "high"},
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestBurnRateWindow:
    """Tests for burn rate window calculation."""

    @pytest.mark.asyncio
    async def test_get_burn_rate_window(self, mock_session):
        """Test calculating burn rate in a window."""
        oldest_budget = MagicMock()
        oldest_budget.burned_minutes = 5.0
        oldest_budget.updated_at = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

        latest_budget = MagicMock()
        latest_budget.burned_minutes = 15.0
        latest_budget.updated_at = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [oldest_budget, latest_budget]
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        burn_rate = await repo.get_burn_rate_window(
            slo_id="slo-test-001",
            start_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
        )

        # Burn of 10 minutes over 60 minutes = 1/6 per minute
        assert burn_rate == pytest.approx(10.0 / 60.0)

    @pytest.mark.asyncio
    async def test_get_burn_rate_window_empty(self, mock_session):
        """Test burn rate with no budget data."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        burn_rate = await repo.get_burn_rate_window(
            slo_id="slo-test-001",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )

        assert burn_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_burn_rate_window_zero_duration(self, mock_session):
        """Test burn rate with zero duration window."""
        budget = MagicMock()
        budget.burned_minutes = 10.0
        budget.updated_at = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [budget]
        mock_session.execute.return_value = mock_result

        repo = SLORepository(mock_session)
        same_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        burn_rate = await repo.get_burn_rate_window(
            slo_id="slo-test-001",
            start_time=same_time,
            end_time=same_time,
        )

        assert burn_rate == 0.0


class TestModelConversions:
    """Tests for model conversion methods."""

    def test_model_to_slo(self, mock_session, mock_slo_model):
        """Test converting database model to SLO object."""
        repo = SLORepository(mock_session)
        slo = repo._model_to_slo(mock_slo_model)

        assert slo.id == mock_slo_model.id
        assert slo.service == mock_slo_model.service
        assert slo.name == mock_slo_model.name
        assert slo.target == mock_slo_model.target
        assert slo.time_window.duration == mock_slo_model.time_window_duration

    def test_model_to_slo_null_description(self, mock_session, mock_slo_model):
        """Test converting model with null description."""
        mock_slo_model.description = None

        repo = SLORepository(mock_session)
        slo = repo._model_to_slo(mock_slo_model)

        assert slo.description == ""

    def test_model_to_slo_null_labels(self, mock_session, mock_slo_model):
        """Test converting model with null labels."""
        mock_slo_model.labels = None

        repo = SLORepository(mock_session)
        slo = repo._model_to_slo(mock_slo_model)

        assert slo.labels == {}

    def test_model_to_error_budget(self, mock_session, mock_error_budget_model):
        """Test converting database model to ErrorBudget object."""
        repo = SLORepository(mock_session)
        budget = repo._model_to_error_budget(mock_error_budget_model)

        assert budget.slo_id == mock_error_budget_model.slo_id
        assert budget.service == mock_error_budget_model.service
        assert budget.burned_minutes == mock_error_budget_model.burned_minutes
        assert budget.status == SLOStatus.WARNING


class TestSLOModel:
    """Tests for SLO model itself."""

    def test_slo_creation(self, sample_slo):
        """Test basic SLO creation."""
        assert sample_slo.id == "slo-availability-001"
        assert sample_slo.service == "payment-api"
        assert sample_slo.target == 99.95

    def test_time_window_to_timedelta(self):
        """Test TimeWindow conversion to timedelta."""
        window = TimeWindow(duration="30d", type=TimeWindowType.ROLLING)
        td = window.to_timedelta()
        assert td == timedelta(days=30)

    def test_time_window_hours(self):
        """Test TimeWindow with hours."""
        window = TimeWindow(duration="24h", type=TimeWindowType.ROLLING)
        td = window.to_timedelta()
        assert td == timedelta(hours=24)

    def test_time_window_weeks(self):
        """Test TimeWindow with weeks."""
        window = TimeWindow(duration="4w", type=TimeWindowType.ROLLING)
        td = window.to_timedelta()
        assert td == timedelta(weeks=4)


class TestSLOStatus:
    """Tests for SLO status enum."""

    def test_status_values(self):
        """Test SLO status enum values."""
        assert SLOStatus.HEALTHY.value == "healthy"
        assert SLOStatus.WARNING.value == "warning"
        assert SLOStatus.CRITICAL.value == "critical"
        assert SLOStatus.EXHAUSTED.value == "exhausted"


class TestTimeWindowType:
    """Tests for time window type enum."""

    def test_window_types(self):
        """Test time window type enum values."""
        assert TimeWindowType.ROLLING.value == "rolling"
        assert TimeWindowType.CALENDAR.value == "calendar"
