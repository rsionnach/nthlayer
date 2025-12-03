import pytest
from nthlayer.queue.memory import InMemoryJobEnqueuer
from nthlayer.queue.models import JobMessage


@pytest.mark.asyncio
async def test_in_memory_enqueuer_buffers_messages():
    queue = InMemoryJobEnqueuer()
    message = JobMessage(job_id="job-1", job_type="team.reconcile", payload={"team_id": "t1"})

    returned_id = await queue.enqueue(message)

    assert returned_id == "job-1"
    assert queue.size() == 1

    dequeued = await queue.dequeue()
    assert dequeued == message
    assert queue.size() == 0
