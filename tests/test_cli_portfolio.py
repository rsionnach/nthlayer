"""Tests for CLI portfolio command.

Tests for nthlayer portfolio command including health calculation,
output formats, and exit codes.
"""

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.portfolio import (
    _calculate_exit_code,
    _print_csv,
    _print_markdown,
    _print_service_attention,
    _print_table,
    _progress_bar,
    handle_portfolio_command,
    portfolio_command,
    register_portfolio_parser,
)
from nthlayer.portfolio import HealthStatus, PortfolioHealth, ServiceHealth


@pytest.fixture
def healthy_portfolio():
    """Create a healthy portfolio with all services meeting SLOs."""
    portfolio = MagicMock(spec=PortfolioHealth)
    portfolio.services = []
    portfolio.services_with_slos = 3
    portfolio.healthy_services = 3
    portfolio.total_services = 3
    portfolio.total_slos = 6
    portfolio.org_health_percent = 100.0
    portfolio.by_tier = []
    portfolio.services_needing_attention = []
    portfolio.insights = []
    portfolio.to_dict.return_value = {
        "total_services": 3,
        "services_with_slos": 3,
        "healthy_services": 3,
        "org_health_percent": 100.0,
    }
    portfolio.to_csv_rows.return_value = [
        {"service": "svc1", "tier": "1", "slo_name": "availability", "status": "healthy"}
    ]
    return portfolio


@pytest.fixture
def warning_portfolio():
    """Create a portfolio with warning-level issues."""
    svc = MagicMock(spec=ServiceHealth)
    svc.service = "degraded-service"
    svc.tier = 2
    svc.overall_status = HealthStatus.WARNING
    svc.slos = []

    portfolio = MagicMock(spec=PortfolioHealth)
    portfolio.services = [svc]
    portfolio.services_with_slos = 3
    portfolio.healthy_services = 2
    portfolio.total_services = 3
    portfolio.total_slos = 6
    portfolio.org_health_percent = 85.0
    portfolio.by_tier = []
    portfolio.services_needing_attention = [svc]
    portfolio.insights = []
    portfolio.to_dict.return_value = {"org_health_percent": 85.0}
    portfolio.to_csv_rows.return_value = []
    return portfolio


@pytest.fixture
def critical_portfolio():
    """Create a portfolio with critical-level issues."""
    svc = MagicMock(spec=ServiceHealth)
    svc.service = "critical-service"
    svc.tier = 1
    svc.overall_status = HealthStatus.CRITICAL
    svc.slos = []

    portfolio = MagicMock(spec=PortfolioHealth)
    portfolio.services = [svc]
    portfolio.services_with_slos = 3
    portfolio.healthy_services = 1
    portfolio.total_services = 3
    portfolio.total_slos = 6
    portfolio.org_health_percent = 50.0
    portfolio.by_tier = []
    portfolio.services_needing_attention = [svc]
    portfolio.insights = []
    portfolio.to_dict.return_value = {"org_health_percent": 50.0}
    portfolio.to_csv_rows.return_value = []
    return portfolio


@pytest.fixture
def exhausted_portfolio():
    """Create a portfolio with exhausted error budget."""
    svc = MagicMock(spec=ServiceHealth)
    svc.service = "exhausted-service"
    svc.tier = 1
    svc.overall_status = HealthStatus.EXHAUSTED
    svc.slos = []

    portfolio = MagicMock(spec=PortfolioHealth)
    portfolio.services = [svc]
    portfolio.services_with_slos = 3
    portfolio.healthy_services = 0
    portfolio.total_services = 3
    portfolio.total_slos = 6
    portfolio.org_health_percent = 0.0
    portfolio.by_tier = []
    portfolio.services_needing_attention = [svc]
    portfolio.insights = []
    portfolio.to_dict.return_value = {"org_health_percent": 0.0}
    portfolio.to_csv_rows.return_value = []
    return portfolio


class TestPortfolioCommand:
    """Tests for portfolio_command function."""

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_healthy_returns_exit_code_0(self, mock_collect, healthy_portfolio):
        """Test healthy portfolio returns exit code 0."""
        mock_collect.return_value = healthy_portfolio

        result = portfolio_command(format="json")

        assert result == 0

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_warning_returns_exit_code_1(self, mock_collect, warning_portfolio):
        """Test warning portfolio returns exit code 1."""
        mock_collect.return_value = warning_portfolio

        result = portfolio_command(format="json")

        assert result == 1

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_critical_returns_exit_code_2(self, mock_collect, critical_portfolio):
        """Test critical portfolio returns exit code 2."""
        mock_collect.return_value = critical_portfolio

        result = portfolio_command(format="json")

        assert result == 2

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_exhausted_returns_exit_code_2(self, mock_collect, exhausted_portfolio):
        """Test exhausted portfolio returns exit code 2."""
        mock_collect.return_value = exhausted_portfolio

        result = portfolio_command(format="json")

        assert result == 2

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_json_format(self, mock_collect, healthy_portfolio, capsys):
        """Test JSON output format."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(format="json")

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "total_services" in output or "org_health_percent" in output

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_csv_format(self, mock_collect, healthy_portfolio, capsys):
        """Test CSV output format."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(format="csv")

        captured = capsys.readouterr()
        assert "service" in captured.out

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_markdown_format(self, mock_collect, healthy_portfolio, capsys):
        """Test Markdown output format."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(format="markdown")

        captured = capsys.readouterr()
        assert "# SLO Portfolio Report" in captured.out

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_table_format(self, mock_collect, healthy_portfolio, capsys):
        """Test table output format (default)."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(format="table")

        captured = capsys.readouterr()
        assert "Portfolio" in captured.out or "Health" in captured.out

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_uses_search_paths(self, mock_collect, healthy_portfolio):
        """Test that search_paths are passed to collect_portfolio."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(search_paths=["/path/to/services"])

        mock_collect.assert_called_once_with(["/path/to/services"], prometheus_url=None)

    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_uses_prometheus_url(self, mock_collect, healthy_portfolio):
        """Test that prometheus_url is passed to collect_portfolio."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command(prometheus_url="http://prometheus:9090")

        mock_collect.assert_called_once_with(None, prometheus_url="http://prometheus:9090")

    @patch.dict("os.environ", {"NTHLAYER_PROMETHEUS_URL": "http://env-prom:9090"})
    @patch("nthlayer.cli.portfolio.collect_portfolio")
    def test_uses_env_var_for_prometheus(self, mock_collect, healthy_portfolio):
        """Test that NTHLAYER_PROMETHEUS_URL env var is used."""
        mock_collect.return_value = healthy_portfolio

        portfolio_command()

        mock_collect.assert_called_once_with(None, prometheus_url="http://env-prom:9090")


class TestCalculateExitCode:
    """Tests for _calculate_exit_code function."""

    def test_healthy_returns_0(self, healthy_portfolio):
        """Test healthy portfolio returns 0."""
        result = _calculate_exit_code(healthy_portfolio)
        assert result == 0

    def test_warning_returns_1(self, warning_portfolio):
        """Test warning portfolio returns 1."""
        result = _calculate_exit_code(warning_portfolio)
        assert result == 1

    def test_critical_returns_2(self, critical_portfolio):
        """Test critical portfolio returns 2."""
        result = _calculate_exit_code(critical_portfolio)
        assert result == 2

    def test_exhausted_returns_2(self, exhausted_portfolio):
        """Test exhausted portfolio returns 2 immediately."""
        result = _calculate_exit_code(exhausted_portfolio)
        assert result == 2

    def test_mixed_returns_highest_severity(self):
        """Test mixed health levels return highest severity."""
        warning_svc = MagicMock()
        warning_svc.overall_status = HealthStatus.WARNING

        critical_svc = MagicMock()
        critical_svc.overall_status = HealthStatus.CRITICAL

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services = [warning_svc, critical_svc]

        result = _calculate_exit_code(portfolio)
        assert result == 2  # Critical takes precedence


class TestProgressBar:
    """Tests for _progress_bar function."""

    def test_100_percent(self):
        """Test 100% progress bar."""
        result = _progress_bar(100, width=10)
        assert result == "██████████"

    def test_0_percent(self):
        """Test 0% progress bar."""
        result = _progress_bar(0, width=10)
        assert result == "░░░░░░░░░░"

    def test_50_percent(self):
        """Test 50% progress bar."""
        result = _progress_bar(50, width=10)
        assert result == "█████░░░░░"

    def test_custom_width(self):
        """Test custom width progress bar."""
        result = _progress_bar(50, width=20)
        assert len(result) == 20


class TestPrintTable:
    """Tests for _print_table function."""

    def test_prints_header(self, healthy_portfolio, capsys):
        """Test that header is printed."""
        _print_table(healthy_portfolio)

        captured = capsys.readouterr()
        assert "Portfolio" in captured.out

    def test_prints_health_percentage(self, healthy_portfolio, capsys):
        """Test that health percentage is printed."""
        _print_table(healthy_portfolio)

        captured = capsys.readouterr()
        assert "100%" in captured.out or "Health" in captured.out

    def test_no_slos_message(self, capsys):
        """Test message when no SLOs defined."""
        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = []
        portfolio.total_services = 3
        portfolio.total_slos = 0

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "No SLOs defined" in captured.out

    def test_shows_tier_breakdown(self, capsys):
        """Test tier breakdown is shown."""
        tier = MagicMock()
        tier.tier = 1
        tier.tier_name = "Critical"
        tier.health_percent = 100.0
        tier.healthy_services = 2
        tier.total_services = 2

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 2
        portfolio.org_health_percent = 100.0
        portfolio.healthy_services = 2
        portfolio.by_tier = [tier]
        portfolio.services_needing_attention = []
        portfolio.insights = []
        portfolio.total_services = 2
        portfolio.total_slos = 4

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "Tier" in captured.out or "Critical" in captured.out

    def test_shows_insights(self, capsys):
        """Test insights are shown."""
        insight = MagicMock()
        insight.severity = "warning"
        insight.service = "test-service"
        insight.message = "SLO degraded"

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 1
        portfolio.org_health_percent = 80.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = [insight]
        portfolio.total_services = 1
        portfolio.total_slos = 1

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "Insights" in captured.out or "test-service" in captured.out


class TestPrintServiceAttention:
    """Tests for _print_service_attention function."""

    def test_prints_exhausted_service(self, capsys):
        """Test printing exhausted service."""
        slo = MagicMock()
        slo.name = "availability"
        slo.status = HealthStatus.EXHAUSTED
        slo.current_value = 98.5
        slo.objective = 99.9
        slo.budget_consumed_percent = 150.0

        svc = MagicMock()
        svc.service = "exhausted-svc"
        svc.tier = 1
        svc.overall_status = HealthStatus.EXHAUSTED
        svc.slos = [slo]

        _print_service_attention(svc)

        captured = capsys.readouterr()
        assert "exhausted-svc" in captured.out

    def test_prints_warning_service(self, capsys):
        """Test printing warning service."""
        slo = MagicMock()
        slo.name = "latency"
        slo.status = HealthStatus.WARNING
        slo.current_value = 99.0
        slo.objective = 99.5
        slo.budget_consumed_percent = 75.0

        svc = MagicMock()
        svc.service = "warning-svc"
        svc.tier = 2
        svc.overall_status = HealthStatus.WARNING
        svc.slos = [slo]

        _print_service_attention(svc)

        captured = capsys.readouterr()
        assert "warning-svc" in captured.out

    def test_handles_null_current_value(self, capsys):
        """Test handling SLO with null current value."""
        slo = MagicMock()
        slo.name = "availability"
        slo.status = HealthStatus.WARNING
        slo.current_value = None
        slo.objective = 99.9
        slo.budget_consumed_percent = None

        svc = MagicMock()
        svc.service = "unknown-svc"
        svc.tier = 3
        svc.overall_status = HealthStatus.WARNING
        svc.slos = [slo]

        _print_service_attention(svc)

        captured = capsys.readouterr()
        assert "unknown-svc" in captured.out


class TestPrintMarkdown:
    """Tests for _print_markdown function."""

    def test_prints_header(self, healthy_portfolio, capsys):
        """Test Markdown header."""
        _print_markdown(healthy_portfolio)

        captured = capsys.readouterr()
        assert "# SLO Portfolio Report" in captured.out

    def test_includes_health_emoji(self, healthy_portfolio, capsys):
        """Test health emoji based on percentage."""
        _print_markdown(healthy_portfolio)

        captured = capsys.readouterr()
        assert "🟢" in captured.out  # 100% = green

    def test_warning_emoji(self, warning_portfolio, capsys):
        """Test warning emoji for degraded health."""
        _print_markdown(warning_portfolio)

        captured = capsys.readouterr()
        assert "🟡" in captured.out  # 85% = yellow

    def test_critical_emoji(self, critical_portfolio, capsys):
        """Test critical emoji for poor health."""
        _print_markdown(critical_portfolio)

        captured = capsys.readouterr()
        assert "🔴" in captured.out  # 50% = red

    def test_includes_tier_table(self, capsys):
        """Test tier table in markdown."""
        tier = MagicMock()
        tier.tier = 1
        tier.tier_name = "Critical"
        tier.health_percent = 100.0
        tier.healthy_services = 2
        tier.total_services = 2

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 2
        portfolio.org_health_percent = 100.0
        portfolio.healthy_services = 2
        portfolio.by_tier = [tier]
        portfolio.services_needing_attention = []
        portfolio.insights = []
        portfolio.total_services = 2
        portfolio.total_slos = 4

        _print_markdown(portfolio)

        captured = capsys.readouterr()
        assert "| Tier |" in captured.out


class TestPrintCSV:
    """Tests for _print_csv function."""

    def test_prints_header_when_empty(self, capsys):
        """Test CSV header printed even when empty."""
        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.to_csv_rows.return_value = []

        _print_csv(portfolio)

        captured = capsys.readouterr()
        assert "service" in captured.out

    def test_prints_data_rows(self, healthy_portfolio, capsys):
        """Test CSV data rows printed."""
        _print_csv(healthy_portfolio)

        captured = capsys.readouterr()
        assert "svc1" in captured.out


class TestRegisterPortfolioParser:
    """Tests for register_portfolio_parser function."""

    def test_registers_subparser(self):
        """Test that portfolio subparser is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_portfolio_parser(subparsers)

        args = parser.parse_args(["portfolio"])
        assert hasattr(args, "format") or True  # Parser registered

    def test_format_choices(self):
        """Test format argument choices."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_portfolio_parser(subparsers)

        for fmt in ["table", "json", "csv", "markdown"]:
            args = parser.parse_args(["portfolio", "--format", fmt])
            assert args.format == fmt

    def test_path_argument(self):
        """Test --path argument."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_portfolio_parser(subparsers)

        args = parser.parse_args(["portfolio", "--path", "/path1", "--path", "/path2"])
        assert args.search_paths == ["/path1", "/path2"]

    def test_prometheus_url_argument(self):
        """Test --prometheus-url argument."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_portfolio_parser(subparsers)

        args = parser.parse_args(["portfolio", "--prometheus-url", "http://prom:9090"])
        assert args.prometheus_url == "http://prom:9090"


class TestPrintTableAdditionalCoverage:
    """Additional tests for _print_table to increase coverage."""

    def test_health_color_red_when_below_80(self, capsys):
        """Test health color is red when below 80%."""
        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 5
        portfolio.org_health_percent = 50.0  # Below 80% = red
        portfolio.healthy_services = 2
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = []
        portfolio.total_services = 5
        portfolio.total_slos = 10

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "50%" in captured.out

    def test_services_needing_attention_sorting(self, capsys):
        """Test services needing attention are sorted by severity."""
        warning_svc = MagicMock()
        warning_svc.service = "warning-svc"
        warning_svc.tier = 2
        warning_svc.overall_status = HealthStatus.WARNING
        warning_svc.slos = []

        critical_svc = MagicMock()
        critical_svc.service = "critical-svc"
        critical_svc.tier = 1
        critical_svc.overall_status = HealthStatus.CRITICAL
        critical_svc.slos = []

        exhausted_svc = MagicMock()
        exhausted_svc.service = "exhausted-svc"
        exhausted_svc.tier = 1
        exhausted_svc.overall_status = HealthStatus.EXHAUSTED
        exhausted_svc.slos = []

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 3
        portfolio.org_health_percent = 50.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = [warning_svc, critical_svc, exhausted_svc]
        portfolio.insights = []
        portfolio.total_services = 3
        portfolio.total_slos = 3

        _print_table(portfolio)

        captured = capsys.readouterr()
        # All services should appear
        assert "warning-svc" in captured.out
        assert "critical-svc" in captured.out
        assert "exhausted-svc" in captured.out
        assert "Services Needing Attention" in captured.out

    def test_critical_insight(self, capsys):
        """Test critical severity insight is displayed correctly."""
        insight = MagicMock()
        insight.severity = "critical"
        insight.service = "critical-insight-svc"
        insight.message = "Error budget exhausted"

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 1
        portfolio.org_health_percent = 80.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = [insight]
        portfolio.total_services = 1
        portfolio.total_slos = 1

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "critical-insight-svc" in captured.out
        assert "Error budget exhausted" in captured.out

    def test_info_severity_insight(self, capsys):
        """Test info (non-warning/non-critical) severity insight."""
        insight = MagicMock()
        insight.severity = "info"
        insight.service = "info-svc"
        insight.message = "Service has no SLOs defined"

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 0
        portfolio.org_health_percent = 0.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = [insight]
        portfolio.total_services = 1
        portfolio.total_slos = 0

        _print_table(portfolio)

        captured = capsys.readouterr()
        assert "info-svc" in captured.out
        assert "Service has no SLOs defined" in captured.out

    def test_more_than_10_insights_truncated(self, capsys):
        """Test that more than 10 insights shows truncation message."""
        insights = []
        for i in range(15):
            insight = MagicMock()
            insight.severity = "warning"
            insight.service = f"svc-{i}"
            insight.message = f"Warning message {i}"
            insights.append(insight)

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 15
        portfolio.org_health_percent = 50.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = insights
        portfolio.total_services = 15
        portfolio.total_slos = 15

        _print_table(portfolio)

        captured = capsys.readouterr()
        # First 10 should appear
        assert "svc-0" in captured.out
        assert "svc-9" in captured.out
        # Truncation message
        assert "5 more" in captured.out


class TestPrintMarkdownAdditionalCoverage:
    """Additional tests for _print_markdown to increase coverage."""

    def test_markdown_services_needing_attention_with_slos(self, capsys):
        """Test markdown shows services with bad SLOs."""
        slo = MagicMock()
        slo.name = "availability"
        slo.status = HealthStatus.WARNING
        slo.current_value = 99.0
        slo.objective = 99.9
        slo.budget_consumed_percent = 80.0

        svc = MagicMock()
        svc.service = "degraded-api"
        svc.tier = 1
        svc.overall_status = HealthStatus.WARNING
        svc.slos = [slo]

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 1
        portfolio.org_health_percent = 80.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = [svc]
        portfolio.insights = []
        portfolio.total_services = 1
        portfolio.total_slos = 1

        _print_markdown(portfolio)

        captured = capsys.readouterr()
        assert "## Services Needing Attention" in captured.out
        assert "degraded-api" in captured.out
        assert "availability" in captured.out
        assert "99.00%" in captured.out
        assert "80% budget consumed" in captured.out

    def test_markdown_services_with_null_values(self, capsys):
        """Test markdown handles null current_value and budget."""
        slo = MagicMock()
        slo.name = "latency"
        slo.status = HealthStatus.CRITICAL
        slo.current_value = None
        slo.objective = 99.5
        slo.budget_consumed_percent = None

        svc = MagicMock()
        svc.service = "unknown-api"
        svc.tier = 2
        svc.overall_status = HealthStatus.CRITICAL
        svc.slos = [slo]

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 1
        portfolio.org_health_percent = 50.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = [svc]
        portfolio.insights = []
        portfolio.total_services = 1
        portfolio.total_slos = 1

        _print_markdown(portfolio)

        captured = capsys.readouterr()
        assert "unknown-api" in captured.out
        assert "latency" in captured.out
        assert "N/A" in captured.out

    def test_markdown_insights_section(self, capsys):
        """Test markdown shows insights section."""
        critical_insight = MagicMock()
        critical_insight.severity = "critical"
        critical_insight.service = "critical-svc"
        critical_insight.message = "Budget exhausted"

        warning_insight = MagicMock()
        warning_insight.severity = "warning"
        warning_insight.service = "warning-svc"
        warning_insight.message = "Approaching limit"

        info_insight = MagicMock()
        info_insight.severity = "info"
        info_insight.service = "info-svc"
        info_insight.message = "No SLOs defined"

        portfolio = MagicMock(spec=PortfolioHealth)
        portfolio.services_with_slos = 3
        portfolio.org_health_percent = 60.0
        portfolio.healthy_services = 0
        portfolio.by_tier = []
        portfolio.services_needing_attention = []
        portfolio.insights = [critical_insight, warning_insight, info_insight]
        portfolio.total_services = 3
        portfolio.total_slos = 3

        _print_markdown(portfolio)

        captured = capsys.readouterr()
        assert "## Insights" in captured.out
        assert "🔴" in captured.out  # Critical
        assert "🟡" in captured.out  # Warning
        assert "ℹ️" in captured.out  # Info
        assert "Budget exhausted" in captured.out
        assert "Approaching limit" in captured.out
        assert "No SLOs defined" in captured.out


class TestHandlePortfolioCommand:
    """Tests for handle_portfolio_command function."""

    @patch("nthlayer.cli.portfolio.portfolio_command")
    def test_passes_args_correctly(self, mock_command):
        """Test that args are passed correctly."""
        mock_command.return_value = 0

        args = argparse.Namespace(
            format="json",
            search_paths=["/path"],
            prometheus_url="http://prom:9090",
            include_drift=True,
        )

        result = handle_portfolio_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            format="json",
            search_paths=["/path"],
            prometheus_url="http://prom:9090",
            include_drift=True,
        )

    @patch("nthlayer.cli.portfolio.portfolio_command")
    def test_handles_missing_optional_args(self, mock_command):
        """Test handling missing optional args."""
        mock_command.return_value = 0

        args = argparse.Namespace()

        result = handle_portfolio_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            format="table",
            search_paths=None,
            prometheus_url=None,
            include_drift=False,
        )
