from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    """Enumeration of job states."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class TeamSource(BaseModel):
    cortex_id: str | None = None
    pagerduty_id: str | None = None


class Team(BaseModel):
    id: str
    name: str
    managers: Sequence[str] = Field(default_factory=list)
    sources: TeamSource = Field(default_factory=TeamSource)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class Service(BaseModel):
    id: str
    name: str
    owner_team_id: str
    tier: str | None = None
    dependencies: Sequence[str] = Field(default_factory=list)


class Run(BaseModel):
    job_id: str
    type: str
    requested_by: str | None = None
    status: RunStatus = RunStatus.queued
    started_at: float | None = None
    finished_at: float | None = None
    idempotency_key: str | None = None


class Finding(BaseModel):
    run_id: str
    entity_ref: str
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    action: str
    api_calls: Iterable[Mapping[str, Any]] = Field(default_factory=list)
    outcome: str | None = None
