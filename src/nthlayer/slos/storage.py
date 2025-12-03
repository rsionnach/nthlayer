"""
SLO storage and repository.

Handles database operations for SLOs and error budgets.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Import Deployment dataclass (avoid circular import)
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.db.models import (
    DeploymentModel,
    ErrorBudgetModel,
    IncidentModel,
    SLOHistoryModel,
    SLOModel,
)
from nthlayer.slos.models import SLO, ErrorBudget, TimeWindowType

if TYPE_CHECKING:
    from nthlayer.slos.deployment import Deployment


class SLORepository:
    """Repository for SLO database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_slo(self, slo: SLO) -> None:
        """Create a new SLO in the database."""
        model = SLOModel(
            id=slo.id,
            service=slo.service,
            name=slo.name,
            description=slo.description,
            target=slo.target,
            time_window_duration=slo.time_window.duration,
            time_window_type=slo.time_window.type.value,
            query=slo.query,
            owner=slo.owner,
            labels=slo.labels,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_slo(self, slo_id: str) -> SLO | None:
        """Get an SLO by ID."""
        result = await self.session.execute(
            select(SLOModel).where(SLOModel.id == slo_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return None
        
        return self._model_to_slo(model)

    async def get_slos_by_service(self, service: str) -> list[SLO]:
        """Get all SLOs for a service."""
        result = await self.session.execute(
            select(SLOModel).where(SLOModel.service == service)
        )
        models = result.scalars().all()
        
        return [self._model_to_slo(model) for model in models]

    async def update_slo(self, slo: SLO) -> None:
        """Update an existing SLO."""
        result = await self.session.execute(
            select(SLOModel).where(SLOModel.id == slo.id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            raise ValueError(f"SLO not found: {slo.id}")
        
        model.service = slo.service
        model.name = slo.name
        model.description = slo.description
        model.target = slo.target
        model.time_window_duration = slo.time_window.duration
        model.time_window_type = slo.time_window.type.value
        model.query = slo.query
        model.owner = slo.owner
        model.labels = slo.labels
        model.updated_at = datetime.utcnow()
        
        await self.session.flush()

    async def delete_slo(self, slo_id: str) -> None:
        """Delete an SLO and all related data."""
        result = await self.session.execute(
            select(SLOModel).where(SLOModel.id == slo_id)
        )
        model = result.scalar_one_or_none()
        
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()

    async def create_or_update_error_budget(self, budget: ErrorBudget) -> None:
        """Create or update an error budget record."""
        # Check if budget exists for this period
        result = await self.session.execute(
            select(ErrorBudgetModel).where(
                ErrorBudgetModel.slo_id == budget.slo_id,
                ErrorBudgetModel.period_start == budget.period_start,
                ErrorBudgetModel.period_end == budget.period_end,
            )
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            # Create new
            model = ErrorBudgetModel(
                slo_id=budget.slo_id,
                service=budget.service,
                period_start=budget.period_start,
                period_end=budget.period_end,
                total_budget_minutes=budget.total_budget_minutes,
                burned_minutes=budget.burned_minutes,
                remaining_minutes=budget.remaining_minutes,
                incident_burn_minutes=budget.incident_burn_minutes,
                deployment_burn_minutes=budget.deployment_burn_minutes,
                slo_breach_burn_minutes=budget.slo_breach_burn_minutes,
                status=budget.status.value,
                burn_rate=budget.burn_rate,
            )
            self.session.add(model)
        else:
            # Update existing
            model.burned_minutes = budget.burned_minutes
            model.remaining_minutes = budget.remaining_minutes
            model.incident_burn_minutes = budget.incident_burn_minutes
            model.deployment_burn_minutes = budget.deployment_burn_minutes
            model.slo_breach_burn_minutes = budget.slo_breach_burn_minutes
            model.status = budget.status.value
            model.burn_rate = budget.burn_rate
            model.updated_at = datetime.utcnow()
        
        await self.session.flush()

    async def get_current_error_budget(self, slo_id: str) -> ErrorBudget | None:
        """Get the current error budget for an SLO."""
        # Get the most recent budget record
        result = await self.session.execute(
            select(ErrorBudgetModel)
            .where(ErrorBudgetModel.slo_id == slo_id)
            .order_by(ErrorBudgetModel.period_start.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return None
        
        return self._model_to_error_budget(model)

    async def record_slo_measurement(
        self,
        slo_id: str,
        service: str,
        timestamp: datetime,
        sli_value: float,
        target_value: float,
        compliant: bool,
        budget_burn_minutes: float,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """Record an SLO measurement in history."""
        model = SLOHistoryModel(
            slo_id=slo_id,
            service=service,
            timestamp=timestamp,
            sli_value=sli_value,
            target_value=target_value,
            compliant=compliant,
            budget_burn_minutes=budget_burn_minutes,
            extra_data=extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_slo_history(
        self,
        slo_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Get SLO measurement history for a time range."""
        result = await self.session.execute(
            select(SLOHistoryModel)
            .where(
                SLOHistoryModel.slo_id == slo_id,
                SLOHistoryModel.timestamp >= start_time,
                SLOHistoryModel.timestamp <= end_time,
            )
            .order_by(SLOHistoryModel.timestamp)
        )
        models = result.scalars().all()
        
        return [
            {
                "timestamp": model.timestamp.isoformat(),
                "sli_value": model.sli_value,
                "target_value": model.target_value,
                "compliant": model.compliant,
                "budget_burn_minutes": model.budget_burn_minutes,
                "extra_data": model.extra_data,
            }
            for model in models
        ]

    async def record_deployment(
        self,
        deployment_id: str,
        service: str,
        deployed_at: datetime,
        commit_sha: str | None = None,
        author: str | None = None,
        pr_number: str | None = None,
        source: str = "argocd",
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """Record a deployment event."""
        model = DeploymentModel(
            id=deployment_id,
            service=service,
            deployed_at=deployed_at,
            commit_sha=commit_sha,
            author=author,
            pr_number=pr_number,
            source=source,
            extra_data=extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    async def record_incident(
        self,
        incident_id: str,
        service: str,
        started_at: datetime,
        title: str | None = None,
        severity: str | None = None,
        resolved_at: datetime | None = None,
        duration_minutes: float | None = None,
        budget_burn_minutes: float | None = None,
        source: str = "pagerduty",
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """Record an incident."""
        model = IncidentModel(
            id=incident_id,
            service=service,
            title=title,
            severity=severity,
            started_at=started_at,
            resolved_at=resolved_at,
            duration_minutes=duration_minutes,
            budget_burn_minutes=budget_burn_minutes,
            source=source,
            extra_data=extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    def _model_to_slo(self, model: SLOModel) -> SLO:
        """Convert SQLAlchemy model to SLO object."""
        from nthlayer.slos.models import TimeWindow
        
        time_window = TimeWindow(
            duration=model.time_window_duration,
            type=TimeWindowType(model.time_window_type),
        )
        
        return SLO(
            id=model.id,
            service=model.service,
            name=model.name,
            description=model.description or "",
            target=model.target,
            time_window=time_window,
            query=model.query,
            owner=model.owner,
            labels=model.labels or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _model_to_error_budget(self, model: ErrorBudgetModel) -> ErrorBudget:
        """Convert SQLAlchemy model to ErrorBudget object."""
        from nthlayer.slos.models import SLOStatus
        
        return ErrorBudget(
            slo_id=model.slo_id,
            service=model.service,
            period_start=model.period_start,
            period_end=model.period_end,
            total_budget_minutes=model.total_budget_minutes,
            burned_minutes=model.burned_minutes,
            remaining_minutes=model.remaining_minutes,
            incident_burn_minutes=model.incident_burn_minutes,
            deployment_burn_minutes=model.deployment_burn_minutes,
            slo_breach_burn_minutes=model.slo_breach_burn_minutes,
            status=SLOStatus(model.status),
            burn_rate=model.burn_rate,
            updated_at=model.updated_at,
        )
    
    # Deployment methods
    
    async def create_deployment(self, deployment: "Deployment") -> None:
        """Create a deployment record."""
        model = DeploymentModel(
            id=deployment.id,
            service=deployment.service,
            environment=deployment.environment,
            deployed_at=deployment.deployed_at,
            commit_sha=deployment.commit_sha,
            author=deployment.author,
            pr_number=deployment.pr_number,
            source=deployment.source,
            extra_data=deployment.extra_data,
            correlated_burn_minutes=deployment.correlated_burn_minutes,
            correlation_confidence=deployment.correlation_confidence,
        )
        self.session.add(model)
        await self.session.flush()
    
    async def get_deployment(self, deployment_id: str) -> "Deployment | None":
        """Get a deployment by ID."""
        from nthlayer.slos.deployment import Deployment
        
        result = await self.session.execute(
            select(DeploymentModel).where(DeploymentModel.id == deployment_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return None
        
        return Deployment(
            id=model.id,
            service=model.service,
            environment=model.environment,
            deployed_at=model.deployed_at,
            commit_sha=model.commit_sha,
            author=model.author,
            pr_number=model.pr_number,
            source=model.source,
            extra_data=model.extra_data or {},
            correlated_burn_minutes=model.correlated_burn_minutes,
            correlation_confidence=model.correlation_confidence,
        )
    
    async def get_recent_deployments(
        self,
        service: str,
        hours: int = 24,
        environment: str = "production",
    ) -> list["Deployment"]:
        """Get recent deployments for a service."""
        from nthlayer.slos.deployment import Deployment
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        result = await self.session.execute(
            select(DeploymentModel)
            .where(
                DeploymentModel.service == service,
                DeploymentModel.environment == environment,
                DeploymentModel.deployed_at >= cutoff_time,
            )
            .order_by(DeploymentModel.deployed_at.desc())
        )
        models = result.scalars().all()
        
        return [
            Deployment(
                id=model.id,
                service=model.service,
                environment=model.environment,
                deployed_at=model.deployed_at,
                commit_sha=model.commit_sha,
                author=model.author,
                pr_number=model.pr_number,
                source=model.source,
                extra_data=model.extra_data or {},
                correlated_burn_minutes=model.correlated_burn_minutes,
                correlation_confidence=model.correlation_confidence,
            )
            for model in models
        ]
    
    async def update_deployment_correlation(
        self,
        deployment_id: str,
        burn_minutes: float,
        confidence: float,
    ) -> None:
        """Update deployment with correlation data."""
        result = await self.session.execute(
            select(DeploymentModel).where(DeploymentModel.id == deployment_id)
        )
        model = result.scalar_one_or_none()
        
        if model is not None:
            model.correlated_burn_minutes = burn_minutes
            model.correlation_confidence = confidence
            await self.session.flush()
    
    async def get_burn_rate_window(
        self,
        slo_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """
        Calculate burn rate (minutes per minute) in a time window.
        
        Args:
            slo_id: SLO identifier
            start_time: Window start
            end_time: Window end
            
        Returns:
            Burn rate in minutes per minute
        """
        # Query error budgets in window
        result = await self.session.execute(
            select(ErrorBudgetModel)
            .where(
                ErrorBudgetModel.slo_id == slo_id,
                ErrorBudgetModel.updated_at >= start_time,
                ErrorBudgetModel.updated_at <= end_time,
            )
        )
        budgets = result.scalars().all()
        
        if not budgets:
            return 0.0
        
        # Get most recent budget (has cumulative burn)
        latest_budget = max(budgets, key=lambda b: b.updated_at)
        
        # Get oldest budget in window
        oldest_budget = min(budgets, key=lambda b: b.updated_at)
        
        # Calculate burn in window
        burn_in_window = latest_budget.burned_minutes - oldest_budget.burned_minutes
        
        # Calculate window duration in minutes
        window_duration = (end_time - start_time).total_seconds() / 60
        
        if window_duration == 0:
            return 0.0
        
        # Return burn rate (minutes per minute)
        return burn_in_window / window_duration
