"""Tests for Portfolio CLI commands.

Tests for nthlayer portfolio command and portfolio module.
"""

import tempfile
from pathlib import Path

from nthlayer.portfolio import (
    HealthStatus,
    InsightType,
    PortfolioAggregator,
    PortfolioHealth,
    ServiceHealth,
    SLOHealth,
    TierHealth,
    collect_portfolio,
)


class TestPortfolioModels:
    """Tests for portfolio data models."""

    def test_slo_health_to_dict(self):
        """Test SLOHealth serialization."""
        slo = SLOHealth(
            name="availability",
            objective=99.95,
            window="30d",
            status=HealthStatus.HEALTHY,
        )
        data = slo.to_dict()
        assert data["name"] == "availability"
        assert data["objective"] == 99.95
        assert data["status"] == "healthy"

    def test_service_health_calculates_worst_status(self):
        """Test ServiceHealth calculates overall status from SLOs."""
        slos = [
            SLOHealth(name="slo1", objective=99.9, window="30d", status=HealthStatus.HEALTHY),
            SLOHealth(name="slo2", objective=99.0, window="30d", status=HealthStatus.WARNING),
        ]
        svc = ServiceHealth(
            service="test-service",
            tier=1,
            team="test",
            service_type="api",
            slos=slos,
        )
        assert svc.overall_status == HealthStatus.WARNING
        assert svc.needs_attention is True

    def test_service_health_healthy_when_all_slos_healthy(self):
        """Test ServiceHealth is healthy when all SLOs are healthy."""
        slos = [
            SLOHealth(name="slo1", objective=99.9, window="30d", status=HealthStatus.HEALTHY),
            SLOHealth(name="slo2", objective=99.0, window="30d", status=HealthStatus.HEALTHY),
        ]
        svc = ServiceHealth(
            service="test-service",
            tier=1,
            team="test",
            service_type="api",
            slos=slos,
        )
        assert svc.overall_status == HealthStatus.HEALTHY
        assert svc.is_healthy is True

    def test_tier_health_percentage(self):
        """Test TierHealth calculates percentage correctly."""
        tier = TierHealth(
            tier=1,
            tier_name="Critical",
            total_services=10,
            healthy_services=8,
        )
        assert tier.health_percent == 80.0

    def test_portfolio_health_org_percentage(self):
        """Test PortfolioHealth calculates org health."""
        from datetime import UTC, datetime

        portfolio = PortfolioHealth(
            timestamp=datetime.now(UTC),
            total_services=10,
            services_with_slos=8,
            healthy_services=6,
        )
        assert portfolio.org_health_percent == 75.0


class TestPortfolioAggregator:
    """Tests for portfolio aggregation."""

    def test_aggregator_discovers_services(self):
        """Test that aggregator discovers services with SLOs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create services directory with SLO resources
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "payment-api.yaml").write_text("""
service:
  name: payment-api
  team: payments
  tier: 1
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
""")

            (services_dir / "search-api.yaml").write_text("""
service:
  name: search-api
  team: search
  tier: 2
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.5
      window: 30d
""")

            aggregator = PortfolioAggregator(search_paths=[services_dir])
            portfolio = aggregator.collect()

            assert portfolio.total_services == 2
            assert portfolio.services_with_slos == 2
            names = {s.service for s in portfolio.services}
            assert "payment-api" in names
            assert "search-api" in names

    def test_aggregator_groups_by_tier(self):
        """Test that aggregator groups services by tier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "critical-svc.yaml").write_text("""
service:
  name: critical-svc
  team: team
  tier: 1
  type: api

resources:
  - kind: SLO
    name: slo
    spec:
      objective: 99.9
      window: 30d
""")

            (services_dir / "standard-svc.yaml").write_text("""
service:
  name: standard-svc
  team: team
  tier: 2
  type: api

resources:
  - kind: SLO
    name: slo
    spec:
      objective: 99.5
      window: 30d
""")

            aggregator = PortfolioAggregator(search_paths=[services_dir])
            portfolio = aggregator.collect()

            assert len(portfolio.by_tier) == 2
            tier_nums = {t.tier for t in portfolio.by_tier}
            assert 1 in tier_nums
            assert 2 in tier_nums

    def test_aggregator_handles_empty_directory(self):
        """Test aggregator handles empty directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aggregator = PortfolioAggregator(search_paths=[Path(tmpdir)])
            portfolio = aggregator.collect()

            assert portfolio.total_services == 0
            assert portfolio.services_with_slos == 0

    def test_aggregator_generates_no_slo_insight(self):
        """Test aggregator generates insight for services without SLOs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "no-slo-svc.yaml").write_text("""
service:
  name: no-slo-svc
  team: team
  tier: 1
  type: api

resources: []
""")

            aggregator = PortfolioAggregator(search_paths=[services_dir])
            portfolio = aggregator.collect()

            no_slo_insights = [i for i in portfolio.insights if i.type == InsightType.NO_SLO]
            assert len(no_slo_insights) == 1


class TestPortfolioCommand:
    """Tests for nthlayer portfolio CLI command."""

    def test_portfolio_command_runs(self):
        """Test portfolio command runs without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "test-service.yaml").write_text("""
service:
  name: test-service
  team: test
  tier: 1
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            from nthlayer.cli.portfolio import portfolio_command

            result = portfolio_command(search_paths=[str(services_dir)])
            assert result == 0

    def test_portfolio_command_empty(self):
        """Test portfolio handles no services gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from nthlayer.cli.portfolio import portfolio_command

            result = portfolio_command(search_paths=[tmpdir])
            assert result == 0

    def test_portfolio_json_export(self):
        """Test portfolio JSON export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "test-service.yaml").write_text("""
service:
  name: test-service
  team: test
  tier: 1
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            portfolio = collect_portfolio([str(services_dir)])
            data = portfolio.to_dict()

            assert "timestamp" in data
            assert "summary" in data
            assert data["summary"]["total_services"] == 1
