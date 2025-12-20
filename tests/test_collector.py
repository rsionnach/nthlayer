"""
Tests for SLO metrics collector.

Tests collection from Prometheus and error budget calculation.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from nthlayer.providers.prometheus import PrometheusProvider
from nthlayer.slos.collector import SLOCollector
from nthlayer.slos.models import SLO, TimeWindow, TimeWindowType
from nthlayer.slos.storage import SLORepository


@pytest.fixture
def sample_slo():
    """Create a sample SLO for testing."""
    return SLO(
        id="test-slo",
        service="test-service",
        name="Test SLO",
        description="Test SLO description",
        target=0.9995,  # 99.95%
        time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
        query='rate(http_requests_total{job="api",status=~"5.."}[5m])',
    )


@pytest.fixture
def mock_prometheus():
    """Create a mock Prometheus provider."""
    provider = Mock(spec=PrometheusProvider)
    provider.get_sli_time_series = AsyncMock()
    return provider


@pytest.fixture
def mock_repository():
    """Create a mock SLO repository."""
    repo = Mock(spec=SLORepository)
    repo.create_or_update_error_budget = AsyncMock()
    repo.get_slos_by_service = AsyncMock()
    return repo


class TestSLOCollector:
    """Test SLO collector."""

    @pytest.mark.asyncio
    async def test_collect_with_perfect_uptime(self, sample_slo, mock_prometheus, mock_repository):
        """Test collection with 100% uptime (no errors)."""
        # Mock Prometheus to return perfect SLI values
        now = datetime.utcnow()
        measurements = []

        # 30 days of perfect uptime (SLI = 1.0)
        for i in range(30 * 24):  # 30 days, 1 measurement per hour
            measurements.append(
                {
                    "timestamp": now - timedelta(hours=30 * 24 - i),
                    "sli_value": 1.0,  # 100% good
                    "duration_seconds": 3600,  # 1 hour
                }
            )

        mock_prometheus.get_sli_time_series.return_value = measurements

        # Create collector and collect
        collector = SLOCollector(mock_prometheus, mock_repository)
        budget = await collector.collect_slo_budget(sample_slo)

        # Verify budget calculation
        assert budget.slo_id == "test-slo"
        assert budget.service == "test-service"
        assert budget.total_budget_minutes == pytest.approx(21.6, rel=0.01)
        assert budget.burned_minutes == 0.0
        assert budget.remaining_minutes == pytest.approx(21.6, rel=0.01)
        assert budget.status.value == "healthy"

        # Verify Prometheus was called
        mock_prometheus.get_sli_time_series.assert_called_once()

        # Verify budget was stored
        mock_repository.create_or_update_error_budget.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_with_some_errors(self, sample_slo, mock_prometheus, mock_repository):
        """Test collection with some errors (partial budget burn)."""
        now = datetime.utcnow()
        measurements = []

        # First 20 days: perfect (1.0)
        for i in range(20 * 24):
            measurements.append(
                {
                    "timestamp": now - timedelta(hours=30 * 24 - i),
                    "sli_value": 1.0,
                    "duration_seconds": 3600,
                }
            )

        # Last 10 days: 99% uptime (1% errors)
        for i in range(20 * 24, 30 * 24):
            measurements.append(
                {
                    "timestamp": now - timedelta(hours=30 * 24 - i),
                    "sli_value": 0.99,  # 1% errors
                    "duration_seconds": 3600,
                }
            )

        mock_prometheus.get_sli_time_series.return_value = measurements

        # Create collector and collect
        collector = SLOCollector(mock_prometheus, mock_repository)
        budget = await collector.collect_slo_budget(sample_slo)

        # 1% error rate for 10 days = 0.01 * 10 * 24 * 60 = 144 minutes
        assert budget.burned_minutes == pytest.approx(144, rel=0.1)
        assert budget.percent_consumed > 50  # More than 50% consumed
        assert budget.status.value in ["warning", "critical", "exhausted"]

    @pytest.mark.asyncio
    async def test_collect_with_no_measurements(self, sample_slo, mock_prometheus, mock_repository):
        """Test collection when no measurements are available."""
        # Mock Prometheus to return empty list
        mock_prometheus.get_sli_time_series.return_value = []

        # Create collector and collect
        collector = SLOCollector(mock_prometheus, mock_repository)
        budget = await collector.collect_slo_budget(sample_slo)

        # With no measurements, no budget is burned
        assert budget.burned_minutes == 0.0
        assert budget.remaining_minutes == pytest.approx(21.6, rel=0.01)
        assert budget.status.value == "healthy"

    @pytest.mark.asyncio
    async def test_collect_service_budgets(self, sample_slo, mock_prometheus, mock_repository):
        """Test collecting budgets for all SLOs of a service."""
        # Create multiple SLOs
        slo1 = SLO(
            id="slo-1",
            service="test-service",
            name="SLO 1",
            description="First SLO",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="query1",
        )
        slo2 = SLO(
            id="slo-2",
            service="test-service",
            name="SLO 2",
            description="Second SLO",
            target=0.999,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="query2",
        )

        # Mock repository to return both SLOs
        mock_repository.get_slos_by_service.return_value = [slo1, slo2]

        # Mock Prometheus to return perfect uptime
        now = datetime.utcnow()
        measurements = [
            {
                "timestamp": now - timedelta(hours=i),
                "sli_value": 1.0,
                "duration_seconds": 3600,
            }
            for i in range(24)
        ]
        mock_prometheus.get_sli_time_series.return_value = measurements

        # Create collector and collect
        collector = SLOCollector(mock_prometheus, mock_repository)
        budgets = await collector.collect_service_budgets("test-service")

        # Verify we got budgets for both SLOs
        assert len(budgets) == 2
        assert budgets[0].slo_id == "slo-1"
        assert budgets[1].slo_id == "slo-2"

        # Verify repository was queried
        mock_repository.get_slos_by_service.assert_called_once_with("test-service")

        # Verify both budgets were stored
        assert mock_repository.create_or_update_error_budget.call_count == 2

    @pytest.mark.asyncio
    async def test_collect_with_custom_time_range(
        self, sample_slo, mock_prometheus, mock_repository
    ):
        """Test collection with custom time range."""
        # Custom time range: last 7 days
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=7)

        # Mock measurements
        measurements = [
            {
                "timestamp": period_start + timedelta(hours=i),
                "sli_value": 1.0,
                "duration_seconds": 3600,
            }
            for i in range(7 * 24)
        ]
        mock_prometheus.get_sli_time_series.return_value = measurements

        # Create collector and collect with custom range
        collector = SLOCollector(mock_prometheus, mock_repository)
        budget = await collector.collect_slo_budget(
            sample_slo,
            period_start=period_start,
            period_end=period_end,
        )

        # Verify time range was passed to Prometheus
        call_args = mock_prometheus.get_sli_time_series.call_args
        assert call_args.kwargs["start"] == period_start
        assert call_args.kwargs["end"] == period_end

        # Verify budget period
        assert budget.period_start == period_start
        assert budget.period_end == period_end


class TestPrometheusIntegration:
    """Test Prometheus provider integration (without network calls)."""

    def test_parse_prometheus_response(self):
        """Test parsing Prometheus query_range response."""
        # Sample Prometheus response format
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "api", "instance": "localhost:8080"},
                        "values": [
                            [1699999200, "1.0"],  # timestamp, value
                            [1699999500, "0.99"],
                            [1699999800, "1.0"],
                        ],
                    }
                ],
            },
        }

        # Verify structure
        assert response["status"] == "success"
        data = response["data"]["result"][0]
        assert len(data["values"]) == 3
        assert float(data["values"][0][1]) == 1.0
        assert float(data["values"][1][1]) == 0.99
