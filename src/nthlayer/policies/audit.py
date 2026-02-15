"""
Policy audit domain models.

Immutable records of policy evaluations, violations, and overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PolicyEvaluation:
    """Record of a policy evaluation (gate check or override)."""

    id: str
    timestamp: datetime
    service: str
    policy_name: str
    actor: str | None
    action: str  # "evaluate" | "override"
    result: str  # "approved" | "warning" | "blocked"
    context_snapshot: dict[str, Any]
    matched_condition: dict[str, Any] | None
    gate_check: dict[str, Any] | None
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyViolation:
    """Record of a policy violation (blocked or warning)."""

    id: str
    timestamp: datetime
    service: str
    policy_name: str
    deployment_id: str | None
    violation_type: str  # "blocked" | "warning"
    reason: str
    budget_remaining_pct: float
    threshold_pct: float
    downstream_services: list[str] = field(default_factory=list)
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyOverride:
    """Record of a manual policy override."""

    id: str
    timestamp: datetime
    service: str
    policy_name: str
    deployment_id: str | None
    approved_by: str
    reason: str
    override_type: str  # "manual_approval" | "team_exception" | "emergency_bypass"
    expires_at: datetime | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)
