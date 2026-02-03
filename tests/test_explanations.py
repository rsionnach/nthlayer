"""Tests for the explanation engine."""

from __future__ import annotations

from datetime import datetime, timedelta

from nthlayer.slos.alerts import AlertEvent, AlertSeverity, AlertType
from nthlayer.slos.explanations import (
    BudgetExplanation,
    ExplanationEngine,
    RecommendedAction,
)
from nthlayer.slos.models import ErrorBudget, SLOStatus


def _make_budget(
    consumed_pct: float = 50.0,
    burn_rate: float = 1.0,
    total: float = 100.0,
) -> ErrorBudget:
    burned = total * (consumed_pct / 100)
    now = datetime.utcnow()
    return ErrorBudget(
        slo_id="availability",
        service="payment-api",
        period_start=now - timedelta(days=15),
        period_end=now,
        total_budget_minutes=total,
        burned_minutes=burned,
        remaining_minutes=max(0.0, total - burned),
        status=SLOStatus.WARNING if consumed_pct >= 50 else SLOStatus.HEALTHY,
        burn_rate=burn_rate,
    )


def _make_event(
    alert_type: str = "budget_threshold",
    severity: AlertSeverity = AlertSeverity.WARNING,
    threshold_percent: float = 75,
) -> AlertEvent:
    return AlertEvent(
        id="evt-1",
        rule_id="rule-1",
        service="payment-api",
        slo_id="availability",
        severity=severity,
        title="Test Alert",
        message="test",
        details={
            "alert_type": alert_type,
            "threshold_percent": threshold_percent,
            "exhaustion_hours": 5,
        },
    )


# -------------------------------------------------------------------------
# BudgetExplanation rendering
# -------------------------------------------------------------------------


class TestBudgetExplanationRendering:
    def test_to_text(self) -> None:
        expl = BudgetExplanation(
            headline="Test",
            body="Body text",
            causes=["Cause A", "Cause B"],
            impact="Impact statement",
            recommended_actions=[
                RecommendedAction("Action 1", 1, "investigate"),
                RecommendedAction("Action 2", 2, "mitigate"),
            ],
        )
        text = expl.to_text()
        assert "Test" in text
        assert "Body text" in text
        assert "Cause A" in text
        assert "Impact statement" in text
        assert "Action 1" in text

    def test_to_markdown(self) -> None:
        expl = BudgetExplanation(
            headline="Headline",
            body="Body",
            causes=["C1"],
            impact="I1",
            recommended_actions=[RecommendedAction("A1", 1, "investigate")],
        )
        md = expl.to_markdown()
        assert md.startswith("## Headline")
        assert "### Possible Causes" in md
        assert "**Impact:**" in md
        assert "### Recommended Actions" in md

    def test_to_slack_blocks(self) -> None:
        expl = BudgetExplanation(
            headline="Head",
            body="Body",
            causes=["C"],
            impact="I",
            recommended_actions=[RecommendedAction("A", 1, "mitigate")],
        )
        blocks = expl.to_slack_blocks()
        assert len(blocks) >= 4
        assert blocks[0]["type"] == "header"
        assert blocks[1]["type"] == "section"

    def test_to_dict(self) -> None:
        expl = BudgetExplanation(
            headline="H",
            body="B",
            causes=["C"],
            impact="I",
            recommended_actions=[RecommendedAction("A", 1, "investigate")],
        )
        d = expl.to_dict()
        assert d["headline"] == "H"
        assert d["body"] == "B"
        assert len(d["causes"]) == 1
        assert d["recommended_actions"][0]["action"] == "A"

    def test_empty_explanation(self) -> None:
        expl = BudgetExplanation(headline="H", body="B")
        text = expl.to_text()
        assert "Possible causes" not in text
        md = expl.to_markdown()
        assert "### Possible Causes" not in md
        blocks = expl.to_slack_blocks()
        assert len(blocks) == 2  # header + section only

    def test_actions_sorted_by_priority(self) -> None:
        expl = BudgetExplanation(
            headline="H",
            body="B",
            recommended_actions=[
                RecommendedAction("Low", 3, "prevent"),
                RecommendedAction("High", 1, "investigate"),
                RecommendedAction("Mid", 2, "mitigate"),
            ],
        )
        text = expl.to_text()
        high_pos = text.index("High")
        mid_pos = text.index("Mid")
        low_pos = text.index("Low")
        assert high_pos < mid_pos < low_pos


# -------------------------------------------------------------------------
# ExplanationEngine.explain_budget
# -------------------------------------------------------------------------


class TestExplainBudget:
    def setup_method(self) -> None:
        self.engine = ExplanationEngine()

    def test_healthy_budget(self) -> None:
        budget = _make_budget(consumed_pct=20)
        expl = self.engine.explain_budget(budget)
        assert "healthy" in expl.headline.lower()

    def test_elevated_budget(self) -> None:
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget)
        assert "elevated" in expl.headline.lower()

    def test_running_low_budget(self) -> None:
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget)
        assert "running low" in expl.headline.lower()

    def test_exhausted_budget(self) -> None:
        budget = _make_budget(consumed_pct=97)
        expl = self.engine.explain_budget(budget)
        assert "exhausted" in expl.headline.lower()

    def test_zero_budget(self) -> None:
        budget = _make_budget(consumed_pct=0, total=0)
        expl = self.engine.explain_budget(budget)
        assert expl.headline  # Should not crash
        assert expl.body

    def test_api_service_type_causes(self) -> None:
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, service_type="api")
        assert any("traffic" in c.lower() for c in expl.causes)

    def test_worker_service_type_causes(self) -> None:
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, service_type="worker")
        assert any("queue" in c.lower() for c in expl.causes)

    def test_stream_service_type_causes(self) -> None:
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, service_type="stream")
        assert any("consumer" in c.lower() or "lag" in c.lower() for c in expl.causes)

    def test_critical_tier_actions(self) -> None:
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="critical")
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("freeze" in t or "halt" in t for t in action_texts)

    def test_low_tier_actions(self) -> None:
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="low")
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("sprint" in t for t in action_texts)

    def test_impact_statement_present(self) -> None:
        budget = _make_budget(consumed_pct=70)
        expl = self.engine.explain_budget(budget)
        assert "remaining" in expl.impact.lower()

    def test_dependency_names_in_causes(self) -> None:
        from nthlayer.specs.manifest import Dependency, DependencyCriticality

        deps = [
            Dependency(name="postgresql", type="database", criticality=DependencyCriticality.HIGH),
            Dependency(name="redis-cache", type="cache", criticality=DependencyCriticality.MEDIUM),
        ]
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, dependencies=deps)
        combined = " ".join(expl.causes)
        assert "postgresql" in combined
        assert "redis-cache" in combined

    def test_no_dependencies_uses_generic(self) -> None:
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, dependencies=None)
        combined = " ".join(expl.causes)
        assert "dependency" in combined.lower()

    def test_deployment_gates_in_causes(self) -> None:
        from nthlayer.specs.manifest import (
            DeploymentConfig,
            DeploymentGates,
            ErrorBudgetGate,
        )

        deploy = DeploymentConfig(
            gates=DeploymentGates(error_budget=ErrorBudgetGate(threshold=0.10))
        )
        budget = _make_budget(consumed_pct=60)
        expl = self.engine.explain_budget(budget, deployment=deploy)
        combined = " ".join(expl.causes)
        assert "error-budget" in combined.lower()

    def test_auto_rollback_in_actions(self) -> None:
        from nthlayer.specs.manifest import DeploymentConfig, RollbackConfig

        deploy = DeploymentConfig(
            rollback=RollbackConfig(
                automatic=True,
                error_rate_increase="5%",
                latency_increase="50%",
            )
        )
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="critical", deployment=deploy)
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("auto-rollback" in t for t in action_texts)

    def test_no_deployment_uses_generic_rollback(self) -> None:
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="critical", deployment=None)
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("rollback" in t for t in action_texts)

    def test_tech_specific_actions_for_postgresql(self) -> None:
        from nthlayer.specs.manifest import Dependency, DependencyCriticality

        deps = [
            Dependency(
                name="main-db",
                type="postgresql",
                criticality=DependencyCriticality.HIGH,
            ),
        ]
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(
            budget,
            tier="critical",
            dependencies=deps,
        )
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("pg_stat_activity" in t for t in action_texts)

    def test_tech_specific_actions_for_redis(self) -> None:
        from nthlayer.specs.manifest import Dependency, DependencyCriticality

        deps = [
            Dependency(
                name="cache",
                type="redis",
                criticality=DependencyCriticality.MEDIUM,
            ),
        ]
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(
            budget,
            tier="critical",
            dependencies=deps,
        )
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("info memory" in t for t in action_texts)

    def test_tech_specific_actions_for_kafka(self) -> None:
        from nthlayer.specs.manifest import Dependency, DependencyCriticality

        deps = [
            Dependency(
                name="events",
                type="kafka",
                criticality=DependencyCriticality.MEDIUM,
            ),
        ]
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(
            budget,
            tier="critical",
            dependencies=deps,
        )
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("consumer group lag" in t for t in action_texts)

    def test_grafana_link_in_actions(self, monkeypatch) -> None:
        monkeypatch.setenv("NTHLAYER_GRAFANA_URL", "http://grafana.local:3000")
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="critical")
        action_texts = [a.action for a in expl.recommended_actions]
        assert any("grafana.local:3000" in t for t in action_texts)

    def test_no_grafana_link_without_env(self, monkeypatch) -> None:
        monkeypatch.delenv("NTHLAYER_GRAFANA_URL", raising=False)
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(budget, tier="critical")
        action_texts = [a.action for a in expl.recommended_actions]
        assert not any("grafana" in t.lower() for t in action_texts)

    def test_grafana_url_from_observability(self) -> None:
        from nthlayer.specs.manifest import Observability

        obs = Observability(grafana_url="http://custom-grafana.com/d/my-svc")
        budget = _make_budget(consumed_pct=80)
        expl = self.engine.explain_budget(
            budget,
            tier="critical",
            observability=obs,
        )
        action_texts = [a.action for a in expl.recommended_actions]
        assert any("custom-grafana.com" in t for t in action_texts)


# -------------------------------------------------------------------------
# ExplanationEngine.explain_alert
# -------------------------------------------------------------------------


class TestExplainAlert:
    def setup_method(self) -> None:
        self.engine = ExplanationEngine()

    def test_budget_threshold_warning(self) -> None:
        budget = _make_budget(consumed_pct=80)
        event = _make_event(alert_type="budget_threshold", severity=AlertSeverity.WARNING)
        expl = self.engine.explain_alert(event, budget)
        assert "warning" in expl.headline.lower()
        assert expl.causes

    def test_budget_threshold_critical(self) -> None:
        budget = _make_budget(consumed_pct=90)
        event = _make_event(alert_type="budget_threshold", severity=AlertSeverity.CRITICAL)
        expl = self.engine.explain_alert(event, budget)
        assert "CRITICAL" in expl.headline

    def test_burn_rate_warning(self) -> None:
        budget = _make_budget(consumed_pct=60, burn_rate=3.0)
        event = _make_event(alert_type="burn_rate", severity=AlertSeverity.WARNING)
        expl = self.engine.explain_alert(event, budget)
        assert "burn" in expl.headline.lower()

    def test_budget_exhaustion_critical(self) -> None:
        budget = _make_budget(consumed_pct=85, burn_rate=5.0)
        event = _make_event(alert_type="budget_exhaustion", severity=AlertSeverity.CRITICAL)
        expl = self.engine.explain_alert(event, budget)
        assert "exhaustion" in expl.headline.lower()

    def test_fallback_on_unknown_type(self) -> None:
        budget = _make_budget(consumed_pct=50)
        event = _make_event(alert_type="unknown_type")
        # Should fall back to explain_budget
        expl = self.engine.explain_alert(event, budget)
        assert expl.headline  # Should not crash

    def test_tier_and_service_type_propagated(self) -> None:
        budget = _make_budget(consumed_pct=80)
        event = _make_event()
        expl = self.engine.explain_alert(event, budget, tier="critical", service_type="worker")
        action_texts = [a.action.lower() for a in expl.recommended_actions]
        assert any("freeze" in t or "halt" in t for t in action_texts)
        assert any("queue" in c.lower() for c in expl.causes)


# -------------------------------------------------------------------------
# AlertEvaluator.evaluate_budget_exhaustion
# -------------------------------------------------------------------------


class TestEvaluateBudgetExhaustion:
    def test_fires_when_exhaustion_imminent(self) -> None:
        from nthlayer.slos.alerts import AlertEvaluator, AlertRule

        budget = _make_budget(consumed_pct=90, burn_rate=5.0, total=1000)
        rule = AlertRule(
            id="exhaustion-1",
            service="payment-api",
            slo_id="availability",
            alert_type=AlertType.BUDGET_EXHAUSTION,
            severity=AlertSeverity.CRITICAL,
            threshold=12.0,  # hours
        )
        evaluator = AlertEvaluator()
        event = evaluator.evaluate_budget_exhaustion(budget, rule)
        assert event is not None
        assert event.severity == AlertSeverity.CRITICAL

    def test_does_not_fire_when_burn_rate_low(self) -> None:
        from nthlayer.slos.alerts import AlertEvaluator, AlertRule

        budget = _make_budget(consumed_pct=50, burn_rate=0.5, total=1000)
        rule = AlertRule(
            id="exhaustion-1",
            service="payment-api",
            slo_id="availability",
            alert_type=AlertType.BUDGET_EXHAUSTION,
            severity=AlertSeverity.CRITICAL,
            threshold=12.0,
        )
        evaluator = AlertEvaluator()
        event = evaluator.evaluate_budget_exhaustion(budget, rule)
        assert event is None

    def test_evaluate_rules_dispatches_exhaustion(self) -> None:
        from nthlayer.slos.alerts import AlertEvaluator, AlertRule

        budget = _make_budget(consumed_pct=90, burn_rate=5.0, total=1000)
        rule = AlertRule(
            id="exhaustion-1",
            service="payment-api",
            slo_id="availability",
            alert_type=AlertType.BUDGET_EXHAUSTION,
            severity=AlertSeverity.CRITICAL,
            threshold=12.0,
        )
        evaluator = AlertEvaluator()
        events = evaluator.evaluate_rules(budget, [rule])
        assert len(events) >= 1
