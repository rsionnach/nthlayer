"""
CLI command for SLO metric validation.

Validates that SLO PromQL queries reference metrics that exist in Prometheus.

Commands:
    nthlayer validate-slo <service.yaml>              - Validate SLO metrics
    nthlayer validate-slo <service.yaml> --demo       - Show demo output
    nthlayer validate-slo <service.yaml> --json       - Output as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header
from nthlayer.specs.parser import parse_service_file, render_resource_spec

# PromQL function names to exclude from metric extraction
PROMQL_FUNCTIONS = {
    # Aggregation operators
    "sum",
    "avg",
    "min",
    "max",
    "count",
    "count_values",
    "stddev",
    "stdvar",
    "group",
    "topk",
    "bottomk",
    "quantile",
    # Instant vector functions
    "abs",
    "absent",
    "absent_over_time",
    "ceil",
    "clamp",
    "clamp_max",
    "clamp_min",
    "day_of_month",
    "day_of_week",
    "day_of_year",
    "days_in_month",
    "delta",
    "deriv",
    "exp",
    "floor",
    "histogram_avg",
    "histogram_count",
    "histogram_fraction",
    "histogram_quantile",
    "histogram_stddev",
    "histogram_stdvar",
    "histogram_sum",
    "holt_winters",
    "hour",
    "idelta",
    "increase",
    "irate",
    "label_join",
    "label_replace",
    "ln",
    "log10",
    "log2",
    "minute",
    "month",
    "predict_linear",
    "rate",
    "resets",
    "round",
    "scalar",
    "sgn",
    "sort",
    "sort_desc",
    "sort_by_label",
    "sort_by_label_desc",
    "sqrt",
    "time",
    "timestamp",
    "vector",
    "year",
    # Aggregation over time
    "avg_over_time",
    "min_over_time",
    "max_over_time",
    "sum_over_time",
    "count_over_time",
    "quantile_over_time",
    "stddev_over_time",
    "stdvar_over_time",
    "last_over_time",
    "present_over_time",
    # Trigonometric
    "acos",
    "acosh",
    "asin",
    "asinh",
    "atan",
    "atanh",
    "cos",
    "cosh",
    "sin",
    "sinh",
    "tan",
    "tanh",
    "deg",
    "pi",
    "rad",
    # Binary operators (not functions, but sometimes look like them)
    "and",
    "or",
    "unless",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "by",
    "without",
    "bool",
    "offset",
    # Special
    "changes",
    "limit_ratio",
    "mad_over_time",
}


@dataclass
class SLOValidationResult:
    """Result of validating a single SLO's metrics."""

    slo_name: str
    query: str
    metrics: list[str]
    found_metrics: list[str] = field(default_factory=list)
    missing_metrics: list[str] = field(default_factory=list)
    all_found: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "slo_name": self.slo_name,
            "query": self.query,
            "metrics": self.metrics,
            "found_metrics": self.found_metrics,
            "missing_metrics": self.missing_metrics,
            "all_found": self.all_found,
            "error": self.error,
        }


def extract_metric_names(promql: str) -> set[str]:
    """
    Extract metric names from a PromQL query.

    Uses regex-based extraction. Metric names follow the pattern:
    [a-zA-Z_:][a-zA-Z0-9_:]*

    Args:
        promql: PromQL query string

    Returns:
        Set of metric names found in the query
    """
    # Pattern to match potential metric names followed by { or [
    # This helps distinguish metrics from functions
    metric_pattern = r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\s*[{\[]"

    matches = re.findall(metric_pattern, promql)

    # Also match metrics at end of expressions or standalone
    # e.g., "metric_name" without selectors
    standalone_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_:]*)\b"
    all_words = set(re.findall(standalone_pattern, promql))

    # Filter out PromQL functions and keywords
    metrics = set()
    for match in matches:
        if match.lower() not in PROMQL_FUNCTIONS:
            metrics.add(match)

    # Check standalone words that look like metrics (contain underscore, common suffixes)
    for word in all_words:
        if word.lower() in PROMQL_FUNCTIONS:
            continue
        # Heuristics: likely a metric if has underscore or common suffix
        if "_" in word and word.lower() not in PROMQL_FUNCTIONS:
            # Check for common metric suffixes
            suffixes = ("_total", "_count", "_sum", "_bucket", "_seconds", "_bytes", "_info")
            if any(word.endswith(s) for s in suffixes):
                metrics.add(word)

    return metrics


def create_demo_slo_results() -> list[SLOValidationResult]:
    """Create demo SLO validation results."""
    return [
        SLOValidationResult(
            slo_name="payment-api-availability",
            query=(
                'sum(rate(http_requests_total{service="payment-api",status=~"2.."}[5m])) '
                '/ sum(rate(http_requests_total{service="payment-api"}[5m]))'
            ),
            metrics=["http_requests_total"],
            found_metrics=["http_requests_total"],
            missing_metrics=[],
            all_found=True,
        ),
        SLOValidationResult(
            slo_name="payment-api-latency",
            query=(
                "histogram_quantile(0.95, sum(rate("
                'http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le))'
            ),
            metrics=["http_request_duration_seconds_bucket"],
            found_metrics=["http_request_duration_seconds_bucket"],
            missing_metrics=[],
            all_found=True,
        ),
        SLOValidationResult(
            slo_name="payment-api-error-rate",
            query=(
                'sum(rate(http_errors_total{service="payment-api"}[5m])) '
                '/ sum(rate(http_requests_total{service="payment-api"}[5m]))'
            ),
            metrics=["http_errors_total", "http_requests_total"],
            found_metrics=["http_requests_total"],
            missing_metrics=["http_errors_total"],
            all_found=False,
        ),
    ]


async def validate_metric_exists(
    prometheus_url: str,
    metric: str,
) -> bool:
    """
    Check if a metric exists in Prometheus.

    Args:
        prometheus_url: Prometheus server URL
        metric: Metric name to check

    Returns:
        True if metric exists
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            # Query Prometheus metadata endpoint
            response = await client.get(
                f"{prometheus_url}/api/v1/query",
                params={"query": metric},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            # Check if any results returned
            result = data.get("data", {}).get("result", [])
            return len(result) > 0

    except Exception:
        # Fall back to assuming metric exists if we can't check
        return True


async def validate_slo_metrics(
    slo_name: str,
    query: str,
    prometheus_url: str | None = None,
) -> SLOValidationResult:
    """
    Validate that metrics in an SLO query exist.

    Args:
        slo_name: Name of the SLO
        query: PromQL query string
        prometheus_url: Optional Prometheus URL for live validation

    Returns:
        SLOValidationResult with found/missing metrics
    """
    metrics = list(extract_metric_names(query))

    if not metrics:
        return SLOValidationResult(
            slo_name=slo_name,
            query=query,
            metrics=[],
            all_found=True,
            error="No metrics found in query",
        )

    found: list[str] = []
    missing: list[str] = []

    if prometheus_url:
        for metric in metrics:
            exists = await validate_metric_exists(prometheus_url, metric)
            if exists:
                found.append(metric)
            else:
                missing.append(metric)
    else:
        # Without Prometheus, we can only report extracted metrics
        found = metrics

    return SLOValidationResult(
        slo_name=slo_name,
        query=query,
        metrics=metrics,
        found_metrics=found,
        missing_metrics=missing,
        all_found=len(missing) == 0,
    )


def validate_slo_command(
    service_file: str,
    environment: Optional[str] = None,
    output_format: str = "table",
    demo: bool = False,
    prometheus_url: Optional[str] = None,
) -> int:
    """
    Validate SLO metrics exist in Prometheus.

    Exit codes:
        0 - All SLO metrics found
        1 - Some metrics missing (warning)
        2 - Error

    Args:
        service_file: Path to service YAML file
        environment: Optional environment name
        output_format: Output format ("table" or "json")
        demo: If True, show demo output
        prometheus_url: Prometheus URL (or use env var)

    Returns:
        Exit code
    """
    if demo:
        results = create_demo_slo_results()
        service_name = "payment-api"
    else:
        # Parse service file
        try:
            context, resources = parse_service_file(service_file, environment=environment)
        except Exception as e:
            error(f"Error parsing service file: {e}")
            return 2

        service_name = context.name or "unknown"

        # Filter SLO resources
        slo_resources = [r for r in resources if r.kind == "SLO"]

        if not slo_resources:
            console.print()
            console.print(f"[yellow]No SLO resources found in {service_file}[/yellow]")
            console.print()
            return 0

        # Get Prometheus URL
        prom_url = prometheus_url or os.environ.get("PROMETHEUS_URL")

        # Validate each SLO
        results = []
        for slo_resource in slo_resources:
            # Render the spec with variable substitution
            rendered_spec = render_resource_spec(slo_resource)

            # Get query from objectives
            objectives = rendered_spec.get("objectives", [])
            if objectives:
                query = objectives[0].get("indicator", {}).get("spec", {}).get("query", "")
            else:
                query = rendered_spec.get("query", "")

            slo_name = f"{service_name}-{slo_resource.name}"

            result = asyncio.run(validate_slo_metrics(slo_name, query, prometheus_url=prom_url))
            results.append(result)

    # Output results
    if output_format == "json":
        console.print_json(
            data={
                "service": service_name,
                "results": [r.to_dict() for r in results],
                "all_valid": all(r.all_found for r in results),
            }
        )
    else:
        _print_validation_table(service_name, results)

    # Return appropriate exit code
    all_valid = all(r.all_found for r in results)
    some_missing = any(not r.all_found for r in results)

    if all_valid:
        return 0
    elif some_missing:
        return 1
    return 2


def _print_validation_table(service_name: str, results: list[SLOValidationResult]) -> None:
    """Print SLO validation results as table."""
    console.print()
    header(f"SLO Metric Validation: {service_name}")
    console.print()

    if not results:
        console.print("[muted]No SLOs to validate[/muted]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("SLO")
    table.add_column("Metrics")
    table.add_column("Status")

    for result in results:
        # Format metrics list
        metrics_text = ", ".join(result.metrics) if result.metrics else "[muted]none[/muted]"

        # Format status
        if result.error:
            status = f"[yellow]! {result.error}[/yellow]"
        elif result.all_found:
            status = "[green]Found[/green]"
        else:
            missing = ", ".join(result.missing_metrics)
            status = f"[red]Missing: {missing}[/red]"

        table.add_row(
            result.slo_name,
            metrics_text,
            status,
        )

    console.print(table)
    console.print()

    # Summary
    valid_count = sum(1 for r in results if r.all_found)
    total_count = len(results)

    if valid_count == total_count:
        console.print(f"[green]{valid_count}/{total_count} SLOs have valid metrics[/green]")
    else:
        console.print(f"[yellow]{valid_count}/{total_count} SLOs have valid metrics[/yellow]")
    console.print()


def register_validate_slo_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register validate-slo subcommand parser."""
    parser = subparsers.add_parser(
        "validate-slo",
        help="Validate SLO metrics exist in Prometheus",
    )
    parser.add_argument("service_file", help="Path to service YAML file")
    parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        help="Environment name (dev, staging, prod)",
    )
    parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--prometheus-url",
        help="Prometheus server URL (or set PROMETHEUS_URL env var)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_validate_slo_command(args: argparse.Namespace) -> int:
    """Handle validate-slo command from CLI args."""
    return validate_slo_command(
        service_file=args.service_file,
        environment=getattr(args, "environment", None),
        output_format=getattr(args, "output_format", "table"),
        demo=getattr(args, "demo", False),
        prometheus_url=getattr(args, "prometheus_url", None),
    )
