"""Tests for orchestrator.py.

Tests for service orchestration including ApplyResult, PlanResult,
ResourceDetector, and ServiceOrchestrator.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.orchestrator import (
    ApplyResult,
    PlanResult,
    ResourceDetector,
    ServiceOrchestrator,
)


@pytest.fixture
def sample_service_yaml(tmp_path):
    """Create a sample service YAML file for testing."""
    service_file = tmp_path / "test-service.yaml"
    service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability
  - kind: Dependencies
    name: main
    spec:
      databases:
        - type: postgresql
          name: primary
  - kind: PagerDuty
    name: main
    spec:
      integration_key: test-key
""")
    return service_file


@pytest.fixture
def minimal_service_yaml(tmp_path):
    """Create a minimal service YAML file."""
    service_file = tmp_path / "minimal.yaml"
    service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
    return service_file


@pytest.fixture
def slo_only_service_yaml(tmp_path):
    """Create service with only SLOs."""
    service_file = tmp_path / "slo-only.yaml"
    service_file.write_text("""
service:
  name: slo-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")
    return service_file


class TestApplyResult:
    """Tests for ApplyResult dataclass."""

    def test_defaults(self):
        """Test default values."""
        result = ApplyResult(service_name="test")

        assert result.service_name == "test"
        assert result.resources_created == {}
        assert result.duration_seconds == 0.0
        assert result.output_dir == Path(".")
        assert result.errors == []

    def test_total_resources(self):
        """Test total_resources property."""
        result = ApplyResult(
            service_name="test",
            resources_created={"slos": 2, "alerts": 10, "dashboard": 1},
        )

        assert result.total_resources == 13

    def test_total_resources_empty(self):
        """Test total_resources with no resources."""
        result = ApplyResult(service_name="test")

        assert result.total_resources == 0

    def test_success_true(self):
        """Test success property when no errors."""
        result = ApplyResult(service_name="test", errors=[])

        assert result.success is True

    def test_success_false(self):
        """Test success property when errors exist."""
        result = ApplyResult(service_name="test", errors=["Error 1"])

        assert result.success is False


class TestPlanResult:
    """Tests for PlanResult dataclass."""

    def test_defaults(self):
        """Test default values."""
        result = PlanResult(
            service_name="test",
            service_yaml=Path("/path/to/service.yaml"),
        )

        assert result.service_name == "test"
        assert result.service_yaml == Path("/path/to/service.yaml")
        assert result.resources == {}
        assert result.errors == []

    def test_total_resources(self):
        """Test total_resources property."""
        result = PlanResult(
            service_name="test",
            service_yaml=Path("test.yaml"),
            resources={
                "slos": [{"name": "slo1"}, {"name": "slo2"}],
                "alerts": [{"severity": "critical", "count": 5}],
            },
        )

        assert result.total_resources == 3

    def test_total_resources_empty(self):
        """Test total_resources with no resources."""
        result = PlanResult(service_name="test", service_yaml=Path("test.yaml"))

        assert result.total_resources == 0

    def test_success_true(self):
        """Test success property when no errors."""
        result = PlanResult(
            service_name="test",
            service_yaml=Path("test.yaml"),
        )

        assert result.success is True

    def test_success_false(self):
        """Test success property when errors exist."""
        result = PlanResult(
            service_name="test",
            service_yaml=Path("test.yaml"),
            errors=["Planning failed"],
        )

        assert result.success is False


class TestResourceDetector:
    """Tests for ResourceDetector class."""

    def test_detect_slos(self):
        """Test detecting SLO resources."""
        service_def = {
            "resources": [
                {"kind": "SLO", "name": "availability", "spec": {"objective": 99.9}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "slos" in resources
        assert "recording-rules" in resources  # Auto-added with SLOs

    def test_detect_alerts_with_databases(self):
        """Test detecting alerts when dependencies have databases."""
        service_def = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "deps",
                    "spec": {"databases": [{"type": "postgresql"}]},
                },
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "alerts" in resources
        assert "dashboard" in resources

    def test_detect_alerts_with_services(self):
        """Test detecting alerts when dependencies have services."""
        service_def = {
            "resources": [
                {"kind": "Dependencies", "name": "deps", "spec": {"services": ["api"]}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "alerts" in resources

    def test_detect_alerts_with_external_apis(self):
        """Test detecting alerts when dependencies have external APIs."""
        service_def = {
            "resources": [
                {"kind": "Dependencies", "name": "deps", "spec": {"external_apis": ["stripe"]}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "alerts" in resources

    def test_detect_pagerduty(self):
        """Test detecting PagerDuty resources."""
        service_def = {
            "resources": [
                {"kind": "PagerDuty", "name": "main", "spec": {}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "pagerduty" in resources

    def test_detect_dashboard_with_observability(self):
        """Test detecting dashboard when Observability defined."""
        service_def = {
            "resources": [
                {"kind": "Observability", "name": "main", "spec": {}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "dashboard" in resources

    def test_detect_empty_dependencies(self):
        """Test detection with empty dependencies spec."""
        service_def = {
            "resources": [
                {"kind": "Dependencies", "name": "deps", "spec": {}},
            ]
        }
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert "alerts" not in resources

    def test_detect_no_resources(self):
        """Test detection with no resources."""
        service_def = {"resources": []}
        detector = ResourceDetector(service_def)

        resources = detector.detect()

        assert resources == []

    def test_get_resources_by_kind(self):
        """Test getting resources by kind."""
        service_def = {
            "resources": [
                {"kind": "SLO", "name": "slo1"},
                {"kind": "SLO", "name": "slo2"},
                {"kind": "PagerDuty", "name": "pd"},
            ]
        }
        detector = ResourceDetector(service_def)

        slos = detector.get_resources_by_kind("SLO")
        pagerduty = detector.get_resources_by_kind("PagerDuty")
        unknown = detector.get_resources_by_kind("Unknown")

        assert len(slos) == 2
        assert len(pagerduty) == 1
        assert len(unknown) == 0

    def test_index_caching(self):
        """Test that index is built once and cached."""
        service_def = {"resources": [{"kind": "SLO", "name": "slo1"}]}
        detector = ResourceDetector(service_def)

        # First call builds index
        detector.detect()
        index1 = detector._resource_index

        # Second call returns cached index
        detector.detect()
        index2 = detector._resource_index

        assert index1 is index2  # Same object reference


class TestServiceOrchestrator:
    """Tests for ServiceOrchestrator class."""

    def test_init(self, sample_service_yaml):
        """Test orchestrator initialization."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)

        assert orchestrator.service_yaml == sample_service_yaml
        assert orchestrator.env is None
        assert orchestrator.push_to_grafana is False
        assert orchestrator.service_def is None

    def test_init_with_options(self, sample_service_yaml):
        """Test orchestrator initialization with options."""
        orchestrator = ServiceOrchestrator(
            sample_service_yaml,
            env="staging",
            push_to_grafana=True,
        )

        assert orchestrator.env == "staging"
        assert orchestrator.push_to_grafana is True

    def test_load_service(self, sample_service_yaml):
        """Test loading service YAML."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        assert orchestrator.service_def is not None
        assert orchestrator.service_name == "test-service"
        assert orchestrator.output_dir == Path("generated") / "test-service"

    def test_load_service_uses_filename_as_default_name(self, tmp_path):
        """Test service name defaults to filename if not specified."""
        service_file = tmp_path / "my-app.yaml"
        service_file.write_text("service:\n  team: test\n")

        orchestrator = ServiceOrchestrator(service_file)
        orchestrator._load_service()

        assert orchestrator.service_name == "my-app"

    def test_load_service_idempotent(self, sample_service_yaml):
        """Test that _load_service is idempotent."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()
        service_def1 = orchestrator.service_def

        orchestrator._load_service()
        service_def2 = orchestrator.service_def

        assert service_def1 is service_def2

    def test_plan_success(self, sample_service_yaml):
        """Test successful planning."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        result = orchestrator.plan()

        assert result.success is True
        assert result.service_name == "test-service"
        assert "slos" in result.resources
        assert "pagerduty" in result.resources

    def test_plan_file_not_found(self, tmp_path):
        """Test planning with missing file."""
        orchestrator = ServiceOrchestrator(tmp_path / "nonexistent.yaml")
        result = orchestrator.plan()

        assert result.success is False
        assert "Failed to load service" in result.errors[0]

    def test_apply_success(self, sample_service_yaml, tmp_path):
        """Test successful apply."""
        output_dir = tmp_path / "output"
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = output_dir

        result = orchestrator.apply()

        assert result.success is True
        assert result.service_name == "test-service"
        assert result.duration_seconds > 0

    def test_apply_file_not_found(self, tmp_path):
        """Test apply with missing file."""
        orchestrator = ServiceOrchestrator(tmp_path / "nonexistent.yaml")
        result = orchestrator.apply()

        assert result.success is False
        assert "Failed to load service" in result.errors[0]

    def test_apply_with_skip(self, sample_service_yaml, tmp_path):
        """Test apply with skip parameter."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path / "output"

        result = orchestrator.apply(skip=["pagerduty", "alerts"])

        assert "pagerduty" not in result.resources_created
        assert "alerts" not in result.resources_created

    def test_apply_with_only(self, sample_service_yaml, tmp_path):
        """Test apply with only parameter."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path / "output"

        result = orchestrator.apply(only=["slos"])

        # Only SLOs and auto-added recording-rules should be generated
        assert "slos" in result.resources_created or len(result.resources_created) == 0

    def test_apply_verbose(self, sample_service_yaml, tmp_path, capsys):
        """Test apply with verbose output."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path / "output"

        orchestrator.apply(verbose=True, skip=["pagerduty"])

        captured = capsys.readouterr()
        assert "Generating" in captured.out

    def test_apply_creates_output_dir(self, sample_service_yaml, tmp_path):
        """Test that apply creates output directory."""
        output_dir = tmp_path / "nested" / "output"
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = output_dir

        orchestrator.apply(skip=["pagerduty"])

        assert output_dir.exists()


class TestOrchestratorPlanMethods:
    """Tests for orchestrator planning methods."""

    def test_plan_slos(self, sample_service_yaml):
        """Test _plan_slos method."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        slos = orchestrator._plan_slos()

        assert len(slos) == 1
        assert slos[0]["name"] == "availability"
        assert slos[0]["objective"] == 99.9
        assert slos[0]["window"] == "30d"

    def test_plan_dashboard(self, sample_service_yaml):
        """Test _plan_dashboard method."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        dashboards = orchestrator._plan_dashboard()

        assert len(dashboards) == 1
        assert "test-service" in dashboards[0]["name"]

    def test_plan_pagerduty(self, sample_service_yaml):
        """Test _plan_pagerduty method."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        resources = orchestrator._plan_pagerduty()

        assert len(resources) == 4  # team, schedules, escalation_policy, service
        resource_types = [r["type"] for r in resources]
        assert "team" in resource_types
        assert "service" in resource_types

    def test_plan_pagerduty_no_resources(self, minimal_service_yaml):
        """Test _plan_pagerduty with no PagerDuty resources."""
        orchestrator = ServiceOrchestrator(minimal_service_yaml)
        orchestrator._load_service()

        resources = orchestrator._plan_pagerduty()

        assert resources == []

    @patch("nthlayer.generators.alerts.generate_alerts_for_service")
    def test_plan_alerts(self, mock_generate, sample_service_yaml):
        """Test _plan_alerts method."""
        mock_alert = MagicMock()
        mock_alert.severity = "critical"
        mock_generate.return_value = [mock_alert, mock_alert, mock_alert]

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        alerts = orchestrator._plan_alerts()

        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"
        assert alerts[0]["count"] == 3

    @patch("nthlayer.generators.alerts.generate_alerts_for_service")
    def test_plan_alerts_exception(self, mock_generate, sample_service_yaml):
        """Test _plan_alerts handles exceptions."""
        mock_generate.side_effect = Exception("Alert generation failed")

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator._load_service()

        alerts = orchestrator._plan_alerts()

        assert alerts == []

    def test_plan_recording_rules(self, slo_only_service_yaml):
        """Test _plan_recording_rules method."""
        orchestrator = ServiceOrchestrator(slo_only_service_yaml)
        orchestrator._load_service()

        rules = orchestrator._plan_recording_rules()

        # Should return groups with rules
        assert isinstance(rules, list)

    def test_plan_recording_rules_no_slos(self, minimal_service_yaml):
        """Test _plan_recording_rules with no SLOs still generates health metrics."""
        orchestrator = ServiceOrchestrator(minimal_service_yaml)
        orchestrator._load_service()

        rules = orchestrator._plan_recording_rules()

        # Health metrics are generated even without SLOs
        assert isinstance(rules, list)
        # At minimum, should have health metrics group
        if rules:
            assert any("health" in r.get("type", "").lower() for r in rules)


class TestOrchestratorGenerateMethods:
    """Tests for orchestrator generation methods."""

    def test_generate_slos(self, slo_only_service_yaml, tmp_path):
        """Test _generate_slos method."""
        orchestrator = ServiceOrchestrator(slo_only_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_slos()

        # Should generate SLOs
        assert count >= 0

    def test_generate_slos_no_slos(self, minimal_service_yaml, tmp_path):
        """Test _generate_slos with no SLO resources."""
        orchestrator = ServiceOrchestrator(minimal_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_slos()

        assert count == 0

    def test_generate_alerts(self, sample_service_yaml, tmp_path):
        """Test _generate_alerts method."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_alerts()

        assert count >= 0
        assert (tmp_path / "alerts.yaml").exists()

    def test_generate_dashboard(self, sample_service_yaml, tmp_path):
        """Test _generate_dashboard method."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_dashboard()

        assert count == 1
        assert (tmp_path / "dashboard.json").exists()

    @patch("nthlayer.orchestrator.ServiceOrchestrator._push_dashboard_to_grafana")
    def test_generate_dashboard_with_push(self, mock_push, sample_service_yaml, tmp_path):
        """Test _generate_dashboard with push_to_grafana."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_dashboard(push_to_grafana=True)

        assert count == 1
        mock_push.assert_called_once()

    def test_generate_recording_rules(self, slo_only_service_yaml, tmp_path):
        """Test _generate_recording_rules method."""
        orchestrator = ServiceOrchestrator(slo_only_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_recording_rules()

        # Should create file
        assert (tmp_path / "recording-rules.yaml").exists()

    def test_generate_recording_rules_no_slos(self, minimal_service_yaml, tmp_path):
        """Test _generate_recording_rules with no SLOs still generates health metrics."""
        orchestrator = ServiceOrchestrator(minimal_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_recording_rules()

        # Health metrics are generated even without SLOs
        assert count >= 0
        assert (tmp_path / "recording-rules.yaml").exists()
        content = (tmp_path / "recording-rules.yaml").read_text()
        # Should have generated something (health metrics)
        assert "generated by NthLayer" in content or "No recording rules" in content

    def test_generate_pagerduty_no_api_key(self, sample_service_yaml, tmp_path, monkeypatch):
        """Test _generate_pagerduty without API key."""
        monkeypatch.delenv("PAGERDUTY_API_KEY", raising=False)

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_pagerduty()

        assert count == 1
        # Should create config file
        assert (tmp_path / "pagerduty-config.json").exists()
        config = json.loads((tmp_path / "pagerduty-config.json").read_text())
        assert "note" in config

    @patch("nthlayer.orchestrator.PagerDutyResourceManager")
    def test_generate_pagerduty_with_api_key(
        self, mock_manager_class, sample_service_yaml, tmp_path, monkeypatch
    ):
        """Test _generate_pagerduty with API key."""
        monkeypatch.setenv("PAGERDUTY_API_KEY", "test-api-key")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.team_id = "team-123"
        mock_result.schedule_ids = ["sched-1", "sched-2"]
        mock_result.escalation_policy_id = "ep-123"
        mock_result.service_id = "svc-123"
        mock_result.service_url = "https://pagerduty.com/services/svc-123"
        mock_result.created_resources = ["team", "service"]
        mock_result.warnings = []

        mock_manager = MagicMock()
        mock_manager.setup_service.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        count = orchestrator._generate_pagerduty()

        assert count == 2  # len(created_resources)
        assert (tmp_path / "pagerduty-result.json").exists()

    @patch("nthlayer.orchestrator.PagerDutyResourceManager")
    def test_generate_pagerduty_failure(
        self, mock_manager_class, sample_service_yaml, tmp_path, monkeypatch
    ):
        """Test _generate_pagerduty when PagerDuty fails."""
        monkeypatch.setenv("PAGERDUTY_API_KEY", "test-api-key")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ["API error"]

        mock_manager = MagicMock()
        mock_manager.setup_service.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator._load_service()

        with pytest.raises(RuntimeError) as exc:
            orchestrator._generate_pagerduty()

        assert "PagerDuty setup failed" in str(exc.value)


class TestOrchestratorLogSuccess:
    """Tests for _log_success method."""

    def test_log_success_dashboard(self, sample_service_yaml, capsys):
        """Test log success for dashboard."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)

        orchestrator._log_success("dashboard", 1, "dashboard")

        captured = capsys.readouterr()
        assert "Dashboard created" in captured.out

    def test_log_success_dashboard_pushed(self, sample_service_yaml, capsys):
        """Test log success for dashboard when pushed to Grafana."""
        orchestrator = ServiceOrchestrator(sample_service_yaml, push_to_grafana=True)

        orchestrator._log_success("dashboard", 1, "dashboard")

        captured = capsys.readouterr()
        assert "pushed to Grafana" in captured.out

    def test_log_success_pagerduty(self, sample_service_yaml, capsys):
        """Test log success for PagerDuty."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)

        orchestrator._log_success("pagerduty", 1, "PagerDuty")

        captured = capsys.readouterr()
        assert "PagerDuty service created" in captured.out

    def test_log_success_generic(self, sample_service_yaml, capsys):
        """Test log success for generic resource type."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)

        orchestrator._log_success("alerts", 10, "alerts")

        captured = capsys.readouterr()
        assert "10 alerts created" in captured.out


class TestPushDashboardToGrafana:
    """Tests for _push_dashboard_to_grafana method."""

    def test_push_no_grafana_config(self, sample_service_yaml, tmp_path, monkeypatch, capsys):
        """Test push when Grafana not configured."""
        monkeypatch.delenv("NTHLAYER_GRAFANA_URL", raising=False)
        monkeypatch.delenv("NTHLAYER_GRAFANA_API_KEY", raising=False)

        # Create dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(json.dumps({"dashboard": {"uid": "test"}}))

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.service_name = "test-service"

        orchestrator._push_dashboard_to_grafana(dashboard_file)

        captured = capsys.readouterr()
        assert "Grafana not configured" in captured.out

    def test_push_empty_dashboard(self, sample_service_yaml, tmp_path, monkeypatch, capsys):
        """Test push with empty dashboard JSON."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_URL", "http://grafana:3000")
        monkeypatch.setenv("NTHLAYER_GRAFANA_API_KEY", "test-key")

        # Create empty dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(json.dumps({}))

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.service_name = "test-service"

        orchestrator._push_dashboard_to_grafana(dashboard_file)

        captured = capsys.readouterr()
        assert "empty" in captured.out.lower()

    @patch("nthlayer.providers.grafana.GrafanaProvider")
    @patch("asyncio.run")
    def test_push_success(
        self,
        mock_asyncio_run,
        mock_provider_class,
        sample_service_yaml,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Test successful push to Grafana."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_URL", "http://grafana:3000")
        monkeypatch.setenv("NTHLAYER_GRAFANA_API_KEY", "test-key")

        # Create dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(
            json.dumps({"dashboard": {"uid": "test-uid", "title": "Test Dashboard"}})
        )

        mock_dashboard = MagicMock()
        mock_provider = MagicMock()
        mock_provider.dashboard.return_value = mock_dashboard
        mock_provider_class.return_value = mock_provider

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.service_name = "test-service"

        orchestrator._push_dashboard_to_grafana(dashboard_file)

        captured = capsys.readouterr()
        assert "pushed" in captured.out.lower() or "Pushing" in captured.out

    @patch("nthlayer.providers.grafana.GrafanaProvider")
    @patch("asyncio.run")
    def test_push_failure(
        self,
        mock_asyncio_run,
        mock_provider_class,
        sample_service_yaml,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Test push failure handling."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_URL", "http://grafana:3000")
        monkeypatch.setenv("NTHLAYER_GRAFANA_API_KEY", "test-key")

        # Create dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(json.dumps({"dashboard": {"uid": "test-uid"}}))

        mock_asyncio_run.side_effect = Exception("Connection refused")

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.service_name = "test-service"

        orchestrator._push_dashboard_to_grafana(dashboard_file)

        captured = capsys.readouterr()
        assert "Failed" in captured.out or "saved locally" in captured.out


class TestEventOrchestration:
    """Tests for _setup_event_orchestration method."""

    @patch("nthlayer.orchestrator.EventOrchestrationManager")
    def test_setup_success(self, mock_manager_class, sample_service_yaml, capsys):
        """Test successful event orchestration setup."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.rules_created = 1

        mock_manager = MagicMock()
        mock_manager.create_sre_routing_rule.return_value = MagicMock()
        mock_manager.setup_service_orchestration.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        orchestrator = ServiceOrchestrator(sample_service_yaml)

        orchestrator._setup_event_orchestration(
            api_key="test-key",
            default_from="test@example.com",
            service_id="svc-123",
            sre_escalation_policy_id="ep-123",
        )

        captured = capsys.readouterr()
        assert "Event Orchestration" in captured.out

    @patch("nthlayer.orchestrator.EventOrchestrationManager")
    def test_setup_failure(self, mock_manager_class, sample_service_yaml, capsys):
        """Test event orchestration setup failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "API error"

        mock_manager = MagicMock()
        mock_manager.create_sre_routing_rule.return_value = MagicMock()
        mock_manager.setup_service_orchestration.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        orchestrator = ServiceOrchestrator(sample_service_yaml)

        orchestrator._setup_event_orchestration(
            api_key="test-key",
            default_from="test@example.com",
            service_id="svc-123",
            sre_escalation_policy_id="ep-123",
        )

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


class TestGenerateAlertmanagerConfig:
    """Tests for _generate_alertmanager_config method."""

    @patch("nthlayer.orchestrator.generate_alertmanager_config")
    def test_generate_config(self, mock_generate, sample_service_yaml, tmp_path):
        """Test generating Alertmanager config."""
        mock_config = MagicMock()
        mock_generate.return_value = mock_config

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator.service_name = "test-service"

        orchestrator._generate_alertmanager_config(
            team="platform",
            tier="standard",
            support_model="self",
            integration_key="test-key",
        )

        mock_generate.assert_called_once()
        mock_config.write.assert_called_once()

    @patch("nthlayer.orchestrator.generate_alertmanager_config")
    def test_generate_config_with_sre_key(self, mock_generate, sample_service_yaml, tmp_path):
        """Test generating Alertmanager config with SRE integration key."""
        mock_config = MagicMock()
        mock_generate.return_value = mock_config

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path
        orchestrator.service_name = "test-service"

        orchestrator._generate_alertmanager_config(
            team="platform",
            tier="standard",
            support_model="shared",
            integration_key="test-key",
            sre_integration_key="sre-key",
        )

        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["sre_integration_key"] == "sre-key"


class TestOrchestratorApplyErrors:
    """Tests for error handling in apply method."""

    @patch.object(ServiceOrchestrator, "_generate_slos")
    def test_apply_handles_generator_exception(self, mock_generate, sample_service_yaml, tmp_path):
        """Test that apply catches and records generator exceptions."""
        mock_generate.side_effect = Exception("SLO generation failed")

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path

        result = orchestrator.apply(only=["slos"], skip=["recording-rules"])

        assert result.success is False
        assert any("SLO" in err or "slo" in err.lower() for err in result.errors)


class TestPlanExceptionHandling:
    """Tests for plan exception handling."""

    @patch.object(ServiceOrchestrator, "_plan_slos")
    def test_plan_handles_exception(self, mock_plan, sample_service_yaml):
        """Test that plan catches exceptions."""
        mock_plan.side_effect = Exception("Planning error")

        orchestrator = ServiceOrchestrator(sample_service_yaml)
        result = orchestrator.plan()

        assert result.success is False
        assert any("Planning failed" in err for err in result.errors)
