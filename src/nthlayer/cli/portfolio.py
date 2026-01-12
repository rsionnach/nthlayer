"""
CLI command for SLO Portfolio.

Usage:
    nthlayer portfolio                      # Basic portfolio view (from YAML)
    nthlayer portfolio --format json        # JSON export
    nthlayer portfolio --format csv         # CSV export
    nthlayer portfolio --format markdown    # Markdown for PR comments
    nthlayer portfolio --prometheus-url URL # Live data from Prometheus
    nthlayer portfolio --drift              # Include drift trend analysis

Exit codes:
    0 = healthy (all SLOs meeting targets)
    1 = warning (some SLOs degraded)
    2 = critical (SLOs exhausted or critical)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os

from rich.table import Table

from nthlayer.cli.ux import console, header
from nthlayer.drift import DriftAnalyzer, DriftResult, DriftSeverity, get_drift_defaults
from nthlayer.portfolio import (
    HealthStatus,
    PortfolioHealth,
    ServiceHealth,
    collect_portfolio,
)


def portfolio_command(
    format: str = "table",
    search_paths: list[str] | None = None,
    prometheus_url: str | None = None,
    include_drift: bool = False,
) -> int:
    """
    Display SLO portfolio health across all services.

    Args:
        format: Output format (table, json, csv, markdown)
        search_paths: Optional directories to search for service files
        prometheus_url: Optional Prometheus URL for live SLO data
        include_drift: If True, include drift trend analysis for each service

    Returns:
        Exit code based on health:
        - 0: healthy (all SLOs meeting targets or unknown)
        - 1: warning (some SLOs degraded)
        - 2: critical (SLOs exhausted or critical)
    """
    # Get Prometheus URL from arg or environment
    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")

    # Collect portfolio data
    portfolio = collect_portfolio(search_paths, prometheus_url=prom_url)

    # Collect drift data if requested
    drift_results: dict[str, DriftResult] = {}
    if include_drift and prom_url:
        drift_results = _collect_drift_data(portfolio, prom_url)

    # Output in requested format
    if format == "json":
        output = portfolio.to_dict()
        if drift_results:
            output["drift"] = {name: r.to_dict() for name, r in drift_results.items()}
        print(json.dumps(output, indent=2, sort_keys=True))
    elif format == "csv":
        _print_csv(portfolio, drift_results)
    elif format == "markdown":
        _print_markdown(portfolio, drift_results)
    else:
        _print_table(portfolio, drift_results)

    # Return exit code based on health (considering drift)
    return _calculate_exit_code(portfolio, drift_results)


def _collect_drift_data(
    portfolio: PortfolioHealth,
    prometheus_url: str,
) -> dict[str, DriftResult]:
    """Collect drift data for all services in portfolio.

    Args:
        portfolio: Portfolio health data
        prometheus_url: Prometheus URL

    Returns:
        Dict mapping service name to DriftResult
    """
    username = os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

    analyzer = DriftAnalyzer(
        prometheus_url=prometheus_url,
        username=username,
        password=password,
    )

    results: dict[str, DriftResult] = {}

    for svc in portfolio.services:
        # Skip services without SLOs
        if not svc.slos:
            continue

        tier = str(svc.tier) if svc.tier else "standard"
        drift_config = get_drift_defaults(tier)

        # Skip if drift not enabled for this tier
        if not drift_config.get("enabled", True):
            continue

        try:
            result = asyncio.run(
                analyzer.analyze(
                    service_name=svc.service,
                    tier=tier,
                    slo="availability",
                    drift_config=drift_config,
                )
            )
            results[svc.service] = result
        except Exception:
            # Skip services where drift analysis fails
            continue

    return results


def _calculate_exit_code(
    portfolio: PortfolioHealth,
    drift_results: dict[str, DriftResult] | None = None,
) -> int:
    """
    Calculate exit code based on portfolio health and drift.

    Returns:
        0: healthy - all SLOs meeting targets (or unknown)
        1: warning - some SLOs degraded but not critical
        2: critical - SLOs exhausted or in critical state, or critical drift
    """
    has_critical = False
    has_warning = False

    for svc in portfolio.services:
        if svc.overall_status == HealthStatus.EXHAUSTED:
            return 2  # Critical - immediate exit
        elif svc.overall_status == HealthStatus.CRITICAL:
            has_critical = True
        elif svc.overall_status == HealthStatus.WARNING:
            has_warning = True

    # Check drift results
    if drift_results:
        for drift in drift_results.values():
            if drift.severity == DriftSeverity.CRITICAL:
                has_critical = True
            elif drift.severity == DriftSeverity.WARN:
                has_warning = True

    if has_critical:
        return 2
    if has_warning:
        return 1
    return 0


def _print_table(
    portfolio: PortfolioHealth,
    drift_results: dict[str, DriftResult] | None = None,
) -> None:
    """Print portfolio in human-readable table format with rich styling."""
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

    # Drift analysis section
    if drift_results:
        console.print("[bold]Drift Analysis:[/bold]")
        console.rule(style="dim")

        drift_table = Table(show_header=True, header_style="bold")
        drift_table.add_column("Service")
        drift_table.add_column("Trend", justify="right")
        drift_table.add_column("Pattern")
        drift_table.add_column("Exhaustion")
        drift_table.add_column("Severity")

        # Sort by severity
        severity_order = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.WARN: 1,
            DriftSeverity.INFO: 2,
            DriftSeverity.NONE: 3,
        }
        sorted_drift = sorted(
            drift_results.items(),
            key=lambda x: severity_order.get(x[1].severity, 99),
        )

        for svc_name, drift in sorted_drift:
            trend_str = f"{drift.metrics.slope_per_week * 100:+.2f}%/wk"
            trend_color = "red" if drift.metrics.slope_per_week < 0 else "green"

            pattern = drift.pattern.value.replace("_", " ").title()

            if drift.projection.days_until_exhaustion is not None:
                days = drift.projection.days_until_exhaustion
                exhaustion_str = f"{days}d"
                exhaustion_color = "red" if days < 14 else "yellow" if days < 30 else "dim"
            else:
                exhaustion_str = "-"
                exhaustion_color = "dim"

            severity_icons = {
                DriftSeverity.CRITICAL: "[red]✗[/red]",
                DriftSeverity.WARN: "[yellow]⚠[/yellow]",
                DriftSeverity.INFO: "[blue]ℹ[/blue]",
                DriftSeverity.NONE: "[green]✓[/green]",
            }
            severity_icon = severity_icons.get(drift.severity, "[dim]?[/dim]")

            drift_table.add_row(
                svc_name,
                f"[{trend_color}]{trend_str}[/]",
                pattern,
                f"[{exhaustion_color}]{exhaustion_str}[/]",
                severity_icon,
            )

        console.print(drift_table)
        console.print()

    # Summary
    console.rule(style="dim")
    summary_parts = [
        f"[bold]Total:[/bold] {portfolio.total_services} services",
        f"{portfolio.services_with_slos} with SLOs",
        f"{portfolio.total_slos} SLOs",
    ]
    if drift_results:
        drifting = sum(
            1
            for d in drift_results.values()
            if d.severity in (DriftSeverity.WARN, DriftSeverity.CRITICAL)
        )
        if drifting > 0:
            summary_parts.append(f"[yellow]{drifting} drifting[/yellow]")
    console.print(", ".join(summary_parts))
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


def _print_markdown(
    portfolio: PortfolioHealth,
    drift_results: dict[str, DriftResult] | None = None,
) -> None:
    """Print portfolio in Markdown format for PR comments, Slack, etc."""
    lines = []

    # Header
    lines.append("# SLO Portfolio Report")
    lines.append("")

    # Summary
    health_pct = portfolio.org_health_percent
    health_emoji = "🟢" if health_pct >= 95 else "🟡" if health_pct >= 80 else "🔴"
    lines.append(f"**Organization Health:** {health_emoji} {health_pct:.0f}%")
    svc_str = f"{portfolio.services_with_slos} with SLOs ({portfolio.healthy_services} healthy)"
    lines.append(f"**Services:** {svc_str}")
    lines.append(f"**Total SLOs:** {portfolio.total_slos}")
    lines.append("")

    # Tier breakdown
    if portfolio.by_tier:
        lines.append("## Health by Tier")
        lines.append("")
        lines.append("| Tier | Health | Services |")
        lines.append("|------|--------|----------|")
        for tier in portfolio.by_tier:
            pct = tier.health_percent
            emoji = "🟢" if pct >= 95 else "🟡" if pct >= 80 else "🔴"
            svc_ratio = f"{tier.healthy_services}/{tier.total_services}"
            lines.append(f"| {tier.tier_name} | {emoji} {pct:.0f}% | {svc_ratio} |")
        lines.append("")

    # Services needing attention
    attention_services = portfolio.services_needing_attention
    if attention_services:
        lines.append("## Services Needing Attention")
        lines.append("")

        status_emojis = {"exhausted": "🔴", "critical": "🔴", "warning": "🟡"}
        for svc in attention_services:
            status_emoji = status_emojis.get(svc.overall_status.value, "⚪")
            lines.append(f"### {status_emoji} {svc.service} (tier-{svc.tier})")
            lines.append("")

            for slo in svc.slos:
                bad_statuses = (HealthStatus.WARNING, HealthStatus.CRITICAL, HealthStatus.EXHAUSTED)
                if slo.status in bad_statuses:
                    val = slo.current_value
                    value_str = f"{val:.2f}%" if val is not None else "N/A"
                    budget = slo.budget_consumed_percent
                    budget_str = f" ({budget:.0f}% budget consumed)" if budget else ""
                    target_str = f"(target: {slo.objective}%)"
                    lines.append(f"- **{slo.name}:** {value_str} {target_str}{budget_str}")

            lines.append("")

    # Insights
    if portfolio.insights:
        lines.append("## Insights")
        lines.append("")
        for insight in portfolio.insights[:10]:
            severity_emoji = {"critical": "🔴", "warning": "🟡"}.get(insight.severity, "ℹ️")
            lines.append(f"- {severity_emoji} **{insight.service}:** {insight.message}")
        lines.append("")

    # Drift Analysis
    if drift_results:
        lines.append("## Drift Analysis")
        lines.append("")
        lines.append("| Service | Trend | Pattern | Exhaustion | Severity |")
        lines.append("|---------|-------|---------|------------|----------|")

        severity_emojis = {
            DriftSeverity.CRITICAL: "🔴",
            DriftSeverity.WARN: "🟡",
            DriftSeverity.INFO: "🔵",
            DriftSeverity.NONE: "🟢",
        }

        for svc_name, drift in drift_results.items():
            trend_str = f"{drift.metrics.slope_per_week * 100:+.2f}%/wk"
            pattern = drift.pattern.value.replace("_", " ")

            if drift.projection.days_until_exhaustion is not None:
                exhaustion_str = f"{drift.projection.days_until_exhaustion}d"
            else:
                exhaustion_str = "-"

            severity_emoji = severity_emojis.get(drift.severity, "⚪")
            lines.append(
                f"| {svc_name} | {trend_str} | {pattern} | {exhaustion_str} | {severity_emoji} |"
            )

        lines.append("")

    print("\n".join(lines))


def _print_csv(
    portfolio: PortfolioHealth,
    drift_results: dict[str, DriftResult] | None = None,
) -> None:
    """Print portfolio in CSV format."""
    rows = portfolio.to_csv_rows()

    if not rows:
        print("service,tier,team,type,slo_name,objective,window,status")
        return

    # Add drift columns if available
    if drift_results:
        for row in rows:
            svc_name = row.get("service", "")
            drift = drift_results.get(svc_name)
            if drift:
                row["drift_trend"] = f"{drift.metrics.slope_per_week * 100:.2f}%/wk"
                row["drift_pattern"] = drift.pattern.value
                row["drift_exhaustion_days"] = (
                    str(drift.projection.days_until_exhaustion)
                    if drift.projection.days_until_exhaustion
                    else ""
                )
                row["drift_severity"] = drift.severity.value
            else:
                row["drift_trend"] = ""
                row["drift_pattern"] = ""
                row["drift_exhaustion_days"] = ""
                row["drift_severity"] = ""

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
        description=(
            "Aggregate SLO status across services. " "Exit codes: 0=healthy, 1=warning, 2=critical"
        ),
    )

    parser.add_argument(
        "--format",
        choices=["table", "json", "csv", "markdown"],
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
        help="Prometheus URL for live SLO data (or set NTHLAYER_PROMETHEUS_URL)",
    )

    parser.add_argument(
        "--drift",
        action="store_true",
        dest="include_drift",
        help="Include drift trend analysis for each service (requires Prometheus)",
    )


def handle_portfolio_command(args: argparse.Namespace) -> int:
    """Handle portfolio subcommand."""
    return portfolio_command(
        format=getattr(args, "format", "table"),
        search_paths=getattr(args, "search_paths", None),
        prometheus_url=getattr(args, "prometheus_url", None),
        include_drift=getattr(args, "include_drift", False),
    )
