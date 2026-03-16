"""
CLI command for Monte Carlo SLO simulation.
"""

from __future__ import annotations

import argparse
from typing import Optional

from nthlayer.cli.ux import console, error
from nthlayer.simulate.engine import run_simulation
from nthlayer.simulate.graph import build_dependency_models, build_failure_models
from nthlayer.simulate.models import (
    PercentileResult,
    ServiceSimulationResult,
    SimulationResult,
    WhatIfResult,
)
from nthlayer.simulate.output import print_simulation_table
from nthlayer.simulate.what_if import apply_scenario, parse_what_if


def simulate_command(
    manifest_file: str,
    manifests_dir: Optional[str] = None,
    num_runs: int = 10000,
    horizon_days: int = 90,
    seed: Optional[int] = None,
    what_if: Optional[list[str]] = None,
    output_format: str = "table",
    min_p_sla: Optional[float] = None,
    demo: bool = False,
) -> int:
    """
    Run Monte Carlo SLO simulation.

    Exit codes:
        0 - SLA likely met (P >= 0.80)
        1 - Marginal (P >= 0.50)
        2 - SLA likely missed or error

    Args:
        manifest_file: Path to the primary manifest YAML file.
        manifests_dir: Optional directory containing additional manifests.
        num_runs: Number of Monte Carlo iterations (default 10000).
        horizon_days: Simulation horizon in days (default 90).
        seed: Optional random seed for reproducibility.
        what_if: Optional list of what-if scenario strings.
        output_format: Output format ("table" or "json").
        min_p_sla: Optional minimum P(meeting SLA) threshold for exit code.
        demo: If True, show demo output with sample data.

    Returns:
        Exit code (0, 1, or 2).
    """
    if demo:
        return _demo_simulate_output(output_format)

    # Load manifests
    try:
        from nthlayer.specs.loader import load_manifest

        manifests = [load_manifest(manifest_file)]
    except FileNotFoundError:
        error(f"Manifest file not found: {manifest_file}")
        return 2
    except Exception as e:
        error(f"Error loading manifest: {e}")
        return 2

    # Load additional manifests from directory
    if manifests_dir:
        dir_manifests = _load_manifests_from_dir(manifests_dir, exclude=manifest_file)
        manifests.extend(dir_manifests)

    # Build simulation models
    try:
        failure_models = build_failure_models(manifests)
        dependency_models = build_dependency_models(manifests)
    except Exception as e:
        error(f"Error building simulation models: {e}")
        return 2

    # Run simulation
    try:
        result = run_simulation(
            services=failure_models,
            dependencies=dependency_models,
            num_runs=num_runs,
            horizon_days=horizon_days,
            seed=seed,
        )
    except Exception as e:
        error(f"Simulation failed: {e}")
        return 2

    # What-if scenarios
    if what_if:
        for scenario_str in what_if:
            try:
                scenario = parse_what_if(scenario_str)
                mod_services, mod_deps = apply_scenario(
                    list(failure_models), list(dependency_models), scenario
                )
                mod_result = run_simulation(
                    services=mod_services,
                    dependencies=mod_deps,
                    num_runs=num_runs,
                    horizon_days=horizon_days,
                    seed=seed,
                )
                what_if_result = WhatIfResult(
                    scenario=scenario_str,
                    base_p_meeting_sla=result.p_meeting_sla,
                    modified_p_meeting_sla=mod_result.p_meeting_sla,
                    delta=mod_result.p_meeting_sla - result.p_meeting_sla,
                    base_weakest_link=result.weakest_link,
                    modified_weakest_link=mod_result.weakest_link,
                )
                result.what_if_results.append(what_if_result)
            except Exception as e:
                error(f"What-if scenario '{scenario_str}' failed: {e}")

    # Determine exit code
    exit_code = result.exit_code
    if min_p_sla is not None:
        exit_code = 0 if result.p_meeting_sla >= min_p_sla else 1

    # Output results
    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        print_simulation_table(result)

    return exit_code


def _load_manifests_from_dir(directory: str, exclude: str = "") -> list:
    """Load all manifest YAML files from a directory.

    Silently skips files that are not valid manifests.

    Args:
        directory: Path to directory containing manifest files.
        exclude: Filename to exclude (e.g., the primary manifest already loaded).

    Returns:
        List of ReliabilityManifest objects.
    """
    from pathlib import Path

    from nthlayer.specs.loader import load_manifest

    manifests: list = []
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return manifests

    for yaml_file in sorted(dir_path.iterdir()):
        if yaml_file.suffix not in (".yaml", ".yml"):
            continue
        if str(yaml_file) == exclude or yaml_file.name == exclude:
            continue
        try:
            manifest = load_manifest(str(yaml_file))
            manifests.append(manifest)
        except Exception:
            pass  # intentionally ignored: non-manifest YAML files in directory are skipped

    return manifests


def _demo_simulate_output(output_format: str) -> int:
    """Show demo simulation output with hardcoded sample data.

    Args:
        output_format: Output format ("table" or "json").

    Returns:
        Exit code (always 0 for demo mode).
    """
    # Build a realistic demo result with three services
    services = {
        "checkout-service": ServiceSimulationResult(
            name="checkout-service",
            target=0.999,
            p_meeting_sla=0.8234,
            availability_p50=0.99945,
            availability_p95=0.99812,
            availability_p99=0.99634,
            downtime_contribution=0.35,
            is_weakest_link=False,
        ),
        "payment-api": ServiceSimulationResult(
            name="payment-api",
            target=0.9995,
            p_meeting_sla=0.7156,
            availability_p50=0.99972,
            availability_p95=0.99891,
            availability_p99=0.99743,
            downtime_contribution=0.45,
            is_weakest_link=True,
        ),
        "database-primary": ServiceSimulationResult(
            name="database-primary",
            target=0.9999,
            p_meeting_sla=0.9412,
            availability_p50=0.99997,
            availability_p95=0.99985,
            availability_p99=0.99962,
            downtime_contribution=0.20,
            is_weakest_link=False,
        ),
    }

    what_if_results = [
        WhatIfResult(
            scenario="redundant:payment-api",
            base_p_meeting_sla=0.8234,
            modified_p_meeting_sla=0.9512,
            delta=0.1278,
            base_weakest_link="payment-api",
            modified_weakest_link="checkout-service",
        ),
        WhatIfResult(
            scenario="improve:database-primary:availability:0.99999",
            base_p_meeting_sla=0.8234,
            modified_p_meeting_sla=0.8456,
            delta=0.0222,
            base_weakest_link="payment-api",
            modified_weakest_link="payment-api",
        ),
    ]

    result = SimulationResult(
        target_service="checkout-service",
        target_sla=0.999,
        horizon_days=90,
        num_runs=10000,
        p_meeting_sla=0.8234,
        services=services,
        weakest_link="payment-api",
        weakest_link_contribution=0.45,
        error_budget_forecast=PercentileResult(p50=0.62, p75=0.41, p95=0.12),
        what_if_results=what_if_results,
        exit_code=0,
    )

    if output_format == "json":
        console.print_json(data=result.to_dict())
    else:
        print_simulation_table(result)

    return 0


def register_simulate_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register simulate subcommand parser."""
    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Run Monte Carlo SLO reliability simulation",
    )
    simulate_parser.add_argument(
        "manifest_file",
        help="Path to the primary service manifest YAML file",
    )
    simulate_parser.add_argument(
        "--manifests-dir",
        help="Directory containing additional manifest files for dependencies",
    )
    simulate_parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=10000,
        dest="num_runs",
        help="Number of Monte Carlo iterations (default: 10000)",
    )
    simulate_parser.add_argument(
        "--horizon",
        type=int,
        default=90,
        dest="horizon_days",
        help="Simulation horizon in days (default: 90)",
    )
    simulate_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    simulate_parser.add_argument(
        "--what-if",
        action="append",
        dest="what_if",
        help="What-if scenario (e.g., redundant:payment-api). Can be repeated",
    )
    simulate_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    simulate_parser.add_argument(
        "--min-p-sla",
        type=float,
        default=None,
        dest="min_p_sla",
        help="Minimum P(meeting SLA) threshold for pass/fail exit code",
    )
    simulate_parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data",
    )


def handle_simulate_command(args: argparse.Namespace) -> int:
    """Handle simulate command from CLI args."""
    return simulate_command(
        manifest_file=args.manifest_file,
        manifests_dir=getattr(args, "manifests_dir", None),
        num_runs=getattr(args, "num_runs", 10000),
        horizon_days=getattr(args, "horizon_days", 90),
        seed=getattr(args, "seed", None),
        what_if=getattr(args, "what_if", None),
        output_format=getattr(args, "output_format", "table"),
        min_p_sla=getattr(args, "min_p_sla", None),
        demo=getattr(args, "demo", False),
    )
