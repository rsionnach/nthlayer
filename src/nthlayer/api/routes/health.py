from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.api.deps import session_dependency
from nthlayer.cache import RedisCache
from nthlayer.config import Settings, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    status: str
    database: str
    redis: str


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """Basic health check endpoint."""
    return HealthResponse(status="healthy")


@router.get("/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def readiness_check(
    session: AsyncSession = Depends(session_dependency),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> ReadinessResponse:
    """Readiness check with database and Redis connectivity."""
    db_status = "unknown"
    redis_status = "unknown"

    try:
        result = await session.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_status = "connected"
    except (ConnectionError, TimeoutError, OSError) as e:  # noqa: F841
        db_status = "disconnected"

    try:
        cache = RedisCache(settings.redis_url, settings.redis_max_connections)
        await cache.set("health_check", "ok", ttl=10)
        value = await cache.get("health_check")
        if value == "ok":
            redis_status = "connected"
        await cache.close()
    except (ConnectionError, TimeoutError, OSError) as e:  # noqa: F841
        redis_status = "disconnected"

    overall_status = (
        "ready" if db_status == "connected" and redis_status == "connected" else "not_ready"
    )

    return ReadinessResponse(
        status=overall_status,
        database=db_status,
        redis=redis_status,
    )
