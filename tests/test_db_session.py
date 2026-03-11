"""Tests for nthlayer.db.session — engine init and session factory."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import nthlayer.db.session as session_module


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """Reset module-level globals before and after each test."""
    session_module._engine = None
    session_module._session_factory = None
    yield
    session_module._engine = None
    session_module._session_factory = None


def _make_fake_settings(**overrides):
    """Build a mock Settings with sensible defaults."""
    defaults = {
        "database_url": "postgresql+psycopg://localhost/testdb",
        "debug": False,
        "db_pool_size": 5,
        "db_max_overflow": 10,
        "db_pool_timeout": 30,
        "db_pool_recycle": 1800,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


# ---------- init_engine ----------


class TestInitEngine:
    """Tests for init_engine()."""

    @patch.object(session_module, "async_sessionmaker")
    @patch.object(session_module, "create_async_engine")
    def test_creates_engine_with_correct_params(self, mock_create_engine, mock_sessionmaker):
        """init_engine passes all settings fields to create_async_engine."""
        settings = _make_fake_settings(
            database_url="postgresql+psycopg://db:5432/app",
            debug=True,
            db_pool_size=8,
            db_max_overflow=15,
            db_pool_timeout=60,
            db_pool_recycle=900,
        )

        session_module.init_engine(settings)

        mock_create_engine.assert_called_once_with(
            "postgresql+psycopg://db:5432/app",
            echo=True,
            future=True,
            pool_size=8,
            max_overflow=15,
            pool_timeout=60,
            pool_recycle=900,
            pool_pre_ping=True,
        )
        mock_sessionmaker.assert_called_once_with(
            mock_create_engine.return_value, expire_on_commit=False
        )

    @patch.object(session_module, "async_sessionmaker")
    @patch.object(session_module, "create_async_engine")
    def test_idempotent_second_call_noop(self, mock_create_engine, mock_sessionmaker):
        """Calling init_engine twice does not create a second engine."""
        settings = _make_fake_settings()

        session_module.init_engine(settings)
        session_module.init_engine(settings)

        assert mock_create_engine.call_count == 1
        assert mock_sessionmaker.call_count == 1

    @patch.object(session_module, "async_sessionmaker")
    @patch.object(session_module, "create_async_engine")
    @patch.object(session_module, "get_settings")
    def test_uses_get_settings_when_none_passed(
        self, mock_get_settings, mock_create_engine, mock_sessionmaker
    ):
        """init_engine falls back to get_settings() when no settings arg."""
        fake = _make_fake_settings()
        mock_get_settings.return_value = fake

        session_module.init_engine()

        mock_get_settings.assert_called_once()
        mock_create_engine.assert_called_once_with(
            fake.database_url,
            echo=fake.debug,
            future=True,
            pool_size=fake.db_pool_size,
            max_overflow=fake.db_max_overflow,
            pool_timeout=fake.db_pool_timeout,
            pool_recycle=fake.db_pool_recycle,
            pool_pre_ping=True,
        )


# ---------- get_session ----------


class TestGetSession:
    """Tests for get_session() async generator."""

    @pytest.mark.asyncio
    @patch.object(session_module, "async_sessionmaker")
    @patch.object(session_module, "create_async_engine")
    async def test_yields_session(self, mock_create_engine, mock_sessionmaker):
        """get_session yields an AsyncSession from the factory."""
        settings = _make_fake_settings()
        mock_session = AsyncMock()

        # async context manager returned by the factory call
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sessionmaker.return_value.return_value = mock_ctx

        session_module.init_engine(settings)

        yielded = []
        async for s in session_module.get_session():
            yielded.append(s)

        assert len(yielded) == 1
        assert yielded[0] is mock_session

    @pytest.mark.asyncio
    @patch.object(session_module, "async_sessionmaker")
    @patch.object(session_module, "create_async_engine")
    @patch.object(session_module, "get_settings")
    async def test_calls_init_engine_when_factory_is_none(
        self, mock_get_settings, mock_create_engine, mock_sessionmaker
    ):
        """get_session auto-initialises the engine when factory is None."""
        fake = _make_fake_settings()
        mock_get_settings.return_value = fake

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sessionmaker.return_value.return_value = mock_ctx

        # factory starts as None, get_session should call init_engine
        assert session_module._session_factory is None

        yielded = []
        async for s in session_module.get_session():
            yielded.append(s)

        # Engine was created via get_settings fallback
        mock_get_settings.assert_called_once()
        mock_create_engine.assert_called_once()
        assert len(yielded) == 1
