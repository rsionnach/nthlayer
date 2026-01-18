"""
CLI command for validating service specs against OPA policies.

Uses conftest when available, falls back to native validation.
"""

from pathlib import Path

from rich.markup import escape

from nthlayer.cli.ux import console, error, header, success, warning
from nthlayer.validation import Severity, is_conftest_available
from nthlayer.validation.conftest import ConftestValidator, ValidationResult


def validate_spec_command(
    file_path: str,
    policy_dir: str | None = None,
    verbose: bool = False,
) -> int:
    """
    Validate service spec against OPA policies.

    Args:
        file_path: Path to service.yaml file or directory
        policy_dir: Optional custom policy directory
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for warnings, 2 for errors)
    """
    header("Validate Service Spec")
    console.print()

    path = Path(file_path)

    if not path.exists():
        error(f"File not found: {file_path}")
        return 2

    # Show validation mode
    if is_conftest_available():
        console.print("[muted]Validator:[/muted] conftest (OPA)")
    else:
        console.print("[muted]Validator:[/muted] native (install conftest for full OPA support)")

    if policy_dir:
        console.print(f"[muted]Policy dir:[/muted] {policy_dir}")
    console.print()

    # Collect files to validate
    if path.is_dir():
        files = list(path.glob("**/*.yaml")) + list(path.glob("**/*.yml"))
        # Filter to likely service specs (have 'service:' section)
        service_files = []
        for f in files:
            try:
                content = f.read_text()
                if "service:" in content and "resources:" in content:
                    service_files.append(f)
            except Exception:
                pass
        files = service_files
    else:
        files = [path]

    if not files:
        warning("No service spec files found")
        return 0

    console.print(f"[muted]Files to validate:[/muted] {len(files)}")
    console.print()

    # Run validation
    validator = ConftestValidator(policy_dir=policy_dir)
    all_results: list[ValidationResult] = []

    for f in files:
        result = validator.validate_file(f)
        all_results.append(result)
        _print_result(result, verbose)

    # Summary
    console.print()
    total_errors = sum(r.error_count for r in all_results)
    total_warnings = sum(r.warning_count for r in all_results)

    if total_errors == 0 and total_warnings == 0:
        success("All specs passed validation")
        return 0
    elif total_errors == 0:
        warning(f"{total_warnings} warnings found")
        return 1
    else:
        error(f"{total_errors} errors, {total_warnings} warnings")
        return 2


def _print_result(result: ValidationResult, verbose: bool) -> None:
    """Print validation result for a single file."""
    if result.passed and not result.issues:
        console.print(f"[success]✓[/success] {result.file_path.name}")
    elif result.passed:
        console.print(f"[warning]⚠[/warning] {result.file_path.name}")
    else:
        console.print(f"[error]✗[/error] {result.file_path.name}")

    if result.issues:
        for issue in result.issues:
            if issue.severity == Severity.ERROR:
                icon = "[error]✗[/error]"
            elif issue.severity == Severity.WARNING:
                icon = "[warning]⚠[/warning]"
            else:
                icon = "[info]ℹ[/info]"

            rule_info = f" [muted]({issue.rule_name})[/muted]" if issue.rule_name else ""
            # Escape brackets in message to prevent Rich markup interpretation
            safe_message = escape(issue.message)
            console.print(f"  {icon} {rule_info} {safe_message}")

            if verbose and issue.suggestion:
                console.print(f"      [muted]→ {issue.suggestion}[/muted]")


def register_validate_spec_parser(subparsers) -> None:
    """Register the validate-spec subcommand."""
    parser = subparsers.add_parser(
        "validate-spec",
        help="Validate service.yaml against OPA policies",
    )
    parser.add_argument(
        "file_path",
        help="Path to service.yaml file or directory",
    )
    parser.add_argument(
        "--policy-dir",
        help="Custom policy directory (default: policies/)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )


def handle_validate_spec_command(args) -> int:
    """Handle the validate-spec subcommand."""
    return validate_spec_command(
        file_path=args.file_path,
        policy_dir=getattr(args, "policy_dir", None),
        verbose=getattr(args, "verbose", False),
    )
