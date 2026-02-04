"""Tests for the alerts CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
import yaml
from nthlayer.cli.alerts import (
    alerts_evaluate_command,
    alerts_explain_command,
    alerts_show_command,
    alerts_test_command,
    handle_alerts_command,
)


def _write_opensrm_manifest(
    dir_path: Path,
    name: str = "test-svc",
    tier: str = "critical",
    with_alerting: bool = True,
) -> str:
    data = {
        "apiVersion": "srm/v1",
        "kind": "ServiceReliabilityManifest",
        "metadata": {"name": name, "team": "eng", "tier": tier},
        "spec": {
            "type": "api",
            "slos": {
                "availability": {"target": 99.9, "window": "30d"},
            },
        },
    }
    if with_alerting:
        data["spec"]["alerting"] = {
            "channels": {"slack_webhook": None},
            "rules": [
                {
                    "name": "budget-warning",
                    "type": "budget_threshold",
                    "slo": "availability",
                    "threshold": 0.75,
                    "severity": "warning",
                },
                {
                    "name": "budget-critical",
                    "type": "budget_threshold",
                    "slo": "availability",
                    "threshold": 0.90,
                    "severity": "critical",
                },
            ],
            "auto_rules": False,
        }

    file_path = dir_path / f"{name}.yaml"
    file_path.write_text(yaml.dump(data, default_flow_style=False))
    return str(file_path)


# -------------------------------------------------------------------------
# alerts show
# -------------------------------------------------------------------------


class TestAlertsShow:
    def test_show_table_format(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_show_command(f, output_format="table")
        assert code == 0

    def test_show_json_format(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_show_command(f, output_format="json")
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 2  # budget-warning + budget-critical

    def test_show_yaml_format(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_show_command(f, output_format="yaml")
        assert code == 0
        out = capsys.readouterr().out
        data = yaml.safe_load(out)
        assert isinstance(data, list)

    def test_show_with_auto_rules(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "slos": {"availability": {"target": 99.9, "window": "30d"}},
                "alerting": {"auto_rules": True, "rules": []},
            },
        }
        fp = tmp_path / "svc.yaml"
        fp.write_text(yaml.dump(data, default_flow_style=False))
        code = alerts_show_command(str(fp), output_format="json")
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        # Critical tier has 4 auto-rules
        assert len(out) == 4


# -------------------------------------------------------------------------
# alerts evaluate
# -------------------------------------------------------------------------


class TestAlertsEvaluate:
    def test_evaluate_dry_run_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        alerts_evaluate_command(f, dry_run=True, output_format="json")
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, list)
        assert len(out) == 1
        assert out[0]["service"] == "test-svc"

    def test_evaluate_table_format(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_evaluate_command(f, dry_run=True, output_format="table")
        assert code in (0, 1, 2)

    def test_evaluate_directory(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        _write_opensrm_manifest(tmp_path, name="svc-a")
        _write_opensrm_manifest(tmp_path, name="svc-b", tier="standard")
        alerts_evaluate_command(
            service_file="",
            dry_run=True,
            output_format="json",
            path=str(tmp_path),
        )
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 2

    def test_evaluate_not_a_directory(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        code = alerts_evaluate_command(
            service_file="",
            dry_run=True,
            output_format="json",
            path=str(tmp_path / "nonexistent"),
        )
        # Empty results → exit 0
        assert code == 0

    def test_evaluate_directory_with_bad_file(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        _write_opensrm_manifest(tmp_path, name="good-svc")
        # Write an invalid YAML that will cause a parse error
        bad_file = tmp_path / "bad-svc.yaml"
        bad_file.write_text("apiVersion: srm/v1\nkind: ServiceReliabilityManifest\n")
        code = alerts_evaluate_command(
            service_file="",
            dry_run=True,
            output_format="table",
            path=str(tmp_path),
        )
        assert code in (0, 1, 2)

    def test_evaluate_table_shows_errors(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Evaluate table output renders error rows."""
        _write_opensrm_manifest(tmp_path, name="ok-svc")
        _write_opensrm_manifest(tmp_path, name="err-svc", with_alerting=False)
        alerts_evaluate_command(
            service_file="",
            dry_run=True,
            output_format="table",
            path=str(tmp_path),
        )
        # Just verify it doesn't crash — error display path exercised
        out = capsys.readouterr().out
        assert "ok-svc" in out or "err-svc" in out


# -------------------------------------------------------------------------
# alerts explain
# -------------------------------------------------------------------------


class TestAlertsExplain:
    def test_explain_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        alerts_explain_command(f, output_format="json")
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, list)
        assert len(out) >= 1
        assert "headline" in out[0]

    def test_explain_markdown(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        alerts_explain_command(f, output_format="markdown")
        out = capsys.readouterr().out
        assert "##" in out  # Markdown headline

    def test_explain_text(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        f = _write_opensrm_manifest(tmp_path)
        alerts_explain_command(f, output_format="table")
        out = capsys.readouterr().out
        assert "budget" in out.lower()

    def test_explain_slo_filter_match(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_explain_command(f, output_format="json", slo_filter="availability")
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, list)
        assert len(out) >= 1
        assert code in (0, 1, 2)

    def test_explain_slo_filter_no_match(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_explain_command(f, slo_filter="nonexistent")
        assert code == 1


# -------------------------------------------------------------------------
# alerts test
# -------------------------------------------------------------------------


class TestAlertsTest:
    def test_simulate_high_burn_triggers_alerts(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=95)
        # Should trigger both warning (0.75) and critical (0.90)
        assert code == 2  # critical

    def test_simulate_low_burn_no_alerts(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=10)
        assert code == 0

    def test_simulate_moderate_burn_warning(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=80)
        # Should trigger warning (0.75) but not critical (0.90)
        assert code == 1

    @respx.mock
    def test_simulate_with_notifications(self, tmp_path: Path) -> None:
        """Verify 'Notifications sent' output when webhook is configured."""
        import httpx

        webhook = "https://hooks.slack.com/services/T/B/TEST"
        respx.post(webhook).mock(return_value=httpx.Response(200, text="ok"))

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "slos": {"availability": {"target": 99.9, "window": "30d"}},
                "alerting": {
                    "channels": {"slack_webhook": webhook},
                    "rules": [
                        {
                            "name": "warn",
                            "type": "budget_threshold",
                            "slo": "availability",
                            "threshold": 0.50,
                            "severity": "warning",
                        },
                    ],
                    "auto_rules": False,
                },
            },
        }
        fp = tmp_path / "svc.yaml"
        fp.write_text(yaml.dump(data, default_flow_style=False))
        code = alerts_test_command(str(fp), simulate_burn=80)
        assert code == 1


# -------------------------------------------------------------------------
# handle_alerts_command routing
# -------------------------------------------------------------------------


class TestHandleAlertsCommand:
    def test_routes_to_show(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        args = _make_namespace(alerts_command="show", service_file=f, format="table")
        code = handle_alerts_command(args)
        assert code == 0

    def test_routes_to_evaluate(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        args = _make_namespace(
            alerts_command="evaluate",
            service_file=f,
            format="table",
            dry_run=True,
            no_notify=True,
            prometheus_url=None,
            path=None,
        )
        code = handle_alerts_command(args)
        assert code in (0, 1, 2)

    def test_routes_to_test(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        args = _make_namespace(
            alerts_command="test",
            service_file=f,
            simulate_burn=85.0,
            prometheus_url=None,
        )
        code = handle_alerts_command(args)
        assert code in (0, 1, 2)

    def test_no_subcommand_returns_1(self) -> None:
        args = _make_namespace(alerts_command=None)
        code = handle_alerts_command(args)
        assert code == 1


# -------------------------------------------------------------------------
# Exit code semantics
# -------------------------------------------------------------------------


class TestExitCodes:
    def test_healthy_exit_0(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=10)
        assert code == 0

    def test_warning_exit_1(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=80)
        assert code == 1

    def test_critical_exit_2(self, tmp_path: Path) -> None:
        f = _write_opensrm_manifest(tmp_path)
        code = alerts_test_command(f, simulate_burn=95)
        assert code == 2


# -------------------------------------------------------------------------
# Integration with argparse via demo.build_parser
# -------------------------------------------------------------------------


class TestArgparsing:
    def test_alerts_subcommand_registered(self) -> None:
        from nthlayer.demo import build_parser

        parser = build_parser()
        # Should not raise
        args = parser.parse_args(["alerts", "show", "some-file.yaml"])
        assert args.command == "alerts"
        assert args.alerts_command == "show"
        assert args.service_file == "some-file.yaml"

    def test_alerts_test_subcommand(self) -> None:
        from nthlayer.demo import build_parser

        parser = build_parser()
        args = parser.parse_args(["alerts", "test", "svc.yaml", "--simulate-burn", "90"])
        assert args.alerts_command == "test"
        assert args.simulate_burn == 90.0


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _make_namespace(**kwargs) -> object:
    """Create a simple namespace object with given attributes."""
    import argparse

    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns
