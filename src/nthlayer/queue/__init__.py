from __future__ import annotations

from typing import Protocol

from nthlayer.queue.memory import InMemoryJobEnqueuer
from nthlayer.queue.models import JobMessage
from nthlayer.queue.sqs import JobEnqueuer


class JobQueue(Protocol):
    async def enqueue(self, message: JobMessage) -> str: ...


__all__ = ["JobEnqueuer", "JobMessage", "InMemoryJobEnqueuer", "JobQueue"]
