from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.api.deps import get_job_enqueuer, session_dependency
from nthlayer.config import Settings, get_settings
from nthlayer.db.repositories import IdempotencyConflict, RunRepository
from nthlayer.domain.models import Run, RunStatus, Team
from nthlayer.queue import JobMessage, JobQueue

router = APIRouter()
logger = structlog.get_logger()


class TeamReconcileRequest(BaseModel):
    team_id: str
    desired: Team | None = None
    source: str | None = None


class TeamReconcileResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    type: str
    status: str
    requested_by: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    idempotency_key: str | None = None


@router.post(
    "/teams/reconcile",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TeamReconcileResponse,
)
async def reconcile_team(
    payload: TeamReconcileRequest,
    request: Request,
    session: AsyncSession = Depends(session_dependency),  # noqa: B008
    enqueuer: JobQueue = Depends(get_job_enqueuer),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
    idempotency_key: str | None = Header(
        default=None, convert_underscores=False, alias="Idempotency-Key"
    ),
) -> TeamReconcileResponse:
    job_id = str(uuid4())
    idem_key = idempotency_key or job_id
    requested_by = request.headers.get("X-Principal-Id", "anonymous")

    repo = RunRepository(session)
    try:
        await repo.register_idempotency(payload.team_id, idem_key)
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Idempotency conflict"
        ) from exc

    run = Run(
        job_id=job_id,
        type="team.reconcile",
        requested_by=requested_by,
        status=RunStatus.queued,
        idempotency_key=idem_key,
    )
    await repo.create_run(run)

    message = JobMessage(
        job_id=job_id,
        job_type="team.reconcile",
        payload={
            "team_id": payload.team_id,
            "desired": payload.desired.model_dump() if payload.desired else None,
            "source": payload.source,
            "settings": {"environment": settings.environment},
        },
        idempotency_key=idem_key,
        requested_by=requested_by,
    )
    try:
        await enqueuer.enqueue(message)
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
        await session.rollback()
        logger.exception("job_enqueue_failed", job_id=job_id, team_id=payload.team_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue reconciliation job",
        ) from exc

    await session.commit()

    logger.info("job_enqueued", job_id=job_id, team_id=payload.team_id, requested_by=requested_by)
    return TeamReconcileResponse(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(session_dependency),  # noqa: B008
) -> JobStatusResponse:
    repo = RunRepository(session)
    run = await repo.get_run(job_id)

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return JobStatusResponse(
        job_id=run.job_id,
        type=run.type,
        status=run.status.value,
        requested_by=run.requested_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
        idempotency_key=run.idempotency_key,
    )
