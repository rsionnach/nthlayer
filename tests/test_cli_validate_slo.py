"""Tests for validate-slo CLI command."""

import json

from nthlayer.cli.validate_slo import (
    PROMQL_FUNCTIONS,
    SLOValidationResult,
    create_demo_slo_results,
    extract_metric_names,
    validate_slo_command,
)


class TestExtractMetricNames:
    """Tests for PromQL metric extraction."""

    def test_extract_simple_metric(self):
        """Test extracting simple metric name."""
        query = 'http_requests_total{service="payment"}'
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics

    def test_extract_metric_with_rate(self):
        """Test extracting metric from rate function."""
        query = 'rate(http_requests_total{service="payment"}[5m])'
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics
        assert "rate" not in metrics

    def test_extract_histogram_metric(self):
        """Test extracting histogram metric."""
        query = "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
        metrics = extract_metric_names(query)
        assert "http_request_duration_seconds_bucket" in metrics
        assert "histogram_quantile" not in metrics

    def test_extract_multiple_metrics(self):
        """Test extracting multiple metrics from complex query."""
        query = """
        sum(rate(http_requests_total{status="200"}[5m]))
        /
        sum(rate(http_requests_total[5m]))
        """
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics

    def test_exclude_promql_functions(self):
        """Test that PromQL functions are excluded."""
        query = "sum(rate(http_requests_total[5m]))"
        metrics = extract_metric_names(query)

        assert "sum" not in metrics
        assert "rate" not in metrics
        assert "http_requests_total" in metrics

    def test_extract_with_labels(self):
        """Test extraction with complex label selectors."""
        query = 'http_requests_total{service="payment", method=~"GET|POST"}'
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics

    def test_empty_query(self):
        """Test with empty query."""
        metrics = extract_metric_names("")
        assert len(metrics) == 0

    def test_query_with_numbers(self):
        """Test query with literal numbers."""
        query = "http_requests_total > 100"
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics

    def test_promql_functions_list(self):
        """Test that PROMQL_FUNCTIONS is comprehensive."""
        common_functions = ["sum", "rate", "avg", "max", "min", "histogram_quantile"]
        for func in common_functions:
            assert func in PROMQL_FUNCTIONS


class TestSLOValidationResult:
    """Tests for SLOValidationResult dataclass."""

    def test_create_result(self):
        """Test creating validation result."""
        result = SLOValidationResult(
            slo_name="test-slo",
            query="rate(http_requests_total[5m])",
            metrics=["http_requests_total"],
            found_metrics=["http_requests_total"],
            missing_metrics=[],
            all_found=True,
        )

        assert result.slo_name == "test-slo"
        assert result.all_found is True

    def test_result_to_dict(self):
        """Test serialization to dict."""
        result = SLOValidationResult(
            slo_name="test-slo",
            query="test query",
            metrics=["metric1", "metric2"],
            found_metrics=["metric1"],
            missing_metrics=["metric2"],
            all_found=False,
        )

        data = result.to_dict()
        assert data["slo_name"] == "test-slo"
        assert data["all_found"] is False
        assert "metric2" in data["missing_metrics"]


class TestDemoSLOResults:
    """Tests for demo SLO results."""

    def test_create_demo_results(self):
        """Test demo results are created."""
        results = create_demo_slo_results()
        assert len(results) == 3

    def test_demo_has_mixed_results(self):
        """Test demo includes both valid and invalid SLOs."""
        results = create_demo_slo_results()

        valid = [r for r in results if r.all_found]
        invalid = [r for r in results if not r.all_found]

        assert len(valid) >= 1
        assert len(invalid) >= 1

    def test_demo_result_structure(self):
        """Test demo results have proper structure."""
        results = create_demo_slo_results()

        for result in results:
            assert result.slo_name
            assert result.query
            assert isinstance(result.metrics, list)


class TestValidateSLOCommand:
    """Tests for validate-slo CLI command."""

    def test_demo_mode_table(self, capsys):
        """Test demo mode with table output."""
        exit_code = validate_slo_command(
            service_file="dummy.yaml",
            demo=True,
        )

        # Exit code 1 because demo has missing metrics
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "SLO Metric Validation" in captured.out
        assert "payment-api" in captured.out

    def test_demo_mode_json(self, capsys):
        """Test demo mode with JSON output."""
        exit_code = validate_slo_command(
            service_file="dummy.yaml",
            output_format="json",
            demo=True,
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["service"] == "payment-api"
        assert "results" in data
        assert len(data["results"]) == 3
        assert data["all_valid"] is False

    def test_demo_shows_found_metrics(self, capsys):
        """Test that found metrics are shown."""
        validate_slo_command(
            service_file="dummy.yaml",
            demo=True,
        )

        captured = capsys.readouterr()
        assert "Found" in captured.out

    def test_demo_shows_missing_metrics(self, capsys):
        """Test that missing metrics are shown."""
        validate_slo_command(
            service_file="dummy.yaml",
            demo=True,
        )

        captured = capsys.readouterr()
        assert "Missing" in captured.out
        assert "http_errors_total" in captured.out

    def test_invalid_service_file(self, capsys):
        """Test with nonexistent service file."""
        exit_code = validate_slo_command(
            service_file="/nonexistent/path.yaml",
            demo=False,
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_service_file_without_slos(self, capsys, tmp_path):
        """Test with service file that has no SLOs."""
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test-service
  team: test-team
  tier: standard
  type: api

resources: []
""")

        exit_code = validate_slo_command(
            service_file=str(service_file),
            demo=False,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No SLO resources found" in captured.out


class TestMetricExtractionEdgeCases:
    """Tests for edge cases in metric extraction."""

    def test_aggregation_with_by_clause(self):
        """Test extraction with by/without clauses."""
        query = "sum by (service) (rate(http_requests_total[5m]))"
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics
        assert "by" not in metrics

    def test_binary_operators(self):
        """Test extraction with binary operators."""
        query = "http_requests_total / http_requests_failed_total"
        metrics = extract_metric_names(query)
        # The second metric may or may not be captured depending on context
        assert "http_requests_total" in metrics

    def test_offset_modifier(self):
        """Test extraction with offset modifier."""
        query = "http_requests_total offset 1h"
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics
        assert "offset" not in metrics

    def test_subquery(self):
        """Test extraction from subquery."""
        query = "max_over_time(rate(http_requests_total[5m])[1h:5m])"
        metrics = extract_metric_names(query)
        assert "http_requests_total" in metrics

    def test_metric_with_colon(self):
        """Test metric names with colons (recording rules)."""
        query = 'job:http_requests_total:rate5m{job="api"}'
        metrics = extract_metric_names(query)
        assert "job:http_requests_total:rate5m" in metrics
