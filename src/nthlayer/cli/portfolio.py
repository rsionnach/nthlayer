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

from rich.table import Table

from nthlayer.cli.ux import console, header
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
    """Print portfolio in human-readable text format with rich styling."""
    console.print()
    header("NthLayer SLO Portfolio")
    console.print()

    # Overall health with color coding
    if portfolio.services_with_slos > 0:
        health_pct = portfolio.org_health_percent
        if health_pct >= 95:
            health_color = "green"
        elif health_pct >= 80:
            health_color = "yellow"
        else:
            health_color = "red"
        svc_count = f"{portfolio.healthy_services}/{portfolio.services_with_slos}"
        console.print(
            f"Organization Health: [{health_color} bold]{health_pct:.0f}%[/{health_color} bold] "
            f"[dim]({svc_count} services meeting SLOs)[/dim]"
        )
    else:
        console.print("[yellow]Organization Health: No SLOs defined[/yellow]")

    console.print()

    # By tier breakdown with rich table
    if portfolio.by_tier:
        table = Table(title="Health by Tier", show_header=True, header_style="bold cyan")
        table.add_column("Tier", style="bold")
        table.add_column("Health", justify="right")
        table.add_column("Progress", width=22)
        table.add_column("Services", justify="right")

        for tier in portfolio.by_tier:
            health_color = (
                "green"
                if tier.health_percent >= 95
                else "yellow"
                if tier.health_percent >= 80
                else "red"
            )
            bar = _progress_bar(tier.health_percent, width=20)
            table.add_row(
                f"Tier {tier.tier} ({tier.tier_name})",
                f"[{health_color}]{tier.health_percent:.0f}%[/{health_color}]",
                bar,
                f"{tier.healthy_services}/{tier.total_services}",
            )

        console.print(table)
        console.print()

    # Services needing attention
    attention_services = portfolio.services_needing_attention
    if attention_services:
        console.print("[bold red]Services Needing Attention:[/bold red]")
        console.rule(style="red")

        # Sort by severity (exhausted > critical > warning)
        status_order = {
            HealthStatus.EXHAUSTED: 0,
            HealthStatus.CRITICAL: 1,
            HealthStatus.WARNING: 2,
        }
        attention_services.sort(key=lambda s: (status_order.get(s.overall_status, 99), -s.tier))

        for svc in attention_services:
            _print_service_attention(svc)

        console.print()

    # Insights
    if portfolio.insights:
        console.print("[bold]Insights:[/bold]")
        console.rule(style="dim")

        for insight in portfolio.insights[:10]:  # Limit to 10
            if insight.severity == "critical":
                console.print(f"  [red]!![/red] {insight.service}: {insight.message}")
            elif insight.severity == "warning":
                console.print(f"  [yellow]![/yellow] {insight.service}: {insight.message}")
            else:
                console.print(f"  [dim]•[/dim] {insight.service}: {insight.message}")

        if len(portfolio.insights) > 10:
            console.print(f"  [dim]... and {len(portfolio.insights) - 10} more[/dim]")

        console.print()

    # Summary
    console.rule(style="dim")
    console.print(
        f"[bold]Total:[/bold] {portfolio.total_services} services, "
        f"{portfolio.services_with_slos} with SLOs, "
        f"{portfolio.total_slos} SLOs"
    )
    console.print()


def _print_service_attention(svc: ServiceHealth) -> None:
    """Print a service that needs attention."""
    # Status icon and color
    status_config = {
        HealthStatus.EXHAUSTED: ("[X]", "red bold"),
        HealthStatus.CRITICAL: ("[!!]", "red"),
        HealthStatus.WARNING: ("[!]", "yellow"),
    }
    icon, style = status_config.get(svc.overall_status, ("[?]", "dim"))

    console.print(
        f"[{style}]{icon}[/{style}] [bold]{svc.service}[/bold] [dim](tier-{svc.tier})[/dim]"
    )

    # Show SLOs with issues
    for slo in svc.slos:
        if slo.status in (HealthStatus.WARNING, HealthStatus.CRITICAL, HealthStatus.EXHAUSTED):
            status_str = slo.status.value.upper()
            slo_style = "red" if slo.status == HealthStatus.EXHAUSTED else "yellow"
            if slo.current_value is not None:
                console.print(
                    f"     {slo.name}: [{slo_style}]{slo.current_value:.2f}%[/{slo_style}] "
                    f"[dim](target: {slo.objective}%)[/dim] - "
                    f"[{slo_style}]{status_str}[/{slo_style}]"
                )
            else:
                console.print(
                    f"     {slo.name}: [dim]target {slo.objective}%[/dim] - "
                    f"[{slo_style}]{status_str}[/{slo_style}]"
                )

            if slo.budget_consumed_percent is not None:
                budget_style = "red" if slo.budget_consumed_percent > 90 else "yellow"
                console.print(
                    f"     [dim]Budget:[/dim] "
                    f"[{budget_style}]{slo.budget_consumed_percent:.0f}% consumed[/{budget_style}]"
                )

    console.print()


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
