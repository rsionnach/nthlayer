"""
Data models for NthLayer CLI formatters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutputFormat(str, Enum):
    """Supported output formats."""

    TABLE = "table"
    JSON = "json"
    SARIF = "sarif"
    JUNIT = "junit"
    MARKDOWN = "markdown"


class CheckStatus(str, Enum):
    """Status of a reliability check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single reliability check."""

    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    rule_id: str | None = None
    location: str | None = None
    line: int | None = None


@dataclass
class ReliabilityReport:
    """
    Unified report structure for all NthLayer commands.

    This is the canonical format that all formatters consume.
    """

    service: str
    command: str
    checks: list[CheckResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> CheckStatus:
        """Overall status based on check results."""
        if any(c.status == CheckStatus.FAIL for c in self.checks):
            return CheckStatus.FAIL
        if any(c.status == CheckStatus.WARN for c in self.checks):
            return CheckStatus.WARN
        return CheckStatus.PASS

    @property
    def errors(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def warnings(self) -> int:
        """Count of warning checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def passed(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)


# SARIF Rule definitions
SARIF_RULES = {
    "NTHLAYER001": {
        "id": "NTHLAYER001",
        "name": "SLOInfeasible",
        "shortDescription": {"text": "SLO target exceeds dependency ceiling"},
        "fullDescription": {
            "text": "The declared SLO target cannot be achieved given the availability of upstream dependencies."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/slo-infeasible/",
        "defaultConfiguration": {"level": "error"},
    },
    "NTHLAYER002": {
        "id": "NTHLAYER002",
        "name": "DriftCritical",
        "shortDescription": {"text": "Error budget projected to exhaust soon"},
        "fullDescription": {
            "text": "Current error budget burn rate will exhaust the budget within the warning threshold."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/drift-critical/",
        "defaultConfiguration": {"level": "warning"},
    },
    "NTHLAYER003": {
        "id": "NTHLAYER003",
        "name": "MetricMissing",
        "shortDescription": {"text": "Required metric not found"},
        "fullDescription": {
            "text": "A metric required for SLO calculation is not being emitted by the service."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/metric-missing/",
        "defaultConfiguration": {"level": "error"},
    },
    "NTHLAYER004": {
        "id": "NTHLAYER004",
        "name": "BudgetExhausted",
        "shortDescription": {"text": "Error budget exhausted"},
        "fullDescription": {
            "text": "The service has consumed 100% or more of its error budget for the current window."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/budget-exhausted/",
        "defaultConfiguration": {"level": "error"},
    },
    "NTHLAYER005": {
        "id": "NTHLAYER005",
        "name": "HighBlastRadius",
        "shortDescription": {"text": "Change affects critical downstream services"},
        "fullDescription": {
            "text": "This service has critical-tier dependents that may be impacted by changes."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/high-blast-radius/",
        "defaultConfiguration": {"level": "warning"},
    },
    "NTHLAYER006": {
        "id": "NTHLAYER006",
        "name": "TierMismatch",
        "shortDescription": {"text": "Service tier lower than dependent's tier"},
        "fullDescription": {
            "text": "A lower-tier service is depended on by a higher-tier service, creating reliability risk."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/tier-mismatch/",
        "defaultConfiguration": {"level": "warning"},
    },
    "NTHLAYER007": {
        "id": "NTHLAYER007",
        "name": "OwnershipMissing",
        "shortDescription": {"text": "No team or owner defined"},
        "fullDescription": {
            "text": "The service does not have a team or owner defined in its configuration."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/ownership-missing/",
        "defaultConfiguration": {"level": "note"},
    },
    "NTHLAYER008": {
        "id": "NTHLAYER008",
        "name": "RunbookMissing",
        "shortDescription": {"text": "Critical service without runbook link"},
        "fullDescription": {
            "text": "A critical-tier service does not have a runbook URL configured."
        },
        "helpUri": "https://rsionnach.github.io/nthlayer/errors/runbook-missing/",
        "defaultConfiguration": {"level": "note"},
    },
}
