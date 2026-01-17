"""Tests for CLI plan command.

Tests for nthlayer plan command including resource preview,
output formatting, and error handling.
"""

import json
import tempfile
from pathlib import Path

import pytest
from nthlayer.cli.plan import plan_command, print_plan_summary
from nthlayer.orchestrator import PlanResult


@pytest.fixture
def sample_service_yaml():
    """Create a sample service YAML file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 99
        threshold_ms: 500
  - kind: Dependencies
    name: main
    spec:
      databases:
        - type: postgresql
          name: primary
      caches:
        - type: redis
          name: sessions
""")
        yield str(service_file)


@pytest.fixture
def minimal_service_yaml():
    """Create a minimal service YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "minimal.yaml"
        service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
        yield str(service_file)


@pytest.fixture
def service_with_pagerduty_yaml():
    """Create a service YAML with PagerDuty configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "pagerduty-service.yaml"
        service_file.write_text("""
service:
  name: pagerduty-service
  team: oncall-team
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
      window: 30d
  - kind: PagerDuty
    name: oncall
    spec:
      team: oncall-team
      schedules:
        - primary
        - secondary
      escalation_policy: standard
""")
        yield str(service_file)


@pytest.fixture
def successful_plan_result():
    """Create a successful PlanResult for testing."""
    return PlanResult(
        service_name="test-service",
        service_yaml=Path("test-service.yaml"),
        resources={
            "slos": [
                {"name": "availability", "objective": 99.95, "window": "30d"},
                {"name": "latency-p99", "objective": 99.0, "window": "30d"},
            ],
            "alerts": [
                {"technology": "postgresql", "count": 12},
                {"technology": "redis", "count": 8},
            ],
            "dashboard": [
                {"name": "test-service", "panels": 24},
            ],
            "recording-rules": [
                {"type": "slo_metrics", "count": 14},
            ],
        },
        errors=[],
    )


@pytest.fixture
def failed_plan_result():
    """Create a failed PlanResult for testing."""
    return PlanResult(
        service_name="broken-service",
        service_yaml=Path("broken-service.yaml"),
        resources={},
        errors=["Invalid YAML syntax", "Missing required field: team"],
    )


class TestPlanCommand:
    """Tests for plan_command function."""

    def test_plan_returns_resource_preview(self, sample_service_yaml):
        """Test that plan returns expected resource preview."""
        result = plan_command(
            service_yaml=sample_service_yaml,
            output_format="json",
        )

        # Should succeed (exit code 0)
        assert result == 0

    def test_plan_with_env(self, sample_service_yaml):
        """Test plan with environment parameter."""
        result = plan_command(
            service_yaml=sample_service_yaml,
            env="production",
            output_format="json",
        )

        assert result == 0

    def test_plan_json_output(self, minimal_service_yaml, capsys):
        """Test plan with JSON output format produces valid, parseable JSON.

        Uses minimal_service_yaml (no dependencies) to avoid alert generator
        progress output that would mix with JSON.
        """
        result = plan_command(
            service_yaml=minimal_service_yaml,
            output_format="json",
        )

        # Should succeed
        assert result == 0

        # Should produce valid JSON with expected structure
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Verify new formatter structure
        assert output["service"] == "minimal-service"
        assert output["command"] == "plan"
        assert "checks" in output
        assert "summary" in output
        assert output["summary"]["status"] in ("pass", "warn", "fail")

    def test_plan_text_output(self, sample_service_yaml, capsys):
        """Test plan with text output format."""
        result = plan_command(
            service_yaml=sample_service_yaml,
            output_format="table",
        )

        captured = capsys.readouterr()
        assert "Plan:" in captured.out or "test-service" in captured.out

    def test_plan_minimal_service(self, minimal_service_yaml):
        """Test plan with minimal service definition."""
        result = plan_command(
            service_yaml=minimal_service_yaml,
            output_format="json",
        )

        # Should succeed even with minimal config
        assert result == 0

    def test_plan_with_pagerduty(self, service_with_pagerduty_yaml, capsys):
        """Test plan with PagerDuty configuration."""
        result = plan_command(
            service_yaml=service_with_pagerduty_yaml,
            output_format="table",
        )

        # Should succeed
        assert result == 0

        # Should produce output
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_plan_missing_file_returns_error(self):
        """Test that plan returns error code for missing file."""
        # CLI handles errors gracefully, doesn't raise
        result = plan_command(
            service_yaml="/nonexistent/path/service.yaml",
        )

        # Should return error exit code
        assert result == 1


class TestPrintPlanSummary:
    """Tests for print_plan_summary function."""

    def test_prints_slos(self, successful_plan_result, capsys):
        """Test printing SLO information."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "SLO" in captured.out
        assert "availability" in captured.out

    def test_prints_alerts(self, successful_plan_result, capsys):
        """Test printing alert information."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "Alert" in captured.out

    def test_prints_dashboard(self, successful_plan_result, capsys):
        """Test printing dashboard information."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "Dashboard" in captured.out

    def test_prints_recording_rules(self, successful_plan_result, capsys):
        """Test printing recording rules information."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "Recording" in captured.out or "rules" in captured.out

    def test_prints_total(self, successful_plan_result, capsys):
        """Test printing total resource count."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "36" in captured.out or "Total" in captured.out

    def test_prints_errors_on_failure(self, failed_plan_result, capsys):
        """Test printing errors for failed plan."""
        print_plan_summary(failed_plan_result)

        captured = capsys.readouterr()
        assert "Error" in captured.out or "Invalid" in captured.out

    def test_shows_apply_command(self, successful_plan_result, capsys):
        """Test that output shows how to apply."""
        print_plan_summary(successful_plan_result)

        captured = capsys.readouterr()
        assert "apply" in captured.out.lower()


class TestPlanIntegration:
    """Integration tests for plan command."""

    def test_plan_then_apply(self, sample_service_yaml, tmp_path, capsys):
        """Test plan followed by apply workflow."""
        from nthlayer.cli.apply import apply_command

        # First plan
        plan_result = plan_command(
            service_yaml=sample_service_yaml,
            output_format="table",
        )
        assert plan_result == 0

        # Then apply
        apply_result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            output_format="table",
        )

        # Both should succeed
        assert apply_result == 0

    def test_plan_different_environments(self, sample_service_yaml, capsys):
        """Test plan produces results for different environments."""
        # Plan for dev
        dev_result = plan_command(
            service_yaml=sample_service_yaml,
            env="dev",
            output_format="table",
        )

        # Plan for prod
        prod_result = plan_command(
            service_yaml=sample_service_yaml,
            env="prod",
            output_format="table",
        )

        # Both should succeed
        assert dev_result == 0
        assert prod_result == 0
