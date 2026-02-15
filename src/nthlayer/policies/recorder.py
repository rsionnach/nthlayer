"""
Policy audit recorder.

Orchestrates audit logging for policy evaluations. All DB operations
are wrapped in try/except for fail-open behavior — audit errors are
logged via structlog but never block deployments.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from nthlayer.policies.evaluator import PolicyContext
    from nthlayer.slos.gates import DeploymentGateCheck

from nthlayer.policies.audit import PolicyEvaluation, PolicyOverride, PolicyViolation
from nthlayer.policies.repository import PolicyAuditRepository

logger = structlog.get_logger()


class PolicyAuditRecorder:
    """Records policy audit events with fail-open semantics."""

    def __init__(self, repository: PolicyAuditRepository) -> None:
        self.repository = repository

    async def record_gate_check(
        self,
        gate_check: DeploymentGateCheck,
        context: PolicyContext,
        matched_condition: dict[str, Any] | None = None,
        actor: str | None = None,
        deployment_id: str | None = None,
    ) -> PolicyEvaluation | None:
        """Record a deployment gate evaluation.

        Creates a PolicyEvaluation, and if the result is WARNING or BLOCKED,
        also creates a PolicyViolation.

        Returns None on DB error (fail open).
        """
        try:
            now = datetime.utcnow()
            eval_id = str(uuid.uuid4())

            result_str = gate_check.result.name.lower()

            evaluation = PolicyEvaluation(
                id=eval_id,
                timestamp=now,
                service=gate_check.service,
                policy_name="deployment-gate",
                actor=actor,
                action="evaluate",
                result=result_str,
                context_snapshot=context.to_dict(),
                matched_condition=matched_condition,
                gate_check={
                    "budget_remaining_pct": gate_check.budget_remaining_percentage,
                    "warning_threshold": gate_check.warning_threshold,
                    "blocking_threshold": gate_check.blocking_threshold,
                    "downstream_services": gate_check.downstream_services,
                    "message": gate_check.message,
                },
                extra_data={"deployment_id": deployment_id} if deployment_id else {},
            )

            await self.repository.record_evaluation(evaluation)

            # Record violation if not approved
            if gate_check.is_blocked or gate_check.is_warning:
                violation = PolicyViolation(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    service=gate_check.service,
                    policy_name="deployment-gate",
                    deployment_id=deployment_id,
                    violation_type="blocked" if gate_check.is_blocked else "warning",
                    reason=gate_check.message,
                    budget_remaining_pct=gate_check.budget_remaining_percentage,
                    threshold_pct=(
                        gate_check.blocking_threshold
                        if gate_check.is_blocked and gate_check.blocking_threshold
                        else gate_check.warning_threshold
                    ),
                    downstream_services=gate_check.downstream_services,
                )
                await self.repository.record_violation(violation)

            logger.info(
                "policy_evaluated",
                evaluation_id=eval_id,
                service=gate_check.service,
                result=result_str,
                budget_remaining_pct=gate_check.budget_remaining_percentage,
            )

            return evaluation

        except Exception:
            logger.warning(
                "policy_audit_record_failed",
                service=gate_check.service,
                action="evaluate",
                exc_info=True,
            )
            return None

    async def record_override(
        self,
        service: str,
        policy_name: str,
        approved_by: str,
        reason: str,
        override_type: str = "manual_approval",
        deployment_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> PolicyOverride | None:
        """Record a policy override.

        Creates a PolicyOverride and a corresponding PolicyEvaluation
        with action="override".

        Returns None on DB error (fail open).
        """
        try:
            now = datetime.utcnow()
            override_id = str(uuid.uuid4())

            override = PolicyOverride(
                id=override_id,
                timestamp=now,
                service=service,
                policy_name=policy_name,
                deployment_id=deployment_id,
                approved_by=approved_by,
                reason=reason,
                override_type=override_type,
                expires_at=expires_at,
            )
            await self.repository.record_override(override)

            # Also record as evaluation
            evaluation = PolicyEvaluation(
                id=str(uuid.uuid4()),
                timestamp=now,
                service=service,
                policy_name=policy_name,
                actor=approved_by,
                action="override",
                result="approved",
                context_snapshot={
                    "override_type": override_type,
                    "reason": reason,
                },
                matched_condition=None,
                gate_check=None,
                extra_data={"override_id": override_id, "deployment_id": deployment_id},
            )
            await self.repository.record_evaluation(evaluation)

            logger.info(
                "policy_override_recorded",
                override_id=override_id,
                service=service,
                policy_name=policy_name,
                approved_by=approved_by,
                override_type=override_type,
            )

            return override

        except Exception:
            logger.warning(
                "policy_audit_record_failed",
                service=service,
                action="override",
                exc_info=True,
            )
            return None
