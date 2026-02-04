"""Tests for the alert pipeline orchestration."""

from __future__ import annotations

import respx
from nthlayer.slos.alerts import AlertEvent, AlertSeverity, AlertType
from nthlayer.slos.pipeline import (
    AlertPipeline,
    PipelineResult,
    _build_slo_from_manifest,
    _convert_spec_rule_to_alert_rule,
)
from nthlayer.specs.alerting import AlertChannels, AlertingConfig, SpecAlertRule
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition


def _make_manifest(
    name: str = "payment-api",
    tier: str = "critical",
    service_type: str = "api",
    slos: list[SLODefinition] | None = None,
    alerting: AlertingConfig | None = None,
) -> ReliabilityManifest:
    if slos is None:
        slos = [
            SLODefinition(name="availability", target=99.9, window="30d"),
        ]
    return ReliabilityManifest(
        name=name,
        team="payments",
        tier=tier,
        type=service_type,
        slos=slos,
        alerting=alerting,
    )


# -------------------------------------------------------------------------
# PipelineResult
# -------------------------------------------------------------------------


class TestPipelineResult:
    def test_to_dict(self) -> None:
        pr = PipelineResult(service="test-svc")
        d = pr.to_dict()
        assert d["service"] == "test-svc"
        assert d["budgets_evaluated"] == 0
        assert d["errors"] == []

    def test_worst_severity_healthy(self) -> None:
        pr = PipelineResult(service="x")
        assert pr.worst_severity == "healthy"

    def test_worst_severity_critical(self) -> None:
        from nthlayer.slos.alerts import AlertEvent

        pr = PipelineResult(
            service="x",
            events=[
                AlertEvent(
                    id="e1",
                    rule_id="r1",
                    service="x",
                    slo_id="s1",
                    severity=AlertSeverity.WARNING,
                    title="t",
                    message="m",
                    details={},
                ),
                AlertEvent(
                    id="e2",
                    rule_id="r2",
                    service="x",
                    slo_id="s1",
                    severity=AlertSeverity.CRITICAL,
                    title="t",
                    message="m",
                    details={},
                ),
            ],
        )
        assert pr.worst_severity == "critical"


# -------------------------------------------------------------------------
# _build_slo_from_manifest
# -------------------------------------------------------------------------


class TestBuildSloFromManifest:
    def test_builds_slo_with_percentage_target(self) -> None:
        manifest = _make_manifest()
        slo = _build_slo_from_manifest(manifest, manifest.slos[0])
        assert slo.service == "payment-api"
        assert slo.name == "availability"
        # 99.9 -> 0.999
        assert abs(slo.target - 0.999) < 0.001

    def test_builds_slo_with_fractional_target(self) -> None:
        manifest = _make_manifest(slos=[SLODefinition(name="avail", target=0.999, window="7d")])
        slo = _build_slo_from_manifest(manifest, manifest.slos[0])
        assert abs(slo.target - 0.999) < 0.001


# -------------------------------------------------------------------------
# _convert_spec_rule_to_alert_rule
# -------------------------------------------------------------------------


class TestConvertSpecRule:
    def test_budget_threshold_conversion(self) -> None:
        spec_rule = SpecAlertRule(
            name="budget-warn",
            type="budget_threshold",
            slo="availability",
            threshold=0.75,
            severity="warning",
        )
        channels = AlertChannels(slack_webhook="https://hooks.slack.com/x")
        rule = _convert_spec_rule_to_alert_rule(spec_rule, "payment-api", "availability", channels)
        assert rule.alert_type == AlertType.BUDGET_THRESHOLD
        assert rule.severity == AlertSeverity.WARNING
        assert rule.threshold == 0.75
        assert rule.slack_webhook == "https://hooks.slack.com/x"

    def test_burn_rate_conversion(self) -> None:
        spec_rule = SpecAlertRule(
            name="burn", type="burn_rate", slo="avail", threshold=3.0, severity="critical"
        )
        rule = _convert_spec_rule_to_alert_rule(spec_rule, "svc", "avail", AlertChannels())
        assert rule.alert_type == AlertType.BURN_RATE
        assert rule.severity == AlertSeverity.CRITICAL

    def test_exhaustion_conversion(self) -> None:
        spec_rule = SpecAlertRule(
            name="exhaust", type="budget_exhaustion", slo="avail", threshold=12.0
        )
        rule = _convert_spec_rule_to_alert_rule(spec_rule, "svc", "avail", AlertChannels())
        assert rule.alert_type == AlertType.BUDGET_EXHAUSTION


# -------------------------------------------------------------------------
# AlertPipeline.evaluate_service
# -------------------------------------------------------------------------


class TestAlertPipelineEvaluateService:
    def test_dry_run_produces_events_no_notifications(self) -> None:
        alerting = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="budget-warn",
                    type="budget_threshold",
                    slo="availability",
                    threshold=0.50,
                    severity="warning",
                )
            ],
            auto_rules=False,
        )
        manifest = _make_manifest(alerting=alerting)
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=80)

        assert result.budgets_evaluated == 1
        assert result.alerts_triggered >= 1
        assert result.notifications_sent == 0
        assert len(result.explanations) >= 1

    def test_no_slos_returns_error(self) -> None:
        manifest = _make_manifest(slos=[])
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest)
        assert len(result.errors) == 1
        assert "No SLOs" in result.errors[0]

    def test_auto_rules_generate_alerts_for_critical_tier(self) -> None:
        manifest = _make_manifest(
            tier="critical",
            alerting=AlertingConfig(auto_rules=True, rules=[]),
        )
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=90)
        # Critical tier + 90% burn should trigger auto-generated budget-critical
        assert result.alerts_triggered >= 1

    def test_simulation_with_low_burn_no_alerts(self) -> None:
        alerting = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="budget-warn",
                    type="budget_threshold",
                    slo="availability",
                    threshold=0.75,
                    severity="warning",
                )
            ],
            auto_rules=False,
        )
        manifest = _make_manifest(alerting=alerting)
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=10)
        assert result.alerts_triggered == 0
        # Should still have a budget explanation
        assert len(result.explanations) == 1

    def test_multiple_slos_evaluated(self) -> None:
        slos = [
            SLODefinition(name="availability", target=99.9, window="30d"),
            SLODefinition(name="latency", target=99.0, window="30d"),
        ]
        alerting = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="budget-warn",
                    type="budget_threshold",
                    slo="*",
                    threshold=0.50,
                    severity="warning",
                )
            ],
            auto_rules=False,
        )
        manifest = _make_manifest(slos=slos, alerting=alerting)
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=80)
        assert result.budgets_evaluated == 2

    def test_result_to_dict_serializes(self) -> None:
        manifest = _make_manifest()
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=60)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["service"] == "payment-api"


# -------------------------------------------------------------------------
# AlertPipeline.evaluate_portfolio
# -------------------------------------------------------------------------


class TestAlertPipelinePortfolio:
    def test_evaluates_multiple_services(self) -> None:
        manifests = [
            _make_manifest(name="svc-a"),
            _make_manifest(name="svc-b", tier="standard"),
        ]
        pipeline = AlertPipeline(dry_run=True)
        results = pipeline.evaluate_portfolio(manifests, simulate_burn_pct=60)
        assert len(results) == 2
        assert results[0].service == "svc-a"
        assert results[1].service == "svc-b"

    def test_error_in_one_service_does_not_block_others(self) -> None:
        good = _make_manifest(name="good-svc")
        # Bad manifest will fail validation
        bad = _make_manifest(name="bad-svc", slos=[])
        pipeline = AlertPipeline(dry_run=True)
        results = pipeline.evaluate_portfolio([good, bad], simulate_burn_pct=50)
        assert len(results) == 2
        # bad-svc should have errors but not crash
        bad_result = next(r for r in results if r.service == "bad-svc")
        assert len(bad_result.errors) >= 1


# -------------------------------------------------------------------------
# Notification payloads
# -------------------------------------------------------------------------


class TestNotificationPayload:
    def test_slack_format_explanation_blocks(self) -> None:
        from nthlayer.slos.explanations import BudgetExplanation, RecommendedAction
        from nthlayer.slos.notifiers import _format_explanation_blocks

        expl = BudgetExplanation(
            headline="H",
            body="B",
            causes=["Cause A"],
            recommended_actions=[RecommendedAction("Act 1", 1, "investigate")],
        )
        blocks = _format_explanation_blocks(expl)
        assert len(blocks) == 2  # causes + actions
        assert "Possible Causes" in blocks[0]["text"]["text"]
        assert "Recommended Actions" in blocks[1]["text"]["text"]

    def test_slack_message_includes_explanation_when_provided(self) -> None:
        from nthlayer.slos.explanations import BudgetExplanation, RecommendedAction
        from nthlayer.slos.notifiers import SlackNotifier

        notifier = SlackNotifier("https://hooks.slack.com/test")
        event = AlertEvent(
            id="e1",
            rule_id="r1",
            service="svc",
            slo_id="avail",
            severity=AlertSeverity.WARNING,
            title="Test",
            message="msg",
            details={},
        )
        expl = BudgetExplanation(
            headline="H",
            body="B",
            causes=["Root cause"],
            recommended_actions=[RecommendedAction("Fix it", 1, "mitigate")],
        )
        payload = notifier._format_slack_message(event, explanation=expl)
        block_texts = [
            b.get("text", {}).get("text", "") for b in payload["blocks"] if b["type"] == "section"
        ]
        combined = " ".join(block_texts)
        assert "Root cause" in combined
        assert "Fix it" in combined

    def test_slack_message_without_explanation(self) -> None:
        from nthlayer.slos.notifiers import SlackNotifier

        notifier = SlackNotifier("https://hooks.slack.com/test")
        event = AlertEvent(
            id="e1",
            rule_id="r1",
            service="svc",
            slo_id="avail",
            severity=AlertSeverity.CRITICAL,
            title="Crit",
            message="msg",
            details={},
        )
        payload = notifier._format_slack_message(event)
        # Should still produce valid blocks without crashing
        assert payload["text"] == "Crit"
        assert payload["attachments"][0]["color"] == "#ff0000"
        # No explanation blocks — only header, message, context
        section_blocks = [b for b in payload["blocks"] if b["type"] == "section"]
        assert len(section_blocks) == 1  # just the message


# -------------------------------------------------------------------------
# Slack HTTP dispatch (mocked)
# -------------------------------------------------------------------------


class TestSlackNotifierHTTP:
    @respx.mock
    async def test_send_alert_posts_to_webhook(self) -> None:
        import httpx
        from nthlayer.slos.notifiers import SlackNotifier

        webhook = "https://hooks.slack.com/services/T/B/X"
        mock_route = respx.post(webhook).mock(return_value=httpx.Response(200, text="ok"))

        notifier = SlackNotifier(webhook)
        event = AlertEvent(
            id="e1",
            rule_id="r1",
            service="svc",
            slo_id="avail",
            severity=AlertSeverity.WARNING,
            title="Warn",
            message="msg",
            details={},
        )
        result = await notifier.send_alert(event)
        assert result["status"] == "sent"
        assert mock_route.called

    @respx.mock
    async def test_send_alert_with_explanation(self) -> None:
        import httpx
        from nthlayer.slos.explanations import BudgetExplanation, RecommendedAction
        from nthlayer.slos.notifiers import SlackNotifier

        webhook = "https://hooks.slack.com/services/T/B/Y"
        captured_payload: dict = {}

        def capture(request: httpx.Request) -> httpx.Response:
            import json as _json

            captured_payload.update(_json.loads(request.content))
            return httpx.Response(200, text="ok")

        respx.post(webhook).mock(side_effect=capture)

        notifier = SlackNotifier(webhook)
        event = AlertEvent(
            id="e2",
            rule_id="r1",
            service="svc",
            slo_id="avail",
            severity=AlertSeverity.CRITICAL,
            title="Critical",
            message="msg",
            details={},
        )
        expl = BudgetExplanation(
            headline="H",
            body="B",
            causes=["Bad deploy"],
            recommended_actions=[RecommendedAction("Rollback", 1, "mitigate")],
        )
        result = await notifier.send_alert(event, explanation=expl)
        assert result["status"] == "sent"
        # Verify explanation content made it into the payload
        all_text = str(captured_payload)
        assert "Bad deploy" in all_text
        assert "Rollback" in all_text

    @respx.mock
    async def test_send_alert_raises_on_http_error(self) -> None:
        import httpx
        import pytest as _pytest
        from nthlayer.slos.notifiers import NotificationError, SlackNotifier

        webhook = "https://hooks.slack.com/services/T/B/Z"
        respx.post(webhook).mock(return_value=httpx.Response(500, text="error"))

        notifier = SlackNotifier(webhook)
        event = AlertEvent(
            id="e3",
            rule_id="r1",
            service="svc",
            slo_id="avail",
            severity=AlertSeverity.WARNING,
            title="Warn",
            message="msg",
            details={},
        )
        with _pytest.raises(NotificationError):
            await notifier.send_alert(event)


# -------------------------------------------------------------------------
# Pipeline dispatch integration (mocked Slack)
# -------------------------------------------------------------------------


class TestPipelineDispatchNotifications:
    @respx.mock
    def test_pipeline_sends_notifications_when_enabled(self) -> None:
        """Pipeline dispatch with mocked Slack webhook.

        ``_dispatch_notifications`` calls ``asyncio.run()``, which works
        when there is no running loop (i.e. inside a sync test).
        """
        import httpx

        webhook = "https://hooks.slack.com/services/T/B/PIPE"
        call_count_holder = [0]

        def count_calls(request: httpx.Request) -> httpx.Response:
            call_count_holder[0] += 1
            return httpx.Response(200, text="ok")

        respx.post(webhook).mock(side_effect=count_calls)

        alerting = AlertingConfig(
            channels=AlertChannels(slack_webhook=webhook),
            rules=[
                SpecAlertRule(
                    name="budget-warn",
                    type="budget_threshold",
                    slo="availability",
                    threshold=0.50,
                    severity="warning",
                ),
            ],
            auto_rules=False,
        )
        manifest = _make_manifest(alerting=alerting)
        pipeline = AlertPipeline(dry_run=False, notify=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=80)
        assert result.alerts_triggered >= 1
        assert result.notifications_sent >= 1
        assert call_count_holder[0] >= 1

    def test_dry_run_sends_zero_notifications(self) -> None:
        alerting = AlertingConfig(
            channels=AlertChannels(slack_webhook="https://hooks.slack.com/x"),
            rules=[
                SpecAlertRule(
                    name="budget-warn",
                    type="budget_threshold",
                    slo="availability",
                    threshold=0.50,
                    severity="warning",
                ),
            ],
            auto_rules=False,
        )
        manifest = _make_manifest(alerting=alerting)
        pipeline = AlertPipeline(dry_run=True)
        result = pipeline.evaluate_service(manifest, simulate_burn_pct=80)
        assert result.alerts_triggered >= 1
        assert result.notifications_sent == 0
