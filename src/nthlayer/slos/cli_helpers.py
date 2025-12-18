"""
CLI helper functions for ResLayer commands.

Provides database session management and common operations for CLI.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.config import get_settings
from nthlayer.db.models import SLOModel
from nthlayer.db.session import get_session, init_engine
from nthlayer.slos.models import SLO
from nthlayer.slos.storage import SLORepository


@asynccontextmanager
async def get_cli_session() -> AsyncIterator[AsyncSession]:
    """
    Get database session for CLI commands.
    
    Initializes engine if needed and provides session context.
    """
    settings = get_settings()
    init_engine(settings)
    
    async for session in get_session():
        yield session
        break


async def save_slo_to_db(slo: SLO) -> str:
    """
    Save SLO to database.
    
    Args:
        slo: SLO object to save
        
    Returns:
        Action taken ("created" or "updated")
        
    Raises:
        Exception: If database operation fails
    """
    async with get_cli_session() as session:
        repo = SLORepository(session)
        
        # Check if SLO already exists
        existing = await repo.get_slo(slo.id)
        
        if existing:
            # Update existing
            await repo.update_slo(slo)
            await session.commit()
            action = "updated"
        else:
            # Create new
            await repo.create_slo(slo)
            await session.commit()
            action = "created"
    
    return action


async def get_slo_from_db(slo_id: str) -> SLO | None:
    """
    Retrieve SLO from database.
    
    Args:
        slo_id: SLO ID to retrieve
        
    Returns:
        SLO object or None if not found
    """
    async with get_cli_session() as session:
        repo = SLORepository(session)
        slo = await repo.get_slo(slo_id)
    
    return slo


async def get_slos_by_service_from_db(service: str) -> list[SLO]:
    """
    Get all SLOs for a service from database.
    
    Args:
        service: Service name
        
    Returns:
        List of SLO objects
    """
    async with get_cli_session() as session:
        repo = SLORepository(session)
        slos = await repo.get_slos_by_service(service)
    
    return slos


async def list_all_slos_from_db() -> list[SLO]:
    """
    List all SLOs from database.
    
    Returns:
        List of all SLO objects
    """
    async with get_cli_session() as session:
        repo = SLORepository(session)
        # Get all SLOs directly
        result = await session.execute(
            select(SLOModel).order_by(SLOModel.service, SLOModel.id)
        )
        models = result.scalars().all()
        
        # Convert to SLO objects
        all_slos = [repo._model_to_slo(model) for model in models]
    
    return all_slos


async def get_current_budget_from_db(slo_id: str) -> dict[str, Any] | None:
    """
    Get current error budget for an SLO.
    
    Args:
        slo_id: SLO ID
        
    Returns:
        Error budget dictionary or None if not found
    """
    async with get_cli_session() as session:
        repo = SLORepository(session)
        budget = await repo.get_current_error_budget(slo_id)
        
        if budget:
            return budget.to_dict()
    
    return None


def run_async(coro):
    """
    Helper to run async functions from sync CLI commands.
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result of coroutine
    """
    return asyncio.run(coro)
