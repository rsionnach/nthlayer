"""Tests for slos/cli_helpers.py.

Tests for CLI helper functions and database operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.slos.cli_helpers import (
    get_cli_session,
    get_current_budget_from_db,
    get_slo_from_db,
    get_slos_by_service_from_db,
    list_all_slos_from_db,
    run_async,
    save_slo_to_db,
)
from nthlayer.slos.models import SLO, TimeWindow, TimeWindowType


@pytest.fixture
def sample_slo():
    """Create a sample SLO for testing."""
    return SLO(
        id="slo-test-001",
        service="test-service",
        name="availability",
        description="Test SLO",
        target=99.9,
        time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
        query="up{service='test'}",
        owner="test-team",
        labels={},
    )


class TestGetCliSession:
    """Tests for get_cli_session function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_session")
    @patch("nthlayer.slos.cli_helpers.init_engine")
    @patch("nthlayer.slos.cli_helpers.get_settings")
    async def test_yields_session(self, mock_settings, mock_init, mock_get_session):
        """Test get_cli_session yields a session."""
        mock_settings.return_value = MagicMock()
        mock_session = AsyncMock()

        async def mock_session_gen():
            yield mock_session

        mock_get_session.return_value = mock_session_gen()

        async with get_cli_session() as session:
            assert session is mock_session

        mock_init.assert_called_once()


class TestSaveSloToDb:
    """Tests for save_slo_to_db function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_create_new_slo(self, mock_get_session, sample_slo):
        """Test creating a new SLO."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_slo = AsyncMock(return_value=None)  # SLO doesn't exist
        mock_repo.create_slo = AsyncMock()

        async def mock_context():
            yield mock_session

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                action = await save_slo_to_db(sample_slo)

        assert action == "created"

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_update_existing_slo(self, mock_get_session, sample_slo):
        """Test updating an existing SLO."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_slo = AsyncMock(return_value=sample_slo)  # SLO exists
        mock_repo.update_slo = AsyncMock()

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                action = await save_slo_to_db(sample_slo)

        assert action == "updated"


class TestGetSloFromDb:
    """Tests for get_slo_from_db function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_get_existing_slo(self, mock_get_session, sample_slo):
        """Test getting an existing SLO."""
        mock_session = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_slo = AsyncMock(return_value=sample_slo)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await get_slo_from_db("slo-test-001")

        assert result == sample_slo

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_get_nonexistent_slo(self, mock_get_session):
        """Test getting a non-existent SLO."""
        mock_session = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_slo = AsyncMock(return_value=None)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await get_slo_from_db("nonexistent")

        assert result is None


class TestGetSlosByServiceFromDb:
    """Tests for get_slos_by_service_from_db function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_get_slos_for_service(self, mock_get_session, sample_slo):
        """Test getting SLOs for a service."""
        mock_session = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_slos_by_service = AsyncMock(return_value=[sample_slo])

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await get_slos_by_service_from_db("test-service")

        assert len(result) == 1
        assert result[0] == sample_slo


class TestListAllSlosFromDb:
    """Tests for list_all_slos_from_db function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_list_all_slos(self, mock_get_session, sample_slo):
        """Test listing all SLOs."""
        mock_session = AsyncMock()

        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_repo = MagicMock()
        mock_repo._model_to_slo = MagicMock(return_value=sample_slo)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await list_all_slos_from_db()

        assert len(result) == 1


class TestGetCurrentBudgetFromDb:
    """Tests for get_current_budget_from_db function."""

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_get_existing_budget(self, mock_get_session):
        """Test getting an existing error budget."""
        mock_session = AsyncMock()

        mock_budget = MagicMock()
        mock_budget.to_dict.return_value = {"burned_minutes": 10.5}

        mock_repo = MagicMock()
        mock_repo.get_current_error_budget = AsyncMock(return_value=mock_budget)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await get_current_budget_from_db("slo-test-001")

        assert result == {"burned_minutes": 10.5}

    @pytest.mark.asyncio
    @patch("nthlayer.slos.cli_helpers.get_cli_session")
    async def test_get_nonexistent_budget(self, mock_get_session):
        """Test getting non-existent error budget."""
        mock_session = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_current_error_budget = AsyncMock(return_value=None)

        with patch("nthlayer.slos.cli_helpers.SLORepository", return_value=mock_repo):
            with patch("nthlayer.slos.cli_helpers.get_cli_session") as mock_ctx:
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await get_current_budget_from_db("nonexistent")

        assert result is None


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_runs_coroutine(self):
        """Test running a simple coroutine."""

        async def simple_coro():
            return 42

        result = run_async(simple_coro())
        assert result == 42

    def test_runs_coroutine_with_value(self):
        """Test running coroutine that returns complex value."""

        async def complex_coro():
            return {"key": "value", "list": [1, 2, 3]}

        result = run_async(complex_coro())
        assert result == {"key": "value", "list": [1, 2, 3]}
