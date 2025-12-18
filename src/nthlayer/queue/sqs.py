from __future__ import annotations

import aioboto3

from nthlayer.config import Settings
from nthlayer.queue.models import JobMessage


class JobEnqueuer:
    """Send reconciliation jobs to SQS."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def enqueue(self, message: JobMessage) -> str:
        session = aioboto3.Session(region_name=self._settings.aws_region)
        async with session.client("sqs") as client:
            queue_url = self._settings.sqs_queue_url or ""
            payload = {
                "QueueUrl": queue_url,
                "MessageBody": message.to_message_body(),
            }
            if queue_url.endswith(".fifo"):
                payload["MessageGroupId"] = message.job_type
                payload["MessageDeduplicationId"] = message.idempotency_key or message.job_id

            response = await client.send_message(**payload)
        return response["MessageId"]
