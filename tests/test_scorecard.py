"""
Tests for the reliability scorecard module.
"""

import pytest

from nthlayer.portfolio.models import HealthStatus, ServiceHealth, SLOHealth
from nthlayer.scorecard import (
    ScoreBand,
    ScoreCalculator,
    ScoreComponents,
    ServiceScore,
    ScorecardReport,
    TeamScore,
    TrendAnalyzer,
    TrendData,
    WEIGHTS,
    TIER_WEIGHTS,
)


class TestScoreBand:
    """Tests for ScoreBand enum."""

    def test_band_values(self):
        """Test band values are correct."""
        assert ScoreBand.EXCELLENT.value == "excellent"
        assert ScoreBand.GOOD.value == "good"
        assert ScoreBand.FAIR.value == "fair"
        assert ScoreBand.POOR.value == "poor"
        assert ScoreBand.CRITICAL.value == "critical"


class TestScoreComponents:
    """Tests for ScoreComponents dataclass."""

    def test_create_components(self):
        """Test creating score components."""
        components = ScoreComponents(
            slo_compliance=100.0,
            incident_score=100.0,
            deploy_success_rate=100.0,
            error_budget_remaining=100.0,
            slos_met=3,
            slos_total=3,
        )
        assert components.slo_compliance == 100.0
        assert components.incident_score == 100.0
        assert components.deploy_success_rate == 100.0
        assert components.error_budget_remaining == 100.0
        assert components.slos_met == 3
        assert components.slos_total == 3

    def test_to_dict(self):
        """Test converting components to dict."""
        components = ScoreComponents(
            slo_compliance=80.0,
            incident_score=90.0,
            deploy_success_rate=100.0,
            error_budget_remaining=50.0,
            slos_met=2,
            slos_total=3,
            incident_count=1,
        )
        d = components.to_dict()
        assert d["slo_compliance"] == 80.0
        assert d["raw"]["slos_met"] == 2
        assert d["raw"]["incident_count"] == 1


class TestServiceScore:
    """Tests for ServiceScore dataclass."""

    def test_create_service_score(self):
        """Test creating a service score."""
        components = ScoreComponents(
            slo_compliance=100.0,
            incident_score=100.0,
            deploy_success_rate=100.0,
            error_budget_remaining=100.0,
        )
        score = ServiceScore(
            service="payment-api",
            tier=1,
            team="platform",
            service_type="api",
            score=100.0,
            band=ScoreBand.EXCELLENT,
            components=components,
        )
        assert score.service == "payment-api"
        assert score.tier == 1
        assert score.score == 100.0
        assert score.band == ScoreBand.EXCELLENT

    def test_to_dict(self):
        """Test converting service score to dict."""
        components = ScoreComponents(
            slo_compliance=100.0,
            incident_score=100.0,
            deploy_success_rate=100.0,
            error_budget_remaining=100.0,
        )
        score = ServiceScore(
            service="payment-api",
            tier=1,
            team="platform",
            service_type="api",
            score=100.0,
            band=ScoreBand.EXCELLENT,
            components=components,
        )
        d = score.to_dict()
        assert d["service"] == "payment-api"
        assert d["score"] == 100.0
        assert d["band"] == "excellent"


class TestTeamScore:
    """Tests for TeamScore dataclass."""

    def test_create_team_score(self):
        """Test creating a team score."""
        score = TeamScore(
            team="platform",
            score=85.0,
            band=ScoreBand.GOOD,
            service_count=5,
            tier1_score=90.0,
            tier2_score=80.0,
        )
        assert score.team == "platform"
        assert score.score == 85.0
        assert score.band == ScoreBand.GOOD
        assert score.tier1_score == 90.0

    def test_to_dict(self):
        """Test converting team score to dict."""
        score = TeamScore(
            team="platform",
            score=85.0,
            band=ScoreBand.GOOD,
            service_count=5,
        )
        d = score.to_dict()
        assert d["team"] == "platform"
        assert d["score"] == 85.0


class TestScoreCalculator:
    """Tests for ScoreCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create a score calculator."""
        return ScoreCalculator()

    @pytest.fixture
    def healthy_service(self):
        """Create a healthy service with all SLOs met."""
        return ServiceHealth(
            service="payment-api",
            tier=1,
            team="platform",
            service_type="api",
            slos=[
                SLOHealth(
                    name="availability",
                    objective=99.9,
                    window="30d",
                    status=HealthStatus.HEALTHY,
                    current_value=99.95,
                    budget_consumed_percent=50.0,
                ),
                SLOHealth(
                    name="latency",
                    objective=99.0,
                    window="30d",
                    status=HealthStatus.HEALTHY,
                    current_value=99.5,
                    budget_consumed_percent=30.0,
                ),
            ],
        )

    @pytest.fixture
    def degraded_service(self):
        """Create a degraded service with some SLOs not met."""
        return ServiceHealth(
            service="search-api",
            tier=2,
            team="search",
            service_type="api",
            slos=[
                SLOHealth(
                    name="availability",
                    objective=99.9,
                    window="30d",
                    status=HealthStatus.WARNING,
                    current_value=99.7,
                    budget_consumed_percent=80.0,
                ),
                SLOHealth(
                    name="latency",
                    objective=99.0,
                    window="30d",
                    status=HealthStatus.HEALTHY,
                    current_value=99.5,
                    budget_consumed_percent=30.0,
                ),
            ],
        )

    def test_weights_sum_to_one(self):
        """Test that weights sum to 1.0."""
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_tier_weights_exist(self):
        """Test tier weights are defined."""
        assert TIER_WEIGHTS[1] == 3.0
        assert TIER_WEIGHTS[2] == 2.0
        assert TIER_WEIGHTS[3] == 1.0

    def test_calculate_perfect_score(self, calculator, healthy_service):
        """Test calculating a perfect score."""
        score = calculator.calculate_service_score(
            service_health=healthy_service,
            incident_count=0,
            deploys_successful=10,
            deploys_total=10,
            budget_remaining_percent=100.0,
        )
        assert score.service == "payment-api"
        assert score.score == 100.0
        assert score.band == ScoreBand.EXCELLENT
        assert score.components.slo_compliance == 100.0
        assert score.components.incident_score == 100.0
        assert score.components.deploy_success_rate == 100.0
        assert score.components.error_budget_remaining == 100.0

    def test_calculate_degraded_score(self, calculator, degraded_service):
        """Test calculating a degraded score."""
        score = calculator.calculate_service_score(
            service_health=degraded_service,
            incident_count=3,
            deploys_successful=8,
            deploys_total=10,
            budget_remaining_percent=50.0,
        )
        assert score.service == "search-api"
        # SLO: 50% (1/2 healthy) * 0.4 = 20
        # Incident: 70% (100 - 3*10) * 0.3 = 21
        # Deploy: 80% * 0.2 = 16
        # Budget: 50% * 0.1 = 5
        # Total = 62
        assert 60 <= score.score <= 65
        assert score.band == ScoreBand.FAIR

    def test_incident_score_floor(self, calculator, healthy_service):
        """Test incident score doesn't go below 0."""
        score = calculator.calculate_service_score(
            service_health=healthy_service,
            incident_count=20,  # More than 10
        )
        assert score.components.incident_score == 0

    def test_no_deploys_is_perfect(self, calculator, healthy_service):
        """Test that no deployments results in perfect deploy score."""
        score = calculator.calculate_service_score(
            service_health=healthy_service,
            deploys_total=0,
        )
        assert score.components.deploy_success_rate == 100.0

    def test_score_to_band_boundaries(self, calculator):
        """Test score to band conversion at boundaries."""
        assert calculator.score_to_band(100) == ScoreBand.EXCELLENT
        assert calculator.score_to_band(90) == ScoreBand.EXCELLENT
        assert calculator.score_to_band(89.9) == ScoreBand.GOOD
        assert calculator.score_to_band(75) == ScoreBand.GOOD
        assert calculator.score_to_band(74.9) == ScoreBand.FAIR
        assert calculator.score_to_band(50) == ScoreBand.FAIR
        assert calculator.score_to_band(49.9) == ScoreBand.POOR
        assert calculator.score_to_band(25) == ScoreBand.POOR
        assert calculator.score_to_band(24.9) == ScoreBand.CRITICAL
        assert calculator.score_to_band(0) == ScoreBand.CRITICAL

    def test_calculate_team_score_empty(self, calculator):
        """Test team score with no services."""
        score = calculator.calculate_team_score("platform", [])
        assert score.score == 0
        assert score.band == ScoreBand.CRITICAL
        assert score.service_count == 0

    def test_calculate_team_score_single_tier(self, calculator, healthy_service):
        """Test team score with single tier."""
        svc_score = calculator.calculate_service_score(healthy_service)
        team_score = calculator.calculate_team_score("platform", [svc_score])

        assert team_score.team == "platform"
        assert team_score.score == svc_score.score
        assert team_score.service_count == 1
        assert team_score.tier1_score == svc_score.score

    def test_calculate_team_score_multi_tier(self, calculator):
        """Test team score with multiple tiers."""
        # Create mock service scores
        tier1_score = ServiceScore(
            service="critical-api",
            tier=1,
            team="platform",
            service_type="api",
            score=90.0,
            band=ScoreBand.EXCELLENT,
            components=ScoreComponents(
                slo_compliance=100,
                incident_score=100,
                deploy_success_rate=100,
                error_budget_remaining=100,
            ),
        )
        tier2_score = ServiceScore(
            service="standard-api",
            tier=2,
            team="platform",
            service_type="api",
            score=70.0,
            band=ScoreBand.FAIR,
            components=ScoreComponents(
                slo_compliance=100,
                incident_score=100,
                deploy_success_rate=100,
                error_budget_remaining=100,
            ),
        )

        team_score = calculator.calculate_team_score("platform", [tier1_score, tier2_score])

        # Weighted average: (90 * 3 + 70 * 2) / (3 + 2) = (270 + 140) / 5 = 82
        assert team_score.score == 82.0
        assert team_score.tier1_score == 90.0
        assert team_score.tier2_score == 70.0
        assert team_score.tier3_score is None

    def test_calculate_org_score(self, calculator):
        """Test organization-wide score calculation."""
        scores = [
            ServiceScore(
                service="api-1",
                tier=1,
                team="team-a",
                service_type="api",
                score=90.0,
                band=ScoreBand.EXCELLENT,
                components=ScoreComponents(
                    slo_compliance=100,
                    incident_score=100,
                    deploy_success_rate=100,
                    error_budget_remaining=100,
                ),
            ),
            ServiceScore(
                service="api-2",
                tier=2,
                team="team-b",
                service_type="api",
                score=80.0,
                band=ScoreBand.GOOD,
                components=ScoreComponents(
                    slo_compliance=100,
                    incident_score=100,
                    deploy_success_rate=100,
                    error_budget_remaining=100,
                ),
            ),
        ]

        # Weighted: (90 * 3 + 80 * 2) / (3 + 2) = 86
        org_score = calculator.calculate_org_score(scores)
        assert org_score == 86.0

    def test_calculate_org_score_empty(self, calculator):
        """Test org score with no services."""
        assert calculator.calculate_org_score([]) == 0.0


class TestTrendAnalyzer:
    """Tests for TrendAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a trend analyzer."""
        return TrendAnalyzer()

    def test_get_historical_score_returns_none(self, analyzer):
        """Test that historical score returns None in MVP."""
        score = analyzer.get_historical_score("test-service", 30)
        assert score is None

    def test_calculate_trend_direction_improving(self, analyzer):
        """Test improving trend detection."""
        direction = analyzer.calculate_trend_direction(90.0, 80.0)
        assert direction == "improving"

    def test_calculate_trend_direction_degrading(self, analyzer):
        """Test degrading trend detection."""
        direction = analyzer.calculate_trend_direction(80.0, 90.0)
        assert direction == "degrading"

    def test_calculate_trend_direction_stable(self, analyzer):
        """Test stable trend detection."""
        direction = analyzer.calculate_trend_direction(85.0, 83.0)
        assert direction == "stable"

    def test_calculate_trend_direction_no_previous(self, analyzer):
        """Test trend with no previous score."""
        direction = analyzer.calculate_trend_direction(85.0, None)
        assert direction == "stable"

    def test_calculate_trend_custom_threshold(self, analyzer):
        """Test trend with custom threshold."""
        direction = analyzer.calculate_trend_direction(85.0, 80.0, threshold=10.0)
        assert direction == "stable"  # 5 point difference < 10 threshold

    def test_get_trend_symbol(self, analyzer):
        """Test trend symbols."""
        assert analyzer.get_trend_symbol("improving") == "\u2191"  # ↑
        assert analyzer.get_trend_symbol("degrading") == "\u2193"  # ↓
        assert analyzer.get_trend_symbol("stable") == "\u2192"  # →
        assert analyzer.get_trend_symbol("unknown") == "-"


class TestScorecardReport:
    """Tests for ScorecardReport."""

    @pytest.fixture
    def sample_report(self):
        """Create a sample report."""
        from datetime import datetime, UTC

        components = ScoreComponents(
            slo_compliance=100.0,
            incident_score=100.0,
            deploy_success_rate=100.0,
            error_budget_remaining=100.0,
        )
        service_score = ServiceScore(
            service="payment-api",
            tier=1,
            team="platform",
            service_type="api",
            score=100.0,
            band=ScoreBand.EXCELLENT,
            components=components,
        )
        team_score = TeamScore(
            team="platform",
            score=100.0,
            band=ScoreBand.EXCELLENT,
            service_count=1,
        )
        return ScorecardReport(
            timestamp=datetime.now(UTC),
            period="30d",
            org_score=100.0,
            org_band=ScoreBand.EXCELLENT,
            services=[service_score],
            teams=[team_score],
            top_services=[service_score],
            bottom_services=[service_score],
            most_improved=[],
        )

    def test_to_dict(self, sample_report):
        """Test converting report to dict."""
        d = sample_report.to_dict()
        assert d["summary"]["org_score"] == 100.0
        assert d["summary"]["org_band"] == "excellent"
        assert len(d["services"]) == 1
        assert len(d["teams"]) == 1

    def test_to_csv_rows(self, sample_report):
        """Test converting report to CSV rows."""
        rows = sample_report.to_csv_rows()
        assert len(rows) == 1
        assert rows[0]["service"] == "payment-api"
        assert rows[0]["score"] == 100.0
        assert rows[0]["band"] == "excellent"


class TestTrendData:
    """Tests for TrendData dataclass."""

    def test_create_trend_data(self):
        """Test creating trend data."""
        from datetime import datetime, UTC

        data = TrendData(
            timestamp=datetime.now(UTC),
            score=85.0,
            components={"slo_compliance": 100.0},
        )
        assert data.score == 85.0
        assert data.components["slo_compliance"] == 100.0


class TestScorecardCLI:
    """Tests for the scorecard CLI command."""

    def test_scorecard_command_no_services(self, tmp_path):
        """Test scorecard command with no services."""
        from nthlayer.cli.scorecard import scorecard_command

        # Create empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Should return 0 (no services = excellent by default)
        exit_code = scorecard_command(
            format="json",
            search_paths=[str(empty_dir)],
        )
        assert exit_code == 2  # No services = critical (score 0)

    def test_scorecard_command_with_services(self, tmp_path):
        """Test scorecard command with service files."""
        from nthlayer.cli.scorecard import scorecard_command

        # Create a service file
        service_dir = tmp_path / "services"
        service_dir.mkdir()
        service_file = service_dir / "test-api.yaml"
        service_file.write_text("""
service:
  name: test-api
  type: api
  tier: tier-1
  team: platform

slos:
  - name: availability
    objective: 99.9
    window: 30d
    indicator:
      type: availability
      query: "sum(rate(http_requests_total{status!~'5..'}[5m])) / sum(rate(http_requests_total[5m]))"
""")

        exit_code = scorecard_command(
            format="json",
            search_paths=[str(service_dir)],
        )
        # SLOs without Prometheus data have UNKNOWN status
        # Score = 0 (SLO not counted) + 30 (incidents) + 20 (deploy) + 10 (budget) = 60 = fair
        assert exit_code == 1  # fair = exit code 1

    def test_scorecard_command_table_format(self, tmp_path, capsys):
        """Test scorecard command table output."""
        from nthlayer.cli.scorecard import scorecard_command

        # Create a service file
        service_dir = tmp_path / "services"
        service_dir.mkdir()
        service_file = service_dir / "test-api.yaml"
        service_file.write_text("""
service:
  name: test-api
  type: api
  tier: tier-1
  team: platform

slos:
  - name: availability
    objective: 99.9
    window: 30d
""")

        exit_code = scorecard_command(
            format="table",
            search_paths=[str(service_dir)],
        )
        # Score is 60 (fair) without Prometheus data
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "test-api" in captured.out or "Reliability Scorecard" in captured.out

    def test_scorecard_command_by_team(self, tmp_path, capsys):
        """Test scorecard command with by_team flag."""
        from nthlayer.cli.scorecard import scorecard_command

        # Create service files for different teams
        service_dir = tmp_path / "services"
        service_dir.mkdir()

        for team in ["platform", "search"]:
            service_file = service_dir / f"{team}-api.yaml"
            service_file.write_text(f"""
service:
  name: {team}-api
  type: api
  tier: tier-1
  team: {team}

slos:
  - name: availability
    objective: 99.9
    window: 30d
""")

        exit_code = scorecard_command(
            format="table",
            search_paths=[str(service_dir)],
            by_team=True,
        )
        # Score is 60 (fair) without Prometheus data
        assert exit_code == 1

    def test_scorecard_command_csv_format(self, tmp_path, capsys):
        """Test scorecard command CSV output."""
        from nthlayer.cli.scorecard import scorecard_command

        # Create a service file
        service_dir = tmp_path / "services"
        service_dir.mkdir()
        service_file = service_dir / "test-api.yaml"
        service_file.write_text("""
service:
  name: test-api
  type: api
  tier: tier-1
  team: platform

slos:
  - name: availability
    objective: 99.9
    window: 30d
""")

        exit_code = scorecard_command(
            format="csv",
            search_paths=[str(service_dir)],
        )
        # Score is 60 (fair) without Prometheus data
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "service" in captured.out  # CSV header
        assert "test-api" in captured.out

    def test_handle_scorecard_command(self, tmp_path):
        """Test the handle_scorecard_command function."""
        import argparse
        from nthlayer.cli.scorecard import handle_scorecard_command

        # Create empty directory to ensure no services are found
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        args = argparse.Namespace(
            format="json",
            search_paths=[str(empty_dir)],
            prometheus_url=None,
            by_team=False,
            top_n=5,
        )
        # Will return 2 (critical) because no services found
        exit_code = handle_scorecard_command(args)
        assert exit_code == 2

    def test_register_scorecard_parser(self):
        """Test parser registration."""
        import argparse
        from nthlayer.cli.scorecard import register_scorecard_parser

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_scorecard_parser(subparsers)

        # Parse scorecard command
        args = parser.parse_args(["scorecard", "--format", "json", "--by-team"])
        assert args.format == "json"
        assert args.by_team is True
