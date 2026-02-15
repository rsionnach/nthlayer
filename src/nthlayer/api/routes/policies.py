"""Policy audit and override API routes."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.api.deps import session_dependency
from nthlayer.policies.recorder import PolicyAuditRecorder
from nthlayer.policies.repository import PolicyAuditRepository

router = APIRouter()
logger = structlog.get_logger()


# -- Request / Response Models --


class OverrideRequest(BaseModel):
    approved_by: str
    reason: str
    override_type: str = "manual_approval"
    deployment_id: str | None = None
    expires_at: datetime | None = None


class OverrideResponse(BaseModel):
    override_id: str
    service: str
    policy_name: str
    approved_by: str
    override_type: str


class EvaluationItem(BaseModel):
    id: str
    timestamp: datetime
    action: str
    result: str
    actor: str | None


class ViolationItem(BaseModel):
    id: str
    timestamp: datetime
    violation_type: str
    reason: str
    budget_remaining_pct: float


class OverrideItem(BaseModel):
    id: str
    timestamp: datetime
    approved_by: str
    reason: str
    override_type: str
    expires_at: datetime | None


class AuditListResponse(BaseModel):
    service: str
    evaluations: list[EvaluationItem]
    violations: list[ViolationItem]
    overrides: list[OverrideItem]


# -- Endpoints --


@router.post(
    "/policies/{service}/override",
    status_code=status.HTTP_201_CREATED,
    response_model=OverrideResponse,
)
async def create_override(
    service: str,
    body: OverrideRequest,
    session: AsyncSession = Depends(session_dependency),  # noqa: B008
) -> OverrideResponse:
    """Create a policy override for a service."""
    repository = PolicyAuditRepository(session)
    recorder = PolicyAuditRecorder(repository)

    override = await recorder.record_override(
        service=service,
        policy_name="deployment-gate",
        approved_by=body.approved_by,
        reason=body.reason,
        override_type=body.override_type,
        deployment_id=body.deployment_id,
        expires_at=body.expires_at,
    )

    if override is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record override",
        )

    await session.commit()

    logger.info(
        "policy_override_created",
        service=service,
        override_id=override.id,
        approved_by=body.approved_by,
    )

    return OverrideResponse(
        override_id=override.id,
        service=service,
        policy_name="deployment-gate",
        approved_by=override.approved_by,
        override_type=override.override_type,
    )


@router.get(
    "/policies/{service}/audit",
    response_model=AuditListResponse,
)
async def get_audit_trail(
    service: str,
    hours: int = Query(default=24, ge=1, le=720),
    session: AsyncSession = Depends(session_dependency),  # noqa: B008
) -> AuditListResponse:
    """Get the policy audit trail for a service."""
    repository = PolicyAuditRepository(session)

    evaluations = await repository.get_evaluations(service, hours=hours)
    violations = await repository.get_violations(service, hours=hours)
    overrides = await repository.get_overrides(service, hours=hours)

    return AuditListResponse(
        service=service,
        evaluations=[
            EvaluationItem(
                id=e.id,
                timestamp=e.timestamp,
                action=e.action,
                result=e.result,
                actor=e.actor,
            )
            for e in evaluations
        ],
        violations=[
            ViolationItem(
                id=v.id,
                timestamp=v.timestamp,
                violation_type=v.violation_type,
                reason=v.reason,
                budget_remaining_pct=v.budget_remaining_pct,
            )
            for v in violations
        ],
        overrides=[
            OverrideItem(
                id=o.id,
                timestamp=o.timestamp,
                approved_by=o.approved_by,
                reason=o.reason,
                override_type=o.override_type,
                expires_at=o.expires_at,
            )
            for o in overrides
        ],
    )
