"""
Policy audit repository.

Handles database operations for policy evaluations, violations, and overrides.
All audit tables are insert-only (no update/delete).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nthlayer.db.models import (
    PolicyEvaluationModel,
    PolicyOverrideModel,
    PolicyViolationModel,
)
from nthlayer.policies.audit import PolicyEvaluation, PolicyOverride, PolicyViolation


class PolicyAuditRepository:
    """Repository for policy audit database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_evaluation(self, evaluation: PolicyEvaluation) -> None:
        """Insert a policy evaluation record."""
        model = PolicyEvaluationModel(
            id=evaluation.id,
            timestamp=evaluation.timestamp,
            service=evaluation.service,
            policy_name=evaluation.policy_name,
            actor=evaluation.actor,
            action=evaluation.action,
            result=evaluation.result,
            context_snapshot=evaluation.context_snapshot,
            matched_condition=evaluation.matched_condition,
            gate_check=evaluation.gate_check,
            extra_data=evaluation.extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    async def record_violation(self, violation: PolicyViolation) -> None:
        """Insert a policy violation record."""
        model = PolicyViolationModel(
            id=violation.id,
            timestamp=violation.timestamp,
            service=violation.service,
            policy_name=violation.policy_name,
            deployment_id=violation.deployment_id,
            violation_type=violation.violation_type,
            reason=violation.reason,
            budget_remaining_pct=violation.budget_remaining_pct,
            threshold_pct=violation.threshold_pct,
            downstream_services=violation.downstream_services,
            extra_data=violation.extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    async def record_override(self, override: PolicyOverride) -> None:
        """Insert a policy override record."""
        model = PolicyOverrideModel(
            id=override.id,
            timestamp=override.timestamp,
            service=override.service,
            policy_name=override.policy_name,
            deployment_id=override.deployment_id,
            approved_by=override.approved_by,
            reason=override.reason,
            override_type=override.override_type,
            expires_at=override.expires_at,
            extra_data=override.extra_data,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_evaluations(self, service: str, hours: int = 24) -> list[PolicyEvaluation]:
        """Get recent policy evaluations for a service."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(PolicyEvaluationModel)
            .where(
                PolicyEvaluationModel.service == service,
                PolicyEvaluationModel.timestamp >= cutoff,
            )
            .order_by(PolicyEvaluationModel.timestamp.desc())
        )
        return [self._eval_to_domain(m) for m in result.scalars().all()]

    async def get_violations(self, service: str, hours: int = 24) -> list[PolicyViolation]:
        """Get recent policy violations for a service."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(PolicyViolationModel)
            .where(
                PolicyViolationModel.service == service,
                PolicyViolationModel.timestamp >= cutoff,
            )
            .order_by(PolicyViolationModel.timestamp.desc())
        )
        return [self._violation_to_domain(m) for m in result.scalars().all()]

    async def get_overrides(self, service: str, hours: int = 24) -> list[PolicyOverride]:
        """Get recent policy overrides for a service."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(PolicyOverrideModel)
            .where(
                PolicyOverrideModel.service == service,
                PolicyOverrideModel.timestamp >= cutoff,
            )
            .order_by(PolicyOverrideModel.timestamp.desc())
        )
        return [self._override_to_domain(m) for m in result.scalars().all()]

    async def get_active_override(self, service: str, policy_name: str) -> PolicyOverride | None:
        """Get active (non-expired) override for a service/policy."""
        now = datetime.utcnow()
        result = await self.session.execute(
            select(PolicyOverrideModel)
            .where(
                PolicyOverrideModel.service == service,
                PolicyOverrideModel.policy_name == policy_name,
            )
            .order_by(PolicyOverrideModel.timestamp.desc())
        )
        for model in result.scalars().all():
            if model.expires_at is None or model.expires_at > now:
                return self._override_to_domain(model)
        return None

    # -- Model-to-domain converters --

    @staticmethod
    def _eval_to_domain(model: PolicyEvaluationModel) -> PolicyEvaluation:
        return PolicyEvaluation(
            id=model.id,
            timestamp=model.timestamp,
            service=model.service,
            policy_name=model.policy_name,
            actor=model.actor,
            action=model.action,
            result=model.result,
            context_snapshot=model.context_snapshot or {},
            matched_condition=model.matched_condition,
            gate_check=model.gate_check,
            extra_data=model.extra_data or {},
        )

    @staticmethod
    def _violation_to_domain(model: PolicyViolationModel) -> PolicyViolation:
        return PolicyViolation(
            id=model.id,
            timestamp=model.timestamp,
            service=model.service,
            policy_name=model.policy_name,
            deployment_id=model.deployment_id,
            violation_type=model.violation_type,
            reason=model.reason,
            budget_remaining_pct=model.budget_remaining_pct,
            threshold_pct=model.threshold_pct,
            downstream_services=model.downstream_services or [],
            extra_data=model.extra_data or {},
        )

    @staticmethod
    def _override_to_domain(model: PolicyOverrideModel) -> PolicyOverride:
        return PolicyOverride(
            id=model.id,
            timestamp=model.timestamp,
            service=model.service,
            policy_name=model.policy_name,
            deployment_id=model.deployment_id,
            approved_by=model.approved_by,
            reason=model.reason,
            override_type=model.override_type,
            expires_at=model.expires_at,
            extra_data=model.extra_data or {},
        )
