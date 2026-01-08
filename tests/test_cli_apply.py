"""Tests for CLI apply command.

Tests for nthlayer apply command including resource generation,
output formatting, and error handling.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.apply import (
    _get_warning_types,
    apply_command,
    print_apply_json,
    print_apply_summary,
)
from nthlayer.orchestrator import ApplyResult


@pytest.fixture
def sample_service_yaml():
    """Create a sample service YAML file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "test-service.yaml"
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
def successful_apply_result(tmp_path):
    """Create a successful ApplyResult for testing."""
    output_dir = tmp_path / "generated" / "test-service"
    output_dir.mkdir(parents=True)

    # Create some generated files
    (output_dir / "dashboard.json").write_text('{"dashboard": {}}')
    (output_dir / "alerts.yaml").write_text("groups: []")

    return ApplyResult(
        service_name="test-service",
        resources_created={
            "slos": 2,
            "alerts": 15,
            "dashboard": 1,
            "recording-rules": 8,
        },
        duration_seconds=1.5,
        output_dir=output_dir,
        errors=[],
    )


@pytest.fixture
def failed_apply_result(tmp_path):
    """Create a failed ApplyResult for testing."""
    output_dir = tmp_path / "generated" / "failed-service"
    output_dir.mkdir(parents=True)

    return ApplyResult(
        service_name="failed-service",
        resources_created={
            "slos": 1,
            "alerts": 0,
        },
        duration_seconds=0.5,
        output_dir=output_dir,
        errors=["PagerDuty API error: authentication failed", "Dashboard generation failed"],
    )


class TestApplyCommand:
    """Tests for apply_command function."""

    def test_apply_generates_resources(self, sample_service_yaml, tmp_path):
        """Test that apply generates expected resources."""
        output_dir = tmp_path / "output"

        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(output_dir),
            output_format="json",
        )

        # Should succeed (exit code 0)
        assert result == 0

        # Output directory should be created
        assert output_dir.exists()

    def test_apply_with_env(self, sample_service_yaml, tmp_path):
        """Test apply with environment parameter."""
        result = apply_command(
            service_yaml=sample_service_yaml,
            env="staging",
            output_dir=str(tmp_path / "output"),
            output_format="json",
        )

        assert result == 0

    def test_apply_dry_run_delegates_to_plan(self, sample_service_yaml):
        """Test that dry_run=True delegates to plan command."""
        with patch("nthlayer.cli.apply.plan_command") as mock_plan:
            mock_plan.return_value = 0

            result = apply_command(
                service_yaml=sample_service_yaml,
                dry_run=True,
            )

            assert result == 0
            mock_plan.assert_called_once()

    def test_apply_with_skip(self, sample_service_yaml, tmp_path):
        """Test apply with skip parameter."""
        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            skip=["pagerduty", "alerts"],
            output_format="json",
        )

        assert result == 0

    def test_apply_with_only(self, sample_service_yaml, tmp_path):
        """Test apply with only parameter."""
        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            only=["dashboard"],
            output_format="json",
        )

        assert result == 0

    def test_apply_json_output(self, minimal_service_yaml, tmp_path, capsys):
        """Test apply with JSON output format produces valid, parseable JSON.

        Uses minimal_service_yaml (no dependencies) to avoid alert generator
        progress output that would mix with JSON.
        """
        result = apply_command(
            service_yaml=minimal_service_yaml,
            output_dir=str(tmp_path / "output"),
            output_format="json",
        )

        # Should succeed
        assert result == 0

        # Should produce valid JSON with expected structure
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Verify structure
        assert output["service_name"] == "minimal-service"
        assert "resources_created" in output
        assert "total_resources" in output
        assert "duration_seconds" in output
        assert output["success"] is True
        assert output["errors"] == []

    def test_apply_missing_file_returns_error(self):
        """Test that apply returns error code for missing file."""
        # CLI handles errors gracefully, doesn't raise
        result = apply_command(
            service_yaml="/nonexistent/path/service.yaml",
        )

        # Should return error exit code
        assert result == 1

    def test_apply_minimal_service(self, minimal_service_yaml, tmp_path):
        """Test apply with minimal service definition."""
        result = apply_command(
            service_yaml=minimal_service_yaml,
            output_dir=str(tmp_path / "output"),
            output_format="json",
        )

        # Should succeed even with minimal config
        assert result == 0


class TestPrintApplySummary:
    """Tests for print_apply_summary function."""

    def test_prints_successful_result(self, successful_apply_result, capsys):
        """Test printing successful apply result."""
        print_apply_summary(successful_apply_result)

        captured = capsys.readouterr()
        assert "SLOs" in captured.out
        assert "Alerts" in captured.out
        assert "Dashboard" in captured.out
        assert "26 resources" in captured.out

    def test_prints_failed_result(self, failed_apply_result, capsys):
        """Test printing failed apply result."""
        print_apply_summary(failed_apply_result)

        captured = capsys.readouterr()
        assert "errors" in captured.out.lower() or "warning" in captured.out.lower()

    def test_prints_warnings(self, failed_apply_result, capsys):
        """Test that warnings are displayed."""
        print_apply_summary(failed_apply_result)

        captured = capsys.readouterr()
        assert "PagerDuty" in captured.out or "pagerduty" in captured.out.lower()

    def test_verbose_shows_files(self, successful_apply_result, capsys):
        """Test verbose mode shows generated files."""
        print_apply_summary(successful_apply_result, verbose=True)

        captured = capsys.readouterr()
        assert "dashboard.json" in captured.out or "Generated files" in captured.out


class TestPrintApplyJson:
    """Tests for print_apply_json function."""

    def test_outputs_valid_json(self, successful_apply_result, capsys):
        """Test that output is valid JSON."""
        print_apply_json(successful_apply_result)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["service_name"] == "test-service"
        assert output["total_resources"] == 26
        assert output["success"] is True

    def test_includes_all_fields(self, successful_apply_result, capsys):
        """Test that all expected fields are included."""
        print_apply_json(successful_apply_result)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        expected_fields = [
            "service_name",
            "resources_created",
            "total_resources",
            "duration_seconds",
            "output_dir",
            "errors",
            "success",
        ]
        for field in expected_fields:
            assert field in output


class TestGetWarningTypes:
    """Tests for _get_warning_types helper function."""

    def test_detects_pagerduty_warnings(self, tmp_path):
        """Test detection of PagerDuty warnings."""
        result = ApplyResult(
            service_name="test",
            resources_created={},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=["PagerDuty API error: rate limited"],
        )

        warning_types = _get_warning_types(result)
        assert "pagerduty" in warning_types

    def test_detects_dashboard_warnings(self, tmp_path):
        """Test detection of dashboard warnings."""
        result = ApplyResult(
            service_name="test",
            resources_created={},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=["Dashboard template not found"],
        )

        warning_types = _get_warning_types(result)
        assert "dashboard" in warning_types

    def test_detects_alert_warnings(self, tmp_path):
        """Test detection of alert warnings."""
        result = ApplyResult(
            service_name="test",
            resources_created={},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=["Alert generation failed"],
        )

        warning_types = _get_warning_types(result)
        assert "alerts" in warning_types

    def test_no_warnings_for_success(self, successful_apply_result):
        """Test no warnings for successful result."""
        warning_types = _get_warning_types(successful_apply_result)
        assert len(warning_types) == 0


class TestApplyIntegration:
    """Integration tests for apply command."""

    def test_full_apply_workflow(self, sample_service_yaml, tmp_path):
        """Test complete apply workflow."""
        output_dir = tmp_path / "generated"

        # Run apply
        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(output_dir),
            verbose=True,
        )

        assert result == 0
        assert output_dir.exists()

        # Check that some files were generated
        generated_files = list(output_dir.glob("**/*"))
        assert len(generated_files) > 0

    def test_apply_idempotent(self, sample_service_yaml, tmp_path):
        """Test that apply is idempotent (running twice produces same result)."""
        output_dir = tmp_path / "generated"

        # First apply
        result1 = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(output_dir),
            output_format="json",
        )

        # Second apply (force to bypass cache)
        result2 = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(output_dir),
            force=True,
            output_format="json",
        )

        assert result1 == result2 == 0


class TestPrintApplySummaryEdgeCases:
    """Tests for print_apply_summary edge cases."""

    def test_unknown_resource_type(self, tmp_path, capsys):
        """Test printing with unknown resource type."""
        result = ApplyResult(
            service_name="test",
            resources_created={"custom-resource": 5},
            duration_seconds=1.0,
            output_dir=tmp_path,
            errors=[],
        )

        print_apply_summary(result)

        captured = capsys.readouterr()
        # Unknown types should be title-cased
        assert "Custom Resource" in captured.out
        assert "5 created" in captured.out

    def test_warning_types_highlighted(self, tmp_path, capsys):
        """Test that resource types with warnings are highlighted."""
        result = ApplyResult(
            service_name="test",
            resources_created={"pagerduty": 1, "alerts": 10},
            duration_seconds=1.0,
            output_dir=tmp_path,
            errors=["PagerDuty API error: rate limited"],
        )

        print_apply_summary(result)

        captured = capsys.readouterr()
        # PagerDuty should have warning icon
        assert "PagerDuty" in captured.out

    def test_zero_duration(self, tmp_path, capsys):
        """Test printing with zero duration."""
        result = ApplyResult(
            service_name="test",
            resources_created={"slos": 1},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=[],
        )

        print_apply_summary(result)

        captured = capsys.readouterr()
        # No duration should be shown
        assert "Applied 1 resources" in captured.out
        assert "in 0" not in captured.out

    def test_truncates_long_errors(self, tmp_path, capsys):
        """Test that long errors are truncated in non-verbose mode."""
        long_error = "A" * 100 + " some error at the end"
        result = ApplyResult(
            service_name="test",
            resources_created={},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=[long_error],
        )

        print_apply_summary(result, verbose=False)

        captured = capsys.readouterr()
        # Should be truncated
        assert "..." in captured.out

    def test_does_not_truncate_in_verbose(self, tmp_path, capsys):
        """Test that long errors are not truncated in verbose mode."""
        long_error = "A" * 100 + " some error at the end"
        result = ApplyResult(
            service_name="test",
            resources_created={},
            duration_seconds=0,
            output_dir=tmp_path,
            errors=[long_error],
        )

        print_apply_summary(result, verbose=True)

        captured = capsys.readouterr()
        # Should show full error
        assert "some error at the end" in captured.out

    def test_verbose_with_no_files(self, tmp_path, capsys):
        """Test verbose mode with empty output directory."""
        output_dir = tmp_path / "empty"
        output_dir.mkdir()

        result = ApplyResult(
            service_name="test",
            resources_created={"slos": 1},
            duration_seconds=0,
            output_dir=output_dir,
            errors=[],
        )

        print_apply_summary(result, verbose=True)

        captured = capsys.readouterr()
        assert "Generated files" in captured.out


class TestLintGeneratedAlerts:
    """Tests for _lint_generated_alerts function."""

    def test_no_alerts_file(self, tmp_path, capsys):
        """Test lint when no alerts.yaml exists."""
        from nthlayer.cli.apply import _lint_generated_alerts

        result = _lint_generated_alerts(tmp_path, verbose=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "No alerts.yaml" in captured.out

    def test_no_alerts_file_non_verbose(self, tmp_path, capsys):
        """Test lint when no alerts.yaml exists, non-verbose."""
        from nthlayer.cli.apply import _lint_generated_alerts

        result = _lint_generated_alerts(tmp_path, verbose=False)

        assert result == 0
        captured = capsys.readouterr()
        assert "No alerts.yaml" not in captured.out

    @patch("nthlayer.validation.is_pint_available")
    def test_pint_not_available(self, mock_pint_available, tmp_path, capsys):
        """Test lint when pint is not installed."""
        from nthlayer.cli.apply import _lint_generated_alerts

        mock_pint_available.return_value = False
        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _lint_generated_alerts(tmp_path)

        assert result == 0  # Should warn but not fail
        captured = capsys.readouterr()
        assert "pint not installed" in captured.out

    @patch("nthlayer.validation.is_pint_available")
    @patch("nthlayer.validation.PintLinter")
    def test_lint_passes(self, mock_linter_class, mock_pint_available, tmp_path, capsys):
        """Test lint when validation passes."""
        from nthlayer.cli.apply import _lint_generated_alerts

        mock_pint_available.return_value = True

        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.issues = []
        mock_result.summary.return_value = "All checks passed"

        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_result
        mock_linter_class.return_value = mock_linter

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _lint_generated_alerts(tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "All checks passed" in captured.out

    @patch("nthlayer.validation.is_pint_available")
    @patch("nthlayer.validation.PintLinter")
    def test_lint_fails(self, mock_linter_class, mock_pint_available, tmp_path, capsys):
        """Test lint when validation fails."""
        from nthlayer.cli.apply import _lint_generated_alerts

        mock_pint_available.return_value = True

        mock_issue = MagicMock()
        mock_issue.is_error = True
        mock_issue.is_warning = False
        mock_issue.check = "syntax"
        mock_issue.line = 10
        mock_issue.message = "Invalid syntax"

        mock_result = MagicMock()
        mock_result.passed = False
        mock_result.issues = [mock_issue]
        mock_result.summary.return_value = "1 error found"

        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_result
        mock_linter_class.return_value = mock_linter

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _lint_generated_alerts(tmp_path)

        assert result == 1
        captured = capsys.readouterr()
        assert "validation failed" in captured.out

    @patch("nthlayer.validation.is_pint_available")
    @patch("nthlayer.validation.PintLinter")
    def test_lint_with_warning_issue(
        self, mock_linter_class, mock_pint_available, tmp_path, capsys
    ):
        """Test lint with warning level issues."""
        from nthlayer.cli.apply import _lint_generated_alerts

        mock_pint_available.return_value = True

        mock_issue = MagicMock()
        mock_issue.is_error = False
        mock_issue.is_warning = True
        mock_issue.check = "promql/syntax"
        mock_issue.line = 5
        mock_issue.message = "Query could be optimized"

        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.issues = [mock_issue]
        mock_result.summary.return_value = "1 warning"

        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_result
        mock_linter_class.return_value = mock_linter

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _lint_generated_alerts(tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "could be optimized" in captured.out

    @patch("nthlayer.validation.is_pint_available")
    @patch("nthlayer.validation.PintLinter")
    def test_lint_with_info_issue(self, mock_linter_class, mock_pint_available, tmp_path, capsys):
        """Test lint with info level issues."""
        from nthlayer.cli.apply import _lint_generated_alerts

        mock_pint_available.return_value = True

        mock_issue = MagicMock()
        mock_issue.is_error = False
        mock_issue.is_warning = False  # Info level
        mock_issue.check = "style"
        mock_issue.line = None  # No line number
        mock_issue.message = "Consider adding description"

        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.issues = [mock_issue]
        mock_result.summary.return_value = "1 info"

        mock_linter = MagicMock()
        mock_linter.lint_file.return_value = mock_result
        mock_linter_class.return_value = mock_linter

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _lint_generated_alerts(tmp_path)

        assert result == 0


class TestPushToMimirRuler:
    """Tests for _push_to_mimir_ruler function."""

    def test_no_alerts_file(self, tmp_path, capsys):
        """Test push when no alerts.yaml exists."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        result = _push_to_mimir_ruler(tmp_path, "test-service", verbose=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "No alerts.yaml" in captured.out

    def test_no_alerts_file_non_verbose(self, tmp_path, capsys):
        """Test push when no alerts.yaml exists, non-verbose."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        result = _push_to_mimir_ruler(tmp_path, "test-service", verbose=False)

        assert result == 0
        captured = capsys.readouterr()
        assert "No alerts.yaml" not in captured.out

    def test_no_ruler_url(self, tmp_path, monkeypatch, capsys):
        """Test push when MIMIR_RULER_URL is not set."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        # Ensure env var is not set
        monkeypatch.delenv("MIMIR_RULER_URL", raising=False)

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        result = _push_to_mimir_ruler(tmp_path, "test-service")

        assert result == 0  # Warns but doesn't fail
        captured = capsys.readouterr()
        assert "MIMIR_RULER_URL not set" in captured.out

    @patch("nthlayer.providers.mimir.MimirRulerProvider")
    def test_push_success(self, mock_provider_class, tmp_path, monkeypatch, capsys):
        """Test successful push to Mimir."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        monkeypatch.setenv("MIMIR_RULER_URL", "http://mimir:8080")
        monkeypatch.setenv("MIMIR_TENANT_ID", "test-tenant")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.groups_pushed = 2
        mock_result.namespace = "test-service"

        mock_provider = MagicMock()
        mock_provider.push_rules = MagicMock(return_value=mock_result)
        mock_provider_class.return_value = mock_provider

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        # Mock asyncio.run
        with patch("asyncio.run", return_value=mock_result):
            result = _push_to_mimir_ruler(tmp_path, "test-service")

        assert result == 0
        captured = capsys.readouterr()
        assert "Pushed 2 rule group(s)" in captured.out

    @patch("nthlayer.providers.mimir.MimirRulerProvider")
    def test_push_failure(self, mock_provider_class, tmp_path, monkeypatch, capsys):
        """Test failed push to Mimir."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        monkeypatch.setenv("MIMIR_RULER_URL", "http://mimir:8080")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "Authentication failed"

        mock_provider = MagicMock()
        mock_provider.push_rules = MagicMock(return_value=mock_result)
        mock_provider_class.return_value = mock_provider

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        with patch("asyncio.run", return_value=mock_result):
            result = _push_to_mimir_ruler(tmp_path, "test-service")

        assert result == 1
        captured = capsys.readouterr()
        assert "Authentication failed" in captured.out

    @patch("nthlayer.providers.mimir.MimirRulerProvider")
    def test_push_ruler_error(self, mock_provider_class, tmp_path, monkeypatch, capsys):
        """Test MimirRulerError handling."""
        from nthlayer.cli.apply import _push_to_mimir_ruler
        from nthlayer.providers.mimir import MimirRulerError

        monkeypatch.setenv("MIMIR_RULER_URL", "http://mimir:8080")

        mock_provider_class.return_value = MagicMock()

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        with patch("asyncio.run", side_effect=MimirRulerError("Connection refused")):
            result = _push_to_mimir_ruler(tmp_path, "test-service")

        assert result == 1
        captured = capsys.readouterr()
        assert "Connection refused" in captured.out

    @patch("nthlayer.providers.mimir.MimirRulerProvider")
    def test_push_with_all_auth_options(self, mock_provider_class, tmp_path, monkeypatch, capsys):
        """Test push with all authentication options set."""
        from nthlayer.cli.apply import _push_to_mimir_ruler

        monkeypatch.setenv("MIMIR_RULER_URL", "http://mimir:8080")
        monkeypatch.setenv("MIMIR_TENANT_ID", "test-tenant")
        monkeypatch.setenv("MIMIR_API_KEY", "test-api-key")
        monkeypatch.setenv("MIMIR_USERNAME", "user")
        monkeypatch.setenv("MIMIR_PASSWORD", "pass")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.groups_pushed = 1
        mock_result.namespace = "test"

        alerts_file = tmp_path / "alerts.yaml"
        alerts_file.write_text("groups: []")

        with patch("asyncio.run", return_value=mock_result):
            result = _push_to_mimir_ruler(tmp_path, "test-service")

        assert result == 0
        # Verify provider was created with auth options
        mock_provider_class.assert_called_once()
        call_kwargs = mock_provider_class.call_args[1]
        assert call_kwargs["api_key"] == "test-api-key"
        assert call_kwargs["username"] == "user"
        assert call_kwargs["password"] == "pass"


class TestApplyWithLintAndPush:
    """Tests for apply command with lint and push options."""

    @patch("nthlayer.cli.apply._lint_generated_alerts")
    def test_apply_with_lint_success(self, mock_lint, sample_service_yaml, tmp_path):
        """Test apply with lint=True when linting passes."""
        mock_lint.return_value = 0

        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            lint=True,
            output_format="json",
        )

        assert result == 0
        mock_lint.assert_called_once()

    @patch("nthlayer.cli.apply._lint_generated_alerts")
    def test_apply_with_lint_failure(self, mock_lint, sample_service_yaml, tmp_path):
        """Test apply with lint=True when linting fails."""
        mock_lint.return_value = 1

        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            lint=True,
            output_format="json",
        )

        assert result == 1

    @patch("nthlayer.cli.apply._push_to_mimir_ruler")
    def test_apply_with_push_ruler_success(self, mock_push, sample_service_yaml, tmp_path):
        """Test apply with push_ruler=True when push succeeds."""
        mock_push.return_value = 0

        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            push_ruler=True,
            output_format="json",
        )

        assert result == 0
        mock_push.assert_called_once()

    @patch("nthlayer.cli.apply._push_to_mimir_ruler")
    def test_apply_with_push_ruler_failure(self, mock_push, sample_service_yaml, tmp_path):
        """Test apply with push_ruler=True when push fails."""
        mock_push.return_value = 1

        result = apply_command(
            service_yaml=sample_service_yaml,
            output_dir=str(tmp_path / "output"),
            push_ruler=True,
            output_format="json",
        )

        assert result == 1

    @patch("nthlayer.cli.apply._lint_generated_alerts")
    @patch("nthlayer.cli.apply._push_to_mimir_ruler")
    def test_lint_not_called_on_failure(self, mock_push, mock_lint, tmp_path):
        """Test lint is not called when apply fails."""
        result = apply_command(
            service_yaml="/nonexistent/service.yaml",
            lint=True,
        )

        assert result == 1
        mock_lint.assert_not_called()

    @patch("nthlayer.cli.apply._lint_generated_alerts")
    @patch("nthlayer.cli.apply._push_to_mimir_ruler")
    def test_push_not_called_on_failure(self, mock_push, mock_lint, tmp_path):
        """Test push is not called when apply fails."""
        result = apply_command(
            service_yaml="/nonexistent/service.yaml",
            push_ruler=True,
        )

        assert result == 1
        mock_push.assert_not_called()
