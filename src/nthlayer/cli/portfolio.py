"""
CLI command for SLO Portfolio.

Usage:
    nthlayer portfolio              # Basic portfolio view
    nthlayer portfolio --format json  # JSON export
    nthlayer portfolio --format csv   # CSV export
"""

from __future__ import annotations

import argparse
import csv
import io
import json

from nthlayer.portfolio import (
    HealthStatus,
    PortfolioHealth,
    ServiceHealth,
    collect_portfolio,
)


def portfolio_command(
    format: str = "text",
    search_paths: list[str] | None = None,
) -> int:
    """
    Display SLO portfolio health across all services.

    Args:
        format: Output format (text, json, csv)
        search_paths: Optional directories to search for service files

    Returns:
        Exit code (0 for success)
    """
    # Collect portfolio data
    portfolio = collect_portfolio(search_paths)

    # Output in requested format
    if format == "json":
        print(json.dumps(portfolio.to_dict(), indent=2))
    elif format == "csv":
        _print_csv(portfolio)
    else:
        _print_text(portfolio)

    return 0


def _print_text(portfolio: PortfolioHealth) -> None:
    """Print portfolio in human-readable text format."""
    print()
    print("=" * 80)
    print("  NthLayer SLO Portfolio")
    print("=" * 80)
    print()

    # Overall health
    if portfolio.services_with_slos > 0:
        health_pct = portfolio.org_health_percent
        print(
            f"Organization Health: {health_pct:.0f}% "
            f"({portfolio.healthy_services}/{portfolio.services_with_slos} services meeting SLOs)"
        )
    else:
        print("Organization Health: No SLOs defined")

    print()

    # By tier breakdown
    if portfolio.by_tier:
        print("By Tier:")
        for tier in portfolio.by_tier:
            bar = _progress_bar(tier.health_percent, width=20)
            print(
                f"  Tier {tier.tier} ({tier.tier_name}):  {tier.health_percent:5.0f}%  "
                f"{bar}  {tier.healthy_services}/{tier.total_services} services"
            )
        print()

    # Services needing attention
    attention_services = portfolio.services_needing_attention
    if attention_services:
        print("-" * 80)
        print("Services Needing Attention:")
        print("-" * 80)

        # Sort by severity (exhausted > critical > warning)
        status_order = {
            HealthStatus.EXHAUSTED: 0,
            HealthStatus.CRITICAL: 1,
            HealthStatus.WARNING: 2,
        }
        attention_services.sort(key=lambda s: (status_order.get(s.overall_status, 99), -s.tier))

        for svc in attention_services:
            _print_service_attention(svc)

        print()

    # Insights
    if portfolio.insights:
        print("-" * 80)
        print("Insights:")
        print("-" * 80)

        for insight in portfolio.insights[:10]:  # Limit to 10
            icon = "•"
            if insight.severity == "warning":
                icon = "!"
            elif insight.severity == "critical":
                icon = "!!"
            print(f"{icon} {insight.service}: {insight.message}")

        if len(portfolio.insights) > 10:
            print(f"  ... and {len(portfolio.insights) - 10} more")

        print()

    # Summary
    print("-" * 80)
    print(
        f"Total: {portfolio.total_services} services, "
        f"{portfolio.services_with_slos} with SLOs, "
        f"{portfolio.total_slos} SLOs"
    )
    print()


def _print_service_attention(svc: ServiceHealth) -> None:
    """Print a service that needs attention."""
    # Status icon
    icons = {
        HealthStatus.EXHAUSTED: "[X]",
        HealthStatus.CRITICAL: "[!!]",
        HealthStatus.WARNING: "[!]",
    }
    icon = icons.get(svc.overall_status, "[?]")

    print(f"{icon} {svc.service} (tier-{svc.tier})")

    # Show SLOs with issues
    for slo in svc.slos:
        if slo.status in (HealthStatus.WARNING, HealthStatus.CRITICAL, HealthStatus.EXHAUSTED):
            status_str = slo.status.value.upper()
            if slo.current_value is not None:
                print(
                    f"     {slo.name}: {slo.current_value:.2f}% "
                    f"(target: {slo.objective}%) - {status_str}"
                )
            else:
                print(f"     {slo.name}: target {slo.objective}% - {status_str}")

            if slo.budget_consumed_percent is not None:
                print(f"     Budget: {slo.budget_consumed_percent:.0f}% consumed")

    print()


def _progress_bar(percent: float, width: int = 20) -> str:
    """Generate a text progress bar."""
    filled = int(width * percent / 100)
    empty = width - filled
    return "█" * filled + "░" * empty


def _print_csv(portfolio: PortfolioHealth) -> None:
    """Print portfolio in CSV format."""
    rows = portfolio.to_csv_rows()

    if not rows:
        print("service,tier,team,type,slo_name,objective,window,status")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    print(output.getvalue())


def register_portfolio_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register portfolio subcommand parser."""
    parser = subparsers.add_parser(
        "portfolio",
        help="View SLO portfolio health across all services",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--path",
        action="append",
        dest="search_paths",
        help="Additional paths to search for service files",
    )


def handle_portfolio_command(args: argparse.Namespace) -> int:
    """Handle portfolio subcommand."""
    return portfolio_command(
        format=getattr(args, "format", "text"),
        search_paths=getattr(args, "search_paths", None),
    )
