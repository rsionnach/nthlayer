"""Tests for CLI dashboard validate command.

Tests for nthlayer dashboard validate command including metric resolution,
technology filtering, and intent listing.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.dashboard_validate import (
    _display_discovery_result,
    _display_final_verdict,
    _display_intent_results,
    _display_service_info,
    _display_single_intent,
    _display_summary,
    _display_technologies,
    list_intents_command,
    validate_dashboard_command,
)
from nthlayer.dashboards.resolver import ResolutionStatus
from nthlayer.dashboards.validator import IntentResult, ValidationResult


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
  - kind: Dependencies
    name: main
    spec:
      databases:
        - type: postgresql
          name: primary
""")
        yield str(service_file)


@pytest.fixture
def service_context():
    """Create a mock service context."""
    ctx = MagicMock()
    ctx.name = "test-service"
    ctx.team = "platform"
    return ctx


@pytest.fixture
def successful_validation_result():
    """Create a successful validation result."""
    return ValidationResult(
        resolved=[
            IntentResult(
                name="postgresql.connections.active",
                status=ResolutionStatus.RESOLVED,
                metric_name="pg_stat_activity_count",
            ),
        ],
        synthesized=[],
        custom=[],
        fallback=[],
        unresolved=[],
        discovery_count=50,
        discovery_error=None,
    )


@pytest.fixture
def partial_validation_result():
    """Create a validation result with unresolved intents."""
    return ValidationResult(
        resolved=[
            IntentResult(
                name="postgresql.connections.active",
                status=ResolutionStatus.RESOLVED,
                metric_name="pg_stat_activity_count",
            ),
        ],
        synthesized=[],
        custom=[],
        fallback=[
            IntentResult(
                name="postgresql.connections.idle",
                status=ResolutionStatus.FALLBACK,
                metric_name="pg_stat_activity_idle",
                message="Using fallback metric",
            ),
        ],
        unresolved=[
            IntentResult(
                name="postgresql.disk.usage",
                status=ResolutionStatus.UNRESOLVED,
                message="No matching metric found",
            ),
        ],
        discovery_count=50,
        discovery_error=None,
    )


class TestValidateDashboardCommand:
    """Tests for validate_dashboard_command function."""

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_successful_validation(
        self,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
        successful_validation_result,
    ):
        """Test successful dashboard validation."""
        mock_parse.return_value = (service_context, [])
        mock_validator = MagicMock()
        mock_validator.validate.return_value = successful_validation_result
        mock_validator_class.return_value = mock_validator

        result = validate_dashboard_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 0

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_validation_with_unresolved_returns_2(
        self,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
        partial_validation_result,
    ):
        """Test that unresolved intents with prometheus_url returns exit code 2."""
        mock_parse.return_value = (service_context, [])
        mock_validator = MagicMock()
        mock_validator.validate.return_value = partial_validation_result
        mock_validator_class.return_value = mock_validator

        result = validate_dashboard_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 2

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_validation_without_prometheus_url(
        self,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
        partial_validation_result,
    ):
        """Test validation without prometheus_url returns 0 even with unresolved."""
        mock_parse.return_value = (service_context, [])
        mock_validator = MagicMock()
        mock_validator.validate.return_value = partial_validation_result
        mock_validator_class.return_value = mock_validator

        result = validate_dashboard_command(
            service_file=sample_service_yaml,
            prometheus_url=None,
        )

        assert result == 0

    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_missing_file_returns_error(self, mock_parse):
        """Test that missing file returns exit code 1."""
        mock_parse.side_effect = FileNotFoundError("Service file not found")

        result = validate_dashboard_command(
            service_file="/nonexistent/service.yaml",
        )

        assert result == 1

    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_invalid_yaml_returns_error(self, mock_parse, sample_service_yaml):
        """Test that invalid YAML returns exit code 1."""
        import yaml

        mock_parse.side_effect = yaml.YAMLError("Invalid YAML")

        result = validate_dashboard_command(service_file=sample_service_yaml)

        assert result == 1

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    @patch("nthlayer.cli.dashboard_validate.extract_technologies")
    def test_technology_filter(
        self,
        mock_extract_tech,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
        successful_validation_result,
    ):
        """Test that technology filter is applied."""
        mock_parse.return_value = (service_context, [])
        mock_extract_tech.return_value = {"postgresql", "redis"}
        mock_validator = MagicMock()
        mock_validator.validate.return_value = successful_validation_result
        mock_validator_class.return_value = mock_validator

        result = validate_dashboard_command(
            service_file=sample_service_yaml,
            technology="postgresql",
        )

        assert result == 0
        # Should only validate postgresql, not redis
        call_args = mock_validator.validate.call_args
        assert call_args.kwargs["technologies"] == {"postgresql"}

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_show_all_parameter(
        self,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
        successful_validation_result,
    ):
        """Test that show_all parameter is passed to validator."""
        mock_parse.return_value = (service_context, [])
        mock_validator = MagicMock()
        mock_validator.validate.return_value = successful_validation_result
        mock_validator_class.return_value = mock_validator

        validate_dashboard_command(
            service_file=sample_service_yaml,
            show_all=True,
        )

        call_args = mock_validator.validate.call_args
        assert call_args.kwargs["validate_all"] is True

    @patch("nthlayer.cli.dashboard_validate.DashboardValidator")
    @patch("nthlayer.cli.dashboard_validate.parse_service_file")
    def test_zero_intents_returns_success(
        self,
        mock_parse,
        mock_validator_class,
        sample_service_yaml,
        service_context,
    ):
        """Test that zero intents returns exit code 0."""
        mock_parse.return_value = (service_context, [])
        mock_validator = MagicMock()
        mock_validator.validate.return_value = ValidationResult(
            resolved=[],
            synthesized=[],
            custom=[],
            fallback=[],
            unresolved=[],
            discovery_count=0,
            discovery_error=None,
        )
        mock_validator_class.return_value = mock_validator

        result = validate_dashboard_command(service_file=sample_service_yaml)

        assert result == 0


class TestDisplayFunctions:
    """Tests for display helper functions."""

    def test_display_service_info(self, service_context, capsys):
        """Test _display_service_info output."""
        _display_service_info("test.yaml", service_context)

        captured = capsys.readouterr()
        assert "test-service" in captured.out
        assert "platform" in captured.out

    def test_display_technologies_with_techs(self, capsys):
        """Test _display_technologies with technologies."""
        _display_technologies({"postgresql", "redis"})

        captured = capsys.readouterr()
        assert "postgresql" in captured.out
        assert "redis" in captured.out

    def test_display_technologies_empty(self, capsys):
        """Test _display_technologies with empty set."""
        _display_technologies(set())

        captured = capsys.readouterr()
        assert "none detected" in captured.out

    def test_display_discovery_result_success(self, capsys):
        """Test _display_discovery_result with successful discovery."""
        result = MagicMock()
        result.discovery_error = None
        result.discovery_count = 50

        _display_discovery_result(result, "http://prometheus:9090")

        captured = capsys.readouterr()
        assert "50 metrics" in captured.out

    def test_display_discovery_result_error(self, capsys):
        """Test _display_discovery_result with discovery error."""
        result = MagicMock()
        result.discovery_error = "Connection refused"

        _display_discovery_result(result, "http://prometheus:9090")

        captured = capsys.readouterr()
        assert "Connection refused" in captured.out

    def test_display_discovery_result_no_url(self, capsys):
        """Test _display_discovery_result without prometheus_url."""
        result = MagicMock()

        _display_discovery_result(result, None)

        captured = capsys.readouterr()
        assert "No Prometheus URL" in captured.out

    def test_display_single_intent_resolved(self, capsys):
        """Test _display_single_intent for resolved intent."""
        intent = IntentResult(
            name="postgresql.connections.active",
            status=ResolutionStatus.RESOLVED,
            metric_name="pg_stat_activity_count",
        )

        _display_single_intent(intent)

        captured = capsys.readouterr()
        assert "postgresql.connections.active" in captured.out
        assert "pg_stat_activity_count" in captured.out

    def test_display_single_intent_custom(self, capsys):
        """Test _display_single_intent for custom intent."""
        intent = IntentResult(
            name="custom.metric",
            status=ResolutionStatus.CUSTOM,
            metric_name="my_custom_metric",
        )

        _display_single_intent(intent)

        captured = capsys.readouterr()
        assert "custom.metric" in captured.out
        assert "Custom" in captured.out

    def test_display_single_intent_fallback(self, capsys):
        """Test _display_single_intent for fallback intent."""
        intent = IntentResult(
            name="postgresql.disk.usage",
            status=ResolutionStatus.FALLBACK,
            metric_name="pg_disk_fallback",
            message="Using fallback metric",
        )

        _display_single_intent(intent)

        captured = capsys.readouterr()
        assert "Fallback" in captured.out
        assert "Using fallback metric" in captured.out

    def test_display_single_intent_synthesized(self, capsys):
        """Test _display_single_intent for synthesized intent."""
        intent = IntentResult(
            name="postgresql.rate",
            status=ResolutionStatus.SYNTHESIZED,
            metric_name="synthesized_rate",
            synthesis_expr="rate(pg_total[5m])",
        )

        _display_single_intent(intent)

        captured = capsys.readouterr()
        assert "Synthesized" in captured.out
        assert "rate(pg_total[5m])" in captured.out

    def test_display_single_intent_unresolved(self, capsys):
        """Test _display_single_intent for unresolved intent."""
        intent = IntentResult(
            name="postgresql.missing",
            status=ResolutionStatus.UNRESOLVED,
            message="No matching metric found",
        )

        _display_single_intent(intent)

        captured = capsys.readouterr()
        assert "postgresql.missing" in captured.out
        assert "No matching metric found" in captured.out

    def test_display_summary(self, capsys, partial_validation_result):
        """Test _display_summary output."""
        _display_summary(partial_validation_result)

        captured = capsys.readouterr()
        assert "Summary" in captured.out
        assert "Total intents" in captured.out

    def test_display_final_verdict_success(self, capsys, successful_validation_result):
        """Test _display_final_verdict for successful validation."""
        result = _display_final_verdict(successful_validation_result, "http://prometheus:9090")

        assert result == 0
        captured = capsys.readouterr()
        assert "resolved successfully" in captured.out

    def test_display_final_verdict_unresolved_with_url(self, capsys, partial_validation_result):
        """Test _display_final_verdict with unresolved intents and URL."""
        result = _display_final_verdict(partial_validation_result, "http://prometheus:9090")

        assert result == 2
        captured = capsys.readouterr()
        assert "could not be resolved" in captured.out

    def test_display_final_verdict_unresolved_no_url(self, capsys, partial_validation_result):
        """Test _display_final_verdict with unresolved intents but no URL."""
        result = _display_final_verdict(partial_validation_result, None)

        assert result == 0
        captured = capsys.readouterr()
        assert "prometheus-url" in captured.out.lower()


class TestListIntentsCommand:
    """Tests for list_intents_command function."""

    def test_list_all_intents(self, capsys):
        """Test listing all intents."""
        result = list_intents_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "All intents" in captured.out or "Intents" in captured.out

    @patch("nthlayer.cli.dashboard_validate.get_intents_for_technology")
    def test_list_intents_for_technology(self, mock_get_intents, capsys):
        """Test listing intents for specific technology."""
        mock_intent = MagicMock()
        mock_intent.metric_type.value = "gauge"
        mock_intent.candidates = ["metric1", "metric2"]

        mock_get_intents.return_value = {"postgresql.test": mock_intent}

        result = list_intents_command(technology="postgresql")

        assert result == 0
        captured = capsys.readouterr()
        assert "postgresql" in captured.out

    @patch("nthlayer.cli.dashboard_validate.ALL_INTENTS", {})
    def test_list_intents_empty(self, capsys):
        """Test listing when no intents available."""
        result = list_intents_command()

        assert result == 0


class TestIntentResults:
    """Tests for intent result display logic."""

    def test_display_intent_results_sorted(self, capsys):
        """Test that intents are sorted by name."""
        result = ValidationResult(
            resolved=[
                IntentResult(
                    name="zebra.metric",
                    status=ResolutionStatus.RESOLVED,
                    metric_name="zebra",
                ),
                IntentResult(
                    name="alpha.metric",
                    status=ResolutionStatus.RESOLVED,
                    metric_name="alpha",
                ),
            ],
            synthesized=[],
            custom=[],
            fallback=[],
            unresolved=[],
            discovery_count=0,
            discovery_error=None,
        )

        _display_intent_results(result)

        captured = capsys.readouterr()
        # alpha should appear before zebra
        alpha_pos = captured.out.find("alpha")
        zebra_pos = captured.out.find("zebra")
        assert alpha_pos < zebra_pos

    def test_display_intent_results_mixed_statuses(self, capsys):
        """Test display with mixed intent statuses."""
        result = ValidationResult(
            resolved=[
                IntentResult(
                    name="resolved.metric",
                    status=ResolutionStatus.RESOLVED,
                    metric_name="resolved",
                ),
            ],
            synthesized=[
                IntentResult(
                    name="synth.metric",
                    status=ResolutionStatus.SYNTHESIZED,
                    metric_name="synth",
                    synthesis_expr="rate(x[5m])",
                ),
            ],
            custom=[
                IntentResult(
                    name="custom.metric",
                    status=ResolutionStatus.CUSTOM,
                    metric_name="custom",
                ),
            ],
            fallback=[
                IntentResult(
                    name="fallback.metric",
                    status=ResolutionStatus.FALLBACK,
                    metric_name="fallback",
                    message="Using fallback",
                ),
            ],
            unresolved=[
                IntentResult(
                    name="unresolved.metric",
                    status=ResolutionStatus.UNRESOLVED,
                    message="Not found",
                ),
            ],
            discovery_count=0,
            discovery_error=None,
        )

        _display_intent_results(result)

        captured = capsys.readouterr()
        # All should appear in output
        assert "resolved.metric" in captured.out
        assert "synth.metric" in captured.out
        assert "custom.metric" in captured.out
        assert "fallback.metric" in captured.out
        assert "unresolved.metric" in captured.out
