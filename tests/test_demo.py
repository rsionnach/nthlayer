"""Tests for demo.py.

Tests for the demo CLI module including helper functions,
demo walkthroughs, and command dispatch.
"""

import argparse
from importlib.metadata import version as get_version
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.alerts.models import AlertRule
from nthlayer.demo import (
    _default_org_id,
    _format_change,
    _plan_and_apply,
    _print_welcome,
    _serialize_plan,
    build_parser,
    build_prometheus_alerts_demo,
    demo_grafana,
    demo_prometheus_alerts,
    demo_reconcile_service,
    demo_reconcile_team,
    list_services,
    list_teams,
    load_demo_data,
    main,
    print_header,
    print_section,
    run_grafana_demo,
)
from nthlayer.providers.grafana import GrafanaProvider, GrafanaProviderError


class TestVersion:
    """Tests for version consistency."""

    def test_version_uses_package_metadata(self):
        """Verify __version__ is read from package metadata, not hardcoded."""
        from nthlayer.demo import __version__

        package_version = get_version("nthlayer")
        assert __version__ == package_version, (
            f"demo.__version__ ({__version__}) does not match package metadata "
            f"({package_version}). Version should be read from importlib.metadata."
        )

    def test_version_format_is_valid(self):
        """Verify version follows PEP 440 format."""
        from nthlayer.demo import __version__

        # Basic check that version contains expected components
        assert __version__, "Version should not be empty"
        # Should start with a digit (e.g., "0.1.0a12")
        assert __version__[0].isdigit(), f"Version should start with digit: {__version__}"


class TestDefaultOrgId:
    """Tests for _default_org_id function."""

    def test_returns_none_when_env_not_set(self, monkeypatch):
        """Returns None when env var is not set."""
        monkeypatch.delenv("NTHLAYER_GRAFANA_ORG_ID", raising=False)
        result = _default_org_id()
        assert result is None

    def test_returns_int_when_valid(self, monkeypatch):
        """Returns integer when env var contains valid int."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_ORG_ID", "42")
        result = _default_org_id()
        assert result == 42

    def test_returns_none_when_invalid(self, monkeypatch):
        """Returns None when env var contains invalid int."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_ORG_ID", "not-a-number")
        result = _default_org_id()
        assert result is None

    def test_handles_empty_string(self, monkeypatch):
        """Returns None when env var is empty string."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_ORG_ID", "")
        result = _default_org_id()
        assert result is None


class TestLoadDemoData:
    """Tests for load_demo_data function."""

    def test_loads_demo_data_successfully(self, tmp_path, monkeypatch):
        """Successfully loads demo data from file."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("services:\n  - id: test-service\nteams:\n  - id: test-team")
        monkeypatch.chdir(tmp_path)

        data = load_demo_data()

        assert "services" in data
        assert data["services"][0]["id"] == "test-service"

    def test_exits_on_file_not_found(self, tmp_path, monkeypatch):
        """Exits with code 1 when demo data file not found."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            load_demo_data()

        assert exc_info.value.code == 1


class TestPrintFunctions:
    """Tests for print_header and print_section functions."""

    def test_print_header(self, capsys):
        """print_header outputs formatted header."""
        print_header("Test Title")
        captured = capsys.readouterr()

        assert "=" * 70 in captured.out
        assert "Test Title" in captured.out

    def test_print_section(self, capsys):
        """print_section outputs formatted section."""
        print_section("Test Section")
        captured = capsys.readouterr()

        assert "--- Test Section ---" in captured.out


class TestFormatChange:
    """Tests for _format_change function."""

    def test_empty_details(self):
        """Returns placeholder for empty details."""
        result = _format_change({})
        assert result == "(no details)"

    def test_formats_single_key(self):
        """Formats single key-value pair."""
        result = _format_change({"key": "value"})
        assert result == "key=value"

    def test_formats_multiple_keys(self):
        """Formats multiple key-value pairs."""
        result = _format_change({"a": 1, "b": 2})
        assert "a=1" in result
        assert "b=2" in result

    def test_none_details(self):
        """Returns placeholder for None details."""
        result = _format_change(None)
        assert result == "(no details)"


class TestSerializePlan:
    """Tests for _serialize_plan function."""

    def test_empty_list(self):
        """Returns empty list for empty input."""
        result = _serialize_plan([])
        assert result == []

    def test_serializes_changes(self):
        """Serializes change objects with action and details."""
        change = MagicMock()
        change.action = "create"
        change.details = {"name": "test"}

        result = _serialize_plan([change])

        assert len(result) == 1
        assert result[0]["action"] == "create"
        assert result[0]["details"] == {"name": "test"}

    def test_handles_missing_attributes(self):
        """Uses defaults when attributes are missing."""
        change = MagicMock(spec=[])

        result = _serialize_plan([change])

        assert result[0]["action"] == "unknown"
        assert result[0]["details"] == {}


class TestPlanAndApply:
    """Tests for _plan_and_apply function."""

    @pytest.mark.asyncio
    async def test_successful_apply(self):
        """Successfully plans and applies changes."""
        resource = MagicMock()
        change = MagicMock()
        change.action = "create"
        change.details = {}
        plan = MagicMock()
        plan.changes = [change]
        resource.plan = AsyncMock(return_value=plan)
        resource.apply = AsyncMock()

        result = await _plan_and_apply(resource, {"key": "value"}, idempotency_key="test-key")

        assert result["applied"] is True
        assert result["error"] is None
        assert len(result["changes"]) == 1

    @pytest.mark.asyncio
    async def test_apply_failure(self):
        """Captures error when apply fails."""
        resource = MagicMock()
        plan = MagicMock()
        plan.changes = []
        resource.plan = AsyncMock(return_value=plan)
        resource.apply = AsyncMock(side_effect=GrafanaProviderError("API error"))

        result = await _plan_and_apply(resource, {}, idempotency_key=None)

        assert result["applied"] is False
        assert "API error" in result["error"]


class TestDemoReconcileTeam:
    """Tests for demo_reconcile_team function."""

    @pytest.mark.asyncio
    async def test_team_not_found(self, tmp_path, monkeypatch, capsys):
        """Handles team not found in demo data."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("teams:\n  - id: other-team\n    name: Other Team")
        monkeypatch.chdir(tmp_path)

        await demo_reconcile_team("nonexistent-team")

        captured = capsys.readouterr()
        assert "not found" in captured.out
        assert "other-team" in captured.out

    @pytest.mark.asyncio
    async def test_successful_reconciliation(self, tmp_path, monkeypatch, capsys):
        """Successfully runs team reconciliation demo."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
teams:
  - id: platform
    name: Platform Team
    slack_channel: '#platform'
    pagerduty_schedule: platform-oncall
    members:
      - email: alice@example.com
        role: manager
      - email: bob@example.com
        role: responder
""")
        monkeypatch.chdir(tmp_path)

        await demo_reconcile_team("platform")

        captured = capsys.readouterr()
        assert "Team Reconciliation Demo" in captured.out
        assert "Reconciliation Complete" in captured.out


class TestDemoReconcileService:
    """Tests for demo_reconcile_service function."""

    @pytest.mark.asyncio
    async def test_service_not_found(self, tmp_path, monkeypatch, capsys):
        """Handles service not found in demo data."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("services:\n  - id: other-service\n    name: Other")
        monkeypatch.chdir(tmp_path)

        await demo_reconcile_service("nonexistent-service")

        captured = capsys.readouterr()
        assert "not found" in captured.out
        assert "other-service" in captured.out

    @pytest.mark.asyncio
    async def test_successful_reconciliation(self, tmp_path, monkeypatch, capsys):
        """Successfully runs service reconciliation demo."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
services:
  - id: search-api
    name: Search API
    tier: 1
    team: platform
    description: Search service
teams:
  - id: platform
    name: Platform
    slack_channel: '#platform'
    pagerduty_schedule: oncall
    members:
      - email: alice@example.com
      - email: bob@example.com
alert_templates:
  tier_1:
    - name: HighLatency
      query: latency > 500
""")
        monkeypatch.chdir(tmp_path)

        await demo_reconcile_service("search-api")

        captured = capsys.readouterr()
        assert "Service Reconciliation Demo" in captured.out
        assert "Service Operationalized" in captured.out


class TestListServices:
    """Tests for list_services function."""

    def test_lists_services(self, tmp_path, monkeypatch, capsys):
        """Lists available demo services."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
services:
  - id: service-a
    name: Service A
    tier: 1
    team: team-a
    description: First service
  - id: service-b
    name: Service B
    tier: 2
    team: team-b
    description: Second service
""")
        monkeypatch.chdir(tmp_path)

        list_services()

        captured = capsys.readouterr()
        assert "Available Demo Services" in captured.out
        assert "service-a" in captured.out
        assert "service-b" in captured.out


class TestListTeams:
    """Tests for list_teams function."""

    def test_lists_teams(self, tmp_path, monkeypatch, capsys):
        """Lists available demo teams."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
teams:
  - id: team-a
    name: Team A
    slack_channel: '#team-a'
    pagerduty_schedule: team-a-oncall
    members:
      - email: a@example.com
      - email: b@example.com
""")
        monkeypatch.chdir(tmp_path)

        list_teams()

        captured = capsys.readouterr()
        assert "Available Demo Teams" in captured.out
        assert "team-a" in captured.out
        assert "Members: 2" in captured.out


class TestDemoPrometheusAlerts:
    """Tests for demo_prometheus_alerts function."""

    def test_no_alerts_found(self, monkeypatch, capsys):
        """Handles no alerts found for technology."""

        class StubLoader:
            def load_technology(self, tech):
                return []

        monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

        demo_prometheus_alerts("unknown-tech", limit=5)

        captured = capsys.readouterr()
        assert "No alert templates found" in captured.out

    def test_displays_alerts(self, monkeypatch, capsys):
        """Displays alerts for technology."""
        samples = [
            AlertRule(name="Alert1", expr="up == 0", severity="critical"),
            AlertRule(name="Alert2", expr="up == 1", severity="warning"),
        ]

        class StubLoader:
            def load_technology(self, tech):
                return samples

        monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

        demo_prometheus_alerts("postgres", limit=5)

        captured = capsys.readouterr()
        assert "Alert 1:" in captured.out
        assert "Alert1" in captured.out
        assert "Displayed 2 alert(s)" in captured.out


class TestBuildPrometheusAlertsDemo:
    """Tests for build_prometheus_alerts_demo function."""

    def test_uses_limit(self, monkeypatch):
        """Respects limit parameter."""
        samples = [
            AlertRule(name="A", expr="up == 0"),
            AlertRule(name="B", expr="up == 1"),
        ]

        class StubLoader:
            def __init__(self):
                self.calls = 0

            def load_technology(self, technology: str):
                self.calls += 1
                return samples

        monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

        result = build_prometheus_alerts_demo("postgres", limit=1)

        assert len(result) == 1
        assert result[0]["name"] == "A"
        assert result[0]["prometheus"]["alert"] == "A"

    def test_filters_non_alert_rules(self, monkeypatch):
        """Filters out non-AlertRule objects."""

        class StubLoader:
            def load_technology(self, tech):
                return [
                    AlertRule(name="Valid", expr="up == 0"),
                    {"not": "an alert rule"},
                    "string",
                ]

        monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

        result = build_prometheus_alerts_demo("postgres", limit=0)

        assert len(result) == 1
        assert result[0]["name"] == "Valid"


class TestDemoGrafana:
    """Tests for demo_grafana function."""

    @pytest.mark.asyncio
    async def test_outputs_info(self, capsys, monkeypatch):
        """Outputs connection info and results."""

        async def fake_demo(provider):
            return {
                "folder": {"changes": [], "applied": True, "error": None},
                "dashboard": {"changes": [], "applied": True, "error": None},
                "datasource": {"changes": [], "applied": True, "error": None},
            }

        monkeypatch.setattr("nthlayer.demo.run_grafana_demo", fake_demo)

        await demo_grafana("http://grafana:3000", "token123", org_id=1, timeout=10.0)

        captured = capsys.readouterr()
        assert "Grafana Provider Demo" in captured.out
        assert "http://grafana:3000" in captured.out
        assert "Org ID: 1" in captured.out
        assert "Bearer token provided" in captured.out

    @pytest.mark.asyncio
    async def test_no_token(self, capsys, monkeypatch):
        """Shows no auth when token not provided."""

        async def fake_demo(provider):
            return {
                "folder": {"changes": [], "applied": True, "error": None},
                "dashboard": {"changes": [], "applied": True, "error": None},
                "datasource": {"changes": [], "applied": True, "error": None},
            }

        monkeypatch.setattr("nthlayer.demo.run_grafana_demo", fake_demo)

        await demo_grafana("http://grafana:3000", None, org_id=None, timeout=10.0)

        captured = capsys.readouterr()
        assert "(none provided)" in captured.out

    @pytest.mark.asyncio
    async def test_displays_changes(self, capsys, monkeypatch):
        """Displays detected changes."""

        async def fake_demo(provider):
            return {
                "folder": {
                    "changes": [{"action": "create", "details": {"title": "Demo"}}],
                    "applied": True,
                    "error": None,
                },
                "dashboard": {"changes": [], "applied": True, "error": None},
                "datasource": {"changes": [], "applied": False, "error": "API error"},
            }

        monkeypatch.setattr("nthlayer.demo.run_grafana_demo", fake_demo)

        await demo_grafana("http://grafana:3000", "token", org_id=None, timeout=10.0)

        captured = capsys.readouterr()
        assert "CREATE:" in captured.out
        assert "Apply succeeded" in captured.out
        assert "Apply failed" in captured.out
        assert "No changes required" in captured.out


class TestRunGrafanaDemo:
    """Tests for run_grafana_demo function."""

    @pytest.mark.asyncio
    async def test_returns_changes(self, monkeypatch):
        """Returns change results for each resource."""
        provider = GrafanaProvider("https://grafana.example.com", "token", org_id=1)

        async def fake_request(self, method, path, **kwargs):
            if method == "GET" and path == "/api/folders/uid/nthlayer-demo":
                return {"title": "Legacy"}
            if method == "PUT" and path == "/api/folders/nthlayer-demo":
                return {}
            if method == "GET" and path == "/api/dashboards/uid/nthlayer-demo-dashboard":
                return {"dashboard": {"title": "Old"}, "meta": {"folderUid": "legacy"}}
            if method == "POST" and path == "/api/dashboards/db":
                return {}
            if method == "GET" and path == "/api/datasources/name/prometheus-demo":
                return {"id": 7, "type": "prometheus", "url": "http://old", "isDefault": False}
            if method == "PUT" and path == "/api/datasources/7":
                return {}
            raise AssertionError(f"unexpected call: {method} {path}")

        monkeypatch.setattr(GrafanaProvider, "_request", fake_request, raising=False)

        result = await run_grafana_demo(provider)

        assert result["folder"]["applied"] is True
        assert any(change["action"] == "update" for change in result["folder"]["changes"])
        assert result["dashboard"]["applied"] is True
        assert result["datasource"]["applied"] is True

    @pytest.mark.asyncio
    async def test_handles_errors(self, monkeypatch):
        """Handles provider errors gracefully."""
        provider = GrafanaProvider("https://grafana.example.com", None)

        async def failing_request(self, method, path, **kwargs):
            raise GrafanaProviderError("connection failed")

        monkeypatch.setattr(GrafanaProvider, "_request", failing_request, raising=False)

        result = await run_grafana_demo(provider)

        assert result["folder"]["applied"] is False
        assert "connection failed" in (result["folder"]["error"] or "")


class TestBuildParser:
    """Tests for build_parser function."""

    def test_returns_parser(self):
        """Returns an ArgumentParser."""
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_has_version_flag(self):
        """Parser has --version flag."""
        parser = build_parser()
        args = parser.parse_args(["-V"])
        assert args.version is True

    def test_plan_command(self):
        """Parser handles plan command."""
        parser = build_parser()
        args = parser.parse_args(["plan", "service.yaml", "--env", "prod"])
        assert args.command == "plan"
        assert args.service_yaml == "service.yaml"
        assert args.env == "prod"

    def test_apply_command(self):
        """Parser handles apply command with all options."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "apply",
                "service.yaml",
                "--env",
                "staging",
                "--output-dir",
                "/tmp/output",
                "--dry-run",
                "--skip",
                "alerts",
                "pagerduty",
                "--only",
                "dashboards",
                "--force",
                "-v",
                "--push-grafana",
            ]
        )
        assert args.command == "apply"
        assert args.dry_run is True
        assert args.skip == ["alerts", "pagerduty"]
        assert args.only == ["dashboards"]
        assert args.force is True
        assert args.verbose is True
        assert args.push_grafana is True

    def test_generate_slo_command(self):
        """Parser handles generate-slo command."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "generate-slo",
                "service.yaml",
                "--format",
                "prometheus",
                "--dry-run",
            ]
        )
        assert args.command == "generate-slo"
        assert args.format == "prometheus"
        assert args.dry_run is True

    def test_validate_command(self):
        """Parser handles validate command."""
        parser = build_parser()
        args = parser.parse_args(["validate", "service.yaml", "--strict"])
        assert args.command == "validate"
        assert args.strict is True

    def test_config_commands(self):
        """Parser handles config subcommands."""
        parser = build_parser()

        args = parser.parse_args(["config", "show", "--reveal-secrets"])
        assert args.command == "config"
        assert args.config_command == "show"
        assert args.reveal_secrets is True

        args = parser.parse_args(["config", "set", "grafana.url", "http://example.com"])
        assert args.config_command == "set"
        assert args.key == "grafana.url"
        assert args.value == "http://example.com"

    def test_secrets_commands(self):
        """Parser handles secrets subcommands."""
        parser = build_parser()

        args = parser.parse_args(["secrets", "list"])
        assert args.command == "secrets"
        assert args.secrets_command == "list"

        args = parser.parse_args(["secrets", "set", "grafana/api_key", "secret-value"])
        assert args.secrets_command == "set"
        assert args.path == "grafana/api_key"

    def test_demo_commands(self):
        """Parser handles demo commands."""
        parser = build_parser()

        args = parser.parse_args(["list-services"])
        assert args.command == "list-services"

        args = parser.parse_args(["reconcile-team", "platform"])
        assert args.command == "reconcile-team"
        assert args.team_id == "platform"

        args = parser.parse_args(["grafana", "--base-url", "http://grafana:3000"])
        assert args.command == "grafana"
        assert args.base_url == "http://grafana:3000"


class TestPrintWelcome:
    """Tests for _print_welcome function."""

    def test_outputs_welcome(self, capsys):
        """Outputs welcome message."""
        _print_welcome()
        captured = capsys.readouterr()
        assert "Quick Start" in captured.out
        assert "nthlayer setup" in captured.out


class TestMain:
    """Tests for main function."""

    def test_version_flag(self, capsys):
        """--version flag shows version."""
        main(["-V"])
        captured = capsys.readouterr()
        assert "nthlayer version" in captured.out

    def test_no_command_shows_welcome(self, capsys):
        """No command shows welcome message."""
        main([])
        captured = capsys.readouterr()
        assert "Quick Start" in captured.out

    def test_list_services_command(self, tmp_path, monkeypatch, capsys):
        """list-services command runs successfully."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
services:
  - id: test-svc
    name: Test
    tier: 1
    team: test
    description: Test service
""")
        monkeypatch.chdir(tmp_path)

        main(["list-services"])

        captured = capsys.readouterr()
        assert "test-svc" in captured.out

    def test_list_teams_command(self, tmp_path, monkeypatch, capsys):
        """list-teams command runs successfully."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
teams:
  - id: test-team
    name: Test Team
    slack_channel: '#test'
    pagerduty_schedule: test-oncall
    members: []
""")
        monkeypatch.chdir(tmp_path)

        main(["list-teams"])

        captured = capsys.readouterr()
        assert "test-team" in captured.out

    def test_prometheus_alerts_command(self, monkeypatch, capsys):
        """prometheus-alerts command runs."""

        class StubLoader:
            def load_technology(self, tech):
                return [AlertRule(name="Test", expr="up == 0")]

        monkeypatch.setattr("nthlayer.demo.AlertTemplateLoader", StubLoader)

        main(["prometheus-alerts", "--technology", "postgres", "--limit", "1"])

        captured = capsys.readouterr()
        assert "Prometheus Alerts Demo" in captured.out

    def test_plan_command_missing_file(self, tmp_path, monkeypatch):
        """plan command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["plan", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_apply_command_missing_file(self, tmp_path, monkeypatch):
        """apply command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["apply", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_generate_slo_command(self, tmp_path, monkeypatch):
        """generate-slo command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["generate-slo", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_validate_command(self, tmp_path, monkeypatch):
        """validate command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_lint_command(self, tmp_path, monkeypatch):
        """lint command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["lint", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_init_command(self, tmp_path, monkeypatch, capsys):
        """init command runs with service name."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.cli.init.init_command", return_value=0) as mock_init:
            with pytest.raises(SystemExit) as exc_info:
                main(["init", "my-service"])

            mock_init.assert_called_once()
            assert exc_info.value.code == 0

    def test_list_templates_command(self, capsys):
        """list-templates command runs."""
        with patch("nthlayer.cli.templates.list_templates_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["list-templates"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_config_show_command(self):
        """config show command dispatches correctly."""
        with patch("nthlayer.config.cli.config_show_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["config", "show"])

            mock.assert_called_once_with(reveal_secrets=False)
            assert exc_info.value.code == 0

    def test_config_set_command(self):
        """config set command dispatches correctly."""
        with patch("nthlayer.config.cli.config_set_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["config", "set", "grafana.url", "http://example.com"])

            mock.assert_called_once_with("grafana.url", "http://example.com", secret=False)
            assert exc_info.value.code == 0

    def test_config_init_command(self):
        """config init command dispatches correctly."""
        with patch("nthlayer.config.cli.config_init_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["config", "init"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_config_no_subcommand(self, capsys):
        """config without subcommand shows usage."""
        with pytest.raises(SystemExit) as exc_info:
            main(["config"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_secrets_list_command(self):
        """secrets list command dispatches correctly."""
        with patch("nthlayer.config.cli.secrets_list_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["secrets", "list"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_secrets_verify_command(self):
        """secrets verify command dispatches correctly."""
        with patch("nthlayer.config.cli.secrets_verify_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["secrets", "verify", "--secrets", "grafana", "pagerduty"])

            mock.assert_called_once_with(secrets=["grafana", "pagerduty"])
            assert exc_info.value.code == 0

    def test_secrets_get_command(self):
        """secrets get command dispatches correctly."""
        with patch("nthlayer.config.cli.secrets_get_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["secrets", "get", "grafana/api_key", "--reveal"])

            mock.assert_called_once_with("grafana/api_key", reveal=True)
            assert exc_info.value.code == 0

    def test_secrets_set_command(self):
        """secrets set command dispatches correctly."""
        with patch("nthlayer.config.cli.secrets_set_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["secrets", "set", "grafana/api_key", "secret-value"])

            mock.assert_called_once_with("grafana/api_key", "secret-value", backend=None)
            assert exc_info.value.code == 0

    def test_secrets_migrate_command(self):
        """secrets migrate command dispatches correctly."""
        with patch("nthlayer.config.cli.secrets_migrate_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["secrets", "migrate", "env", "vault", "--dry-run"])

            mock.assert_called_once_with("env", "vault", secrets=None, dry_run=True)
            assert exc_info.value.code == 0

    def test_secrets_no_subcommand(self, capsys):
        """secrets without subcommand shows usage."""
        with pytest.raises(SystemExit) as exc_info:
            main(["secrets"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_unknown_command_shows_help(self, capsys):
        """Unknown command shows help."""
        # Parser exits with error for unknown commands
        with pytest.raises(SystemExit) as exc_info:
            main(["unknown-command"])

        assert exc_info.value.code == 2  # argparse error code

    def test_slo_command_dispatch(self, tmp_path, monkeypatch):
        """slo command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_slo_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["slo", "list"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_portfolio_command_dispatch(self, tmp_path, monkeypatch):
        """portfolio command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_portfolio_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["portfolio"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_setup_command_dispatch(self):
        """setup command dispatches to handler."""
        with patch("nthlayer.demo.handle_setup_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["setup"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_verify_command_dispatch(self, tmp_path, monkeypatch):
        """verify command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_verify_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["verify", "service.yaml"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_generate_loki_alerts_dispatch(self, tmp_path, monkeypatch):
        """generate-loki-alerts command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_loki_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["generate-loki-alerts", "service.yaml"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_validate_metadata_dispatch(self, tmp_path, monkeypatch):
        """validate-metadata command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_validate_metadata_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate-metadata", "service.yaml"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_validate_spec_dispatch(self, tmp_path, monkeypatch):
        """validate-spec command dispatches to handler."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.demo.handle_validate_spec_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate-spec", "service.yaml"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_reconcile_team_command(self, tmp_path, monkeypatch, capsys):
        """reconcile-team command runs async demo."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
teams:
  - id: platform
    name: Platform Team
    slack_channel: '#platform'
    pagerduty_schedule: oncall
    members:
      - email: alice@example.com
      - email: bob@example.com
""")
        monkeypatch.chdir(tmp_path)

        main(["reconcile-team", "platform"])

        captured = capsys.readouterr()
        assert "Team Reconciliation Demo" in captured.out

    def test_reconcile_service_command(self, tmp_path, monkeypatch, capsys):
        """reconcile-service command runs async demo."""
        demo_file = tmp_path / "tests" / "fixtures" / "demo_data.yaml"
        demo_file.parent.mkdir(parents=True)
        demo_file.write_text("""
services:
  - id: search-api
    name: Search API
    tier: 1
    team: platform
    description: Search service
teams:
  - id: platform
    name: Platform
    slack_channel: '#platform'
    pagerduty_schedule: oncall
    members:
      - email: alice@example.com
      - email: bob@example.com
alert_templates:
  tier_1: []
""")
        monkeypatch.chdir(tmp_path)

        main(["reconcile-service", "search-api"])

        captured = capsys.readouterr()
        assert "Service Reconciliation Demo" in captured.out

    def test_grafana_command(self, monkeypatch, capsys):
        """grafana command runs async demo."""

        async def fake_demo(provider):
            return {
                "folder": {"changes": [], "applied": True, "error": None},
                "dashboard": {"changes": [], "applied": True, "error": None},
                "datasource": {"changes": [], "applied": True, "error": None},
            }

        monkeypatch.setattr("nthlayer.demo.run_grafana_demo", fake_demo)

        main(["grafana", "--base-url", "http://test:3000"])

        captured = capsys.readouterr()
        assert "Grafana Provider Demo" in captured.out

    def test_list_environments_command(self, tmp_path, monkeypatch):
        """list-environments command dispatches correctly."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.cli.environments.list_environments_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["list-environments"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_diff_envs_command(self, tmp_path, monkeypatch):
        """diff-envs command dispatches correctly."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.cli.environments.diff_envs_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["diff-envs", "service.yaml", "dev", "prod"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_validate_env_command(self, tmp_path, monkeypatch):
        """validate-env command dispatches correctly."""
        monkeypatch.chdir(tmp_path)

        with patch("nthlayer.cli.environments.validate_env_command", return_value=0) as mock:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate-env", "prod"])

            mock.assert_called_once()
            assert exc_info.value.code == 0

    def test_generate_dashboard_command(self, tmp_path, monkeypatch):
        """generate-dashboard command raises error for missing file."""
        from nthlayer.specs.parser import ServiceParseError

        monkeypatch.chdir(tmp_path)

        # The generate_dashboard_command raises ServiceParseError for missing files
        with pytest.raises(ServiceParseError):
            main(["generate-dashboard", "nonexistent.yaml"])

    def test_generate_recording_rules_command(self, tmp_path, monkeypatch):
        """generate-recording-rules command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["generate-recording-rules", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_check_deploy_command(self, tmp_path, monkeypatch):
        """check-deploy command exits 2 for missing file (parse error)."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["check-deploy", "nonexistent.yaml"])

        # Check-deploy command returns exit code 2 for parse errors
        assert exc_info.value.code == 2

    def test_generate_alerts_command(self, tmp_path, monkeypatch):
        """generate-alerts command exits 1 for missing file."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["generate-alerts", "nonexistent.yaml"])

        assert exc_info.value.code == 1

    def test_setup_pagerduty_command(self, tmp_path, monkeypatch):
        """setup-pagerduty command exits 1 when no API key."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PAGERDUTY_API_KEY", raising=False)

        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  tier: tier-1
  team: test
  type: api
""")

        with pytest.raises(SystemExit) as exc_info:
            main(["setup-pagerduty", str(service_file)])

        # Should fail due to no PagerDuty resource
        assert exc_info.value.code == 1
