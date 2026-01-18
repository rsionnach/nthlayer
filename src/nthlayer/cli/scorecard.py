"""
CLI command for Reliability Scorecard.

Usage:
    nthlayer scorecard                      # Basic scorecard (from YAML)
    nthlayer scorecard --format json        # JSON export
    nthlayer scorecard --format csv         # CSV export
    nthlayer scorecard --by-team            # Group by team
    nthlayer scorecard --prometheus-url URL # Live data from Prometheus

Exit codes:
    0 = excellent/good (score >= 75)
    1 = fair (score 50-74)
    2 = poor/critical (score < 50)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from datetime import UTC, datetime

from rich.panel import Panel
from rich.table import Table

from nthlayer.cli.ux import console, header
from nthlayer.portfolio import collect_portfolio
from nthlayer.scorecard.calculator import ScoreCalculator
from nthlayer.scorecard.models import ScoreBand, ScorecardReport, ServiceScore, TeamScore
from nthlayer.scorecard.trends import TrendAnalyzer

# Band styling for table output
BAND_STYLES: dict[ScoreBand, tuple[str, str]] = {
    ScoreBand.EXCELLENT: ("green bold", "\u2713"),  # ✓
    ScoreBand.GOOD: ("green", "\u2713"),  # ✓
    ScoreBand.FAIR: ("yellow", "!"),
    ScoreBand.POOR: ("red", "!!"),
    ScoreBand.CRITICAL: ("red bold", "\u2717"),  # ✗
}


def scorecard_command(
    format: str = "table",
    search_paths: list[str] | None = None,
    prometheus_url: str | None = None,
    by_team: bool = False,
    top_n: int = 5,
) -> int:
    """
    Display reliability scorecard.

    Args:
        format: Output format (table, json, csv)
        search_paths: Optional directories to search for service files
        prometheus_url: Optional Prometheus URL for live data
        by_team: If True, display by team instead of by service
        top_n: Number of top/bottom services to highlight

    Returns:
        Exit code: 0=excellent/good, 1=fair, 2=poor/critical
    """
    # Get Prometheus URL from arg or environment
    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")

    # Collect portfolio data
    portfolio = collect_portfolio(search_paths, prometheus_url=prom_url)

    # Calculate scores
    calculator = ScoreCalculator(prometheus_url=prom_url)
    trend_analyzer = TrendAnalyzer(prometheus_url=prom_url)

    service_scores: list[ServiceScore] = []
    for svc_health in portfolio.services:
        # Get budget remaining from SLO health
        budget_remaining = 100.0
        if svc_health.slos:
            budgets = [
                s.budget_consumed_percent
                for s in svc_health.slos
                if s.budget_consumed_percent is not None
            ]
            if budgets:
                avg_consumed = sum(budgets) / len(budgets)
                budget_remaining = max(0, 100 - avg_consumed)

        score = calculator.calculate_service_score(
            service_health=svc_health,
            incident_count=0,  # MVP: No incident source yet
            deploys_successful=0,
            deploys_total=0,
            budget_remaining_percent=budget_remaining,
        )

        # Add trend data
        score.score_30d_ago = trend_analyzer.get_historical_score(svc_health.service, 30)
        score.score_90d_ago = trend_analyzer.get_historical_score(svc_health.service, 90)
        score.trend_direction = trend_analyzer.calculate_trend_direction(
            score.score, score.score_30d_ago
        )

        service_scores.append(score)

    # Calculate team scores
    team_scores: list[TeamScore] = []
    teams = set(s.team for s in service_scores)
    for team in sorted(teams):
        team_services = [s for s in service_scores if s.team == team]
        team_score = calculator.calculate_team_score(team, team_services)
        team_scores.append(team_score)

    # Calculate org score
    org_score = calculator.calculate_org_score(service_scores)
    org_band = calculator.score_to_band(org_score)

    # Build report
    report = ScorecardReport(
        timestamp=datetime.now(UTC),
        period="30d",
        org_score=org_score,
        org_band=org_band,
        services=service_scores,
        teams=team_scores,
        top_services=sorted(service_scores, key=lambda s: s.score, reverse=True)[:top_n],
        bottom_services=sorted(service_scores, key=lambda s: s.score)[:top_n],
        most_improved=[],  # MVP: No trend data yet
    )

    # Output
    if format == "json":
        _print_json(report)
    elif format == "csv":
        _print_csv(report)
    elif by_team:
        _print_team_table(report)
    else:
        _print_table(report)

    # Exit code based on org score
    if report.org_band in (ScoreBand.EXCELLENT, ScoreBand.GOOD):
        return 0
    elif report.org_band == ScoreBand.FAIR:
        return 1
    else:
        return 2


def _print_table(report: ScorecardReport) -> None:
    """Print scorecard in table format."""
    console.print()
    header("Reliability Scorecard")
    console.print()

    # Org score banner
    style, icon = BAND_STYLES[report.org_band]
    console.print(
        Panel(
            f"[{style}]{icon} {report.org_score:.0f}[/{style}]  "
            f"[dim]{report.org_band.value.upper()}[/dim]",
            title="Organization Score",
            border_style=style.split()[0],
        )
    )
    console.print()

    # Service scores table
    table = Table(title="Service Scores", show_header=True, header_style="bold cyan")
    table.add_column("Service", style="bold")
    table.add_column("Tier", justify="center")
    table.add_column("Team")
    table.add_column("Score", justify="right")
    table.add_column("Band")
    table.add_column("SLO", justify="right")
    table.add_column("Budget", justify="right")

    # Sort by score descending
    for svc in sorted(report.services, key=lambda s: s.score, reverse=True):
        style, icon = BAND_STYLES[svc.band]
        c = svc.components
        table.add_row(
            svc.service,
            str(svc.tier),
            svc.team,
            f"[{style}]{svc.score:.0f}[/{style}]",
            f"[{style}]{icon}[/{style}]",
            f"{c.slos_met}/{c.slos_total}",
            f"{c.budget_percent_remaining:.0f}%",
        )

    console.print(table)
    console.print()

    # Summary
    console.rule(style="dim")
    console.print(
        f"[bold]Total:[/bold] {len(report.services)} services, " f"{len(report.teams)} teams"
    )
    console.print()


def _print_team_table(report: ScorecardReport) -> None:
    """Print scorecard grouped by team."""
    console.print()
    header("Reliability Scorecard - By Team")
    console.print()

    # Org score banner
    style, icon = BAND_STYLES[report.org_band]
    console.print(
        Panel(
            f"[{style}]{icon} {report.org_score:.0f}[/{style}]  "
            f"[dim]{report.org_band.value.upper()}[/dim]",
            title="Organization Score",
            border_style=style.split()[0],
        )
    )
    console.print()

    # Team scores table
    table = Table(title="Team Scores", show_header=True, header_style="bold cyan")
    table.add_column("Team", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Band")
    table.add_column("Services", justify="right")
    table.add_column("Tier 1", justify="right")
    table.add_column("Tier 2", justify="right")
    table.add_column("Tier 3", justify="right")

    # Sort by score descending
    for team in sorted(report.teams, key=lambda t: t.score, reverse=True):
        style, icon = BAND_STYLES[team.band]
        table.add_row(
            team.team,
            f"[{style}]{team.score:.0f}[/{style}]",
            f"[{style}]{icon}[/{style}]",
            str(team.service_count),
            f"{team.tier1_score:.0f}" if team.tier1_score is not None else "-",
            f"{team.tier2_score:.0f}" if team.tier2_score is not None else "-",
            f"{team.tier3_score:.0f}" if team.tier3_score is not None else "-",
        )

    console.print(table)
    console.print()


def _print_json(report: ScorecardReport) -> None:
    """Print scorecard in JSON format."""
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))


def _print_csv(report: ScorecardReport) -> None:
    """Print scorecard in CSV format."""
    rows = report.to_csv_rows()

    if not rows:
        print("service,tier,team,type,score,band")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    print(output.getvalue())


def register_scorecard_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register scorecard subcommand parser."""
    parser = subparsers.add_parser(
        "scorecard",
        help="Display reliability scorecard with weighted scores",
        description=(
            "Calculate per-service reliability scores (0-100). "
            "Exit codes: 0=good, 1=fair, 2=poor"
        ),
    )

    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )

    parser.add_argument(
        "--path",
        action="append",
        dest="search_paths",
        help="Additional paths to search for service files",
    )

    parser.add_argument(
        "--prometheus-url",
        dest="prometheus_url",
        help="Prometheus URL for live data (or set NTHLAYER_PROMETHEUS_URL)",
    )

    parser.add_argument(
        "--by-team",
        action="store_true",
        help="Group and display scores by team",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=5,
        dest="top_n",
        help="Number of top/bottom services to highlight (default: 5)",
    )


def handle_scorecard_command(args: argparse.Namespace) -> int:
    """Handle scorecard subcommand."""
    return scorecard_command(
        format=getattr(args, "format", "table"),
        search_paths=getattr(args, "search_paths", None),
        prometheus_url=getattr(args, "prometheus_url", None),
        by_team=getattr(args, "by_team", False),
        top_n=getattr(args, "top_n", 5),
    )
