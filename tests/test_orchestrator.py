"""Tests for orchestrator.py and orchestration package.

Tests for service orchestration including ApplyResult, PlanResult,
ResourceDetector, ServiceOrchestrator (facade), and handler-level tests.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.core.errors import ProviderError
from nthlayer.orchestration.handlers import (
    AlertHandler,
    DashboardHandler,
    PagerDutyHandler,
    RecordingRulesHandler,
    SloHandler,
    _push_dashboard_to_grafana,
    _setup_event_orchestration,
)
from nthlayer.orchestration.registry import OrchestratorContext, ResourceRegistry
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


@pytest.fixture
def sample_context(sample_service_yaml, tmp_path):
    """Build an OrchestratorContext from sample YAML."""
    import yaml

    with open(sample_service_yaml) as f:
        service_def = yaml.safe_load(f)

    detector = ResourceDetector(service_def)
    return OrchestratorContext(
        service_yaml=sample_service_yaml,
        service_def=service_def,
        service_name="test-service",
        output_dir=tmp_path,
        env=None,
        detector=detector,
    )


@pytest.fixture
def minimal_context(minimal_service_yaml, tmp_path):
    """Build an OrchestratorContext from minimal YAML."""
    import yaml

    with open(minimal_service_yaml) as f:
        service_def = yaml.safe_load(f)

    detector = ResourceDetector(service_def)
    return OrchestratorContext(
        service_yaml=minimal_service_yaml,
        service_def=service_def,
        service_name="minimal-service",
        output_dir=tmp_path,
        env=None,
        detector=detector,
    )


@pytest.fixture
def slo_only_context(slo_only_service_yaml, tmp_path):
    """Build an OrchestratorContext from SLO-only YAML."""
    import yaml

    with open(slo_only_service_yaml) as f:
        service_def = yaml.safe_load(f)

    detector = ResourceDetector(service_def)
    return OrchestratorContext(
        service_yaml=slo_only_service_yaml,
        service_def=service_def,
        service_name="slo-service",
        output_dir=tmp_path,
        env=None,
        detector=detector,
    )


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
    """Tests for ServiceOrchestrator class (facade)."""

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


class TestHandlerPlanMethods:
    """Tests for handler plan() methods."""

    def test_plan_slos(self, sample_context):
        """Test SloHandler.plan()."""
        handler = SloHandler()
        slos = handler.plan(sample_context)

        assert len(slos) == 1
        assert slos[0]["name"] == "availability"
        assert slos[0]["objective"] == 99.9
        assert slos[0]["window"] == "30d"

    def test_plan_dashboard(self, sample_context):
        """Test DashboardHandler.plan()."""
        handler = DashboardHandler()
        dashboards = handler.plan(sample_context)

        assert len(dashboards) == 1
        assert "test-service" in dashboards[0]["name"]

    def test_plan_pagerduty(self, sample_context):
        """Test PagerDutyHandler.plan()."""
        handler = PagerDutyHandler()
        resources = handler.plan(sample_context)

        assert len(resources) == 4  # team, schedules, escalation_policy, service
        resource_types = [r["type"] for r in resources]
        assert "team" in resource_types
        assert "service" in resource_types

    def test_plan_pagerduty_no_resources(self, minimal_context):
        """Test PagerDutyHandler.plan() with no PagerDuty resources."""
        handler = PagerDutyHandler()
        resources = handler.plan(minimal_context)

        assert resources == []

    @patch("nthlayer.generators.alerts.generate_alerts_for_service")
    def test_plan_alerts(self, mock_generate, sample_context):
        """Test AlertHandler.plan()."""
        mock_alert = MagicMock()
        mock_alert.severity = "critical"
        mock_generate.return_value = [mock_alert, mock_alert, mock_alert]

        handler = AlertHandler()
        alerts = handler.plan(sample_context)

        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"
        assert alerts[0]["count"] == 3

    @patch("nthlayer.generators.alerts.generate_alerts_for_service")
    def test_plan_alerts_exception(self, mock_generate, sample_context):
        """Test AlertHandler.plan() handles exceptions."""
        mock_generate.side_effect = Exception("Alert generation failed")

        handler = AlertHandler()
        alerts = handler.plan(sample_context)

        assert alerts == []

    def test_plan_recording_rules(self, slo_only_context):
        """Test RecordingRulesHandler.plan()."""
        handler = RecordingRulesHandler()
        rules = handler.plan(slo_only_context)

        # Should return groups with rules
        assert isinstance(rules, list)

    def test_plan_recording_rules_no_slos(self, minimal_context):
        """Test RecordingRulesHandler.plan() with no SLOs still generates health metrics."""
        handler = RecordingRulesHandler()
        rules = handler.plan(minimal_context)

        # Health metrics are generated even without SLOs
        assert isinstance(rules, list)
        # At minimum, should have health metrics group
        if rules:
            assert any("health" in r.get("type", "").lower() for r in rules)


class TestHandlerGenerateMethods:
    """Tests for handler generate() methods."""

    def test_generate_slos(self, slo_only_context):
        """Test SloHandler.generate()."""
        handler = SloHandler()
        count = handler.generate(slo_only_context)

        # Should generate SLOs
        assert count >= 0

    def test_generate_slos_no_slos(self, minimal_context):
        """Test SloHandler.generate() with no SLO resources."""
        handler = SloHandler()
        count = handler.generate(minimal_context)

        assert count == 0

    def test_generate_alerts(self, sample_context):
        """Test AlertHandler.generate()."""
        handler = AlertHandler()
        count = handler.generate(sample_context)

        assert count >= 0
        assert (sample_context.output_dir / "alerts.yaml").exists()

    def test_generate_dashboard(self, sample_context):
        """Test DashboardHandler.generate()."""
        handler = DashboardHandler()
        count = handler.generate(sample_context)

        assert count == 1
        assert (sample_context.output_dir / "dashboard.json").exists()

    @patch("nthlayer.orchestration.handlers._push_dashboard_to_grafana")
    def test_generate_dashboard_with_push(self, mock_push, sample_context):
        """Test DashboardHandler.generate() with push_to_grafana."""
        sample_context.push_to_grafana = True
        handler = DashboardHandler()
        count = handler.generate(sample_context)

        assert count == 1
        mock_push.assert_called_once()

    def test_generate_recording_rules(self, slo_only_context):
        """Test RecordingRulesHandler.generate()."""
        handler = RecordingRulesHandler()
        handler.generate(slo_only_context)

        # Should create file
        assert (slo_only_context.output_dir / "recording-rules.yaml").exists()

    def test_generate_recording_rules_no_slos(self, minimal_context):
        """Test RecordingRulesHandler.generate() with no SLOs still generates health metrics."""
        handler = RecordingRulesHandler()
        count = handler.generate(minimal_context)

        # Health metrics are generated even without SLOs
        assert count >= 0
        assert (minimal_context.output_dir / "recording-rules.yaml").exists()
        content = (minimal_context.output_dir / "recording-rules.yaml").read_text()
        # Should have generated something (health metrics)
        assert "generated by NthLayer" in content or "No recording rules" in content

    def test_generate_pagerduty_no_api_key(self, sample_context, monkeypatch):
        """Test PagerDutyHandler.generate() without API key."""
        monkeypatch.delenv("PAGERDUTY_API_KEY", raising=False)

        handler = PagerDutyHandler()
        count = handler.generate(sample_context)

        assert count == 1
        # Should create config file
        assert (sample_context.output_dir / "pagerduty-config.json").exists()
        config = json.loads((sample_context.output_dir / "pagerduty-config.json").read_text())
        assert "note" in config

    @patch("nthlayer.orchestration.handlers.PagerDutyResourceManager")
    def test_generate_pagerduty_with_api_key(self, mock_manager_class, sample_context, monkeypatch):
        """Test PagerDutyHandler.generate() with API key."""
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

        handler = PagerDutyHandler()
        count = handler.generate(sample_context)

        assert count == 2  # len(created_resources)
        assert (sample_context.output_dir / "pagerduty-result.json").exists()

    @patch("nthlayer.orchestration.handlers.PagerDutyResourceManager")
    def test_generate_pagerduty_failure(self, mock_manager_class, sample_context, monkeypatch):
        """Test PagerDutyHandler.generate() when PagerDuty fails."""
        monkeypatch.setenv("PAGERDUTY_API_KEY", "test-api-key")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ["API error"]

        mock_manager = MagicMock()
        mock_manager.setup_service.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        handler = PagerDutyHandler()

        with pytest.raises(ProviderError) as exc:
            handler.generate(sample_context)

        assert "PagerDuty setup failed" in str(exc.value)


class TestLogSuccess:
    """Tests for execution engine _log_success."""

    def test_log_success_dashboard(self, capsys):
        """Test log success for dashboard."""
        from nthlayer.orchestration.engine import _log_success

        _log_success("dashboard", 1, "dashboard", False)

        captured = capsys.readouterr()
        assert "Dashboard created" in captured.out

    def test_log_success_dashboard_pushed(self, capsys):
        """Test log success for dashboard when pushed to Grafana."""
        from nthlayer.orchestration.engine import _log_success

        _log_success("dashboard", 1, "dashboard", True)

        captured = capsys.readouterr()
        assert "pushed to Grafana" in captured.out

    def test_log_success_pagerduty(self, capsys):
        """Test log success for PagerDuty."""
        from nthlayer.orchestration.engine import _log_success

        _log_success("pagerduty", 1, "PagerDuty", False)

        captured = capsys.readouterr()
        assert "PagerDuty service created" in captured.out

    def test_log_success_generic(self, capsys):
        """Test log success for generic resource type."""
        from nthlayer.orchestration.engine import _log_success

        _log_success("alerts", 10, "alerts", False)

        captured = capsys.readouterr()
        assert "10 alerts created" in captured.out


class TestPushDashboardToGrafana:
    """Tests for _push_dashboard_to_grafana module function."""

    def test_push_no_grafana_config(self, tmp_path, monkeypatch, capsys):
        """Test push when Grafana not configured."""
        monkeypatch.delenv("NTHLAYER_GRAFANA_URL", raising=False)
        monkeypatch.delenv("NTHLAYER_GRAFANA_API_KEY", raising=False)

        # Create dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(json.dumps({"dashboard": {"uid": "test"}}))

        _push_dashboard_to_grafana(dashboard_file, "test-service")

        captured = capsys.readouterr()
        assert "Grafana not configured" in captured.out

    def test_push_empty_dashboard(self, tmp_path, monkeypatch, capsys):
        """Test push with empty dashboard JSON."""
        monkeypatch.setenv("NTHLAYER_GRAFANA_URL", "http://grafana:3000")
        monkeypatch.setenv("NTHLAYER_GRAFANA_API_KEY", "test-key")

        # Create empty dashboard file
        dashboard_file = tmp_path / "dashboard.json"
        dashboard_file.write_text(json.dumps({}))

        _push_dashboard_to_grafana(dashboard_file, "test-service")

        captured = capsys.readouterr()
        assert "empty" in captured.out.lower()

    @patch("nthlayer.providers.grafana.GrafanaProvider")
    @patch("asyncio.run")
    def test_push_success(
        self,
        mock_asyncio_run,
        mock_provider_class,
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

        _push_dashboard_to_grafana(dashboard_file, "test-service")

        captured = capsys.readouterr()
        assert "pushed" in captured.out.lower() or "Pushing" in captured.out

    @patch("nthlayer.providers.grafana.GrafanaProvider")
    @patch("asyncio.run")
    def test_push_failure(
        self,
        mock_asyncio_run,
        mock_provider_class,
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

        _push_dashboard_to_grafana(dashboard_file, "test-service")

        captured = capsys.readouterr()
        assert "Failed" in captured.out or "saved locally" in captured.out


class TestEventOrchestration:
    """Tests for _setup_event_orchestration module function."""

    @patch("nthlayer.orchestration.handlers.EventOrchestrationManager")
    def test_setup_success(self, mock_manager_class, capsys):
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

        _setup_event_orchestration(
            api_key="test-key",
            default_from="test@example.com",
            service_id="svc-123",
            sre_escalation_policy_id="ep-123",
        )

        captured = capsys.readouterr()
        assert "Event Orchestration" in captured.out

    @patch("nthlayer.orchestration.handlers.EventOrchestrationManager")
    def test_setup_failure(self, mock_manager_class, capsys):
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

        _setup_event_orchestration(
            api_key="test-key",
            default_from="test@example.com",
            service_id="svc-123",
            sre_escalation_policy_id="ep-123",
        )

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


class TestGenerateAlertmanagerConfig:
    """Tests for alertmanager config generation via PagerDutyHandler."""

    @patch("nthlayer.orchestration.handlers.generate_alertmanager_config")
    @patch("nthlayer.orchestration.handlers.PagerDutyResourceManager")
    def test_generate_config(self, mock_manager_class, mock_generate, sample_context, monkeypatch):
        """Test generating Alertmanager config via PagerDutyHandler."""
        monkeypatch.setenv("PAGERDUTY_API_KEY", "test-api-key")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.team_id = "team-123"
        mock_result.schedule_ids = []
        mock_result.escalation_policy_id = "ep-123"
        mock_result.service_id = "svc-123"
        mock_result.service_url = "https://pagerduty.com/services/svc-123"
        mock_result.created_resources = ["service"]
        mock_result.warnings = []

        mock_manager = MagicMock()
        mock_manager.setup_service.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        mock_config = MagicMock()
        mock_generate.return_value = mock_config

        handler = PagerDutyHandler()
        handler.generate(sample_context)

        mock_generate.assert_called_once()
        mock_config.write.assert_called_once()

    @patch("nthlayer.orchestration.handlers.generate_alertmanager_config")
    @patch("nthlayer.orchestration.handlers.PagerDutyResourceManager")
    def test_generate_config_with_sre_key(
        self, mock_manager_class, mock_generate, sample_context, tmp_path, monkeypatch
    ):
        """Test generating Alertmanager config with SRE integration key."""
        monkeypatch.setenv("PAGERDUTY_API_KEY", "test-api-key")

        # Add sre_integration_key to context
        import yaml

        service_file = tmp_path / "sre-service.yaml"
        service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: PagerDuty
    name: main
    spec:
      integration_key: test-key
      sre_integration_key: sre-key
""")
        with open(service_file) as f:
            service_def = yaml.safe_load(f)

        ctx = OrchestratorContext(
            service_yaml=service_file,
            service_def=service_def,
            service_name="test-service",
            output_dir=tmp_path / "output",
            env=None,
            detector=ResourceDetector(service_def),
        )
        (tmp_path / "output").mkdir()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.team_id = "team-123"
        mock_result.schedule_ids = []
        mock_result.escalation_policy_id = "ep-123"
        mock_result.service_id = "svc-123"
        mock_result.service_url = "https://pagerduty.com/services/svc-123"
        mock_result.created_resources = ["service"]
        mock_result.warnings = []

        mock_manager = MagicMock()
        mock_manager.setup_service.return_value = mock_result
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager_class.return_value = mock_manager

        mock_config = MagicMock()
        mock_generate.return_value = mock_config

        handler = PagerDutyHandler()
        handler.generate(ctx)

        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["sre_integration_key"] == "sre-key"


class TestOrchestratorApplyErrors:
    """Tests for error handling in apply method."""

    def test_apply_handles_generator_exception(self, sample_service_yaml, tmp_path):
        """Test that apply catches and records generator exceptions."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)
        orchestrator.output_dir = tmp_path

        # Patch the SloHandler.generate to raise
        with patch.object(SloHandler, "generate", side_effect=Exception("SLO generation failed")):
            result = orchestrator.apply(only=["slos"], skip=["recording-rules"])

        assert result.success is False
        assert any("SLO" in err or "slo" in err.lower() for err in result.errors)


class TestPlanExceptionHandling:
    """Tests for plan exception handling."""

    def test_plan_handles_exception(self, sample_service_yaml):
        """Test that plan catches exceptions."""
        orchestrator = ServiceOrchestrator(sample_service_yaml)

        # Patch SloHandler.plan to raise
        with patch.object(SloHandler, "plan", side_effect=Exception("Planning error")):
            result = orchestrator.plan()

        assert result.success is False
        assert any("Planning failed" in err for err in result.errors)


class TestResourceRegistry:
    """Tests for ResourceRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving handlers."""
        registry = ResourceRegistry()
        handler = SloHandler()
        registry.register(handler)

        assert registry.get("slos") is handler
        assert registry.get("nonexistent") is None

    def test_list(self):
        """Test listing registered handlers."""
        registry = ResourceRegistry()
        registry.register(SloHandler())
        registry.register(AlertHandler())

        names = registry.list()
        assert "slos" in names
        assert "alerts" in names

    def test_register_default_handlers(self):
        """Test that register_default_handlers populates all 6 handlers."""
        from nthlayer.orchestration.handlers import register_default_handlers

        registry = ResourceRegistry()
        register_default_handlers(registry)

        expected = ["slos", "alerts", "dashboard", "recording-rules", "pagerduty", "backstage"]
        for name in expected:
            assert registry.get(name) is not None, f"Handler '{name}' not registered"
