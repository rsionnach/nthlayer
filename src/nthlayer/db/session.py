from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nthlayer.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> None:
    """Initialise SQLAlchemy engine lazily with connection pooling."""

    global _engine, _session_factory

    cfg = settings or get_settings()
    if _engine is not None:
        return

    _engine = create_async_engine(
        cfg.database_url,
        echo=cfg.debug,
        future=True,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        pool_timeout=cfg.db_pool_timeout,
        pool_recycle=cfg.db_pool_recycle,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for FastAPI dependency."""

    global _session_factory
    if _session_factory is None:
        init_engine()
        assert _session_factory is not None  # defensive

    async with _session_factory() as session:
        yield session
