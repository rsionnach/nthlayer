"""Tests for contract verification."""

from nthlayer.specs.models import Resource
from nthlayer.verification import (
    MetricSource,
    extract_metric_contract,
)
from nthlayer.verification.extractor import _extract_metrics_from_query
from nthlayer.verification.models import (
    ContractVerificationResult,
    DeclaredMetric,
    VerificationResult,
)


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
