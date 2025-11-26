from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.config import Settings, get_settings
from nthlayer.db.session import get_session
from nthlayer.queue import InMemoryJobEnqueuer, JobEnqueuer, JobQueue


async def session_dependency() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


_memory_enqueuer: InMemoryJobEnqueuer | None = None


def get_job_enqueuer(settings: Settings = Depends(get_settings)) -> JobQueue:
    global _memory_enqueuer

    if settings.job_queue_backend == "memory":
        if _memory_enqueuer is None:
            _memory_enqueuer = InMemoryJobEnqueuer()
        return _memory_enqueuer

    if settings.job_queue_backend == "sqs":
        return JobEnqueuer(settings)

    raise ValueError(f"Unsupported job queue backend: {settings.job_queue_backend}")
