"""
Tests for the Metrics Recommendation Engine.
"""

from nthlayer.metrics.models import (
    MetricDefinition,
    MetricType,
    RequirementLevel,
)
from nthlayer.metrics.recommender import (
    _match_metrics,
    filter_metrics_by_level,
    get_missing_required_metrics,
    get_slo_blocking_metrics,
    recommend_metrics,
)
from nthlayer.metrics.runtime import get_runtime_metrics, get_supported_runtimes
from nthlayer.metrics.standards.aliases import (
    METRIC_ALIASES,
    get_aliases_for_canonical,
    get_canonical_name,
)
from nthlayer.metrics.templates.registry import (
    get_template,
    get_template_names,
    resolve_template_metrics,
)
from nthlayer.specs.models import ServiceContext


class TestMetricAliases:
    """Tests for metric aliasing."""

    def test_get_canonical_name_known_alias(self):
        """Test getting canonical name for known alias."""
        canonical = get_canonical_name("http_requests_total")
        assert canonical == "http.server.request.duration"

    def test_get_canonical_name_unknown(self):
        """Test getting canonical name for unknown metric."""
        canonical = get_canonical_name("unknown_metric")
        assert canonical is None

    def test_get_aliases_for_canonical(self):
        """Test getting aliases for canonical name."""
        aliases = get_aliases_for_canonical("http.server.request.duration")
        assert "http_requests_total" in aliases
        assert "http_request_duration_seconds" in aliases

    def test_aliases_coverage(self):
        """Test that we have aliases for common Prometheus patterns."""
        assert "flask_http_request_duration_seconds" in METRIC_ALIASES
        assert "fastapi_requests_total" in METRIC_ALIASES
        assert "grpc_server_handled_total" in METRIC_ALIASES


class TestTemplateRegistry:
    """Tests for template registry."""

    def test_get_template_api(self):
        """Test getting API template."""
        template = get_template("api")
        assert template is not None
        assert template.name == "api"
        assert len(template.required) > 0

    def test_get_template_aliases(self):
        """Test that aliases work."""
        api_template = get_template("api")
        web_template = get_template("web")
        assert web_template == api_template

    def test_get_template_unknown(self):
        """Test getting unknown template returns None."""
        template = get_template("unknown-type")
        assert template is None

    def test_get_template_names(self):
        """Test getting list of template names."""
        names = get_template_names()
        assert "api" in names
        assert "grpc" in names
        assert "worker" in names
        assert "queue-consumer" in names

    def test_resolve_template_metrics_required(self):
        """Test resolving required metrics."""
        template = get_template("api")
        metrics = resolve_template_metrics(template, "required")
        assert len(metrics) > 0
        assert all(m.requirement_level == RequirementLevel.REQUIRED for m in metrics)

    def test_resolve_template_metrics_inheritance(self):
        """Test that gateway inherits from api."""
        gateway_template = get_template("gateway")
        assert gateway_template.extends == "api"

        metrics = resolve_template_metrics(gateway_template, "required")
        metric_names = [m.name for m in metrics]
        # Should have both api metrics and gateway-specific metrics
        assert "http.server.request.duration" in metric_names
        assert "http.client.request.duration" in metric_names


class TestRuntimeMetrics:
    """Tests for runtime-specific metrics."""

    def test_get_python_metrics(self):
        """Test getting Python runtime metrics."""
        metrics = get_runtime_metrics("python")
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        assert "process.runtime.cpython.gc_count" in metric_names

    def test_get_jvm_metrics(self):
        """Test getting JVM runtime metrics."""
        metrics = get_runtime_metrics("java")  # Should alias to JVM
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        # Using official OTel semconv metric name
        assert "process.runtime.jvm.memory.usage" in metric_names

    def test_get_go_metrics(self):
        """Test getting Go runtime metrics."""
        metrics = get_runtime_metrics("go")
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        assert "process.runtime.go.goroutines" in metric_names

    def test_get_nodejs_metrics(self):
        """Test getting Node.js runtime metrics."""
        metrics = get_runtime_metrics("nodejs")
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        assert "process.runtime.nodejs.event_loop.lag" in metric_names

    def test_get_unknown_runtime(self):
        """Test getting metrics for unknown runtime."""
        metrics = get_runtime_metrics("unknown")
        assert metrics == []

    def test_get_none_runtime(self):
        """Test getting metrics when runtime is None."""
        metrics = get_runtime_metrics(None)
        assert metrics == []

    def test_supported_runtimes(self):
        """Test getting supported runtimes list."""
        runtimes = get_supported_runtimes()
        assert "python" in runtimes
        assert "jvm" in runtimes
        assert "go" in runtimes
        assert "nodejs" in runtimes


class TestMatchMetrics:
    """Tests for metric matching logic."""

    def test_direct_match(self):
        """Test direct metric name match."""
        definitions = [
            MetricDefinition(
                name="http.server.request.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        discovered = ["http.server.request.duration"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        assert matches[0].status == "found"
        assert matches[0].match_confidence == 1.0

    def test_aliased_match(self):
        """Test matching via alias."""
        definitions = [
            MetricDefinition(
                name="http.server.request.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        discovered = ["http_request_duration_seconds"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        assert matches[0].status == "aliased"
        assert matches[0].found_as == "http_request_duration_seconds"

    def test_missing_metric(self):
        """Test missing metric detection."""
        definitions = [
            MetricDefinition(
                name="http.server.request.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        discovered = ["some_other_metric"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        assert matches[0].status == "missing"

    def test_unknown_when_no_discovery(self):
        """Test unknown status when discovery not performed."""
        definitions = [
            MetricDefinition(
                name="http.server.request.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        matches = _match_metrics(definitions, None)

        assert len(matches) == 1
        assert matches[0].status == "unknown"


class TestRecommendMetrics:
    """Tests for the main recommend_metrics function."""

    def test_recommend_api_service(self):
        """Test recommendations for API service."""
        context = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        assert result.service == "payment-api"
        assert result.service_type == "api"
        assert result.tier == "critical"
        assert len(result.required) > 0
        assert len(result.recommended) > 0

    def test_recommend_with_runtime(self):
        """Test recommendations include runtime metrics."""
        context = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
            language="python",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        assert result.runtime == "python"
        assert len(result.runtime_metrics) > 0

    def test_recommend_worker_service(self):
        """Test recommendations for worker service."""
        context = ServiceContext(
            name="task-processor",
            team="platform",
            tier="standard",
            type="worker",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        assert result.service_type == "worker"
        required_names = [m.definition.name for m in result.required]
        assert "jobs.duration" in required_names
        assert "jobs.total" in required_names

    def test_slo_ready_all_found(self):
        """Test SLO readiness when all required metrics found."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        # Provide the required metric
        discovered = ["http.server.request.duration"]
        result = recommend_metrics(context, discovered)

        assert result.slo_ready is True
        assert result.required_coverage == 1.0

    def test_slo_not_ready_missing(self):
        """Test SLO not ready when required metrics missing."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        discovered = ["some_unrelated_metric"]
        result = recommend_metrics(context, discovered)

        assert result.slo_ready is False
        assert result.required_coverage < 1.0

    def test_fallback_to_api_for_unknown_type(self):
        """Test that unknown service types fall back to API template."""
        context = ServiceContext(
            name="mystery-service",
            team="test",
            tier="standard",
            type="unknown-type",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        # Should use API template as fallback
        assert result.service_type == "api"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_missing_required_metrics(self):
        """Test getting list of missing required metrics."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=[])

        missing = get_missing_required_metrics(result)
        assert len(missing) > 0
        assert all(isinstance(m, MetricDefinition) for m in missing)

    def test_get_slo_blocking_metrics(self):
        """Test getting SLO-blocking metrics."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=[])

        blocking = get_slo_blocking_metrics(result)
        assert len(blocking) > 0
        # All blocking metrics should have slo_usage
        assert all(m.slo_usage for m in blocking)

    def test_filter_metrics_by_level_required(self):
        """Test filtering by required level."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        filtered = filter_metrics_by_level(result, "required")
        assert filtered == result.required

    def test_filter_metrics_by_level_all(self):
        """Test filtering by all level."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
            language="python",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        filtered = filter_metrics_by_level(result, "all")
        total = len(result.required) + len(result.recommended) + len(result.runtime_metrics)
        assert len(filtered) == total


class TestMatchMetricsAdvanced:
    """Tests for advanced metric matching scenarios."""

    def test_reverse_alias_lookup(self):
        """Test matching via reverse alias lookup (discovered name maps to canonical)."""
        # The reverse lookup happens when discovered name is in METRIC_ALIASES
        # but the forward lookup (canonical -> alias list) didn't find it
        definitions = [
            MetricDefinition(
                name="http.server.request.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        # Use a metric that's in METRIC_ALIASES but might not be in the alias list
        discovered = ["flask_http_request_duration_seconds"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        assert matches[0].status in ("aliased", "found")

    def test_fuzzy_match_prometheus_style(self):
        """Test fuzzy matching for Prometheus-style metric names."""
        definitions = [
            MetricDefinition(
                name="custom.metric.duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Custom metric",
            )
        ]
        # Prometheus-style name that partially matches
        discovered = ["custom_metric_duration_seconds_bucket"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        # Should find via fuzzy match
        assert matches[0].status == "aliased"
        assert matches[0].match_confidence == 0.7

    def test_filter_metrics_by_level_recommended(self):
        """Test filtering by recommended level."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        filtered = filter_metrics_by_level(result, "recommended")
        assert filtered == result.recommended

    def test_case_insensitive_matching(self):
        """Test that matching is case insensitive."""
        definitions = [
            MetricDefinition(
                name="HTTP.Server.Request.Duration",
                type=MetricType.HISTOGRAM,
                unit="seconds",
                description="Test metric",
            )
        ]
        discovered = ["http.server.request.duration"]
        matches = _match_metrics(definitions, discovered)

        assert len(matches) == 1
        assert matches[0].status == "found"


class TestRecommendMetricsEdgeCases:
    """Tests for edge cases in recommendation logic."""

    def test_empty_required_metrics_coverage(self):
        """Test coverage is 1.0 when template has no required metrics."""
        from unittest.mock import patch

        from nthlayer.metrics.models import ServiceTypeTemplate

        # Create a template with no required metrics
        empty_template = ServiceTypeTemplate(
            name="empty",
            required=[],
            recommended=[],
        )

        context = ServiceContext(
            name="test",
            team="test",
            tier="standard",
            type="api",
        )

        with (
            patch("nthlayer.metrics.recommender.get_template") as mock_get_template,
            patch("nthlayer.metrics.recommender.resolve_template_metrics") as mock_resolve,
        ):
            mock_get_template.return_value = empty_template
            mock_resolve.return_value = []

            result = recommend_metrics(context, discovered_metrics=[])

            assert result.required_coverage == 1.0
            assert result.recommended_coverage == 1.0
            assert result.slo_ready is True


class TestMetricRecommendationSerialization:
    """Tests for MetricRecommendation serialization."""

    def test_to_dict(self):
        """Test converting recommendation to dictionary."""
        context = ServiceContext(
            name="test-api",
            team="test",
            tier="standard",
            type="api",
        )
        result = recommend_metrics(context, discovered_metrics=None)

        data = result.to_dict()
        assert data["service"] == "test-api"
        assert data["service_type"] == "api"
        assert data["tier"] == "standard"
        assert "required" in data
        assert "recommended" in data
        assert "summary" in data
        assert "required_coverage" in data["summary"]
        assert "slo_ready" in data["summary"]
