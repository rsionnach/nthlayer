"""
Alert Rule Models

Data models for representing alerting rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .validator import ValidationResult


@dataclass
class AlertRule:
    """
    Prometheus alerting rule.

    Based on awesome-prometheus-alerts format with extensions
    for NthLayer-specific metadata.
    """

    name: str
    expr: str  # PromQL expression
    duration: str = "5m"  # How long condition must be true
    severity: str = "warning"  # critical, warning, info
    summary: str = ""
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    # NthLayer-specific metadata
    technology: str = ""  # postgres, redis, nginx, etc.
    category: str = ""  # database, proxy, orchestrator, etc.

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], technology: str = "", category: str = ""
    ) -> "AlertRule":
        """
        Parse alert rule from YAML dict (awesome-prometheus-alerts format).

        Example input:
            {
                "alert": "PostgresqlDown",
                "expr": "pg_up == 0",
                "for": "0m",
                "labels": {"severity": "critical"},
                "annotations": {
                    "summary": "Postgresql down (instance {{ $labels.instance }})",
                    "description": "Postgresql instance is down"
                }
            }
        """
        return cls(
            name=data["alert"],
            expr=data["expr"],
            duration=data.get("for", "5m"),
            severity=data.get("labels", {}).get("severity", "warning"),
            summary=data.get("annotations", {}).get("summary", ""),
            description=data.get("annotations", {}).get("description", ""),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            technology=technology,
            category=category,
        )

    def to_prometheus(self) -> Dict[str, Any]:
        """
        Convert to Prometheus YAML format.

        Output format matches Prometheus alerting rule syntax.
        """
        return {
            "alert": self.name,
            "expr": self.expr,
            "for": self.duration,
            "labels": self.labels,
            "annotations": self.annotations,
        }

    def customize_for_service(
        self,
        service_name: str,
        team: str,
        tier: str,
        notification_channel: str = "",
        runbook_url: str = "",
        routing: str | None = "",
    ) -> "AlertRule":
        """
        Customize alert for a specific service.

        Adds service context labels and annotations:
        - service: Service name
        - team: Owning team
        - tier: Service tier
        - routing: PagerDuty routing (for Event Orchestration)
        - notification_channel: Where to send alerts
        - runbook_url: Link to troubleshooting docs

        The routing label is used by PagerDuty Event Orchestration to
        route alerts to different escalation policies:
        - "sre": Route to SRE escalation policy
        - "team": Route to team escalation policy (default)
        - "shared": Team during business hours, SRE off-hours
        """
        # Create a copy
        customized = AlertRule(
            name=self.name,
            expr=self.expr,
            duration=self.duration,
            severity=self.severity,
            summary=self.summary,
            description=self.description,
            labels=self.labels.copy(),
            annotations=self.annotations.copy(),
            technology=self.technology,
            category=self.category,
        )

        # Add service context to labels
        customized.labels["service"] = service_name
        customized.labels["team"] = team
        customized.labels["tier"] = str(tier)

        # Add routing label for PagerDuty Event Orchestration
        if routing:
            customized.labels["routing"] = routing

        # Add notification and runbook to annotations
        if notification_channel:
            customized.annotations["channel"] = notification_channel

        if runbook_url:
            customized.annotations["runbook"] = f"{runbook_url}/{service_name}/{self.name}"

        return customized

    def is_critical(self) -> bool:
        """Check if alert is critical severity"""
        return self.severity == "critical"

    def is_down_alert(self) -> bool:
        """Check if alert is a 'down' or 'unavailable' alert"""
        down_keywords = ["down", "unavailable", "unreachable", "offline"]
        name_lower = self.name.lower()
        return any(keyword in name_lower for keyword in down_keywords)

    def validate_and_fix(self) -> tuple["AlertRule", "ValidationResult"]:
        """
        Validate alert and fix common issues from upstream templates.

        Fixes:
        1. Label references in annotations that don't exist in PromQL output
        2. 'for: 0m' duration changed to minimum safe value (1m)

        Returns:
            Tuple of (fixed AlertRule, ValidationResult with issues and fixes)

        Example:
            alert = AlertRule.from_dict(data)
            fixed_alert, result = alert.validate_and_fix()
            if result.fixes_applied:
                print(f"Applied fixes: {result.fixes_applied}")
        """
        from .validator import validate_and_fix_alert

        return validate_and_fix_alert(self)

    def __repr__(self) -> str:
        return (
            f"AlertRule(name='{self.name}', severity='{self.severity}', tech='{self.technology}')"
        )
