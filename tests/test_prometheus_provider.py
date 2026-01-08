"""Tests for Prometheus provider.

Tests for querying Prometheus metrics, SLI calculation,
and error handling.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nthlayer.providers.prometheus import (
    DEFAULT_USER_AGENT,
    PrometheusProvider,
    PrometheusProviderError,
)


@pytest.fixture
def prometheus_provider():
    """Create a PrometheusProvider instance for testing."""
    return PrometheusProvider(
        url="http://localhost:9090",
        timeout=10.0,
    )


@pytest.fixture
def authenticated_provider():
    """Create a PrometheusProvider with authentication."""
    return PrometheusProvider(
        url="http://prometheus.example.com:9090",
        username="user",
        password="secret",
        timeout=30.0,
    )


@pytest.fixture
def mock_successful_response():
    """Create a mock successful Prometheus API response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "job": "test"},
                    "value": [1609459200, "1"],
                }
            ],
        },
    }


@pytest.fixture
def mock_sli_response():
    """Create a mock SLI query response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {},
                    "value": [1609459200, "0.9995"],
                }
            ],
        },
    }


@pytest.fixture
def mock_range_response():
    """Create a mock range query response."""
    base_time = 1609459200
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {},
                    "values": [
                        [base_time, "0.999"],
                        [base_time + 300, "0.998"],
                        [base_time + 600, "0.9995"],
                        [base_time + 900, "0.997"],
                    ],
                }
            ],
        },
    }


@pytest.fixture
def mock_error_response():
    """Create a mock error response."""
    return {
        "status": "error",
        "errorType": "bad_data",
        "error": "invalid query syntax",
    }


class TestPrometheusProviderInit:
    """Tests for PrometheusProvider initialization."""

    def test_basic_init(self):
        """Test basic initialization."""
        provider = PrometheusProvider(url="http://localhost:9090")

        assert provider._base_url == "http://localhost:9090"
        assert provider._auth is None
        assert provider._user_agent == DEFAULT_USER_AGENT

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from URL."""
        provider = PrometheusProvider(url="http://localhost:9090/")

        assert provider._base_url == "http://localhost:9090"

    def test_init_with_auth(self, authenticated_provider):
        """Test initialization with authentication."""
        assert authenticated_provider._auth == ("user", "secret")

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        provider = PrometheusProvider(url="http://localhost:9090", timeout=60.0)

        assert provider._timeout == 60.0

    def test_init_with_custom_user_agent(self):
        """Test initialization with custom user agent."""
        provider = PrometheusProvider(
            url="http://localhost:9090",
            user_agent="custom-agent/1.0",
        )

        assert provider._user_agent == "custom-agent/1.0"


class TestQuery:
    """Tests for instant query method."""

    @pytest.mark.asyncio
    async def test_query_success(self, prometheus_provider, mock_successful_response):
        """Test successful instant query."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_successful_response

            result = await prometheus_provider.query("up")

            assert result["status"] == "success"
            assert len(result["data"]["result"]) == 1
            mock_request.assert_called_once_with("GET", "/api/v1/query", params={"query": "up"})

    @pytest.mark.asyncio
    async def test_query_with_time(self, prometheus_provider, mock_successful_response):
        """Test query with specific timestamp."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_successful_response

            query_time = datetime(2021, 1, 1, 0, 0, 0)
            await prometheus_provider.query("up", time=query_time)

            call_args = mock_request.call_args
            assert "time" in call_args.kwargs["params"]
            assert call_args.kwargs["params"]["time"] == query_time.timestamp()


class TestQueryRange:
    """Tests for range query method."""

    @pytest.mark.asyncio
    async def test_query_range_success(self, prometheus_provider, mock_range_response):
        """Test successful range query."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_range_response

            start = datetime(2021, 1, 1, 0, 0, 0)
            end = datetime(2021, 1, 1, 1, 0, 0)

            result = await prometheus_provider.query_range(
                query="rate(http_requests_total[5m])",
                start=start,
                end=end,
                step="5m",
            )

            assert result["status"] == "success"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_range_custom_step(self, prometheus_provider, mock_range_response):
        """Test range query with custom step."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_range_response

            start = datetime(2021, 1, 1)
            end = datetime(2021, 1, 2)

            await prometheus_provider.query_range(
                query="up",
                start=start,
                end=end,
                step="1h",
            )

            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["step"] == "1h"


class TestGetSliValue:
    """Tests for get_sli_value method."""

    @pytest.mark.asyncio
    async def test_get_sli_value_success(self, prometheus_provider, mock_sli_response):
        """Test getting SLI value successfully."""
        with patch.object(prometheus_provider, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_sli_response

            sli = await prometheus_provider.get_sli_value(
                "sum(rate(http_requests_total{status!~'5..'}[5m])) / "
                "sum(rate(http_requests_total[5m]))"
            )

            assert sli == pytest.approx(0.9995)

    @pytest.mark.asyncio
    async def test_get_sli_value_empty_result(self, prometheus_provider):
        """Test SLI value returns 0 for empty result."""
        with patch.object(prometheus_provider, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {
                "status": "success",
                "data": {"resultType": "vector", "result": []},
            }

            sli = await prometheus_provider.get_sli_value("nonexistent_metric")

            assert sli == 0.0

    @pytest.mark.asyncio
    async def test_get_sli_value_invalid_value(self, prometheus_provider):
        """Test SLI value returns NaN for invalid value (Prometheus behavior)."""
        import math

        with patch.object(prometheus_provider, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {}, "value": [1609459200, "NaN"]}],
                },
            }

            sli = await prometheus_provider.get_sli_value("broken_metric")

            # Prometheus returns NaN as-is, not converted to 0
            assert math.isnan(sli)


class TestGetSliTimeSeries:
    """Tests for get_sli_time_series method."""

    @pytest.mark.asyncio
    async def test_get_sli_time_series_success(self, prometheus_provider, mock_range_response):
        """Test getting SLI time series successfully."""
        with patch.object(
            prometheus_provider, "query_range", new_callable=AsyncMock
        ) as mock_query_range:
            mock_query_range.return_value = mock_range_response

            start = datetime(2021, 1, 1, 0, 0, 0)
            end = datetime(2021, 1, 1, 1, 0, 0)

            measurements = await prometheus_provider.get_sli_time_series(
                query="availability_ratio",
                start=start,
                end=end,
                step="5m",
            )

            assert len(measurements) == 4
            assert measurements[0]["sli_value"] == pytest.approx(0.999)
            assert "timestamp" in measurements[0]
            assert "duration_seconds" in measurements[0]

    @pytest.mark.asyncio
    async def test_get_sli_time_series_empty(self, prometheus_provider):
        """Test empty time series result."""
        with patch.object(
            prometheus_provider, "query_range", new_callable=AsyncMock
        ) as mock_query_range:
            mock_query_range.return_value = {
                "status": "success",
                "data": {"resultType": "matrix", "result": []},
            }

            start = datetime(2021, 1, 1)
            end = datetime(2021, 1, 2)

            measurements = await prometheus_provider.get_sli_time_series(
                query="missing_metric",
                start=start,
                end=end,
            )

            assert measurements == []


class TestHealthCheck:
    """Tests for health check method."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, prometheus_provider, mock_successful_response):
        """Test health check returns healthy status."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_successful_response

            health = await prometheus_provider.health_check()

            assert health.status == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_unreachable(self, prometheus_provider):
        """Test health check returns unreachable on error."""
        with patch.object(prometheus_provider, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = PrometheusProviderError("Connection refused")

            health = await prometheus_provider.health_check()

            assert health.status == "unreachable"
            assert "Connection refused" in health.details


class TestRequest:
    """Tests for internal _request method."""

    @pytest.mark.asyncio
    async def test_request_handles_api_error(self, prometheus_provider, mock_error_response):
        """Test that API errors are properly handled."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_error_response
            mock_response.raise_for_status = MagicMock()
            mock_client.request.return_value = mock_response

            with pytest.raises(PrometheusProviderError) as exc_info:
                await prometheus_provider._request("GET", "/api/v1/query", params={"query": "bad"})

            assert "invalid query syntax" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_handles_http_error(self, prometheus_provider):
        """Test that HTTP errors are properly handled."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.request.side_effect = httpx.HTTPError("Connection failed")

            with pytest.raises(PrometheusProviderError):
                await prometheus_provider._request("GET", "/api/v1/query", params={})


class TestParseStepToSeconds:
    """Tests for _parse_step_to_seconds helper."""

    def test_parse_seconds(self, prometheus_provider):
        """Test parsing seconds format."""
        assert prometheus_provider._parse_step_to_seconds("30s") == 30.0
        assert prometheus_provider._parse_step_to_seconds("120s") == 120.0

    def test_parse_minutes(self, prometheus_provider):
        """Test parsing minutes format."""
        assert prometheus_provider._parse_step_to_seconds("5m") == 300.0
        assert prometheus_provider._parse_step_to_seconds("15m") == 900.0

    def test_parse_hours(self, prometheus_provider):
        """Test parsing hours format."""
        assert prometheus_provider._parse_step_to_seconds("1h") == 3600.0
        assert prometheus_provider._parse_step_to_seconds("24h") == 86400.0

    def test_parse_days(self, prometheus_provider):
        """Test parsing days format."""
        assert prometheus_provider._parse_step_to_seconds("1d") == 86400.0
        assert prometheus_provider._parse_step_to_seconds("7d") == 604800.0

    def test_parse_unknown_defaults(self, prometheus_provider):
        """Test unknown format returns default."""
        assert prometheus_provider._parse_step_to_seconds("unknown") == 300.0


class TestResources:
    """Tests for resources method."""

    @pytest.mark.asyncio
    async def test_resources_returns_empty(self, prometheus_provider):
        """Test that resources returns empty list (Prometheus doesn't use plan/apply)."""
        resources = await prometheus_provider.resources()
        assert resources == []


class TestAclose:
    """Tests for aclose method."""

    @pytest.mark.asyncio
    async def test_aclose_returns_none(self, prometheus_provider):
        """Test that aclose returns None (no cleanup needed)."""
        result = await prometheus_provider.aclose()
        assert result is None
