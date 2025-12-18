from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nthlayer.api.routes import health, teams
from nthlayer.config import get_settings
from nthlayer.db.session import init_engine
from nthlayer.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    init_engine(settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NthLayer API",
        version="0.1.0",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.cors_origins],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    app.include_router(teams.router, prefix=settings.api_prefix, tags=["teams"])
    app.include_router(health.router, tags=["health"])
    return app


app = create_app()

try:
    from mangum import Mangum

    handler: Mangum | None = Mangum(app)
except ImportError:  # pragma: no cover
    handler = None
