"""Tests for the alert pipeline orchestration."""

from __future__ import annotations

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
        # ExplanationEngine removed in Phase 1 migration — explanations always []
        assert result.explanations == []

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
        # ExplanationEngine removed in Phase 1 migration — explanations always []
        assert result.explanations == []

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


# TestNotificationPayload, TestSlackNotifierHTTP, and the enabled-dispatch
# test in TestPipelineDispatchNotifications were removed: they tested
# ExplanationEngine, SlackNotifier, and notification dispatch, all of which
# were deleted from generate in Phase 1 (moved to nthlayer-respond).
# Restoration tracked in nthlayer-observe bead nthlayer-hmj.


class TestPipelineDispatchNotifications:
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


# -------------------------------------------------------------------------
# ForDuration wiring through alert generation pipeline
# -------------------------------------------------------------------------


class TestForDurationPipeline:
    def test_for_duration_applied_through_pipeline(self) -> None:
        """for_duration from alerting config flows through the pipeline to generated alerts."""
        from unittest.mock import MagicMock, patch

        from nthlayer.alerts.models import AlertRule
        from nthlayer.generators.alerts import _load_and_customize_alerts
        from nthlayer.specs.alerting import AlertingConfig, ForDuration

        # Create mock alerts that would come from templates
        mock_alerts = [
            AlertRule(name="TestCritical", expr="up == 0", duration="5m", severity="critical", technology="test"),
            AlertRule(name="TestWarning", expr="up == 0", duration="5m", severity="warning", technology="test"),
        ]

        mock_loader = MagicMock()
        mock_loader.load_technology.return_value = mock_alerts

        config = AlertingConfig(
            for_duration=ForDuration(page="1m", ticket="20m"),
        )

        with patch("nthlayer.generators.alerts.AlertTemplateLoader", return_value=mock_loader):
            result = _load_and_customize_alerts(
                service_name="test-svc",
                team="eng",
                tier="critical",
                dependencies=["test"],
                quiet=True,
                alerting_config=config,
            )

        assert len(result) == 2
        critical_alert = next(a for a in result if a.name == "TestCritical")
        warning_alert = next(a for a in result if a.name == "TestWarning")
        assert critical_alert.duration == "1m"
        assert warning_alert.duration == "20m"

    def test_no_alerting_config_keeps_original_duration(self) -> None:
        """Without alerting config, original template durations are preserved."""
        from unittest.mock import MagicMock, patch

        from nthlayer.alerts.models import AlertRule
        from nthlayer.generators.alerts import _load_and_customize_alerts

        mock_alerts = [
            AlertRule(name="TestAlert", expr="up == 0", duration="5m", severity="critical", technology="test"),
        ]

        mock_loader = MagicMock()
        mock_loader.load_technology.return_value = mock_alerts

        with patch("nthlayer.generators.alerts.AlertTemplateLoader", return_value=mock_loader):
            result = _load_and_customize_alerts(
                service_name="test-svc",
                team="eng",
                tier="critical",
                dependencies=["test"],
                quiet=True,
                alerting_config=None,
            )

        assert len(result) == 1
        assert result[0].duration == "5m"
