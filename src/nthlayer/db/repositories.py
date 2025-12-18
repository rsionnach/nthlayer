from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.db import models as db_models
from nthlayer.domain.models import Finding, Run, RunStatus


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotent operation has already been processed."""


@dataclass(slots=True)
class RunRepository:
    """Persistence helpers for job lifecycle."""

    session: AsyncSession

    async def register_idempotency(self, team_id: str, key: str) -> None:
        stmt = insert(db_models.IdempotencyKey).values(team_id=team_id, idem_key=key)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_team_idem")
        result = await self.session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise IdempotencyConflict(key)

    async def create_run(self, run: Run) -> None:
        db_run = db_models.Run(
            job_id=run.job_id,
            type=run.type,
            requested_by=run.requested_by,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            idempotency_key=run.idempotency_key,
        )
        self.session.add(db_run)

    async def get_run(self, job_id: str) -> Run | None:
        stmt = select(db_models.Run).where(db_models.Run.job_id == job_id)
        result = await self.session.execute(stmt)
        db_run = result.scalar_one_or_none()
        if not db_run:
            return None
        return Run(
            job_id=db_run.job_id,
            type=db_run.type,
            requested_by=db_run.requested_by,
            status=RunStatus(db_run.status),
            started_at=db_run.started_at,
            finished_at=db_run.finished_at,
            idempotency_key=db_run.idempotency_key,
        )

    async def update_status(
        self,
        job_id: str,
        status: RunStatus,
        *,
        started_at: float | None = None,
        finished_at: float | None = None,
        outcome: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        stmt = select(db_models.Run).where(db_models.Run.job_id == job_id)
        result = await self.session.execute(stmt)
        db_run = result.scalar_one_or_none()
        if not db_run:
            return

        db_run.status = status.value
        if started_at is not None:
            db_run.started_at = started_at
        if finished_at is not None:
            db_run.finished_at = finished_at
        if outcome is not None:
            db_run.outcome = outcome
        if failure_reason is not None:
            db_run.failure_reason = failure_reason

    async def record_finding(self, finding: Finding) -> None:
        db_finding = db_models.Finding(
            run_id=finding.run_id,
            entity_ref=finding.entity_ref,
            before_state=dict(finding.before) if finding.before else None,
            after_state=dict(finding.after) if finding.after else None,
            action=finding.action,
            api_calls=[dict(call) for call in finding.api_calls],
            outcome=finding.outcome,
        )
        self.session.add(db_finding)
