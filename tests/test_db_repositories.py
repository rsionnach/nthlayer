"""Tests for nthlayer.db.repositories — RunRepository with mocked async session."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from nthlayer.db.repositories import IdempotencyConflict, RunRepository
from nthlayer.domain.models import Finding, Run, RunStatus


class TestIdempotencyConflict:
    def test_is_runtime_error(self):
        err = IdempotencyConflict("key1")
        assert isinstance(err, RuntimeError)
        assert "key1" in str(err)


class TestRunRepository:
    def _make_repo(self, session=None):
        return RunRepository(session=session or AsyncMock())

    @pytest.mark.asyncio
    async def test_create_run(self):
        session = AsyncMock()
        repo = self._make_repo(session)
        run = Run(job_id="j1", type="validate")
        await repo.create_run(run)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_run_found(self):
        db_run = MagicMock()
        db_run.job_id = "j1"
        db_run.type = "validate"
        db_run.requested_by = None
        db_run.status = "queued"
        db_run.started_at = None
        db_run.finished_at = None
        db_run.idempotency_key = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_run

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        run = await repo.get_run("j1")

        assert run is not None
        assert run.job_id == "j1"
        assert run.status == RunStatus.queued

    @pytest.mark.asyncio
    async def test_get_run_not_found(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        run = await repo.get_run("nonexistent")
        assert run is None

    @pytest.mark.asyncio
    async def test_update_status(self):
        db_run = MagicMock()
        db_run.job_id = "j1"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_run

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        await repo.update_status("j1", RunStatus.running, started_at=1000.0)

        assert db_run.status == "running"
        assert db_run.started_at == 1000.0

    @pytest.mark.asyncio
    async def test_update_status_not_found(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        await repo.update_status("nonexistent", RunStatus.failed)
        # Should return without error

    @pytest.mark.asyncio
    async def test_record_finding(self):
        session = AsyncMock()
        repo = self._make_repo(session)

        finding = Finding(
            run_id="r1",
            entity_ref="svc:checkout",
            action="create",
            before={"old": True},
            after={"new": True},
            api_calls=[{"method": "POST"}],
            outcome="applied",
        )
        await repo.record_finding(finding)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_sets_outcome(self):
        db_run = MagicMock()
        db_run.job_id = "j1"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_run

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        await repo.update_status("j1", RunStatus.failed, outcome="error", failure_reason="timeout")

        assert db_run.outcome == "error"
        assert db_run.failure_reason == "timeout"

    @pytest.mark.asyncio
    async def test_record_finding_minimal(self):
        session = AsyncMock()
        repo = self._make_repo(session)

        finding = Finding(
            run_id="r1",
            entity_ref="svc:checkout",
            action="create",
        )
        await repo.record_finding(finding)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_idempotency_conflict(self):
        """When rowcount=0, raise IdempotencyConflict."""
        result_mock = MagicMock()
        result_mock.rowcount = 0

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)

        with pytest.raises(IdempotencyConflict):
            await repo.register_idempotency("team1", "duplicate-key")

    @pytest.mark.asyncio
    async def test_register_idempotency_success(self):
        """When rowcount=1, no error should be raised."""
        result_mock = MagicMock()
        result_mock.rowcount = 1

        session = AsyncMock()
        session.execute.return_value = result_mock

        repo = self._make_repo(session)
        await repo.register_idempotency("team1", "unique-key")
