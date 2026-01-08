"""
CLI command for drift detection.

Analyzes reliability drift for a service by querying historical SLO metrics
and detecting degradation trends.

Commands:
    nthlayer drift <service.yaml>         - Analyze drift for a service
    nthlayer drift <service.yaml> --json  - Output as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header, info
from nthlayer.drift import (
    DriftAnalysisError,
    DriftAnalyzer,
    DriftSeverity,
    get_drift_defaults,
)
from nthlayer.specs.parser import parse_service_file


def drift_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    environment: Optional[str] = None,
    window: Optional[str] = None,
    slo: str = "availability",
    output_format: str = "table",
    demo: bool = False,
) -> int:
    """
    Analyze reliability drift for a service.

    Queries historical SLO metrics and detects degradation trends.

    Exit codes:
        0 - No significant drift (or positive trend)
        1 - Warning: drift detected, investigate
        2 - Critical: severe drift, immediate action needed

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus server URL (or use env var)
        environment: Optional environment name
        window: Analysis window (e.g., "30d"). Uses tier default if not specified
        slo: SLO name to analyze (default: availability)
        output_format: Output format ("table" or "json")
        demo: If True, show demo output with sample data

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_drift_output(service_file, slo, output_format)

    # Resolve Prometheus URL
    prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
    if not prom_url:
        error("No Prometheus URL provided")
        console.print()
        console.print(
            "[muted]Provide via --prometheus-url or NTHLAYER_PROMETHEUS_URL env var[/muted]"
        )
        return 2

    # Parse service file
    try:
        context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    service_name = context.name or "unknown"
    tier = getattr(context, "tier", "standard") or "standard"

    # Get drift config from tier defaults
    drift_config = get_drift_defaults(tier)

    # Check if drift detection is enabled for this tier
    if not drift_config.get("enabled", True):
        info(f"Drift detection is disabled for tier '{tier}'")
        console.print()
        console.print("[muted]Enable with drift.enabled: true in service.yaml[/muted]")
        return 0

    # Create analyzer with auth if available
    username = os.environ.get("NTHLAYER_METRICS_USER")
    password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

    analyzer = DriftAnalyzer(
        prometheus_url=prom_url,
        username=username,
        password=password,
    )

    # Override window if provided
    analysis_window = window or drift_config["window"]

    # Run analysis
    try:
        result = asyncio.run(
            analyzer.analyze(
                service_name=service_name,
                tier=tier,
                slo=slo,
                window=analysis_window,
                drift_config=drift_config,
            )
        )
    except DriftAnalysisError as e:
        error(f"Drift analysis failed: {e}")
        return 2
    except Exception as e:
        error(f"Unexpected error: {e}")
        return 2

    # Output results
    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        _print_drift_table(result)

    return result.exit_code


def _print_drift_table(result) -> None:
    """Print drift analysis as formatted table."""
    # Severity coloring
    severity_colors = {
        DriftSeverity.NONE: "green",
        DriftSeverity.INFO: "blue",
        DriftSeverity.WARN: "yellow",
        DriftSeverity.CRITICAL: "red",
    }
    color = severity_colors[result.severity]

    # Header
    console.print()
    header(f"Drift Analysis: {result.service_name}")
    console.print()
    console.print(f"[cyan]SLO:[/cyan] {result.slo_name}")
    console.print(f"[cyan]Window:[/cyan] {result.window}")
    console.print(
        f"[cyan]Data Range:[/cyan] {result.data_start:%Y-%m-%d} → {result.data_end:%Y-%m-%d}"
    )
    console.print()

    # Metrics table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Current Budget", f"{result.metrics.current_budget:.2%}")
    table.add_row(
        "Trend",
        f"[{'red' if result.metrics.slope_per_week < 0 else 'green'}]"
        f"{result.metrics.slope_per_week * 100:+.3f}%/week[/]",
    )
    table.add_row("Pattern", result.pattern.value.replace("_", " ").title())
    table.add_row("Fit Quality (R²)", f"{result.metrics.r_squared:.3f}")
    table.add_row("Data Points", str(result.metrics.data_points))

    console.print(table)
    console.print()

    # Projection table
    console.print("[bold]Projection:[/bold]")
    proj_table = Table(show_header=False, box=None, padding=(0, 2))
    proj_table.add_column("Label", style="muted")
    proj_table.add_column("Value")

    if result.projection.days_until_exhaustion is not None:
        days = result.projection.days_until_exhaustion
        exhaustion_color = "red" if days < 14 else "yellow" if days < 30 else "green"
        proj_table.add_row("Days to Exhaustion", f"[{exhaustion_color}]{days} days[/]")
    else:
        proj_table.add_row("Days to Exhaustion", "[green]N/A (stable or improving)[/]")

    proj_table.add_row("Budget in 30d", f"{result.projection.projected_budget_30d:.2%}")
    proj_table.add_row("Budget in 60d", f"{result.projection.projected_budget_60d:.2%}")
    proj_table.add_row("Confidence", f"{result.projection.confidence:.0%}")

    console.print(proj_table)
    console.print()

    # Severity banner
    severity_icons = {
        DriftSeverity.NONE: "✓",
        DriftSeverity.INFO: "ℹ",
        DriftSeverity.WARN: "⚠",
        DriftSeverity.CRITICAL: "✗",
    }
    icon = severity_icons[result.severity]

    console.print(f"[{color} bold]{icon} Severity: {result.severity.value.upper()}[/]")
    console.print(f"[muted]{result.summary}[/muted]")
    console.print()

    if result.recommendation and result.severity != DriftSeverity.NONE:
        console.print(f"[bold]Recommendation:[/bold] {result.recommendation}")
        console.print()


def _demo_drift_output(service_file: str, slo: str, output_format: str) -> int:
    """Show demo drift analysis output."""
    from datetime import datetime, timedelta

    from nthlayer.drift.models import (
        DriftMetrics,
        DriftPattern,
        DriftProjection,
        DriftResult,
        DriftSeverity,
    )

    # Create demo result
    now = datetime.now()
    result = DriftResult(
        service_name="payment-api",
        tier="critical",
        slo_name=slo,
        window="30d",
        analyzed_at=now,
        data_start=now - timedelta(days=30),
        data_end=now,
        metrics=DriftMetrics(
            slope_per_day=-0.00074,
            slope_per_week=-0.00523,
            r_squared=0.847,
            current_budget=0.7234,
            budget_at_window_start=0.8012,
            variance=0.00089,
            data_points=720,
        ),
        projection=DriftProjection(
            days_until_exhaustion=138,
            projected_budget_30d=0.7025,
            projected_budget_60d=0.6817,
            projected_budget_90d=0.6608,
            confidence=0.847,
        ),
        pattern=DriftPattern.GRADUAL_DECLINE,
        severity=DriftSeverity.WARN,
        summary="Error budget declining at 0.52% per week with high confidence (R²=0.85).",
        recommendation=(
            "Investigate recent changes. Common causes: increased traffic, "
            "dependency degradation, or configuration drift. "
            "Run `nthlayer verify` to check metric coverage."
        ),
        exit_code=1,
    )

    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        _print_drift_table(result)

    return result.exit_code


def register_drift_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register drift subcommand parser."""
    drift_parser = subparsers.add_parser(
        "drift",
        help="Analyze reliability drift for a service",
    )
    drift_parser.add_argument("service_file", help="Path to service YAML file")
    drift_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus server URL (or set NTHLAYER_PROMETHEUS_URL)",
    )
    drift_parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        help="Environment name (dev, staging, prod)",
    )
    drift_parser.add_argument(
        "--window",
        "-w",
        help="Analysis window (e.g., 30d, 14d). Uses tier default if not specified",
    )
    drift_parser.add_argument(
        "--slo",
        "-s",
        default="availability",
        help="SLO to analyze (default: availability)",
    )
    drift_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    drift_parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_drift_command(args: argparse.Namespace) -> int:
    """Handle drift command from CLI args."""
    return drift_command(
        service_file=args.service_file,
        prometheus_url=getattr(args, "prometheus_url", None),
        environment=getattr(args, "environment", None),
        window=getattr(args, "window", None),
        slo=getattr(args, "slo", "availability"),
        output_format=getattr(args, "output_format", "table"),
        demo=getattr(args, "demo", False),
    )
