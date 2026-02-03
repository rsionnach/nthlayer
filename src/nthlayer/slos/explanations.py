"""
Explanation engine for error budget alerts.

Generates human-readable explanations with causes, impact statements,
and recommended actions based on alert type, severity, tier, and
service type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nthlayer.slos.alerts import AlertEvent, AlertSeverity, AlertType
from nthlayer.slos.models import ErrorBudget

if TYPE_CHECKING:
    from nthlayer.specs.manifest import Dependency, DeploymentConfig, Observability


@dataclass
class RecommendedAction:
    """A single recommended action."""

    action: str
    priority: int  # 1 = highest
    category: str  # investigate, mitigate, communicate, prevent


@dataclass
class BudgetExplanation:
    """Rich explanation of an error budget state or alert."""

    headline: str
    body: str
    causes: list[str] = field(default_factory=list)
    impact: str = ""
    recommended_actions: list[RecommendedAction] = field(default_factory=list)

    # -------------------------------------------------------------------
    # Rendering methods
    # -------------------------------------------------------------------

    def to_text(self) -> str:
        lines = [self.headline, "", self.body]
        if self.causes:
            lines.append("")
            lines.append("Possible causes:")
            for c in self.causes:
                lines.append(f"  - {c}")
        if self.impact:
            lines.append("")
            lines.append(f"Impact: {self.impact}")
        if self.recommended_actions:
            lines.append("")
            lines.append("Recommended actions:")
            for a in sorted(self.recommended_actions, key=lambda x: x.priority):
                lines.append(f"  [{a.priority}] ({a.category}) {a.action}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [f"## {self.headline}", "", self.body]
        if self.causes:
            lines.append("")
            lines.append("### Possible Causes")
            for c in self.causes:
                lines.append(f"- {c}")
        if self.impact:
            lines.append("")
            lines.append(f"**Impact:** {self.impact}")
        if self.recommended_actions:
            lines.append("")
            lines.append("### Recommended Actions")
            for a in sorted(self.recommended_actions, key=lambda x: x.priority):
                lines.append(f"1. **[{a.category}]** {a.action}")
        return "\n".join(lines)

    def to_slack_blocks(self) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": self.headline},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": self.body},
            },
        ]
        if self.causes:
            causes_text = "\n".join(f"\u2022 {c}" for c in self.causes)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Possible Causes:*\n{causes_text}",
                    },
                }
            )
        if self.impact:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Impact:* {self.impact}",
                    },
                }
            )
        if self.recommended_actions:
            actions_text = "\n".join(
                f"{i+1}. [{a.category}] {a.action}"
                for i, a in enumerate(sorted(self.recommended_actions, key=lambda x: x.priority))
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Recommended Actions:*\n{actions_text}",
                    },
                }
            )
        return blocks

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "body": self.body,
            "causes": self.causes,
            "impact": self.impact,
            "recommended_actions": [
                {
                    "action": a.action,
                    "priority": a.priority,
                    "category": a.category,
                }
                for a in self.recommended_actions
            ],
        }


# -------------------------------------------------------------------------
# Service-type-specific causes
# -------------------------------------------------------------------------

_SERVICE_TYPE_CAUSES: dict[str, list[str]] = {
    "api": [
        "Upstream traffic spike exceeding capacity",
        "{dep_cause}",
        "{deploy_cause}",
    ],
    "worker": [
        "Queue backlog causing processing delays",
        "Increased job failure rate",
        "{dep_cause}",
    ],
    "stream": [
        "Consumer lag increasing",
        "Partition rebalancing or broker issues",
        "{dep_cause}",
    ],
    "batch": [
        "Job runtime exceeding expectations",
        "Input data volume spike",
        "{dep_cause}",
    ],
    "database": [
        "Query performance degradation",
        "Connection pool exhaustion",
        "Replication lag or failover",
    ],
}

_DEFAULT_CAUSES = [
    "{deploy_cause}",
    "{dep_cause}",
    "Increased error rate or latency",
]

# Fallback text when no dependencies / deployment config are available
_GENERIC_DEP_CAUSE = "Degraded upstream dependency"
_GENERIC_DEPLOY_CAUSE = "Recent deployment or configuration change"


def _dep_cause_text(dependencies: list[Dependency] | None) -> str:
    """One-liner listing known dependencies, or a generic fallback."""
    if not dependencies:
        return _GENERIC_DEP_CAUSE
    names = ", ".join(dep.name for dep in dependencies)
    return f"Degraded dependency ({names})"


def _deploy_cause_text(deployment: DeploymentConfig | None) -> str:
    """Reference actual gate config when available."""
    if not deployment or not deployment.gates:
        return _GENERIC_DEPLOY_CAUSE

    gate_parts: list[str] = []
    gates = deployment.gates
    if gates.error_budget and gates.error_budget.enabled:
        th = gates.error_budget.threshold
        if th is not None:
            gate_parts.append(f"error-budget ≥{th * 100:.0f}%")
    if gates.slo_compliance:
        gate_parts.append(f"SLO compliance ≥{gates.slo_compliance.threshold}")
    if gates.recent_incidents:
        ri = gates.recent_incidents
        gate_parts.append(f"P1≤{ri.p1_max}/P2≤{ri.p2_max} in {ri.lookback}")

    if gate_parts:
        return (
            "Recent deployment passed gates "
            f"({', '.join(gate_parts)}) — verify post-deploy metrics"
        )
    return _GENERIC_DEPLOY_CAUSE


def _build_causes(
    service_type: str,
    dependencies: list[Dependency] | None = None,
    deployment: DeploymentConfig | None = None,
) -> list[str]:
    """Build cause list with concrete dependency and deployment context."""
    templates = list(_SERVICE_TYPE_CAUSES.get(service_type, _DEFAULT_CAUSES))
    dep_text = _dep_cause_text(dependencies)
    deploy_text = _deploy_cause_text(deployment)

    return [t.format(dep_cause=dep_text, deploy_cause=deploy_text) for t in templates]


# -------------------------------------------------------------------------
# Tier-specific actions
# -------------------------------------------------------------------------

_TIER_ACTIONS: dict[str, list[RecommendedAction]] = {
    "critical": [
        RecommendedAction("Halt non-essential deployments (deployment freeze)", 1, "mitigate"),
        RecommendedAction("Page on-call engineer immediately", 1, "communicate"),
        RecommendedAction("{rollback_action}", 2, "investigate"),
        RecommendedAction("Schedule post-incident review", 3, "prevent"),
    ],
    "high": [
        RecommendedAction("Pause deployments until budget stabilises", 1, "mitigate"),
        RecommendedAction("Notify team lead and on-call", 2, "communicate"),
        RecommendedAction("{rollback_action}", 2, "investigate"),
    ],
    "standard": [
        RecommendedAction("Investigate root cause", 1, "investigate"),
        RecommendedAction("Consider pausing risky deployments", 2, "mitigate"),
        RecommendedAction("Notify owning team", 3, "communicate"),
    ],
    "low": [
        RecommendedAction("Investigate at next sprint planning", 1, "investigate"),
        RecommendedAction("Log for trend analysis", 2, "prevent"),
    ],
}


# -------------------------------------------------------------------------
# Technology-specific investigation actions
# -------------------------------------------------------------------------

_DEP_TYPE_ACTIONS: dict[str, str] = {
    "postgresql": (
        "Check pg_stat_activity for long-running queries " "and connection pool utilisation"
    ),
    "mysql": "Check slow query log and InnoDB buffer pool hit ratio",
    "redis": "Check Redis memory usage (INFO memory) and eviction policy",
    "memcached": "Check slab allocation and eviction counters",
    "kafka": "Check consumer group lag and partition assignment",
    "rabbitmq": "Check queue depth and consumer acknowledgement rate",
    "elasticsearch": "Check cluster health, pending tasks, and JVM heap",
    "mongodb": "Check oplog window, replication lag, and slow queries",
    "dynamodb": "Check consumed vs provisioned capacity and throttle events",
    "s3": "Check request latency and 5xx error rate",
    "grpc": "Check upstream gRPC deadline exceeded and unavailable errors",
    "http": "Check upstream HTTP 5xx rate and p99 latency",
}


def _dep_investigation_actions(
    dependencies: list[Dependency] | None,
) -> list[RecommendedAction]:
    """Generate investigation actions specific to each dependency's type."""
    if not dependencies:
        return []
    actions: list[RecommendedAction] = []
    seen_types: set[str] = set()
    for dep in dependencies:
        # Match on database_type (e.g. "postgresql") or fall back to dep.type
        dep_tech = (getattr(dep, "database_type", None) or dep.type).lower()
        if dep_tech in seen_types:
            continue
        seen_types.add(dep_tech)
        text = _DEP_TYPE_ACTIONS.get(dep_tech)
        if text:
            actions.append(
                RecommendedAction(
                    action=f"{dep.name}: {text}",
                    priority=2,
                    category="investigate",
                )
            )
    return actions


# -------------------------------------------------------------------------
# Grafana dashboard URL resolution
# -------------------------------------------------------------------------


def _resolve_grafana_url(
    service: str,
    observability: Observability | None = None,
) -> str | None:
    """Return dashboard URL from observability config or NTHLAYER_GRAFANA_URL."""
    import os

    if observability and observability.grafana_url:
        return observability.grafana_url
    base = os.environ.get("NTHLAYER_GRAFANA_URL")
    if base:
        return f"{base.rstrip('/')}/d/{service}-overview/{service}"
    return None


# -------------------------------------------------------------------------
# Rollback / deployment helpers
# -------------------------------------------------------------------------

_GENERIC_ROLLBACK = "Check recent deployments and rollback if needed"


def _rollback_action_text(deployment: DeploymentConfig | None) -> str:
    """Specific rollback advice when deployment config is present."""
    if not deployment:
        return _GENERIC_ROLLBACK
    if deployment.rollback and deployment.rollback.automatic:
        triggers: list[str] = []
        if deployment.rollback.error_rate_increase:
            triggers.append(f"error rate +{deployment.rollback.error_rate_increase}")
        if deployment.rollback.latency_increase:
            triggers.append(f"latency +{deployment.rollback.latency_increase}")
        if triggers:
            return (
                "Auto-rollback is configured "
                f"({', '.join(triggers)}) — verify it has not already triggered"
            )
        return "Auto-rollback is configured — verify it has not already triggered"
    if deployment.rollback:
        return "Manual rollback is configured — initiate if post-deploy metrics degraded"
    return _GENERIC_ROLLBACK


def _build_actions(
    tier: str,
    service: str = "",
    deployment: DeploymentConfig | None = None,
    dependencies: list[Dependency] | None = None,
    observability: Observability | None = None,
) -> list[RecommendedAction]:
    """Build actions from tier defaults + tech-specific investigation + dashboard link."""
    # 1. Tier-level actions (with rollback text)
    templates = list(_TIER_ACTIONS.get(tier, _TIER_ACTIONS["standard"]))
    rollback_text = _rollback_action_text(deployment)
    actions = [
        RecommendedAction(
            action=a.action.format(rollback_action=rollback_text),
            priority=a.priority,
            category=a.category,
        )
        for a in templates
    ]

    # 2. Technology-specific investigation for each dependency
    actions.extend(_dep_investigation_actions(dependencies))

    # 3. Grafana dashboard link
    dashboard_url = _resolve_grafana_url(service, observability)
    if dashboard_url:
        actions.append(
            RecommendedAction(
                action=f"View service dashboard: {dashboard_url}",
                priority=1,
                category="investigate",
            )
        )

    return actions


# -------------------------------------------------------------------------
# Template registry
# -------------------------------------------------------------------------

# Key: (AlertType, AlertSeverity) -> (headline_template, body_template)
_TEMPLATES: dict[tuple[AlertType, AlertSeverity], tuple[str, str]] = {
    (AlertType.BUDGET_THRESHOLD, AlertSeverity.WARNING): (
        "Error budget warning for {service}",
        "{consumed:.0f}% of the error budget for *{slo}* has been consumed. "
        "The warning threshold of {threshold:.0f}% was breached.",
    ),
    (AlertType.BUDGET_THRESHOLD, AlertSeverity.CRITICAL): (
        "CRITICAL: Error budget nearly exhausted for {service}",
        "{consumed:.0f}% of the error budget for *{slo}* has been consumed. "
        "The critical threshold of {threshold:.0f}% was breached. Immediate action required.",
    ),
    (AlertType.BUDGET_THRESHOLD, AlertSeverity.INFO): (
        "Error budget notice for {service}",
        "{consumed:.0f}% of the error budget for *{slo}* has been consumed.",
    ),
    (AlertType.BURN_RATE, AlertSeverity.WARNING): (
        "Elevated burn rate for {service}",
        "The error budget for *{slo}* is burning at {burn_rate:.1f}x the baseline rate "
        "(threshold: {threshold:.1f}x). At this pace the budget may exhaust prematurely.",
    ),
    (AlertType.BURN_RATE, AlertSeverity.CRITICAL): (
        "CRITICAL: High burn rate for {service}",
        "The error budget for *{slo}* is burning at {burn_rate:.1f}x the baseline rate "
        "(threshold: {threshold:.1f}x). Immediate investigation required.",
    ),
    (AlertType.BURN_RATE, AlertSeverity.INFO): (
        "Burn rate notice for {service}",
        "The burn rate for *{slo}* is {burn_rate:.1f}x the baseline.",
    ),
    (AlertType.BUDGET_EXHAUSTION, AlertSeverity.WARNING): (
        "Budget exhaustion projected for {service}",
        "At the current burn rate, the error budget for *{slo}* will exhaust within "
        "{exhaustion_hours:.0f} hours.",
    ),
    (AlertType.BUDGET_EXHAUSTION, AlertSeverity.CRITICAL): (
        "CRITICAL: Budget exhaustion imminent for {service}",
        "The error budget for *{slo}* will exhaust within {exhaustion_hours:.0f} hours "
        "at the current burn rate. Immediate action required.",
    ),
    (AlertType.BUDGET_EXHAUSTION, AlertSeverity.INFO): (
        "Budget exhaustion projection for {service}",
        "The error budget for *{slo}* is projected to exhaust in {exhaustion_hours:.0f} hours.",
    ),
}


# -------------------------------------------------------------------------
# Engine
# -------------------------------------------------------------------------


class ExplanationEngine:
    """Generates rich explanations for error budget alerts."""

    def explain_budget(
        self,
        budget: ErrorBudget,
        tier: str = "standard",
        service_type: str = "api",
        dependencies: list[Dependency] | None = None,
        deployment: DeploymentConfig | None = None,
        observability: Observability | None = None,
    ) -> BudgetExplanation:
        """Explain the current state of an error budget."""
        consumed = budget.percent_consumed
        slo = budget.slo_id
        service = budget.service

        if consumed >= 95:
            headline = f"Error budget exhausted for {service}"
            body = (
                f"The error budget for *{slo}* is {consumed:.0f}% consumed. "
                "Service reliability is critically degraded."
            )
        elif consumed >= 75:
            headline = f"Error budget running low for {service}"
            body = (
                f"The error budget for *{slo}* is {consumed:.0f}% consumed. "
                "Budget is running low."
            )
        elif consumed >= 50:
            headline = f"Error budget elevated for {service}"
            body = f"The error budget for *{slo}* is {consumed:.0f}% consumed. " "Monitor closely."
        else:
            headline = f"Error budget healthy for {service}"
            body = (
                f"The error budget for *{slo}* is {consumed:.0f}% consumed. "
                "Budget is within normal range."
            )

        causes = _build_causes(service_type, dependencies, deployment)
        actions = _build_actions(tier, service, deployment, dependencies, observability)
        remaining = budget.remaining_minutes
        impact = (
            f"{remaining:.0f} minutes of error budget remaining "
            f"({budget.percent_remaining:.1f}%)"
        )

        return BudgetExplanation(
            headline=headline,
            body=body,
            causes=list(causes),
            impact=impact,
            recommended_actions=actions,
        )

    def explain_alert(
        self,
        event: AlertEvent,
        budget: ErrorBudget,
        tier: str = "standard",
        service_type: str = "api",
        dependencies: list[Dependency] | None = None,
        deployment: DeploymentConfig | None = None,
        observability: Observability | None = None,
    ) -> BudgetExplanation:
        """Explain a triggered alert event with budget context."""
        try:
            alert_type = AlertType(event.details.get("alert_type", "budget_threshold"))
        except ValueError:
            return self.explain_budget(
                budget,
                tier,
                service_type,
                dependencies,
                deployment,
                observability,
            )
        severity = event.severity

        template = _TEMPLATES.get((alert_type, severity))
        if template is None:
            return self.explain_budget(
                budget,
                tier,
                service_type,
                dependencies,
                deployment,
                observability,
            )

        headline_tpl, body_tpl = template

        fmt_kwargs: dict[str, Any] = {
            "service": budget.service,
            "slo": budget.slo_id,
            "consumed": budget.percent_consumed,
            "threshold": event.details.get("threshold_percent", 0),
            "burn_rate": budget.burn_rate or 0,
            "exhaustion_hours": event.details.get("exhaustion_hours", 0),
        }

        headline = headline_tpl.format(**fmt_kwargs)
        body = body_tpl.format(**fmt_kwargs)

        causes = _build_causes(service_type, dependencies, deployment)
        actions = _build_actions(tier, budget.service, deployment, dependencies, observability)
        impact = (
            f"{budget.remaining_minutes:.0f} minutes of error budget remaining "
            f"({budget.percent_remaining:.1f}%)"
        )

        return BudgetExplanation(
            headline=headline,
            body=body,
            causes=list(causes),
            impact=impact,
            recommended_actions=actions,
        )
