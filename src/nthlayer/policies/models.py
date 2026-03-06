"""Policy engine models for build-time spec validation.

These models are for evaluating service spec correctness at build time.
The existing ``policies/audit.py`` models handle runtime deployment gate
audit trails — a separate concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuleType(StrEnum):
    required_fields = "required_fields"
    tier_constraint = "tier_constraint"
    dependency_rule = "dependency_rule"


class PolicySeverity(StrEnum):
    error = "error"
    warning = "warning"


@dataclass
class PolicyRule:
    """A single policy rule definition."""

    name: str
    type: RuleType
    severity: PolicySeverity = PolicySeverity.error
    params: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


@dataclass
class PolicyViolation:
    """A single policy violation found during evaluation."""

    rule_name: str
    rule_type: RuleType
    severity: PolicySeverity
    message: str
    field_path: str | None = None


@dataclass
class PolicyReport:
    """Result of evaluating all policies against a manifest."""

    service: str
    violations: list[PolicyViolation] = field(default_factory=list)
    rules_evaluated: int = 0

    @property
    def passed(self) -> bool:
        return not any(v.severity == PolicySeverity.error for v in self.violations)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == PolicySeverity.error)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == PolicySeverity.warning)
