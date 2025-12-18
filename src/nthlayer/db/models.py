from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from nthlayer.domain.models import RunStatus


class Base(DeclarativeBase):
    pass


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(255), nullable=False)
    idem_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "idem_key", name="uq_team_idem"),
        Index("idx_idem_key", "idem_key"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        Enum(RunStatus, name="run_status", native_enum=False), nullable=False, index=True
    )
    started_at: Mapped[float | None] = mapped_column()
    finished_at: Mapped[float | None] = mapped_column()
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    outcome: Mapped[str | None] = mapped_column(String(100))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_runs_status_created", "status", "created_at"),)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    api_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_findings_run_entity", "run_id", "entity_ref"),)


# SLO and Error Budget Models


class SLOModel(Base):
    """SLO (Service Level Objective) definition."""

    __tablename__ = "slos"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    time_window_duration: Mapped[str] = mapped_column(String(50), nullable=False)
    time_window_type: Mapped[str] = mapped_column(String(50), nullable=False, default="rolling")
    query: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255))
    labels: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (Index("idx_slos_service", "service"),)


class ErrorBudgetModel(Base):
    """Error budget tracking for an SLO."""

    __tablename__ = "error_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slo_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("slos.id", ondelete="CASCADE"), nullable=False
    )
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_budget_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    burned_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    remaining_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    incident_burn_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deployment_burn_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    slo_breach_burn_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="healthy")
    burn_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_error_budgets_service_period", "service", "period_start", "period_end"),
        Index("idx_error_budgets_slo_period", "slo_id", "period_start"),
    )


class SLOHistoryModel(Base):
    """Historical SLI measurements and budget burns."""

    __tablename__ = "slo_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slo_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("slos.id", ondelete="CASCADE"), nullable=False
    )
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    sli_value: Mapped[float] = mapped_column(Float, nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    compliant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    budget_burn_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_slo_history_slo_timestamp", "slo_id", "timestamp"),
        Index("idx_slo_history_service_timestamp", "service", "timestamp"),
    )


class DeploymentModel(Base):
    """Deployment events for correlation with error budget burns."""

    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    deployed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    pr_number: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlated_burn_minutes: Mapped[float | None] = mapped_column(Float)
    correlation_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_deployments_service_deployed", "service", "deployed_at"),)


class IncidentModel(Base):
    """Incidents from PagerDuty or other sources."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_minutes: Mapped[float | None] = mapped_column(Float)
    budget_burn_minutes: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="pagerduty")
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (Index("idx_incidents_service_started", "service", "started_at"),)
