"""
Tests for deployment gate CLI command.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.cli.deploy import (
    _display_gate_result,
    _display_slo_table,
    _extract_downstream_services,
    _run_demo_mode,
    check_deploy_command,
)
from nthlayer.slos.collector import SLOMetricCollector, SLOResult


class TestParseWindowMinutes:
    """Test window parsing."""

    def test_parse_days(self):
        collector = SLOMetricCollector()
        assert collector._parse_window_minutes("30d") == 30 * 24 * 60
        assert collector._parse_window_minutes("7d") == 7 * 24 * 60

    def test_parse_hours(self):
        collector = SLOMetricCollector()
        assert collector._parse_window_minutes("24h") == 24 * 60
        assert collector._parse_window_minutes("1h") == 60

    def test_parse_weeks(self):
        collector = SLOMetricCollector()
        assert collector._parse_window_minutes("1w") == 7 * 24 * 60
        assert collector._parse_window_minutes("4w") == 4 * 7 * 24 * 60

    def test_parse_default(self):
        # Unknown format defaults to 30 days
        collector = SLOMetricCollector()
        assert collector._parse_window_minutes("unknown") == 30 * 24 * 60


class TestCheckDeployCommand:
    """Test deployment gate CLI command."""

    def test_no_prometheus_url_shows_examples(self, tmp_path):
        """Test that without Prometheus URL, example scenarios are shown."""
        # Create a minimal service file
        service_file = tmp_path / "test-service.yaml"
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
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{status!~"5.."}[5m]))
""")

        # Without Prometheus URL, should return 0 and show examples
        result = check_deploy_command(str(service_file), prometheus_url=None)
        assert result == 0

    def test_missing_service_file(self):
        """Test error handling for missing service file."""
        # Should return exit code 2 for missing file
        result = check_deploy_command("/nonexistent/file.yaml")
        assert result == 2

    def test_no_slos_returns_success(self, tmp_path):
        """Test that service without SLOs returns success with warning."""
        service_file = tmp_path / "no-slo-service.yaml"
        service_file.write_text("""
service:
  name: no-slo-service
  team: platform
  tier: standard
  type: api

resources: []
""")

        result = check_deploy_command(str(service_file))
        assert result == 0


class TestCollectSLOMetrics:
    """Test SLO metrics collection."""

    @pytest.mark.asyncio
    async def test_collect_metrics_success(self):
        """Test successful metrics collection."""
        mock_provider_instance = MagicMock()
        # 99.99% success rate - way better than 99.9% target
        mock_provider_instance.get_sli_value = AsyncMock(return_value=0.9999)

        # Create mock SLO resource with proper attribute structure
        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": 'sum(rate(http_requests_total{status!~"5.."}[5m]))'},
        }
        slo_resources = [mock_slo]

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            collector = SLOMetricCollector("http://prometheus:9090")
            results = await collector.collect(slo_resources, "test-service")

        assert len(results) == 1
        assert results[0].name == "availability"
        assert results[0].current_sli == 99.99
        assert results[0].status == "HEALTHY"

    @pytest.mark.asyncio
    async def test_collect_metrics_no_data(self):
        """Test handling when Prometheus returns no data."""
        mock_provider_instance = MagicMock()
        mock_provider_instance.get_sli_value = AsyncMock(return_value=0)

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "some_query"},
        }
        slo_resources = [mock_slo]

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            collector = SLOMetricCollector("http://prometheus:9090")
            results = await collector.collect(slo_resources, "test-service")

        assert len(results) == 1
        assert results[0].status == "NO_DATA"

    @pytest.mark.asyncio
    async def test_collect_metrics_error(self):
        """Test handling of Prometheus errors."""
        from nthlayer.providers.prometheus import PrometheusProviderError

        mock_provider_instance = MagicMock()
        mock_provider_instance.get_sli_value = AsyncMock(
            side_effect=PrometheusProviderError("Connection failed")
        )

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "some_query"},
        }
        slo_resources = [mock_slo]

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            collector = SLOMetricCollector("http://prometheus:9090")
            results = await collector.collect(slo_resources, "test-service")

        assert len(results) == 1
        assert results[0].status == "ERROR"
        assert "Connection failed" in results[0].error

    @pytest.mark.asyncio
    async def test_budget_calculation(self):
        """Test that budget consumption is calculated correctly."""
        mock_provider_instance = MagicMock()
        # 99.5% success rate means 0.5% error rate
        mock_provider_instance.get_sli_value = AsyncMock(return_value=0.995)

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,  # 0.1% error budget
            "window": "30d",
            "indicator": {"query": "some_query"},
        }
        slo_resources = [mock_slo]

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            collector = SLOMetricCollector("http://prometheus:9090")
            results = await collector.collect(slo_resources, "test-service")

        # With 0.5% error rate and 0.1% budget, we're at 500% consumption
        # (but capped at actual minutes)
        assert results[0].current_sli == 99.5
        assert results[0].burned_minutes is not None
        assert results[0].percent_consumed > 100  # Budget exhausted


class TestIntegration:
    """Integration tests for deployment gate with mock Prometheus."""

    def test_approved_with_healthy_budget(self, tmp_path):
        """Test deployment is approved with healthy error budget."""
        service_file = tmp_path / "healthy-service.yaml"
        service_file.write_text("""
service:
  name: healthy-service
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{status!~"5.."}[5m]))
""")

        mock_provider_instance = MagicMock()
        mock_provider_instance.get_sli_value = AsyncMock(return_value=0.9995)

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            result = check_deploy_command(
                str(service_file),
                prometheus_url="http://prometheus:9090",
            )

        # Should be approved (0) - 99.95% is better than 99.9% target
        assert result == 0

    def test_blocked_with_exhausted_budget(self, tmp_path):
        """Test deployment is blocked when error budget exhausted."""
        service_file = tmp_path / "exhausted-service.yaml"
        service_file.write_text("""
service:
  name: exhausted-service
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{status!~"5.."}[5m]))
""")

        mock_provider_instance = MagicMock()
        # 99% success = 1% error rate, way over 0.1% budget
        mock_provider_instance.get_sli_value = AsyncMock(return_value=0.99)

        with patch(
            "nthlayer.slos.collector.PrometheusProvider",
            return_value=mock_provider_instance,
        ):
            result = check_deploy_command(
                str(service_file),
                prometheus_url="http://prometheus:9090",
            )

        # Should be blocked (2) - budget is exhausted
        assert result == 2


class TestDemoMode:
    """Tests for demo mode."""

    def test_demo_warning_mode(self, tmp_path):
        """Test demo mode returns warning exit code."""
        service_file = tmp_path / "demo-service.yaml"
        service_file.write_text("""
service:
  name: demo-service
  team: platform
  tier: critical
  type: api

resources: []
""")

        result = check_deploy_command(str(service_file), demo=True)
        assert result == 1  # Warning scenario

    def test_demo_blocked_mode(self, tmp_path):
        """Test demo blocked mode returns blocked exit code."""
        service_file = tmp_path / "demo-service.yaml"
        service_file.write_text("""
service:
  name: demo-service
  team: platform
  tier: critical
  type: api

resources: []
""")

        result = check_deploy_command(str(service_file), demo_blocked=True)
        assert result == 2  # Blocked scenario

    def test_run_demo_mode_warning(self, tmp_path):
        """Test _run_demo_mode with warning scenario."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: my-service
  team: platform
  tier: critical
  type: api
""")

        result = _run_demo_mode(str(service_file), blocked=False)
        assert result == 1

    def test_run_demo_mode_blocked(self, tmp_path):
        """Test _run_demo_mode with blocked scenario."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: my-service
  team: platform
  tier: critical
  type: api
""")

        result = _run_demo_mode(str(service_file), blocked=True)
        assert result == 2

    def test_run_demo_mode_invalid_file(self, tmp_path):
        """Test _run_demo_mode with invalid service file."""
        service_file = tmp_path / "invalid.yaml"
        service_file.write_text("invalid: yaml: {{")

        # Should use defaults when file is invalid
        result = _run_demo_mode(str(service_file), blocked=False)
        assert result == 1


class TestExtractDownstreamServices:
    """Tests for _extract_downstream_services."""

    def test_extracts_services_from_dependencies(self):
        """Extracts downstream services from Dependencies resource."""
        deps_resource = MagicMock()
        deps_resource.kind = "Dependencies"
        deps_resource.spec = {
            "services": [
                {"name": "auth-service", "criticality": "high"},
                {"name": "cache-service"},  # No criticality specified
            ]
        }

        result = _extract_downstream_services([deps_resource])

        assert len(result) == 2
        assert result[0]["name"] == "auth-service"
        assert result[0]["criticality"] == "high"
        assert result[1]["name"] == "cache-service"
        assert result[1]["criticality"] == "medium"  # Default

    def test_handles_no_dependencies(self):
        """Returns empty list when no Dependencies resource."""
        slo_resource = MagicMock()
        slo_resource.kind = "SLO"

        result = _extract_downstream_services([slo_resource])

        assert result == []


class TestDisplaySloTable:
    """Tests for _display_slo_table."""

    def test_displays_healthy_slo(self, capsys):
        """Displays healthy SLO status."""
        result = SLOResult(
            name="availability",
            objective=99.9,
            window="30d",
            current_sli=99.95,
            total_budget_minutes=43.2,
            burned_minutes=10,
            percent_consumed=23.15,
            status="HEALTHY",
        )

        _display_slo_table([result])

        captured = capsys.readouterr()
        assert "availability" in captured.out

    def test_displays_no_data_slo(self, capsys):
        """Displays SLO with no data."""
        result = SLOResult(
            name="latency",
            objective=99.0,
            window="30d",
            current_sli=None,
            total_budget_minutes=43.2,
            burned_minutes=0,
            percent_consumed=0,
            status="NO_DATA",
            error="No data available",
        )

        _display_slo_table([result])

        captured = capsys.readouterr()
        assert "latency" in captured.out


class TestDisplayGateResult:
    """Tests for _display_gate_result."""

    def test_displays_approved(self, capsys):
        """Displays approved result."""
        mock_result = MagicMock()
        mock_result.result = 0  # GateResult.APPROVED
        mock_result.warning_threshold = 50
        mock_result.blocking_threshold = 10
        mock_result.high_criticality_downstream = []
        mock_result.recommendations = []

        exit_code = _display_gate_result(mock_result, "critical", 80.0)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "APPROVED" in captured.out

    def test_displays_warning(self, capsys):
        """Displays warning result."""
        from nthlayer.slos.gates import GateResult

        mock_result = MagicMock()
        mock_result.result = GateResult.WARNING
        mock_result.warning_threshold = 50
        mock_result.blocking_threshold = 10
        mock_result.high_criticality_downstream = []
        mock_result.recommendations = ["Monitor closely", "Prepare rollback"]

        exit_code = _display_gate_result(mock_result, "critical", 40.0)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_displays_blocked(self, capsys):
        """Displays blocked result."""
        from nthlayer.slos.gates import GateResult

        mock_result = MagicMock()
        mock_result.result = GateResult.BLOCKED
        mock_result.warning_threshold = 50
        mock_result.blocking_threshold = 10
        mock_result.high_criticality_downstream = []
        mock_result.recommendations = ["Wait for budget recovery"]

        exit_code = _display_gate_result(mock_result, "critical", 5.0)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_displays_high_criticality_downstream(self, capsys):
        """Displays high criticality downstream services."""
        mock_result = MagicMock()
        mock_result.result = 0
        mock_result.warning_threshold = 50
        mock_result.blocking_threshold = 10
        mock_result.high_criticality_downstream = ["auth-service", "payment-service"]
        mock_result.recommendations = []

        _display_gate_result(mock_result, "critical", 80.0)

        captured = capsys.readouterr()
        assert "auth-service" in captured.out
        assert "payment-service" in captured.out

    def test_displays_no_blocking_threshold(self, capsys):
        """Displays advisory only when no blocking threshold."""
        mock_result = MagicMock()
        mock_result.result = 0
        mock_result.warning_threshold = 50
        mock_result.blocking_threshold = None  # Advisory only
        mock_result.high_criticality_downstream = []
        mock_result.recommendations = []

        _display_gate_result(mock_result, "low", 80.0)

        captured = capsys.readouterr()
        assert "advisory only" in captured.out


class TestPrometheusQueryError:
    """Tests for Prometheus query error handling."""

    def test_prometheus_query_exception(self, tmp_path):
        """Test handling of Prometheus query exception."""
        service_file = tmp_path / "test-service.yaml"
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
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{status!~"5.."}[5m]))
""")

        with patch("nthlayer.cli.deploy.SLOMetricCollector") as mock_collector_class:
            mock_collector = MagicMock()
            mock_collector_class.return_value = mock_collector
            mock_collector.collect.side_effect = Exception("Connection refused")

            result = check_deploy_command(
                str(service_file),
                prometheus_url="http://prometheus:9090",
            )

        assert result == 2  # Error exit code


class TestEnvironmentDisplay:
    """Tests for environment display in header."""

    def test_displays_environment(self, tmp_path):
        """Test environment is displayed in header."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: critical
  type: api

resources: []
""")

        # Just verify it doesn't crash with environment parameter
        result = check_deploy_command(str(service_file), environment="production")
        assert result == 0  # No SLOs returns success


class TestNoValidSloData:
    """Tests for when no valid SLO data is returned."""

    def test_no_valid_slo_data_returns_zero(self, tmp_path):
        """Test returns 0 when no valid SLO data available."""
        service_file = tmp_path / "test-service.yaml"
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
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{status!~"5.."}[5m]))
""")

        with patch("nthlayer.cli.deploy.SLOMetricCollector") as mock_collector_class:
            mock_collector = MagicMock()
            mock_collector_class.return_value = mock_collector

            # Return results with no valid data
            mock_collector.collect = AsyncMock(
                return_value=[
                    SLOResult(
                        name="availability",
                        objective=99.9,
                        window="30d",
                        current_sli=None,
                        total_budget_minutes=43.2,
                        burned_minutes=0,
                        percent_consumed=0,
                        status="NO_DATA",
                    )
                ]
            )
            # Budget with 0 valid SLOs
            mock_collector.calculate_aggregate_budget.return_value = MagicMock(
                valid_slo_count=0,
                total_budget_minutes=0,
                burned_budget_minutes=0,
            )

            result = check_deploy_command(
                str(service_file),
                prometheus_url="http://prometheus:9090",
            )

        assert result == 0  # Returns 0 when no valid data


class TestExampleScenariosDefaultBudget:
    """Tests for example scenarios with default budget."""

    def test_shows_examples_without_slos(self, tmp_path):
        """Test shows examples when no SLOs defined."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: critical
  type: api

resources: []
""")

        # Without Prometheus URL and no SLOs, should return 0 and use default budget
        result = check_deploy_command(str(service_file), prometheus_url=None)
        assert result == 0
