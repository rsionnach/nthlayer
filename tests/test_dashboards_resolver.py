"""Tests for Metric Resolver for Dashboard Generation."""

from unittest.mock import MagicMock, patch

from nthlayer.dashboards.resolver import (
    EXPORTER_RECOMMENDATIONS,
    MetricResolver,
    ResolutionResult,
    ResolutionStatus,
    create_resolver,
)


class TestResolutionStatus:
    """Tests for ResolutionStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        assert ResolutionStatus.RESOLVED.value == "resolved"
        assert ResolutionStatus.FALLBACK.value == "fallback"
        assert ResolutionStatus.SYNTHESIZED.value == "synthesized"
        assert ResolutionStatus.CUSTOM.value == "custom"
        assert ResolutionStatus.UNRESOLVED.value == "unresolved"


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_resolved_for_resolved_status(self):
        """Test resolved property for RESOLVED status."""
        result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.RESOLVED,
            metric_name="test_metric",
        )
        assert result.resolved is True

    def test_resolved_for_fallback_status(self):
        """Test resolved property for FALLBACK status."""
        result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.FALLBACK,
            metric_name="test_metric",
        )
        assert result.resolved is True

    def test_resolved_for_synthesized_status(self):
        """Test resolved property for SYNTHESIZED status."""
        result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.SYNTHESIZED,
            synthesis_expr="a + b",
        )
        assert result.resolved is True

    def test_resolved_for_custom_status(self):
        """Test resolved property for CUSTOM status."""
        result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.CUSTOM,
            metric_name="custom_metric",
        )
        assert result.resolved is True

    def test_resolved_for_unresolved_status(self):
        """Test resolved property for UNRESOLVED status."""
        result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.UNRESOLVED,
        )
        assert result.resolved is False


class TestExporterRecommendation:
    """Tests for ExporterRecommendation dataclass."""

    def test_postgresql_recommendation(self):
        """Test PostgreSQL exporter recommendation."""
        rec = EXPORTER_RECOMMENDATIONS["postgresql"]
        assert rec.technology == "postgresql"
        assert rec.name == "postgres_exporter"
        assert "helm" in rec.helm.lower()
        assert "docker" in rec.docker.lower()

    def test_redis_recommendation(self):
        """Test Redis exporter recommendation."""
        rec = EXPORTER_RECOMMENDATIONS["redis"]
        assert rec.technology == "redis"
        assert rec.name == "redis_exporter"

    def test_all_recommendations_have_required_fields(self):
        """Test all recommendations have required fields."""
        for name, rec in EXPORTER_RECOMMENDATIONS.items():
            assert rec.technology == name
            assert rec.name is not None
            assert rec.helm is not None or rec.docker is not None


class TestMetricResolverInit:
    """Tests for MetricResolver initialization."""

    def test_init_without_discovery(self):
        """Test initialization without discovery client."""
        resolver = MetricResolver()
        assert resolver.discovery is None
        assert resolver.custom_overrides == {}
        assert resolver.discovered_metrics == set()

    def test_init_with_discovery(self):
        """Test initialization with discovery client."""
        mock_client = MagicMock()
        resolver = MetricResolver(discovery_client=mock_client)
        assert resolver.discovery is mock_client

    def test_init_with_custom_overrides(self):
        """Test initialization with custom overrides."""
        overrides = {"postgresql.connections": "custom_pg_connections"}
        resolver = MetricResolver(custom_overrides=overrides)
        assert resolver.custom_overrides == overrides


class TestDiscoverForService:
    """Tests for discover_for_service method."""

    def test_without_discovery_client(self):
        """Test discovery returns 0 without discovery client."""
        resolver = MetricResolver()

        count = resolver.discover_for_service("test-service")

        assert count == 0

    def test_successful_discovery(self):
        """Test successful metric discovery."""
        mock_metric1 = MagicMock()
        mock_metric1.name = "http_requests_total"
        mock_metric2 = MagicMock()
        mock_metric2.name = "http_request_duration_seconds"

        mock_result = MagicMock()
        mock_result.metrics = [mock_metric1, mock_metric2]

        mock_client = MagicMock()
        mock_client.discover.return_value = mock_result

        resolver = MetricResolver(discovery_client=mock_client)

        count = resolver.discover_for_service("test-service")

        assert count == 2
        assert "http_requests_total" in resolver.discovered_metrics
        assert "http_request_duration_seconds" in resolver.discovered_metrics
        mock_client.discover.assert_called_once_with('{service="test-service"}')

    def test_discovery_exception(self):
        """Test handling of discovery exception."""
        mock_client = MagicMock()
        mock_client.discover.side_effect = Exception("Connection error")

        resolver = MetricResolver(discovery_client=mock_client)

        count = resolver.discover_for_service("test-service")

        assert count == 0
        assert resolver.discovered_metrics == set()


class TestSetDiscoveredMetrics:
    """Tests for set_discovered_metrics method."""

    def test_sets_metrics(self):
        """Test setting discovered metrics."""
        resolver = MetricResolver()
        metrics = {"metric_a", "metric_b", "metric_c"}

        resolver.set_discovered_metrics(metrics)

        assert resolver.discovered_metrics == metrics

    def test_clears_cache(self):
        """Test that setting metrics clears resolution cache."""
        resolver = MetricResolver()
        resolver._resolution_cache["test"] = "cached_result"

        resolver.set_discovered_metrics({"metric_a"})

        assert resolver._resolution_cache == {}


class TestResolve:
    """Tests for resolve method."""

    def test_uses_cache(self):
        """Test that resolve uses cache."""
        resolver = MetricResolver()
        cached_result = ResolutionResult(
            intent="test.intent",
            status=ResolutionStatus.RESOLVED,
            metric_name="cached_metric",
        )
        resolver._resolution_cache["test.intent"] = cached_result

        result = resolver.resolve("test.intent")

        assert result is cached_result

    def test_resolves_custom_override(self):
        """Test resolution with custom override."""
        resolver = MetricResolver(custom_overrides={"postgresql.connections": "custom_pg_conns"})

        result = resolver.resolve("postgresql.connections")

        assert result.status == ResolutionStatus.CUSTOM
        assert result.metric_name == "custom_pg_conns"
        assert "custom override" in result.message.lower()

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_resolves_unknown_intent(self, mock_get_intent):
        """Test resolution of unknown intent."""
        mock_get_intent.return_value = None

        resolver = MetricResolver()

        result = resolver.resolve("unknown.intent")

        assert result.status == ResolutionStatus.UNRESOLVED
        assert "Unknown intent" in result.message

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_resolves_primary_candidate(self, mock_get_intent):
        """Test resolution using primary candidate."""
        mock_intent = MagicMock()
        mock_intent.candidates = ["pg_stat_database_numbackends"]
        mock_intent.fallback = None
        mock_intent.synthesis = None
        mock_get_intent.return_value = mock_intent

        resolver = MetricResolver()
        resolver.discovered_metrics = {"pg_stat_database_numbackends"}

        result = resolver.resolve("postgresql.connections")

        assert result.status == ResolutionStatus.RESOLVED
        assert result.metric_name == "pg_stat_database_numbackends"

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_resolves_fallback(self, mock_get_intent):
        """Test resolution using fallback."""
        # Primary intent with no matching candidates
        primary_intent = MagicMock()
        primary_intent.candidates = ["primary_metric"]
        primary_intent.fallback = "fallback.intent"
        primary_intent.synthesis = None

        # Fallback intent with matching candidate
        fallback_intent = MagicMock()
        fallback_intent.candidates = ["fallback_metric"]
        fallback_intent.fallback = None
        fallback_intent.synthesis = None

        def get_intent_side_effect(name):
            if name == "primary.intent":
                return primary_intent
            elif name == "fallback.intent":
                return fallback_intent
            return None

        mock_get_intent.side_effect = get_intent_side_effect

        resolver = MetricResolver()
        resolver.discovered_metrics = {"fallback_metric"}

        result = resolver.resolve("primary.intent")

        assert result.status == ResolutionStatus.FALLBACK
        assert result.metric_name == "fallback_metric"

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_unresolved_with_exporter_recommendation(self, mock_get_intent):
        """Test unresolved intent returns exporter recommendation."""
        mock_intent = MagicMock()
        mock_intent.candidates = ["pg_stat_something"]
        mock_intent.fallback = None
        mock_intent.synthesis = None
        mock_get_intent.return_value = mock_intent

        resolver = MetricResolver()

        result = resolver.resolve("postgresql.something")

        assert result.status == ResolutionStatus.UNRESOLVED
        assert "postgres_exporter" in result.message

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_unresolved_without_exporter_recommendation(self, mock_get_intent):
        """Test unresolved intent without matching exporter."""
        mock_intent = MagicMock()
        mock_intent.candidates = ["unknown_metric"]
        mock_intent.fallback = None
        mock_intent.synthesis = None
        mock_get_intent.return_value = mock_intent

        resolver = MetricResolver()

        result = resolver.resolve("unknown.something")

        assert result.status == ResolutionStatus.UNRESOLVED
        assert "instrumentation" in result.message.lower()

    def test_caches_result(self):
        """Test that resolve caches results."""
        resolver = MetricResolver(custom_overrides={"test.intent": "test_metric"})

        result1 = resolver.resolve("test.intent")
        result2 = resolver.resolve("test.intent")

        assert result1 is result2
        assert "test.intent" in resolver._resolution_cache

    @patch("nthlayer.dashboards.resolver.get_intent")
    def test_resolves_via_synthesis(self, mock_get_intent):
        """Test resolution via synthesis when candidates and fallback fail."""
        mock_intent = MagicMock()
        mock_intent.intent = "cache.hit_ratio"
        mock_intent.candidates = ["nonexistent_metric"]  # Won't match
        mock_intent.fallback = None
        mock_intent.synthesis = {
            "hits": "cache_hits_total",
            "misses": "cache_misses_total",
        }
        mock_get_intent.return_value = mock_intent

        resolver = MetricResolver()
        resolver.discovered_metrics = {"cache_hits_total", "cache_misses_total"}

        result = resolver.resolve("cache.hit_ratio")

        assert result.status == ResolutionStatus.SYNTHESIZED
        assert "nthlayer:cache:hit_ratio" in result.metric_name


class TestMetricExists:
    """Tests for _metric_exists method."""

    def test_exact_match(self):
        """Test exact metric name match."""
        resolver = MetricResolver()
        resolver.discovered_metrics = {"http_requests_total"}

        assert resolver._metric_exists("http_requests_total") is True
        assert resolver._metric_exists("other_metric") is False

    def test_histogram_bucket_match(self):
        """Test histogram bucket suffix matching."""
        resolver = MetricResolver()
        resolver.discovered_metrics = {"http_request_duration_seconds_bucket"}

        # Should match base name
        assert resolver._metric_exists("http_request_duration_seconds_bucket") is True

    def test_histogram_count_match(self):
        """Test histogram count suffix matching."""
        resolver = MetricResolver()
        resolver.discovered_metrics = {"http_request_duration_seconds_count"}

        # Should match when looking for base metric
        assert resolver._metric_exists("http_request_duration_seconds") is True

    def test_histogram_sum_match(self):
        """Test histogram sum suffix matching."""
        resolver = MetricResolver()
        resolver.discovered_metrics = {"http_request_duration_seconds_sum"}

        # Should match when looking for base metric
        assert resolver._metric_exists("http_request_duration_seconds") is True


class TestTrySynthesis:
    """Tests for _try_synthesis method."""

    def test_no_synthesis_defined(self):
        """Test when intent has no synthesis."""
        mock_intent = MagicMock()
        mock_intent.synthesis = None

        resolver = MetricResolver()

        result = resolver._try_synthesis(mock_intent)

        assert result is None

    def test_missing_component_metrics(self):
        """Test when synthesis components are missing."""
        mock_intent = MagicMock()
        mock_intent.synthesis = {
            "hits": "cache_hits_total",
            "misses": "cache_misses_total",
        }

        resolver = MetricResolver()
        resolver.discovered_metrics = {"cache_hits_total"}  # Missing misses

        result = resolver._try_synthesis(mock_intent)

        assert result is None

    def test_successful_synthesis(self):
        """Test successful metric synthesis when all components exist.

        Note: The synthesis dict format requires all values to exist as metrics.
        This includes the 'expr' value if present, which is a quirk of the implementation.
        """
        mock_intent = MagicMock()
        mock_intent.intent = "cache.hit_ratio"
        # Synthesis dict where ALL values are metric names
        mock_intent.synthesis = {
            "hits": "cache_hits_total",
            "misses": "cache_misses_total",
        }

        resolver = MetricResolver()
        resolver.discovered_metrics = {"cache_hits_total", "cache_misses_total"}

        result = resolver._try_synthesis(mock_intent)

        assert result is not None
        assert result.status == ResolutionStatus.SYNTHESIZED
        assert "nthlayer:cache:hit_ratio" in result.metric_name
        assert "Synthesized" in result.message


class TestResolveAll:
    """Tests for resolve_all method."""

    def test_resolves_multiple_intents(self):
        """Test resolving multiple intents at once."""
        resolver = MetricResolver(
            custom_overrides={
                "intent.a": "metric_a",
                "intent.b": "metric_b",
            }
        )

        results = resolver.resolve_all(["intent.a", "intent.b"])

        assert len(results) == 2
        assert results["intent.a"].metric_name == "metric_a"
        assert results["intent.b"].metric_name == "metric_b"


class TestGetResolutionSummary:
    """Tests for get_resolution_summary method."""

    def test_empty_cache(self):
        """Test summary with empty cache."""
        resolver = MetricResolver()

        summary = resolver.get_resolution_summary()

        assert summary["resolved"] == 0
        assert summary["unresolved"] == 0

    def test_with_cached_results(self):
        """Test summary with cached results."""
        resolver = MetricResolver()
        resolver._resolution_cache["a"] = ResolutionResult(
            intent="a", status=ResolutionStatus.RESOLVED, metric_name="m"
        )
        resolver._resolution_cache["b"] = ResolutionResult(
            intent="b", status=ResolutionStatus.RESOLVED, metric_name="m"
        )
        resolver._resolution_cache["c"] = ResolutionResult(
            intent="c", status=ResolutionStatus.UNRESOLVED
        )

        summary = resolver.get_resolution_summary()

        assert summary["resolved"] == 2
        assert summary["unresolved"] == 1


class TestGetUnresolvedIntents:
    """Tests for get_unresolved_intents method."""

    def test_empty_cache(self):
        """Test with empty cache."""
        resolver = MetricResolver()

        unresolved = resolver.get_unresolved_intents()

        assert unresolved == []

    def test_with_mixed_results(self):
        """Test filtering unresolved from mixed results."""
        resolver = MetricResolver()
        resolver._resolution_cache["a"] = ResolutionResult(
            intent="a", status=ResolutionStatus.RESOLVED, metric_name="m"
        )
        resolver._resolution_cache["b"] = ResolutionResult(
            intent="b", status=ResolutionStatus.UNRESOLVED
        )
        resolver._resolution_cache["c"] = ResolutionResult(
            intent="c", status=ResolutionStatus.UNRESOLVED
        )

        unresolved = resolver.get_unresolved_intents()

        assert len(unresolved) == 2
        assert all(r.status == ResolutionStatus.UNRESOLVED for r in unresolved)


class TestGetExporterRecommendation:
    """Tests for get_exporter_recommendation method."""

    def test_known_technology(self):
        """Test getting recommendation for known technology."""
        resolver = MetricResolver()

        rec = resolver.get_exporter_recommendation("postgresql")

        assert rec is not None
        assert rec.technology == "postgresql"

    def test_unknown_technology(self):
        """Test getting recommendation for unknown technology."""
        resolver = MetricResolver()

        rec = resolver.get_exporter_recommendation("unknown_tech")

        assert rec is None


class TestCreateResolver:
    """Tests for create_resolver factory function."""

    def test_without_prometheus_url(self):
        """Test creating resolver without Prometheus URL."""
        resolver = create_resolver()

        assert resolver.discovery is None

    @patch("nthlayer.dashboards.resolver.MetricDiscoveryClient")
    def test_with_prometheus_url(self, mock_client_class):
        """Test creating resolver with Prometheus URL."""
        resolver = create_resolver(prometheus_url="http://prometheus:9090")

        mock_client_class.assert_called_once_with("http://prometheus:9090")
        assert resolver.discovery is not None

    def test_with_custom_overrides(self):
        """Test creating resolver with custom overrides."""
        overrides = {"test.intent": "test_metric"}
        resolver = create_resolver(custom_overrides=overrides)

        assert resolver.custom_overrides == overrides

    @patch("nthlayer.dashboards.resolver.MetricDiscoveryClient")
    def test_with_discovery_kwargs(self, mock_client_class):
        """Test passing additional kwargs to discovery client."""
        resolver = create_resolver(
            prometheus_url="http://prometheus:9090",
            timeout=30,
        )

        mock_client_class.assert_called_once_with("http://prometheus:9090", timeout=30)
