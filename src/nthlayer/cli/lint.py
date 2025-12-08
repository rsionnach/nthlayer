"""
CLI command for linting Prometheus alert rules with pint.
"""

from pathlib import Path
from typing import Optional

from nthlayer.cli.ux import console, error, success
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
        error("pint is not installed")
        console.print()
        console.print("[muted]Install pint:[/muted]")
        console.print("  [info]brew install cloudflare/cloudflare/pint[/info]")
        console.print(
            "  [muted]# or download from https://github.com/cloudflare/pint/releases[/muted]"
        )
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
        console.print()
        if all_passed:
            success(f"All {len(results)} files passed")
        else:
            failed = sum(1 for r in results if not r.passed)
            error(f"{failed}/{len(results)} files have errors")

        if total_errors or total_warnings:
            console.print(
                f"  [muted]Total: {total_errors} errors, {total_warnings} warnings[/muted]"
            )

    return 0 if all_passed else 1


def _print_result(result: LintResult, verbose: bool) -> None:
    """Print a single lint result."""
    if result.passed:
        console.print(f"[success]✓[/success] {result.file_path}")
    else:
        console.print(f"[error]✗[/error] {result.file_path}")

    if result.issues:
        for issue in result.issues:
            if issue.is_error:
                icon = "[error]✗[/error]"
            elif issue.is_warning:
                icon = "[warning]⚠[/warning]"
            else:
                icon = "[info]ℹ[/info]"
            line_info = f":{issue.line}" if issue.line else ""
            rule_info = f" [muted]({issue.rule_name})[/muted]" if issue.rule_name else ""
            console.print(f"  {icon} [{issue.check}]{line_info}{rule_info} {issue.message}")

    if verbose and result.raw_output:
        console.print()
        console.print("[muted]Raw pint output:[/muted]")
        for line in result.raw_output.split("\n"):
            console.print(f"  [muted]{line}[/muted]")
