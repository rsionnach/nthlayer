"""
Alert rules and evaluation for error budget monitoring.

Evaluates alert conditions and triggers notifications when
error budgets are at risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from nthlayer.slos.models import ErrorBudget

logger = structlog.get_logger()


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alert conditions."""
    BUDGET_THRESHOLD = "budget_threshold"  # Budget consumed > X%
    BURN_RATE = "burn_rate"                # Burn rate > Xx baseline
    BUDGET_EXHAUSTION = "budget_exhaustion" # Budget will exhaust soon


@dataclass
class AlertRule:
    """Alert rule definition."""
    
    id: str
    service: str
    slo_id: str
    alert_type: AlertType
    severity: AlertSeverity
    
    # Rule parameters
    threshold: float  # e.g., 0.75 for 75% consumed
    
    # Notification config
    slack_webhook: str | None = None
    pagerduty_key: str | None = None
    
    # Metadata
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "service": self.service,
            "slo_id": self.slo_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "threshold": self.threshold,
            "slack_webhook": self.slack_webhook,
            "pagerduty_key": self.pagerduty_key,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class AlertEvent:
    """Alert event that was triggered."""
    
    id: str
    rule_id: str
    service: str
    slo_id: str
    severity: AlertSeverity
    title: str
    message: str
    details: dict[str, Any]
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "service": self.service,
            "slo_id": self.slo_id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "triggered_at": self.triggered_at.isoformat(),
        }


class AlertEvaluator:
    """Evaluates alert rules against error budgets."""
    
    def __init__(self) -> None:
        pass
    
    def evaluate_budget_threshold(
        self,
        budget: ErrorBudget,
        rule: AlertRule,
    ) -> AlertEvent | None:
        """
        Evaluate budget threshold alert.
        
        Triggers when budget consumed exceeds threshold.
        
        Args:
            budget: Current error budget
            rule: Alert rule to evaluate
            
        Returns:
            AlertEvent if triggered, None otherwise
        """
        percent_consumed = budget.percent_consumed / 100  # Convert to 0-1
        
        if percent_consumed < rule.threshold:
            return None
        
        logger.info(
            "budget_threshold_triggered",
            service=budget.service,
            slo_id=budget.slo_id,
            percent_consumed=budget.percent_consumed,
            threshold=rule.threshold * 100,
        )
        
        # Create alert event
        event = AlertEvent(
            id=f"alert-{budget.service}-{int(datetime.utcnow().timestamp())}",
            rule_id=rule.id,
            service=budget.service,
            slo_id=budget.slo_id,
            severity=rule.severity,
            title=f"Error Budget Alert: {budget.service}",
            message=self._format_threshold_message(budget, rule),
            details={
                "budget_consumed_percent": budget.percent_consumed,
                "threshold_percent": rule.threshold * 100,
                "burned_minutes": budget.burned_minutes,
                "remaining_minutes": budget.remaining_minutes,
                "status": budget.status.value,
            },
        )
        
        return event
    
    def evaluate_burn_rate(
        self,
        budget: ErrorBudget,
        rule: AlertRule,
    ) -> AlertEvent | None:
        """
        Evaluate burn rate alert.
        
        Triggers when burn rate exceeds threshold multiplier
        (e.g., 3x baseline).
        
        Args:
            budget: Current error budget
            rule: Alert rule to evaluate
            
        Returns:
            AlertEvent if triggered, None otherwise
        """
        if not budget.burn_rate or budget.burn_rate < rule.threshold:
            return None
        
        logger.info(
            "burn_rate_triggered",
            service=budget.service,
            slo_id=budget.slo_id,
            burn_rate=budget.burn_rate,
            threshold=rule.threshold,
        )
        
        # Create alert event
        event = AlertEvent(
            id=f"alert-{budget.service}-{int(datetime.utcnow().timestamp())}",
            rule_id=rule.id,
            service=budget.service,
            slo_id=budget.slo_id,
            severity=rule.severity,
            title=f"High Burn Rate Alert: {budget.service}",
            message=self._format_burn_rate_message(budget, rule),
            details={
                "burn_rate": budget.burn_rate,
                "threshold": rule.threshold,
                "burned_minutes": budget.burned_minutes,
                "remaining_minutes": budget.remaining_minutes,
            },
        )
        
        return event
    
    def evaluate_rules(
        self,
        budget: ErrorBudget,
        rules: list[AlertRule],
    ) -> list[AlertEvent]:
        """
        Evaluate all rules for a budget.
        
        Args:
            budget: Current error budget
            rules: List of alert rules to evaluate
            
        Returns:
            List of triggered alert events
        """
        events = []
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            event = None
            
            if rule.alert_type == AlertType.BUDGET_THRESHOLD:
                event = self.evaluate_budget_threshold(budget, rule)
            elif rule.alert_type == AlertType.BURN_RATE:
                event = self.evaluate_burn_rate(budget, rule)
            
            if event:
                events.append(event)
        
        return events
    
    def _format_threshold_message(self, budget: ErrorBudget, rule: AlertRule) -> str:
        """Format threshold alert message."""
        threshold_pct = rule.threshold * 100
        consumed_pct = budget.percent_consumed
        
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🔥",
        }
        emoji = severity_emoji.get(rule.severity, "⚠️")
        
        message = (
            f"{emoji} *Error Budget Alert*\n\n"
            f"*Service:* `{budget.service}`\n"
            f"*SLO:* `{budget.slo_id}`\n"
            f"*Consumed:* {consumed_pct:.1f}% (threshold: {threshold_pct:.0f}%)\n"
            f"*Remaining:* {budget.remaining_minutes:.1f} minutes\n"
            f"*Status:* {budget.status.value.upper()}\n\n"
        )
        
        if consumed_pct >= 90:
            message += "⚠️ *CRITICAL: Budget nearly exhausted!*\n"
            message += "Consider deployment freeze or immediate action.\n"
        elif consumed_pct >= 75:
            message += "⚠️ *WARNING: Budget running low*\n"
            message += "Review recent changes and incidents.\n"
        else:
            message += "ℹ️ Budget threshold exceeded. Monitor closely.\n"
        
        return message
    
    def _format_burn_rate_message(self, budget: ErrorBudget, rule: AlertRule) -> str:
        """Format burn rate alert message."""
        burn_rate = budget.burn_rate or 0
        threshold = rule.threshold
        
        message = (
            f"🔥 *High Burn Rate Alert*\n\n"
            f"*Service:* `{budget.service}`\n"
            f"*SLO:* `{budget.slo_id}`\n"
            f"*Burn Rate:* {burn_rate:.2f}x baseline (threshold: {threshold:.1f}x)\n"
            f"*Burned:* {budget.burned_minutes:.1f} minutes\n"
            f"*Remaining:* {budget.remaining_minutes:.1f} minutes\n\n"
        )
        
        if burn_rate >= 6:
            message += "🚨 *CRITICAL: Burn rate extremely high!*\n"
            message += "Budget will exhaust in hours. Investigate immediately.\n"
        elif burn_rate >= 3:
            message += "⚠️ *WARNING: Elevated burn rate*\n"
            message += "Check recent deployments and incidents.\n"
        else:
            message += "ℹ️ Burn rate above normal. Monitor situation.\n"
        
        return message


class AlertRuleStorage:
    """Storage for alert rules (simple in-memory for MVP)."""
    
    def __init__(self) -> None:
        self._rules: dict[str, list[AlertRule]] = {}
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule for a service."""
        if rule.service not in self._rules:
            self._rules[rule.service] = []
        
        # Remove existing rule with same ID
        self._rules[rule.service] = [
            r for r in self._rules[rule.service] 
            if r.id != rule.id
        ]
        
        self._rules[rule.service].append(rule)
        
        logger.info(
            "alert_rule_added",
            rule_id=rule.id,
            service=rule.service,
            alert_type=rule.alert_type.value,
        )
    
    def get_rules(self, service: str) -> list[AlertRule]:
        """Get all alert rules for a service."""
        return self._rules.get(service, [])
    
    def get_all_rules(self) -> dict[str, list[AlertRule]]:
        """Get all alert rules."""
        return self._rules
    
    def delete_rule(self, rule_id: str, service: str) -> bool:
        """Delete an alert rule."""
        if service not in self._rules:
            return False
        
        before_count = len(self._rules[service])
        self._rules[service] = [
            r for r in self._rules[service]
            if r.id != rule_id
        ]
        after_count = len(self._rules[service])
        
        deleted = before_count > after_count
        
        if deleted:
            logger.info("alert_rule_deleted", rule_id=rule_id, service=service)
        
        return deleted


# Global alert rule storage (for MVP)
_alert_storage = AlertRuleStorage()


def get_alert_storage() -> AlertRuleStorage:
    """Get global alert storage instance."""
    return _alert_storage
