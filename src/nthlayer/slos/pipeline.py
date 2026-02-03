"""
Alert pipeline orchestration.

Wires spec parsing, error budget calculation, alert evaluation,
explanation generation, and notification dispatch into a single
``evaluate_service`` / ``evaluate_portfolio`` entry-point.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from nthlayer.slos.alerts import (
    AlertEvaluator,
    AlertEvent,
    AlertRule,
    AlertSeverity,
    AlertType,
)
from nthlayer.slos.explanations import BudgetExplanation, ExplanationEngine
from nthlayer.slos.models import SLO, ErrorBudget, TimeWindow
from nthlayer.slos.notifiers import AlertNotifier
from nthlayer.specs.alerting import (
    AlertingConfig,
    SpecAlertRule,
    resolve_effective_rules,
)
from nthlayer.specs.manifest import ReliabilityManifest

logger = structlog.get_logger()


@dataclass
class PipelineResult:
    """Result of a single service alert evaluation."""

    service: str
    budgets_evaluated: int = 0
    rules_evaluated: int = 0
    alerts_triggered: int = 0
    notifications_sent: int = 0
    explanations: list[BudgetExplanation] = field(default_factory=list)
    events: list[AlertEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    budgets: list[ErrorBudget] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "budgets_evaluated": self.budgets_evaluated,
            "rules_evaluated": self.rules_evaluated,
            "alerts_triggered": self.alerts_triggered,
            "notifications_sent": self.notifications_sent,
            "explanations": [e.to_dict() for e in self.explanations],
            "events": [e.to_dict() for e in self.events],
            "errors": self.errors,
            "budgets": [b.to_dict() for b in self.budgets],
        }

    @property
    def worst_severity(self) -> str:
        """Return the worst severity among triggered events."""
        if not self.events:
            return "healthy"
        severities = [e.severity for e in self.events]
        if AlertSeverity.CRITICAL in severities:
            return "critical"
        if AlertSeverity.WARNING in severities:
            return "warning"
        return "info"


class AlertPipeline:
    """
    Orchestrate end-to-end alert evaluation for a service.

    1. Load manifest -> resolve effective alert rules
    2. Calculate error budgets (from measurements or simulation)
    3. Evaluate rules via AlertEvaluator
    4. Generate explanations via ExplanationEngine
    5. Dispatch notifications via AlertNotifier (if enabled)
    """

    def __init__(
        self,
        prometheus_url: str | None = None,
        dry_run: bool = False,
        notify: bool = True,
    ) -> None:
        self.prometheus_url = prometheus_url
        self.dry_run = dry_run
        self.notify = notify and not dry_run
        self._evaluator = AlertEvaluator()
        self._explainer = ExplanationEngine()

    def evaluate_service(
        self,
        manifest: ReliabilityManifest,
        sli_measurements: dict[str, list[dict[str, Any]]] | None = None,
        simulate_burn_pct: float | None = None,
    ) -> PipelineResult:
        """
        Run the full pipeline for a single service manifest.

        Args:
            manifest: Parsed reliability manifest.
            sli_measurements: Optional dict mapping SLO name to measurement list.
            simulate_burn_pct: If set, simulate this % of budget burned (0-100).

        Returns:
            PipelineResult with all evaluation data.
        """
        result = PipelineResult(service=manifest.name)

        # 1. Resolve effective rules
        alerting = manifest.alerting or AlertingConfig()
        slo_names = [s.name for s in manifest.slos]
        effective_rules = resolve_effective_rules(alerting, manifest.tier, slo_names)
        result.rules_evaluated = len(effective_rules)

        if not manifest.slos:
            result.errors.append("No SLOs defined in manifest")
            return result

        # Resolve channels for notification
        channels = alerting.channels.resolve_env_vars()

        # Map event id -> explanation for notification enrichment
        event_explanations: dict[str, BudgetExplanation] = {}

        # 2. For each SLO: build budget, evaluate rules, explain
        for slo_def in manifest.slos:
            slo = _build_slo_from_manifest(manifest, slo_def)
            budget = _calculate_budget(
                slo,
                sli_measurements=(sli_measurements or {}).get(slo_def.name),
                simulate_burn_pct=simulate_burn_pct,
            )
            result.budgets.append(budget)
            result.budgets_evaluated += 1

            # Get rules for this SLO
            slo_rules = [r for r in effective_rules if r.slo == slo_def.name]
            alert_rules = [
                _convert_spec_rule_to_alert_rule(r, manifest.name, slo_def.name, channels)
                for r in slo_rules
            ]

            # Evaluate
            events = self._evaluator.evaluate_rules(budget, alert_rules)
            result.events.extend(events)
            result.alerts_triggered += len(events)

            # Explain each triggered event
            deps = manifest.dependencies or None
            deploy = manifest.deployment
            obs = manifest.observability
            for event in events:
                explanation = self._explainer.explain_alert(
                    event,
                    budget,
                    tier=manifest.tier,
                    service_type=manifest.type,
                    dependencies=deps,
                    deployment=deploy,
                    observability=obs,
                )
                result.explanations.append(explanation)
                event_explanations[event.id] = explanation

            # Also generate a budget explanation regardless of alerts
            if not events:
                explanation = self._explainer.explain_budget(
                    budget,
                    tier=manifest.tier,
                    service_type=manifest.type,
                    dependencies=deps,
                    deployment=deploy,
                    observability=obs,
                )
                result.explanations.append(explanation)

        # 5. Dispatch notifications
        if self.notify and result.events:
            sent = _dispatch_notifications(result.events, channels, event_explanations)
            result.notifications_sent = sent

        return result

    def evaluate_portfolio(
        self,
        manifests: list[ReliabilityManifest],
        simulate_burn_pct: float | None = None,
    ) -> list[PipelineResult]:
        """Evaluate multiple services and return aggregated results."""
        results: list[PipelineResult] = []
        for manifest in manifests:
            try:
                r = self.evaluate_service(manifest, simulate_burn_pct=simulate_burn_pct)
                results.append(r)
            except Exception as exc:
                pr = PipelineResult(service=manifest.name)
                pr.errors.append(str(exc))
                results.append(pr)
        return results


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------


def _build_slo_from_manifest(
    manifest: ReliabilityManifest,
    slo_def: Any,
) -> SLO:
    """Convert a manifest SLODefinition to the SLO model used by calculator."""
    return SLO(
        id=f"{manifest.name}-{slo_def.name}",
        service=manifest.name,
        name=slo_def.name,
        description=slo_def.description or slo_def.name,
        target=slo_def.target / 100 if slo_def.target > 1 else slo_def.target,
        time_window=TimeWindow(duration=slo_def.window),
        query=slo_def.indicator_query or "",
    )


def _calculate_budget(
    slo: SLO,
    sli_measurements: list[dict[str, Any]] | None = None,
    simulate_burn_pct: float | None = None,
) -> ErrorBudget:
    """Calculate error budget from measurements or simulation."""
    from nthlayer.slos.calculator import ErrorBudgetCalculator

    calc = ErrorBudgetCalculator(slo)

    if simulate_burn_pct is not None:
        # Simulated budget
        total = slo.error_budget_minutes()
        burned = total * (simulate_burn_pct / 100)
        now = datetime.utcnow()
        budget = ErrorBudget(
            slo_id=slo.id,
            service=slo.service,
            period_start=now - slo.time_window.to_timedelta(),
            period_end=now,
            total_budget_minutes=total,
            burned_minutes=burned,
            remaining_minutes=max(0.0, total - burned),
        )
        budget.status = budget.calculate_status()
        # Simulate proportional burn rate
        if simulate_burn_pct > 0:
            budget.burn_rate = simulate_burn_pct / 50  # >50% → >1x
        return budget

    return calc.calculate_budget(sli_measurements=sli_measurements)


def _convert_spec_rule_to_alert_rule(
    spec_rule: SpecAlertRule,
    service: str,
    slo_name: str,
    channels: Any,
) -> AlertRule:
    """Convert a SpecAlertRule from the config into a runtime AlertRule."""
    alert_type_map = {
        "budget_threshold": AlertType.BUDGET_THRESHOLD,
        "burn_rate": AlertType.BURN_RATE,
        "budget_exhaustion": AlertType.BUDGET_EXHAUSTION,
    }
    severity_map = {
        "info": AlertSeverity.INFO,
        "warning": AlertSeverity.WARNING,
        "critical": AlertSeverity.CRITICAL,
    }
    return AlertRule(
        id=f"{service}-{slo_name}-{spec_rule.name}",
        service=service,
        slo_id=slo_name,
        alert_type=alert_type_map.get(spec_rule.type, AlertType.BUDGET_THRESHOLD),
        severity=severity_map.get(spec_rule.severity, AlertSeverity.WARNING),
        threshold=spec_rule.threshold,
        slack_webhook=getattr(channels, "slack_webhook", None),
        pagerduty_key=getattr(channels, "pagerduty_key", None),
        enabled=spec_rule.enabled,
    )


def _dispatch_notifications(
    events: list[AlertEvent],
    channels: Any,
    event_explanations: dict[str, BudgetExplanation] | None = None,
) -> int:
    """Send notifications for triggered events. Returns count sent."""
    sent = 0
    notifier = AlertNotifier()
    if getattr(channels, "slack_webhook", None):
        notifier.add_slack(channels.slack_webhook)
    if getattr(channels, "pagerduty_key", None):
        notifier.add_pagerduty(channels.pagerduty_key)

    if not notifier.notifiers:
        return 0

    explanations = event_explanations or {}

    async def _send_all() -> int:
        count = 0
        for event in events:
            try:
                expl = explanations.get(event.id)
                results = await notifier.send_alert(event, explanation=expl)
                # Only count if at least one channel succeeded
                if any(r.get("status") == "sent" for r in results.values() if isinstance(r, dict)):
                    count += 1
            except Exception as exc:
                logger.warning("notification_failed", error=str(exc))
        return count

    try:
        sent = asyncio.run(_send_all())
    except RuntimeError:
        # Already in an event loop — use nest_asyncio or skip
        logger.warning("async_dispatch_skipped", reason="event_loop_running")

    return sent
