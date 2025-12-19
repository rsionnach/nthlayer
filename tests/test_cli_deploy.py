"""
Tests for deployment gate CLI command.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.cli.deploy import check_deploy_command
from nthlayer.slos.collector import SLOMetricCollector


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
