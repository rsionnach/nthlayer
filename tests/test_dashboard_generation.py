"""Tests for Grafana dashboard generation."""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skip(
    reason="Legacy tests - use test_hybrid_dashboard_builder.py for current functionality"
)
class TestDashboardBuilder:
    """Tests for dashboard builder."""

    def test_builds_dashboard_from_service_spec(self):
        """Test that dashboard builder creates valid dashboard."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(name="payment-api", team="payments", tier="critical", type="api")

        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={"objective": 99.9, "window": "30d"},
                context=context,
            ),
            Resource(
                kind="SLO",
                name="latency-p95",
                spec={"objective": 99.0, "latency_threshold": 500},
                context=context,
            ),
        ]

        dashboard = build_dashboard(context, resources)

        assert dashboard.title == "payment-api - Service Dashboard"
        assert dashboard.uid == "payment-api-overview"
        assert "payments" in dashboard.tags
        assert "critical" in dashboard.tags
        assert len(dashboard.rows) >= 1  # At least SLO row
        assert len(dashboard.template_variables) >= 1  # At least service variable

    def test_dashboard_has_slo_panels(self):
        """Test that SLOs generate appropriate panels."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
        ]

        dashboard = build_dashboard(context, resources)

        # Find SLO row
        slo_row = next((r for r in dashboard.rows if "SLO" in r.title), None)
        assert slo_row is not None
        assert len(slo_row.panels) >= 1

        # Check availability panel
        panel = slo_row.panels[0]
        assert "availability" in panel.title.lower()
        assert panel.panel_type == "gauge"
        assert len(panel.targets) == 1

    def test_dashboard_has_health_panels(self):
        """Test that service health panels are included."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        dashboard = build_dashboard(context, [])

        # Find health row
        health_row = next((r for r in dashboard.rows if "Health" in r.title), None)
        assert health_row is not None
        assert len(health_row.panels) == 3  # Request rate, error rate, response time

    def test_dashboard_includes_technology_panels(self):
        """Test that technology-specific panels are added."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(
                kind="Dependencies",
                name="databases",
                spec={"databases": [{"type": "postgres", "instance": "test-db"}]},
                context=context,
            ),
        ]

        dashboard = build_dashboard(context, resources)

        # Should have dependencies row
        dep_row = next((r for r in dashboard.rows if "Depend" in r.title), None)
        assert dep_row is not None
        assert len(dep_row.panels) >= 1  # At least postgres panel

    def test_dashboard_json_is_valid(self):
        """Test that generated JSON is valid Grafana format."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        dashboard = build_dashboard(context, [])
        json_payload = dashboard.to_grafana_payload()

        # Check required Grafana fields
        assert "dashboard" in json_payload
        assert "overwrite" in json_payload

        db = json_payload["dashboard"]
        assert "title" in db
        assert "panels" in db
        assert "schemaVersion" in db
        assert isinstance(db["panels"], list)


@pytest.mark.skip(
    reason="Legacy tests - use test_hybrid_dashboard_builder.py for current functionality"
)
class TestDashboardCommand:
    """Tests for generate-dashboard CLI command."""

    def test_generates_dashboard_file(self):
        """Test that command generates dashboard JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
            """)

            output_file = tmpdir / "dashboard.json"

            from nthlayer.cli.dashboard import generate_dashboard_command

            result = generate_dashboard_command(
                str(service_file), output=str(output_file), environment=None, dry_run=False
            )

            assert result == 0
            assert output_file.exists()

            # Verify JSON is valid
            dashboard_data = json.loads(output_file.read_text())
            assert "dashboard" in dashboard_data
            assert dashboard_data["dashboard"]["title"] == "test-api - Service Dashboard"

    def test_dry_run_doesnt_write_file(self):
        """Test that dry-run mode doesn't create files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api
            """)

            output_file = tmpdir / "dashboard.json"

            from nthlayer.cli.dashboard import generate_dashboard_command

            result = generate_dashboard_command(
                str(service_file), output=str(output_file), environment=None, dry_run=True
            )

            assert result == 0
            assert not output_file.exists()  # No file in dry-run mode

    def test_environment_aware_dashboard(self):
        """Test that dashboards include environment in variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
            """)

            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "prod.yaml").write_text("""
environment: prod
service:
  tier: critical
            """)

            output_file = tmpdir / "dashboard.json"

            from nthlayer.cli.dashboard import generate_dashboard_command

            result = generate_dashboard_command(
                str(service_file), output=str(output_file), environment="prod", dry_run=False
            )

            assert result == 0

            # Check environment variable is included
            dashboard_data = json.loads(output_file.read_text())
            variables = dashboard_data["dashboard"].get("templating", {}).get("list", [])

            env_var = next((v for v in variables if v["name"] == "environment"), None)
            assert env_var is not None
            assert env_var["current"]["value"] == "prod"


@pytest.mark.skip(
    reason="Legacy tests - use test_hybrid_dashboard_builder.py for current functionality"
)
class TestVariableSubstitution:
    """Tests for variable substitution in dashboards."""

    def test_substitutes_env_in_dashboard(self):
        """Test that ${env} is substituted in dashboard generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api-${env}
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability-${env}
    spec:
      objective: 99.9
      description: "SLO for ${env} environment"
            """)

            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "staging.yaml").write_text("environment: staging")

            output_file = tmpdir / "dashboard.json"

            from nthlayer.cli.dashboard import generate_dashboard_command

            result = generate_dashboard_command(
                str(service_file), output=str(output_file), environment="staging", dry_run=False
            )

            assert result == 0

            dashboard_data = json.loads(output_file.read_text())
            db = dashboard_data["dashboard"]

            # Service name should be substituted
            assert "test-api-staging" in db["title"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
