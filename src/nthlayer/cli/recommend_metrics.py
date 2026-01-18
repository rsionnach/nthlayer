"""
CLI command for metric recommendations.

Generates metric recommendations based on service type and validates
coverage against live Prometheus metrics.

Commands:
    nthlayer recommend-metrics <service.yaml>              - Show recommendations
    nthlayer recommend-metrics <service.yaml> --check      - Check against Prometheus
    nthlayer recommend-metrics <service.yaml> --format json - Output as JSON
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import yaml
from rich.table import Table

from nthlayer.cli.ux import console, error, header, info, success
from nthlayer.metrics.discovery import discover_service_metrics
from nthlayer.metrics.models import MetricMatch, MetricRecommendation
from nthlayer.metrics.recommender import recommend_metrics
from nthlayer.specs.parser import parse_service_file


def recommend_metrics_command(
    service_file: str,
    prometheus_url: str | None = None,
    output_format: str = "table",
    level: str = "all",
    check: bool = False,
    show_code: bool = False,
    environment: str | None = None,
    selector_label: str = "service",
) -> int:
    """
    Generate metric recommendations for a service.

    Based on service type and runtime, provides recommendations
    following OpenTelemetry Semantic Conventions.

    Exit codes:
        0 - All required metrics present (or no check performed)
        1 - Missing recommended metrics (warning)
        2 - Missing required metrics (error) or parse failure

    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus server URL (or use env var)
        output_format: Output format ("table", "json", "yaml")
        level: Which metrics to show ("required", "recommended", "all")
        check: Check against live Prometheus
        show_code: Show instrumentation code snippets
        environment: Optional environment name
        selector_label: Prometheus label for service selection

    Returns:
        Exit code (0, 1, or 2)
    """
    header("Metric Recommendations")
    console.print()

    # Parse service file
    try:
        context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        return 2

    service_name = context.name
    service_type = context.type
    service_tier = context.tier
    service_runtime = context.language

    # Show service info
    console.print(f"[muted]Service:[/muted] {service_name}")
    console.print(f"[muted]Type:[/muted] {service_type}")
    console.print(f"[muted]Tier:[/muted] {service_tier}")
    if service_runtime:
        console.print(f"[muted]Runtime:[/muted] {service_runtime}")
    console.print()

    # Discover metrics if --check flag provided
    discovered_metrics: list[str] | None = None
    if check:
        prom_url = prometheus_url or os.environ.get("NTHLAYER_PROMETHEUS_URL")
        if not prom_url:
            error("--check requires Prometheus URL")
            console.print()
            console.print(
                "[muted]Provide via --prometheus-url or NTHLAYER_PROMETHEUS_URL env var[/muted]"
            )
            return 2

        info(f"Discovering metrics from {prom_url}...")
        discovered_metrics = discover_service_metrics(
            prometheus_url=prom_url,
            service_name=service_name,
            selector_label=selector_label,
        )
        info(f"Discovered {len(discovered_metrics)} metrics")
        console.print()

    # Generate recommendations
    recommendation = recommend_metrics(context, discovered_metrics)

    # Output results
    if output_format == "json":
        _output_json(recommendation)
    elif output_format == "yaml":
        _output_yaml(recommendation)
    else:
        _output_table(recommendation, level, show_code, check)

    # Determine exit code
    if check:
        if not recommendation.slo_ready:
            return 2  # Missing required metrics
        if recommendation.recommended_coverage < 1.0:
            return 1  # Missing recommended metrics (warning)
    return 0


def _output_table(
    recommendation: MetricRecommendation,
    level: str,
    show_code: bool,
    checked: bool,
) -> None:
    """Output recommendation as formatted table."""
    console.print("[bold]Standard:[/bold] OpenTelemetry Semantic Conventions")
    console.print()

    # Required metrics
    if level in ("required", "all") and recommendation.required:
        console.print("[bold]REQUIRED (SLO-critical)[/bold]")
        _print_metrics_table(recommendation.required, checked)
        console.print()

    # Recommended metrics
    if level in ("recommended", "all") and recommendation.recommended:
        console.print("[bold]RECOMMENDED[/bold]")
        _print_metrics_table(recommendation.recommended, checked)
        console.print()

    # Runtime metrics
    if level == "all" and recommendation.runtime_metrics:
        runtime_label = recommendation.runtime or "unknown"
        console.print(f"[bold]RUNTIME ({runtime_label})[/bold]")
        _print_metrics_table(recommendation.runtime_metrics, checked)
        console.print()

    # Summary
    console.print("[bold]SUMMARY[/bold]")
    _print_summary(recommendation, checked)

    if show_code:
        console.print()
        _print_code_snippets(recommendation)


def _print_metrics_table(matches: list[MetricMatch], checked: bool) -> None:
    """Print a table of metric matches."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Type")
    table.add_column("Unit")
    if checked:
        table.add_column("Status")
        table.add_column("SLO Usage")

    for match in matches:
        defn = match.definition
        type_str = defn.type.value
        unit_str = defn.unit

        if checked:
            status = _format_status(match.status)
            slo_str = ", ".join(defn.slo_usage) if defn.slo_usage else "-"
            table.add_row(defn.name, type_str, unit_str, status, slo_str)
        else:
            table.add_row(defn.name, type_str, unit_str)

    console.print(table)


def _format_status(status: str) -> str:
    """Format status with color."""
    if status == "found":
        return "[success]FOUND[/success]"
    elif status == "aliased":
        return "[success]FOUND[/success] [muted](aliased)[/muted]"
    elif status == "missing":
        return "[error]MISSING[/error]"
    else:
        return "[muted]UNKNOWN[/muted]"


def _print_summary(recommendation: MetricRecommendation, checked: bool) -> None:
    """Print recommendation summary."""
    req_count = len(recommendation.required)
    rec_count = len(recommendation.recommended)
    runtime_count = len(recommendation.runtime_metrics)

    if checked:
        req_found = sum(1 for m in recommendation.required if m.status in ("found", "aliased"))
        rec_found = sum(1 for m in recommendation.recommended if m.status in ("found", "aliased"))
        runtime_found = sum(
            1 for m in recommendation.runtime_metrics if m.status in ("found", "aliased")
        )

        req_pct = f"{recommendation.required_coverage * 100:.0f}%"
        rec_pct = f"{recommendation.recommended_coverage * 100:.0f}%"

        if recommendation.slo_ready:
            status = "[success]Ready for SLOs[/success]"
        else:
            status = "[error]Missing metrics[/error]"
        console.print(f"  Required:    {req_found}/{req_count} ({req_pct}) {status}")

        console.print(f"  Recommended: {rec_found}/{rec_count} ({rec_pct})")
        if runtime_count > 0:
            console.print(f"  Runtime:     {runtime_found}/{runtime_count}")
    else:
        console.print(f"  Required:    {req_count} metrics")
        console.print(f"  Recommended: {rec_count} metrics")
        if runtime_count > 0:
            console.print(f"  Runtime:     {runtime_count} metrics")
        console.print()
        console.print("[muted]Run with --check to validate against live Prometheus[/muted]")


def _print_code_snippets(recommendation: MetricRecommendation) -> None:
    """Print code snippets for missing metrics."""
    missing = [m for m in recommendation.required if m.status == "missing"]
    if not missing:
        missing = [m for m in recommendation.recommended if m.status == "missing"]

    if not missing:
        success("All checked metrics are present!")
        return

    console.print("[bold]INSTRUMENTATION EXAMPLES[/bold]")
    console.print()

    for match in missing[:3]:  # Show max 3 examples
        defn = match.definition
        console.print(f"[bold cyan]{defn.name}[/bold cyan]")
        console.print(f"[muted]{defn.description}[/muted]")
        console.print()

        # Python example
        console.print("[bold]Python (opentelemetry-api):[/bold]")
        console.print(_generate_python_snippet(defn))
        console.print()


def _generate_python_snippet(defn: Any) -> str:
    """Generate Python instrumentation snippet."""
    from nthlayer.metrics.models import MetricType

    metric_name = defn.name.replace(".", "_")
    type_name = defn.type.value

    if defn.type == MetricType.HISTOGRAM:
        return f"""    from opentelemetry import metrics

    meter = metrics.get_meter("my-service")
    {metric_name} = meter.create_histogram(
        name="{defn.name}",
        unit="{defn.unit}",
        description="{defn.description}"
    )

    # Record a measurement:
    {metric_name}.record(duration_seconds)"""

    elif defn.type == MetricType.COUNTER:
        return f"""    from opentelemetry import metrics

    meter = metrics.get_meter("my-service")
    {metric_name} = meter.create_counter(
        name="{defn.name}",
        unit="{defn.unit}",
        description="{defn.description}"
    )

    # Increment counter:
    {metric_name}.add(1)"""

    elif defn.type == MetricType.GAUGE:
        return f"""    from opentelemetry import metrics

    meter = metrics.get_meter("my-service")
    {metric_name} = meter.create_observable_gauge(
        name="{defn.name}",
        unit="{defn.unit}",
        description="{defn.description}",
        callbacks=[lambda: current_value]
    )"""

    elif defn.type == MetricType.UPDOWN_COUNTER:
        return f"""    from opentelemetry import metrics

    meter = metrics.get_meter("my-service")
    {metric_name} = meter.create_up_down_counter(
        name="{defn.name}",
        unit="{defn.unit}",
        description="{defn.description}"
    )

    # Increment/decrement:
    {metric_name}.add(1)   # Request started
    {metric_name}.add(-1)  # Request completed"""

    return f"    # {type_name} metric: {defn.name}"


def _output_json(recommendation: MetricRecommendation) -> None:
    """Output recommendation as JSON."""
    console.print_json(data=recommendation.to_dict())


def _output_yaml(recommendation: MetricRecommendation) -> None:
    """Output recommendation as YAML."""
    console.print(yaml.dump(recommendation.to_dict(), default_flow_style=False, sort_keys=True))


def register_recommend_metrics_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the recommend-metrics subcommand."""
    parser = subparsers.add_parser(
        "recommend-metrics",
        help="Generate metric recommendations based on service type",
        description="Recommend metrics following OpenTelemetry Semantic Conventions",
    )
    parser.add_argument(
        "service_file",
        help="Path to service YAML file",
    )
    parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL for metric discovery",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "yaml"],
        default="table",
        dest="output_format",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--level",
        choices=["required", "recommended", "all"],
        default="all",
        help="Which metrics to show (default: all)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check against live Prometheus",
    )
    parser.add_argument(
        "--show-code",
        action="store_true",
        help="Show instrumentation code snippets",
    )
    parser.add_argument(
        "--env",
        "-e",
        dest="environment",
        help="Environment for variable substitution",
    )
    parser.add_argument(
        "--selector-label",
        default="service",
        help="Prometheus label for service selection (default: service)",
    )


def handle_recommend_metrics_command(args: argparse.Namespace) -> int:
    """Handle the recommend-metrics subcommand."""
    return recommend_metrics_command(
        service_file=args.service_file,
        prometheus_url=getattr(args, "prometheus_url", None),
        output_format=getattr(args, "output_format", "table"),
        level=getattr(args, "level", "all"),
        check=getattr(args, "check", False),
        show_code=getattr(args, "show_code", False),
        environment=getattr(args, "environment", None),
        selector_label=getattr(args, "selector_label", "service"),
    )
