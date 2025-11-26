from __future__ import annotations

import asyncio

from nthlayer.queue.models import JobMessage


class InMemoryJobEnqueuer:
    """Simple asyncio-backed queue for local development."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[JobMessage] = asyncio.Queue()

    async def enqueue(self, message: JobMessage) -> str:
        await self._queue.put(message)
        return message.job_id

    async def dequeue(self) -> JobMessage:
        return await self._queue.get()

    def size(self) -> int:
        return self._queue.qsize()
