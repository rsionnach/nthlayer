"""
CLI command for applying (generating) all service resources.
"""

import json
from pathlib import Path
from typing import List, Optional

from nthlayer.cli.plan import plan_command
from nthlayer.orchestrator import ApplyResult, ServiceOrchestrator


def print_apply_summary(result: ApplyResult, verbose: bool = False) -> None:
    """Print clean apply summary."""
    print()

    # Resource type display config: (label, width, detail_fn)
    resource_config = {
        "slos": ("SLOs", lambda c: f"{c} created"),
        "alerts": ("Alerts", lambda c: f"{c} generated"),
        "dashboard": ("Dashboard", lambda c: f"{c} generated"),
        "recording-rules": ("Recording", lambda c: f"{c} rules"),
        "pagerduty": ("PagerDuty", lambda c: "configured"),
    }

    # Print each resource on one line
    for resource_type, count in result.resources_created.items():
        config = resource_config.get(resource_type)
        if config:
            label, detail_fn = config
            detail = detail_fn(count)
        else:
            label = resource_type.replace("-", " ").title()
            detail = f"{count} created"

        icon = "✓" if resource_type not in _get_warning_types(result) else "⚠"
        print(f"  {icon} {label:<12} {detail}")

    # Summary line
    print()
    duration = f" in {result.duration_seconds:.1f}s" if result.duration_seconds > 0 else ""
    if result.success:
        print(f"Applied {result.total_resources} resources{duration} → {result.output_dir}/")
    else:
        print(f"Applied {result.total_resources} resources with errors{duration}")

    # Show warnings/errors at end (grouped)
    if result.errors:
        print()
        print("Warnings:")
        for error in result.errors:
            # Truncate long errors in non-verbose mode
            if not verbose and len(error) > 80:
                error = error[:77] + "..."
            print(f"  • {error}")

    # Only show file list in verbose mode
    if verbose and result.output_dir.exists():
        print()
        print("Generated files:")
        for file in sorted(result.output_dir.iterdir()):
            if file.is_file():
                size = file.stat().st_size
                size_str = f"{size:,}B" if size < 1024 else f"{size/1024:.1f}KB"
                print(f"  • {file.name} ({size_str})")

    print()


def _get_warning_types(result: ApplyResult) -> set:
    """Get resource types that had warnings."""
    warning_types = set()
    for error in result.errors:
        error_lower = error.lower()
        if "pagerduty" in error_lower:
            warning_types.add("pagerduty")
        elif "dashboard" in error_lower:
            warning_types.add("dashboard")
        elif "alert" in error_lower:
            warning_types.add("alerts")
    return warning_types


def print_apply_json(result: ApplyResult) -> None:
    """Print apply result in JSON format."""
    output = {
        "service_name": result.service_name,
        "resources_created": result.resources_created,
        "total_resources": result.total_resources,
        "duration_seconds": result.duration_seconds,
        "output_dir": str(result.output_dir),
        "errors": result.errors,
        "success": result.success,
    }
    print(json.dumps(output, indent=2))


def apply_command(
    service_yaml: str,
    env: Optional[str] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
    skip: Optional[List[str]] = None,
    only: Optional[List[str]] = None,
    force: bool = False,
    verbose: bool = False,
    output_format: str = "text",
    push_grafana: bool = False,
    lint: bool = False,
) -> int:
    """
    Generate all resources for a service.

    Args:
        service_yaml: Path to service YAML file
        env: Environment name (dev, staging, prod)
        output_dir: Output directory for generated files
        dry_run: Preview without writing files (same as plan)
        skip: Resource types to skip (e.g., ['alerts', 'pagerduty'])
        only: Only generate specific resource types
        force: Force regeneration, ignore cache
        verbose: Show detailed progress
        output_format: Output format (text, json)
        push_grafana: Push dashboard to Grafana Cloud
        lint: Validate generated alerts with pint

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Dry-run delegates to plan command
    if dry_run:
        return plan_command(service_yaml, env=env, verbose=verbose)

    # Create orchestrator
    orchestrator = ServiceOrchestrator(Path(service_yaml), env=env, push_to_grafana=push_grafana)

    # Override output directory if specified
    if output_dir:
        orchestrator.output_dir = Path(output_dir)

    # Apply
    result = orchestrator.apply(skip=skip, only=only, force=force, verbose=verbose)

    # Print result
    if output_format == "json":
        print_apply_json(result)
    else:  # text (default)
        print_apply_summary(result, verbose=verbose)

    # Lint generated alerts if requested
    if lint and result.success:
        lint_exit_code = _lint_generated_alerts(result.output_dir, verbose=verbose)
        if lint_exit_code != 0:
            return lint_exit_code

    return 0 if result.success else 1


def _lint_generated_alerts(output_dir: Path, verbose: bool = False) -> int:
    """Lint generated alerts with pint."""
    from nthlayer.validation import PintLinter, is_pint_available

    alerts_file = output_dir / "alerts.yaml"
    if not alerts_file.exists():
        if verbose:
            print("  ℹ No alerts.yaml found, skipping lint")
        return 0

    if not is_pint_available():
        print()
        print("  ⚠ pint not installed - skipping alert validation")
        print("    Install: brew install cloudflare/cloudflare/pint")
        print("    Or download from: https://github.com/cloudflare/pint/releases")
        return 0  # Don't fail, just warn

    print()
    print("Validating alerts with pint...")

    linter = PintLinter()
    result = linter.lint_file(alerts_file)

    print(f"  {result.summary()}")

    if result.issues:
        for issue in result.issues:
            icon = "✗" if issue.is_error else "⚠" if issue.is_warning else "ℹ"
            line_info = f":{issue.line}" if issue.line else ""
            print(f"    {icon} [{issue.check}]{line_info} {issue.message}")

    if not result.passed:
        print()
        print("  Alert validation failed. Fix issues before deploying.")
        return 1

    return 0
