import pytest
from nthlayer.db.models import Base
from nthlayer.db.repositories import IdempotencyConflict, RunRepository
from nthlayer.domain.models import Finding, Run, RunStatus
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_run(session):
    repo = RunRepository(session)
    run = Run(
        job_id="job-123",
        type="team.reconcile",
        status=RunStatus.queued,
        requested_by="user-1",
    )

    await repo.create_run(run)
    await session.commit()

    retrieved = await repo.get_run("job-123")
    assert retrieved is not None
    assert retrieved.job_id == "job-123"
    assert retrieved.type == "team.reconcile"
    assert retrieved.status == RunStatus.queued


@pytest.mark.asyncio
async def test_update_status(session):
    repo = RunRepository(session)
    run = Run(job_id="job-123", type="team.reconcile", status=RunStatus.queued)

    await repo.create_run(run)
    await session.commit()

    await repo.update_status(
        "job-123",
        RunStatus.succeeded,
        started_at=1234.5,
        finished_at=1235.5,
        outcome="applied",
    )
    await session.commit()

    retrieved = await repo.get_run("job-123")
    assert retrieved.status == RunStatus.succeeded
    assert retrieved.started_at == 1234.5
    assert retrieved.finished_at == 1235.5


@pytest.mark.asyncio
async def test_register_idempotency(session):
    repo = RunRepository(session)

    await repo.register_idempotency("team-123", "idem-key-1")
    await session.commit()

    with pytest.raises(IdempotencyConflict):
        await repo.register_idempotency("team-123", "idem-key-1")


@pytest.mark.asyncio
async def test_record_finding(session):
    repo = RunRepository(session)
    finding = Finding(
        run_id="job-123",
        entity_ref="pagerduty:team:team-123",
        before={"members": []},
        after={"members": ["user-1"]},
        action="sync_team_members",
        api_calls=[{"name": "set_members", "count": 1}],
        outcome="applied",
    )

    await repo.record_finding(finding)
    await session.commit()
