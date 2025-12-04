"""
CLI command for linting Prometheus alert rules with pint.
"""

from pathlib import Path
from typing import Optional

from nthlayer.validation import LintResult, PintLinter, is_pint_available


def lint_command(
    file_path: str,
    config: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """
    Lint Prometheus alert rules using pint.

    Args:
        file_path: Path to alerts YAML file or directory
        config: Optional path to .pint.hcl config file
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for errors)
    """
    if not is_pint_available():
        print("Error: pint is not installed")
        print()
        print("Install pint:")
        print("  brew install cloudflare/cloudflare/pint")
        print("  # or download from https://github.com/cloudflare/pint/releases")
        return 1

    linter = PintLinter(config_path=Path(config) if config else None)

    path = Path(file_path)

    if path.is_dir():
        results = linter.lint_directory(path)
    else:
        results = [linter.lint_file(path)]

    # Print results
    all_passed = True
    total_errors = 0
    total_warnings = 0

    for result in results:
        _print_result(result, verbose)
        if not result.passed:
            all_passed = False
        total_errors += result.error_count
        total_warnings += result.warning_count

    # Summary
    if len(results) > 1:
        print()
        if all_passed:
            print(f"✓ All {len(results)} files passed")
        else:
            failed = sum(1 for r in results if not r.passed)
            print(f"✗ {failed}/{len(results)} files have errors")

        if total_errors or total_warnings:
            print(f"  Total: {total_errors} errors, {total_warnings} warnings")

    return 0 if all_passed else 1


def _print_result(result: LintResult, verbose: bool) -> None:
    """Print a single lint result."""
    print(result.summary())

    if result.issues:
        for issue in result.issues:
            icon = "✗" if issue.is_error else "⚠" if issue.is_warning else "ℹ"
            line_info = f":{issue.line}" if issue.line else ""
            rule_info = f" ({issue.rule_name})" if issue.rule_name else ""
            print(f"  {icon} [{issue.check}]{line_info}{rule_info} {issue.message}")

    if verbose and result.raw_output:
        print()
        print("Raw pint output:")
        for line in result.raw_output.split("\n"):
            print(f"  {line}")
