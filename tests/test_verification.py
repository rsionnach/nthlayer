"""Tests for contract verification."""

from unittest.mock import MagicMock, patch

from nthlayer.specs.models import Resource
from nthlayer.verification import (
    MetricSource,
    extract_metric_contract,
)
from nthlayer.verification.extractor import _extract_metrics_from_query
from nthlayer.verification.models import (
    ContractVerificationResult,
    DeclaredMetric,
    MetricContract,
    VerificationResult,
)
from nthlayer.verification.verifier import MetricVerifier


class TestMetricExtraction:
    """Tests for extracting metrics from PromQL queries."""

    def test_extract_simple_metric(self):
        """Extract metric from simple rate query."""
        query = 'sum(rate(http_requests_total{service="checkout"}[5m]))'
        metrics = _extract_metrics_from_query(query)
        assert "http_requests_total" in metrics

    def test_extract_histogram_metric(self):
        """Extract metric from histogram_quantile query."""
        query = (
            "histogram_quantile(0.99, "
            'rate(http_request_duration_seconds_bucket{service="checkout"}[5m]))'
        )
        metrics = _extract_metrics_from_query(query)
        assert "http_request_duration_seconds_bucket" in metrics

    def test_extract_multiple_metrics(self):
        """Extract multiple metrics from complex query."""
        query = "sum(rate(success_total[5m])) / sum(rate(requests_total[5m]))"
        metrics = _extract_metrics_from_query(query)
        assert "success_total" in metrics
        assert "requests_total" in metrics

    def test_exclude_promql_functions(self):
        """Ensure PromQL functions are not extracted as metrics."""
        query = 'sum(rate(my_metric{label="value"}[5m]))'
        metrics = _extract_metrics_from_query(query)
        assert "sum" not in metrics
        assert "rate" not in metrics
        assert "my_metric" in metrics

    def test_exclude_histogram_quantile(self):
        """Ensure histogram_quantile is not extracted."""
        query = "histogram_quantile(0.95, rate(latency_bucket[5m]))"
        metrics = _extract_metrics_from_query(query)
        assert "histogram_quantile" not in metrics
        assert "latency_bucket" in metrics


class TestExtractMetricContract:
    """Tests for extracting metric contract from resources."""

    def test_extract_slo_metrics(self):
        """Extract metrics from SLO indicators."""
        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={
                    "indicators": [
                        {
                            "type": "availability",
                            "success_ratio": {
                                "total_query": (
                                    'sum(rate(http_requests_total{service="test"}[5m]))'
                                ),
                                "good_query": (
                                    "sum(rate(http_requests_total"
                                    '{service="test",status!~"5.."}[5m]))'
                                ),
                            },
                        }
                    ]
                },
            )
        ]

        contract = extract_metric_contract("test-service", resources)

        assert contract.service_name == "test-service"
        assert len(contract.metrics) == 1
        assert contract.metrics[0].name == "http_requests_total"
        assert contract.metrics[0].source == MetricSource.SLO_INDICATOR
        assert contract.metrics[0].is_critical

    def test_extract_latency_metrics(self):
        """Extract metrics from latency SLO indicators."""
        resources = [
            Resource(
                kind="SLO",
                name="latency-p99",
                spec={
                    "indicators": [
                        {
                            "type": "latency",
                            "latency_query": (
                                "histogram_quantile(0.99, rate("
                                'http_request_duration_seconds_bucket{service="test"}[5m]))'
                            ),
                        }
                    ]
                },
            )
        ]

        contract = extract_metric_contract("test-service", resources)

        assert len(contract.metrics) == 1
        assert contract.metrics[0].name == "http_request_duration_seconds_bucket"

    def test_extract_observability_metrics(self):
        """Extract metrics from Observability declarations."""
        resources = [
            Resource(
                kind="Observability",
                name="observability",
                spec={
                    "metrics": [
                        "checkout_started_total",
                        "checkout_completed_total",
                        "checkout_abandoned_total",
                    ]
                },
            )
        ]

        contract = extract_metric_contract("test-service", resources)

        assert len(contract.metrics) == 3
        assert all(m.source == MetricSource.OBSERVABILITY for m in contract.metrics)
        assert all(not m.is_critical for m in contract.metrics)

    def test_deduplicate_metrics(self):
        """Ensure duplicate metrics are removed."""
        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={
                    "indicators": [
                        {
                            "success_ratio": {
                                "total_query": "rate(http_requests_total[5m])",
                                "good_query": "rate(http_requests_total[5m])",
                            }
                        }
                    ]
                },
            )
        ]

        contract = extract_metric_contract("test-service", resources)

        # Should be deduplicated
        assert len(contract.metrics) == 1

    def test_mixed_resources(self):
        """Extract from both SLO and Observability resources."""
        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={
                    "indicators": [
                        {
                            "success_ratio": {
                                "total_query": "rate(http_requests_total[5m])",
                            }
                        }
                    ]
                },
            ),
            Resource(
                kind="Observability",
                name="observability",
                spec={"metrics": ["custom_metric_total"]},
            ),
        ]

        contract = extract_metric_contract("test-service", resources)

        assert len(contract.metrics) == 2
        assert len(contract.critical_metrics) == 1
        assert len(contract.optional_metrics) == 1


class TestVerificationResult:
    """Tests for verification result models."""

    def test_critical_failure(self):
        """Test critical failure detection."""
        metric = DeclaredMetric(
            name="http_requests_total",
            source=MetricSource.SLO_INDICATOR,
        )
        result = VerificationResult(metric=metric, exists=False)

        assert result.is_critical_failure

    def test_non_critical_failure(self):
        """Test non-critical failure (optional metric)."""
        metric = DeclaredMetric(
            name="custom_metric",
            source=MetricSource.OBSERVABILITY,
        )
        result = VerificationResult(metric=metric, exists=False)

        assert not result.is_critical_failure

    def test_successful_verification(self):
        """Test successful verification."""
        metric = DeclaredMetric(
            name="http_requests_total",
            source=MetricSource.SLO_INDICATOR,
        )
        result = VerificationResult(metric=metric, exists=True)

        assert not result.is_critical_failure


class TestContractVerificationResult:
    """Tests for contract verification result."""

    def test_all_verified(self):
        """Test when all metrics are verified."""
        results = [
            VerificationResult(
                metric=DeclaredMetric(name="m1", source=MetricSource.SLO_INDICATOR),
                exists=True,
            ),
            VerificationResult(
                metric=DeclaredMetric(name="m2", source=MetricSource.OBSERVABILITY),
                exists=True,
            ),
        ]

        contract_result = ContractVerificationResult(
            service_name="test",
            target_url="http://prometheus:9090",
            results=results,
        )

        assert contract_result.all_verified
        assert contract_result.critical_verified
        assert contract_result.exit_code == 0

    def test_critical_missing(self):
        """Test when critical metric is missing."""
        results = [
            VerificationResult(
                metric=DeclaredMetric(name="m1", source=MetricSource.SLO_INDICATOR),
                exists=False,
            ),
            VerificationResult(
                metric=DeclaredMetric(name="m2", source=MetricSource.OBSERVABILITY),
                exists=True,
            ),
        ]

        contract_result = ContractVerificationResult(
            service_name="test",
            target_url="http://prometheus:9090",
            results=results,
        )

        assert not contract_result.all_verified
        assert not contract_result.critical_verified
        assert len(contract_result.missing_critical) == 1
        assert contract_result.exit_code == 2

    def test_optional_missing(self):
        """Test when only optional metric is missing."""
        results = [
            VerificationResult(
                metric=DeclaredMetric(name="m1", source=MetricSource.SLO_INDICATOR),
                exists=True,
            ),
            VerificationResult(
                metric=DeclaredMetric(name="m2", source=MetricSource.OBSERVABILITY),
                exists=False,
            ),
        ]

        contract_result = ContractVerificationResult(
            service_name="test",
            target_url="http://prometheus:9090",
            results=results,
        )

        assert not contract_result.all_verified
        assert contract_result.critical_verified
        assert len(contract_result.missing_optional) == 1
        assert contract_result.exit_code == 1


class TestMetricVerifier:
    """Tests for MetricVerifier class."""

    def test_init_basic(self):
        """Test basic initialization."""
        verifier = MetricVerifier("http://prometheus:9090")

        assert verifier.prometheus_url == "http://prometheus:9090"
        assert verifier.auth is None
        assert verifier.timeout == 30.0

    def test_init_with_auth(self):
        """Test initialization with auth credentials."""
        verifier = MetricVerifier(
            "http://prometheus:9090",
            username="admin",
            password="secret",
        )

        assert verifier.auth == ("admin", "secret")

    def test_init_trailing_slash_removed(self):
        """Test trailing slash is removed from URL."""
        verifier = MetricVerifier("http://prometheus:9090/")

        assert verifier.prometheus_url == "http://prometheus:9090"

    @patch.dict(
        "os.environ", {"PROMETHEUS_USERNAME": "env_user", "PROMETHEUS_PASSWORD": "env_pass"}
    )
    def test_init_env_var_auth(self):
        """Test auth from environment variables."""
        verifier = MetricVerifier("http://prometheus:9090")

        assert verifier.auth == ("env_user", "env_pass")

    @patch("httpx.Client")
    def test_verify_metric_exists(self, mock_client_class):
        """Test verifying a metric that exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": [{"__name__": "http_requests_total", "service": "test"}],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")
        metric = DeclaredMetric(name="http_requests_total", source=MetricSource.SLO_INDICATOR)

        result = verifier.verify_metric(metric, "test-service")

        assert result.exists is True
        assert result.sample_labels == {"service": "test"}

    @patch("httpx.Client")
    def test_verify_metric_not_exists(self, mock_client_class):
        """Test verifying a metric that doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": []}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")
        metric = DeclaredMetric(name="nonexistent_metric", source=MetricSource.SLO_INDICATOR)

        result = verifier.verify_metric(metric, "test-service")

        assert result.exists is False

    @patch("httpx.Client")
    def test_verify_metric_connection_error(self, mock_client_class):
        """Test verifying metric with connection error."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")
        metric = DeclaredMetric(name="http_requests_total", source=MetricSource.SLO_INDICATOR)

        result = verifier.verify_metric(metric, "test-service")

        assert result.exists is False
        assert result.error is not None
        assert "Cannot connect" in result.error

    @patch("httpx.Client")
    def test_verify_metric_timeout(self, mock_client_class):
        """Test verifying metric with timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")
        metric = DeclaredMetric(name="http_requests_total", source=MetricSource.SLO_INDICATOR)

        result = verifier.verify_metric(metric, "test-service")

        assert result.exists is False
        assert result.error is not None
        assert "Timeout" in result.error

    @patch("httpx.Client")
    def test_verify_contract(self, mock_client_class):
        """Test verifying a full contract."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": [{"__name__": "http_requests_total", "service": "test"}],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")
        contract = MetricContract(
            service_name="test-service",
            metrics=[
                DeclaredMetric(name="http_requests_total", source=MetricSource.SLO_INDICATOR),
                DeclaredMetric(name="http_duration_seconds", source=MetricSource.OBSERVABILITY),
            ],
        )

        result = verifier.verify_contract(contract)

        assert result.service_name == "test-service"
        assert result.target_url == "http://prometheus:9090"
        assert len(result.results) == 2

    @patch("httpx.Client")
    def test_test_connection_success(self, mock_client_class):
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")

        assert verifier.test_connection() is True

    @patch("httpx.Client")
    def test_test_connection_failure(self, mock_client_class):
        """Test failed connection test."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")

        assert verifier.test_connection() is False

    @patch("httpx.Client")
    def test_test_connection_exception(self, mock_client_class):
        """Test connection test with exception."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")

        assert verifier.test_connection() is False

    @patch("httpx.Client")
    def test_query_series_404(self, mock_client_class):
        """Test _query_series with 404 response."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")

        exists, labels = verifier._query_series("nonexistent{}")

        assert exists is False
        assert labels is None

    @patch("httpx.Client")
    def test_check_metric_falls_back_to_no_service_label(self, mock_client_class):
        """Test _check_metric_exists falls back when service label not found."""
        # First call with service label returns empty
        # Second call without service label returns data
        mock_response_empty = MagicMock()
        mock_response_empty.status_code = 200
        mock_response_empty.json.return_value = {"status": "success", "data": []}

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = {
            "status": "success",
            "data": [{"__name__": "test_metric", "instance": "localhost:9090"}],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [mock_response_empty, mock_response_found]
        mock_client_class.return_value = mock_client

        verifier = MetricVerifier("http://prometheus:9090")

        exists, labels = verifier._check_metric_exists("test_metric", "test-service")

        assert exists is True
        assert labels == {"instance": "localhost:9090"}
