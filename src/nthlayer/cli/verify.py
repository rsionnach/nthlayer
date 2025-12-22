"""
CLI command for contract verification.

Verifies that declared metrics in service.yaml exist in a target Prometheus.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import yaml

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.specs.parser import parse_service_file
from nthlayer.verification import MetricVerifier, extract_metric_contract


def verify_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    environment: Optional[str] = None,
    fail_on_missing: bool = True,
    demo: bool = False,
) -> int:
    """
    Verify that declared metrics exist in Prometheus.

    This is the "Contract Verification" step - ensuring that metrics
    declared in service.yaml actually exist before promoting to production.

    Exit codes:
        0 = All metrics verified
        1 = Optional metrics missing (warning)
        2 = Critical SLO metrics missing (block promotion)

    Args:
        service_file: Path to service YAML file
        prometheus_url: Target Prometheus URL (or use env var)
        environment: Optional environment name
        fail_on_missing: If True, exit 2 on critical failures
        demo: If True, show demo output with sample data

    Returns:
        Exit code (0, 1, or 2)
    """
    # Demo mode - show sample output
    if demo:
        return _demo_verify_output(service_file, environment)

    # Resolve Prometheus URL
    prom_url = prometheus_url or os.environ.get("PROMETHEUS_URL")
    if not prom_url:
        error("No Prometheus URL provided")
        console.print()
        console.print("[muted]Provide via --prometheus-url or PROMETHEUS_URL env var[/muted]")
        return 2

    # Parse service file
    try:
        context, resources = parse_service_file(service_file, environment=environment)
    except (FileNotFoundError, yaml.YAMLError, KeyError, ValueError, TypeError) as e:
        error(f"Error parsing service file: {e}")
        return 2

    # Print header
    header(f"Contract Verification: {context.name}")
    console.print()

    console.print(f"[cyan]Target:[/cyan] {prom_url}")
    console.print(f"[cyan]Service:[/cyan] {context.name}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    console.print()

    # Extract metric contract
    contract = extract_metric_contract(context.name, resources)

    if not contract.metrics:
        info("No metrics declared in service.yaml")
        console.print()
        console.print("[muted]Add SLO indicators or Observability.metrics to verify[/muted]")
        return 0

    console.print(f"[muted]Found {len(contract.metrics)} declared metrics[/muted]")
    console.print()

    # Create verifier and test connection
    verifier = MetricVerifier(prometheus_url=prom_url)

    if not verifier.test_connection():
        error(f"Cannot connect to Prometheus at {prom_url}")
        return 2

    # Verify contract
    result = verifier.verify_contract(contract)

    # Display results
    _print_verification_results(result)

    # Return appropriate exit code
    if not fail_on_missing:
        return 0

    return result.exit_code


def _print_verification_results(result) -> None:
    """Print verification results with styling."""
    # Group by critical vs optional
    critical_results = [r for r in result.results if r.metric.is_critical]
    optional_results = [r for r in result.results if not r.metric.is_critical]

    # Print critical metrics (SLO indicators)
    if critical_results:
        console.print("[bold]SLO Metrics (Critical):[/bold]")
        for r in critical_results:
            if r.exists:
                console.print(f"  [success]✓[/success] {r.metric.name}")
            elif r.error:
                console.print(f"  [error]✗[/error] {r.metric.name} [muted]({r.error})[/muted]")
            else:
                console.print(f"  [error]✗[/error] {r.metric.name} [error]← MISSING[/error]")
        console.print()

    # Print optional metrics (Observability)
    if optional_results:
        console.print("[bold]Observability Metrics (Optional):[/bold]")
        for r in optional_results:
            if r.exists:
                console.print(f"  [success]✓[/success] {r.metric.name}")
            elif r.error:
                console.print(f"  [warning]⚠[/warning] {r.metric.name} [muted]({r.error})[/muted]")
            else:
                console.print(
                    f"  [warning]⚠[/warning] {r.metric.name} [muted]← Not instrumented[/muted]"
                )
        console.print()

    # Summary
    console.print("[bold]Summary:[/bold]")
    console.print(f"  [muted]Total:[/muted] {len(result.results)} metrics")
    console.print(f"  [success]✓[/success] Verified: {result.verified_count}")

    missing_critical = len(result.missing_critical)
    missing_optional = len(result.missing_optional)

    if missing_critical:
        console.print(f"  [error]✗[/error] Critical missing: {missing_critical}")
    if missing_optional:
        console.print(f"  [warning]⚠[/warning] Optional missing: {missing_optional}")

    console.print()

    # Final verdict
    if result.all_verified:
        success("All declared metrics verified")
        console.print("[muted]Contract verification passed - safe to promote[/muted]")
    elif result.critical_verified:
        warning("Optional metrics missing")
        console.print("[muted]Critical SLOs verified - promotion allowed with warnings[/muted]")
    else:
        error("Critical SLO metrics missing - blocking promotion")
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for r in result.missing_critical:
            console.print(f"  [muted]•[/muted] Ensure {r.metric.name} is instrumented")
        console.print(
            "  [muted]•[/muted] Run integration tests to generate traffic before re-verifying"
        )

    console.print()

    # Check for missing exporter metrics and provide guidance
    all_missing = [r.metric.name for r in result.results if not r.exists]
    if all_missing:
        _print_exporter_guidance(all_missing)


def _print_exporter_guidance(missing_metrics: list[str]) -> None:
    """Print guidance for missing exporter metrics."""
    from nthlayer.verification.exporter_guidance import (
        detect_missing_exporters,
        format_exporter_guidance,
    )

    missing_by_exporter = detect_missing_exporters(missing_metrics)
    if not missing_by_exporter:
        return

    guidance_lines = format_exporter_guidance(missing_by_exporter)
    for line in guidance_lines:
        console.print(line)


def _demo_verify_output(service_file: str, environment: Optional[str] = None) -> int:
    """Show demo verification output with sample data."""
    # Try to get service name from file
    service_name = "checkout-service"
    try:
        with open(service_file) as f:
            data = yaml.safe_load(f)
            if data and "service" in data:
                service_name = data["service"].get("name", service_name)
            elif data and "name" in data:
                service_name = data.get("name", service_name)
    except Exception:
        pass

    # Print header
    header(f"Contract Verification: {service_name}")
    console.print()

    console.print("[cyan]Target:[/cyan] http://prometheus:9090")
    console.print(f"[cyan]Service:[/cyan] {service_name}")
    if environment:
        console.print(f"[cyan]Environment:[/cyan] {environment}")
    console.print()

    console.print("[muted]Found 4 declared metrics[/muted]")
    console.print()

    # Demo results
    console.print("[bold]SLO Metrics (Critical):[/bold]")
    console.print(f'  [success]✓[/success] http_requests_total{{service="{service_name}"}}')
    console.print(
        f'  [success]✓[/success] http_request_duration_seconds_bucket{{service="{service_name}"}}'
    )
    console.print()

    console.print("[bold]Observability Metrics (Optional):[/bold]")
    console.print(f"  [success]✓[/success] {service_name.replace('-', '_')}_cache_hits_total")
    console.print(
        f"  [warning]⚠[/warning] {service_name.replace('-', '_')}_queue_depth "
        "[muted]← Not instrumented[/muted]"
    )
    console.print()

    console.print("[bold]Summary:[/bold]")
    console.print("  [muted]Total:[/muted] 4 metrics")
    console.print("  [success]✓[/success] Verified: 3")
    console.print("  [warning]⚠[/warning] Optional missing: 1")
    console.print()

    warning("Optional metrics missing")
    console.print("[muted]Critical SLOs verified - promotion allowed with warnings[/muted]")
    console.print()

    return 1  # Exit code 1 = warnings


def register_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register verify subcommand parser."""
    parser = subparsers.add_parser(
        "verify",
        help="Verify declared metrics exist in Prometheus (contract verification)",
    )

    parser.add_argument(
        "service_file",
        help="Path to service YAML file",
    )

    parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Target Prometheus URL (or set PROMETHEUS_URL env var)",
    )

    parser.add_argument(
        "--env",
        dest="environment",
        help="Environment name (dev, staging, prod)",
    )

    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Don't fail on missing metrics (always exit 0)",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data (for VHS recordings)",
    )


def handle_verify_command(args: argparse.Namespace) -> int:
    """Handle verify subcommand."""
    return verify_command(
        service_file=args.service_file,
        prometheus_url=getattr(args, "prometheus_url", None),
        environment=getattr(args, "environment", None),
        fail_on_missing=not getattr(args, "no_fail", False),
        demo=getattr(args, "demo", False),
    )
