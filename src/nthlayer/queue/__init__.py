from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from nthlayer.queue.memory import InMemoryJobEnqueuer
from nthlayer.queue.models import JobMessage

if TYPE_CHECKING:
    from nthlayer.queue.sqs import JobEnqueuer


def __getattr__(name: str):
    if name == "JobEnqueuer":
        from nthlayer.queue.sqs import JobEnqueuer

        return JobEnqueuer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class JobQueue(Protocol):
    async def enqueue(self, message: JobMessage) -> str: ...


__all__ = ["JobEnqueuer", "JobMessage", "InMemoryJobEnqueuer", "JobQueue"]
