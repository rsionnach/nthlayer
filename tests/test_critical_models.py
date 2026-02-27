"""Tests for critical model files: formatters/models, verification/models, alerts/models."""

from nthlayer.alerts.models import AlertRule
from nthlayer.cli.formatters.models import CheckResult, CheckStatus, ReliabilityReport
from nthlayer.verification.models import (
    ContractVerificationResult,
    DeclaredMetric,
    MetricSource,
    VerificationResult,
)


class TestReliabilityReportStatus:
    """Tests for ReliabilityReport.status aggregation (FAIL > WARN > PASS)."""

    def test_all_pass_returns_pass(self):
        report = ReliabilityReport(
            service="test",
            command="check",
            checks=[
                CheckResult("a", CheckStatus.PASS, "ok"),
                CheckResult("b", CheckStatus.PASS, "ok"),
            ],
        )
        assert report.status == CheckStatus.PASS

    def test_warn_present_returns_warn(self):
        report = ReliabilityReport(
            service="test",
            command="check",
            checks=[
                CheckResult("a", CheckStatus.PASS, "ok"),
                CheckResult("b", CheckStatus.WARN, "slow"),
            ],
        )
        assert report.status == CheckStatus.WARN

    def test_fail_overrides_warn(self):
        report = ReliabilityReport(
            service="test",
            command="check",
            checks=[
                CheckResult("a", CheckStatus.FAIL, "broken"),
                CheckResult("b", CheckStatus.WARN, "slow"),
                CheckResult("c", CheckStatus.PASS, "ok"),
            ],
        )
        assert report.status == CheckStatus.FAIL

    def test_empty_checks_returns_pass(self):
        report = ReliabilityReport(service="test", command="check")
        assert report.status == CheckStatus.PASS

    def test_counts(self):
        report = ReliabilityReport(
            service="test",
            command="check",
            checks=[
                CheckResult("a", CheckStatus.FAIL, "broken"),
                CheckResult("b", CheckStatus.WARN, "slow"),
                CheckResult("c", CheckStatus.PASS, "ok"),
                CheckResult("d", CheckStatus.PASS, "ok"),
            ],
        )
        assert report.errors == 1
        assert report.warnings == 1
        assert report.passed == 2


class TestContractVerificationExitCode:
    """Tests for ContractVerificationResult.exit_code (CI gate logic)."""

    def _metric(self, name, source=MetricSource.SLO_INDICATOR):
        return DeclaredMetric(name=name, source=source)

    def test_all_verified_exit_0(self):
        result = ContractVerificationResult(
            service_name="test",
            target_url="http://test",
            results=[VerificationResult(metric=self._metric("m1"), exists=True)],
        )
        assert result.exit_code == 0

    def test_missing_critical_exit_2(self):
        result = ContractVerificationResult(
            service_name="test",
            target_url="http://test",
            results=[VerificationResult(metric=self._metric("m1"), exists=False)],
        )
        assert result.exit_code == 2

    def test_missing_optional_exit_1(self):
        result = ContractVerificationResult(
            service_name="test",
            target_url="http://test",
            results=[
                VerificationResult(metric=self._metric("m1"), exists=True),
                VerificationResult(
                    metric=self._metric("m2", MetricSource.OBSERVABILITY), exists=False
                ),
            ],
        )
        assert result.exit_code == 1

    def test_critical_overrides_optional(self):
        result = ContractVerificationResult(
            service_name="test",
            target_url="http://test",
            results=[
                VerificationResult(metric=self._metric("m1"), exists=False),
                VerificationResult(
                    metric=self._metric("m2", MetricSource.OBSERVABILITY), exists=False
                ),
            ],
        )
        assert result.exit_code == 2

    def test_critical_verified_property(self):
        result = ContractVerificationResult(
            service_name="test",
            target_url="http://test",
            results=[
                VerificationResult(metric=self._metric("m1"), exists=True),
                VerificationResult(
                    metric=self._metric("m2", MetricSource.OBSERVABILITY), exists=False
                ),
            ],
        )
        assert result.critical_verified is True
        assert result.all_verified is False


class TestAlertRuleModel:
    """Tests for AlertRule model behavior."""

    def test_from_dict(self):
        data = {
            "alert": "PostgresqlDown",
            "expr": "pg_up == 0",
            "for": "0m",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "PG down"},
        }
        alert = AlertRule.from_dict(data, technology="postgres", category="databases")
        assert alert.name == "PostgresqlDown"
        assert alert.severity == "critical"
        assert alert.technology == "postgres"
        assert alert.duration == "0m"

    def test_customize_for_service(self):
        alert = AlertRule(name="TestAlert", expr="up == 0", severity="critical")
        customized = alert.customize_for_service(
            service_name="payment-api",
            team="payments",
            tier="critical",
            routing="sre",
            runbook_url="https://runbook.example.com",
        )
        assert customized.labels["service"] == "payment-api"
        assert customized.labels["team"] == "payments"
        assert customized.labels["routing"] == "sre"
        assert "runbook" in customized.annotations
        # Original should be unmodified
        assert "service" not in alert.labels

    def test_is_critical(self):
        assert AlertRule(name="a", expr="x", severity="critical").is_critical()
        assert not AlertRule(name="a", expr="x", severity="warning").is_critical()

    def test_is_down_alert(self):
        assert AlertRule(name="PostgresqlDown", expr="x").is_down_alert()
        assert AlertRule(name="ServiceUnavailable", expr="x").is_down_alert()
        assert not AlertRule(name="HighLatency", expr="x").is_down_alert()

    def test_to_prometheus(self):
        alert = AlertRule(name="Test", expr="up == 0", duration="5m", severity="critical")
        prom = alert.to_prometheus()
        assert prom["alert"] == "Test"
        assert prom["expr"] == "up == 0"
        assert prom["for"] == "5m"
