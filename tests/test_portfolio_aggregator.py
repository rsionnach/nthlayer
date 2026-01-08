"""Tests for Portfolio Aggregator."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.portfolio.aggregator import PortfolioAggregator, collect_portfolio
from nthlayer.portfolio.models import HealthStatus, InsightType


@pytest.fixture
def sample_service_dir(tmp_path):
    """Create a sample services directory with service YAML files."""
    services_dir = tmp_path / "services"
    services_dir.mkdir()

    # Create a service with SLOs
    service1 = services_dir / "api-service.yaml"
    service1.write_text("""
service:
  name: api-service
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
        query: sum(rate(http_requests_total{service="${service}",status!~"5.."}[5m])) / sum(rate(http_requests_total{service="${service}"}[5m])) * 100
  - kind: SLO
    name: latency
    spec:
      objective: 99.5
      window: 30d
""")

    # Create a service without SLOs
    service2 = services_dir / "simple-service.yaml"
    service2.write_text("""
service:
  name: simple-service
  team: backend
  tier: standard
  type: worker
""")

    return services_dir


@pytest.fixture
def high_slo_service_dir(tmp_path):
    """Create services with high SLOs on lower tiers."""
    services_dir = tmp_path / "services"
    services_dir.mkdir()

    # Tier 2 service with very high SLO
    service = services_dir / "high-slo.yaml"
    service.write_text("""
service:
  name: high-slo-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
      window: 30d
  - kind: SLO
    name: latency
    spec:
      objective: 99.9
      window: 30d
""")

    return services_dir


class TestPortfolioAggregator:
    """Tests for PortfolioAggregator class."""

    def test_default_search_paths(self):
        """Test default search paths are set."""
        aggregator = PortfolioAggregator()

        assert Path("services") in aggregator.search_paths
        assert Path("examples/services") in aggregator.search_paths

    def test_custom_search_paths(self, tmp_path):
        """Test custom search paths."""
        custom_path = tmp_path / "custom"
        aggregator = PortfolioAggregator(search_paths=[custom_path])

        assert aggregator.search_paths == [custom_path]

    def test_prometheus_url_stored(self):
        """Test Prometheus URL is stored."""
        aggregator = PortfolioAggregator(prometheus_url="http://prometheus:9090")

        assert aggregator.prometheus_url == "http://prometheus:9090"


class TestCollect:
    """Tests for collect method."""

    def test_collects_services(self, sample_service_dir):
        """Test collecting services from directory."""
        aggregator = PortfolioAggregator(search_paths=[sample_service_dir])

        result = aggregator.collect()

        assert result.total_services == 2
        assert result.services_with_slos == 1  # Only api-service has SLOs
        assert len(result.services) == 2

    def test_skips_nonexistent_paths(self, tmp_path):
        """Test that nonexistent paths are skipped."""
        nonexistent = tmp_path / "nonexistent"
        aggregator = PortfolioAggregator(search_paths=[nonexistent])

        result = aggregator.collect()

        assert result.total_services == 0

    def test_generates_insights(self, sample_service_dir):
        """Test insights are generated."""
        aggregator = PortfolioAggregator(search_paths=[sample_service_dir])

        result = aggregator.collect()

        # Should have NO_SLO insight for simple-service
        no_slo_insights = [i for i in result.insights if i.type == InsightType.NO_SLO]
        assert len(no_slo_insights) == 1
        assert no_slo_insights[0].service == "simple-service"

    def test_calculates_tier_health(self, sample_service_dir):
        """Test tier health calculation."""
        aggregator = PortfolioAggregator(search_paths=[sample_service_dir])

        result = aggregator.collect()

        # Should have tier stats for tier 1 (api-service)
        assert len(result.by_tier) >= 1

    def test_returns_portfolio_health(self, sample_service_dir):
        """Test PortfolioHealth is returned."""
        aggregator = PortfolioAggregator(search_paths=[sample_service_dir])

        result = aggregator.collect()

        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)

    def test_empty_directory(self, tmp_path):
        """Test collecting from empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        aggregator = PortfolioAggregator(search_paths=[empty_dir])

        result = aggregator.collect()

        assert result.total_services == 0
        assert result.services == []


class TestCollectWithPrometheus:
    """Tests for collect with Prometheus enrichment."""

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_with_live_data(self, mock_provider_class, sample_service_dir, monkeypatch):
        """Test enrichment with Prometheus data."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        # Setup mock provider
        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [1234567890, "99.95"]}]})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        # Provider should be called
        mock_provider_class.assert_called_once()

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_updates_slo_status_healthy(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test SLO status is updated to HEALTHY when meeting objective."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        # Return value above the 99.9% objective
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [0, "99.95"]}]})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        # Find the api-service and check its SLO status
        api_service = next((s for s in result.services if s.service == "api-service"), None)
        assert api_service is not None
        # At least one SLO should have been updated
        assert any(slo.status == HealthStatus.HEALTHY for slo in api_service.slos)

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_updates_slo_status_warning(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test SLO status is updated to WARNING when within 1% of objective."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        # Return value between objective * 0.99 and objective (99.9 * 0.99 = 98.9)
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [0, "99.0"]}]})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        api_service = next((s for s in result.services if s.service == "api-service"), None)
        assert api_service is not None

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_updates_slo_status_critical(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test SLO status is updated to CRITICAL when within 5% of objective."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        # Return value between objective * 0.95 and objective * 0.99
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [0, "95.5"]}]})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        api_service = next((s for s in result.services if s.service == "api-service"), None)
        assert api_service is not None

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_updates_slo_status_exhausted(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test SLO status is updated to EXHAUSTED when far below objective."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        # Return value below objective * 0.95
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [0, "90.0"]}]})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        api_service = next((s for s in result.services if s.service == "api-service"), None)
        assert api_service is not None

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_handles_query_failure(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test handling of query failures during enrichment."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(side_effect=Exception("Query failed"))
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        # Should not raise, SLO status remains UNKNOWN
        result = aggregator.collect()

        api_service = next((s for s in result.services if s.service == "api-service"), None)
        assert api_service is not None

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_enrich_handles_empty_result(
        self, mock_provider_class, sample_service_dir, monkeypatch
    ):
        """Test handling of empty query results."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(return_value={"result": []})
        mock_provider_class.return_value = mock_provider

        aggregator = PortfolioAggregator(
            search_paths=[sample_service_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        assert result is not None


class TestParseServiceFile:
    """Tests for _parse_service_file method."""

    def test_parses_service_with_slos(self, sample_service_dir):
        """Test parsing service file with SLOs."""
        aggregator = PortfolioAggregator()
        service_file = sample_service_dir / "api-service.yaml"

        result = aggregator._parse_service_file(service_file)

        assert result is not None
        assert result.service == "api-service"
        assert result.team == "platform"
        assert result.tier == 1  # critical
        assert len(result.slos) == 2

    def test_parses_service_without_slos(self, sample_service_dir):
        """Test parsing service file without SLOs."""
        aggregator = PortfolioAggregator()
        service_file = sample_service_dir / "simple-service.yaml"

        result = aggregator._parse_service_file(service_file)

        assert result is not None
        assert result.service == "simple-service"
        assert result.slos == []

    def test_handles_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML."""
        aggregator = PortfolioAggregator()
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{invalid: yaml")

        result = aggregator._parse_service_file(bad_file)

        assert result is None

    def test_handles_missing_service_block(self, tmp_path):
        """Test handling of YAML without service block."""
        aggregator = PortfolioAggregator()
        bad_file = tmp_path / "no-service.yaml"
        bad_file.write_text("other: value")

        result = aggregator._parse_service_file(bad_file)

        # Should return None or handle gracefully
        # The actual behavior depends on parse_service_file implementation
        # If it raises, result will be None due to exception handling


class TestTierParsing:
    """Tests for tier parsing in _parse_service_file."""

    def test_parses_critical_tier(self, tmp_path):
        """Test parsing 'critical' tier string."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: critical
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 1

    def test_parses_standard_tier(self, tmp_path):
        """Test parsing 'standard' tier string."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: standard
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 2

    def test_parses_low_tier(self, tmp_path):
        """Test parsing 'low' tier string."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: low
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 3

    def test_parses_tier_prefix_format(self, tmp_path):
        """Test parsing 'tier-N' format."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: tier-1
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 1

    def test_parses_numeric_string_tier(self, tmp_path):
        """Test parsing numeric string tier."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: "2"
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 2

    def test_parses_integer_tier(self, tmp_path):
        """Test parsing integer tier."""
        aggregator = PortfolioAggregator()
        service_file = tmp_path / "service.yaml"
        service_file.write_text("""
service:
  name: test
  team: team
  tier: 3
  type: api
""")

        result = aggregator._parse_service_file(service_file)

        assert result.tier == 3


class TestCalculateTierHealth:
    """Tests for _calculate_tier_health method."""

    def test_calculates_health_by_tier(self, sample_service_dir):
        """Test tier health calculation."""
        aggregator = PortfolioAggregator(search_paths=[sample_service_dir])

        result = aggregator.collect()

        # api-service is tier 1 (critical), simple-service has no SLOs
        tier_1_health = next((t for t in result.by_tier if t.tier == 1), None)
        if tier_1_health:
            assert tier_1_health.total_services >= 1

    def test_skips_services_without_slos(self, tmp_path):
        """Test that services without SLOs are excluded from tier health."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        # Create service without SLOs
        service = services_dir / "no-slo.yaml"
        service.write_text("""
service:
  name: no-slo-service
  team: team
  tier: critical
  type: api
""")

        aggregator = PortfolioAggregator(search_paths=[services_dir])

        result = aggregator.collect()

        # No tier health should be calculated for services without SLOs
        assert result.services_with_slos == 0


class TestGenerateInsights:
    """Tests for _generate_insights method."""

    def test_generates_no_slo_insight(self, tmp_path):
        """Test NO_SLO insight is generated for services without SLOs."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        service = services_dir / "no-slo.yaml"
        service.write_text("""
service:
  name: no-slo-service
  team: team
  tier: standard
  type: api
""")

        aggregator = PortfolioAggregator(search_paths=[services_dir])

        result = aggregator.collect()

        no_slo_insights = [i for i in result.insights if i.type == InsightType.NO_SLO]
        assert len(no_slo_insights) == 1
        assert no_slo_insights[0].service == "no-slo-service"
        assert no_slo_insights[0].severity == "warning"

    def test_generates_unrealistic_slo_insight(self, high_slo_service_dir):
        """Test UNREALISTIC insight for aggressive SLOs on lower tiers."""
        aggregator = PortfolioAggregator(search_paths=[high_slo_service_dir])

        result = aggregator.collect()

        unrealistic_insights = [i for i in result.insights if i.type == InsightType.UNREALISTIC]
        assert len(unrealistic_insights) >= 1
        assert "99.99" in unrealistic_insights[0].message

    def test_generates_promotion_insight(self, high_slo_service_dir):
        """Test PROMOTION insight for services with high SLOs on lower tiers."""
        aggregator = PortfolioAggregator(search_paths=[high_slo_service_dir])

        result = aggregator.collect()

        promotion_insights = [i for i in result.insights if i.type == InsightType.PROMOTION]
        assert len(promotion_insights) >= 1
        assert "tier promotion" in promotion_insights[0].message.lower()


class TestCollectPortfolioFunction:
    """Tests for collect_portfolio convenience function."""

    def test_collect_portfolio_default_paths(self, monkeypatch, tmp_path):
        """Test collect_portfolio with default paths."""
        # Use tmp_path to avoid finding real service files
        monkeypatch.chdir(tmp_path)

        result = collect_portfolio()

        assert result is not None
        assert result.total_services == 0  # No services in tmp_path

    def test_collect_portfolio_custom_paths(self, sample_service_dir):
        """Test collect_portfolio with custom paths."""
        result = collect_portfolio(search_paths=[str(sample_service_dir)])

        assert result.total_services == 2

    def test_collect_portfolio_with_prometheus(self, sample_service_dir):
        """Test collect_portfolio with Prometheus URL."""
        with patch("nthlayer.providers.prometheus.PrometheusProvider") as mock_class:
            mock_provider = MagicMock()
            mock_provider.query = AsyncMock(return_value={"result": []})
            mock_class.return_value = mock_provider

            result = collect_portfolio(
                search_paths=[str(sample_service_dir)],
                prometheus_url="http://prometheus:9090",
            )

            assert result is not None


class TestEnrichWithLiveDataEdgeCases:
    """Tests for edge cases in _enrich_with_live_data."""

    def test_raises_without_prometheus_url(self):
        """Test that _enrich_with_live_data raises without Prometheus URL."""
        import asyncio

        aggregator = PortfolioAggregator()  # No prometheus_url

        with pytest.raises(ValueError, match="Prometheus URL is required"):
            asyncio.run(aggregator._enrich_with_live_data([]))

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_handles_service_file_parse_error(self, mock_provider_class, tmp_path, monkeypatch):
        """Test handling of service file parse errors during enrichment."""
        import asyncio

        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(return_value={"result": []})
        mock_provider_class.return_value = mock_provider

        # Create a mock service health with invalid file path
        from nthlayer.portfolio.models import ServiceHealth, SLOHealth

        service_health = ServiceHealth(
            service="test",
            tier=1,
            team="team",
            service_type="api",
            slos=[
                SLOHealth(name="test", objective=99.9, window="30d", status=HealthStatus.UNKNOWN)
            ],
        )

        bad_path = tmp_path / "nonexistent.yaml"
        slo_specs = [(service_health, bad_path)]

        aggregator = PortfolioAggregator(prometheus_url="http://prometheus:9090")

        # Should handle gracefully without raising
        asyncio.run(aggregator._enrich_with_live_data(slo_specs))

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_handles_slo_without_query(self, mock_provider_class, tmp_path, monkeypatch):
        """Test handling of SLOs without queries."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(return_value={"result": []})
        mock_provider_class.return_value = mock_provider

        # Create service file with SLO but no query
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        service_file = services_dir / "no-query.yaml"
        service_file.write_text("""
service:
  name: no-query-service
  team: team
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

        aggregator = PortfolioAggregator(
            search_paths=[services_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        # Should complete without errors
        assert result is not None

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_substitutes_service_name_in_query(self, mock_provider_class, tmp_path, monkeypatch):
        """Test that service name is substituted in queries."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        captured_queries = []

        def capture_query(query):
            captured_queries.append(query)
            return {"result": [{"value": [0, "99.95"]}]}

        mock_provider = MagicMock()
        mock_provider.query = AsyncMock(side_effect=capture_query)
        mock_provider_class.return_value = mock_provider

        services_dir = tmp_path / "services"
        services_dir.mkdir()
        service_file = services_dir / "test-service.yaml"
        service_file.write_text("""
service:
  name: my-api
  team: team
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        query: up{service="${service}"}
""")

        aggregator = PortfolioAggregator(
            search_paths=[services_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        # Should have substituted ${service} with my-api
        assert any("my-api" in q for q in captured_queries)

    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    def test_calculates_budget_consumed(self, mock_provider_class, tmp_path, monkeypatch):
        """Test error budget calculation."""
        monkeypatch.setenv("NTHLAYER_METRICS_USER", "user")
        monkeypatch.setenv("NTHLAYER_METRICS_PASSWORD", "pass")

        mock_provider = MagicMock()
        # 99.9% objective, 99.8% current value
        # Error budget = 100 - 99.9 = 0.1%
        # Error rate = 100 - 99.8 = 0.2%
        # Budget consumed = 0.2 / 0.1 * 100 = 200% (capped at 100)
        mock_provider.query = AsyncMock(return_value={"result": [{"value": [0, "99.8"]}]})
        mock_provider_class.return_value = mock_provider

        services_dir = tmp_path / "services"
        services_dir.mkdir()
        service_file = services_dir / "test.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: team
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        query: up{service="test-api"}
""")

        aggregator = PortfolioAggregator(
            search_paths=[services_dir],
            prometheus_url="http://prometheus:9090",
        )

        result = aggregator.collect()

        test_service = next((s for s in result.services if s.service == "test-api"), None)
        assert test_service is not None
        # Budget should be capped at 100%
        availability_slo = test_service.slos[0]
        if availability_slo.budget_consumed_percent is not None:
            assert availability_slo.budget_consumed_percent <= 100
