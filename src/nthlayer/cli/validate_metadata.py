"""
CLI command for validating Prometheus rule metadata.

Enhanced validation beyond PromQL syntax:
- Required labels and annotations
- Label value patterns
- Runbook URL validation
- Range query vs retention checks
"""

from pathlib import Path

from nthlayer.cli.ux import console, error, header, success
from nthlayer.validation import (
    MetadataValidator,
    Severity,
    ValidationResult,
    is_promruval_available,
    validate_with_promruval,
)


def validate_metadata_command(
    file_path: str,
    strict: bool = False,
    check_urls: bool = False,
    use_promruval: bool = False,
    verbose: bool = False,
) -> int:
    """
    Validate Prometheus rule metadata.

    Args:
        file_path: Path to alerts YAML file or directory
        strict: Use strict validation (requires runbook_url, team, service)
        check_urls: Actually check if runbook URLs are accessible
        use_promruval: Use promruval if available
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for warnings, 2 for errors)
    """
    header("Validate Rule Metadata")
    console.print()

    path = Path(file_path)

    if not path.exists():
        error(f"File not found: {file_path}")
        return 2

    # Collect files to validate
    if path.is_dir():
        files = list(path.glob("**/*.yaml")) + list(path.glob("**/*.yml"))
    else:
        files = [path]

    if not files:
        error("No YAML files found")
        return 2

    console.print(f"[muted]Files to validate:[/muted] {len(files)}")
    console.print(f"[muted]Mode:[/muted] {'strict' if strict else 'default'}")
    if check_urls:
        console.print("[muted]URL checking:[/muted] enabled")
    console.print()

    # Run validation
    all_results: list[ValidationResult] = []

    for file in files:
        # Native metadata validation
        if strict:
            validator = MetadataValidator.strict()
        else:
            validator = MetadataValidator.default()

        if check_urls:
            from nthlayer.validation import ValidRunbookUrl

            validator.add_validator(ValidRunbookUrl(check_accessibility=True))

        result = validator.validate_file(file)
        all_results.append(result)

        # Optionally also run promruval
        if use_promruval and is_promruval_available():
            promruval_result = validate_with_promruval(file)
            # Merge issues
            result.issues.extend(promruval_result.issues)

    # Print results
    total_errors = 0
    total_warnings = 0
    total_rules = 0

    for result in all_results:
        _print_validation_result(result, verbose)
        total_errors += result.error_count
        total_warnings += result.warning_count
        total_rules += result.rules_checked

    # Summary
    console.print()
    console.print(f"[muted]Rules checked:[/muted] {total_rules}")

    if total_errors == 0 and total_warnings == 0:
        success("All rules passed validation")
        return 0
    elif total_errors == 0:
        console.print(f"[warning]⚠[/warning] {total_warnings} warnings found")
        return 1
    else:
        error(f"{total_errors} errors, {total_warnings} warnings")
        return 2


def _print_validation_result(result: ValidationResult, verbose: bool) -> None:
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
            console.print(f"  {icon} [{issue.validator}]{rule_info} {issue.message}")

            if verbose and issue.suggestion:
                console.print(f"      [muted]→ {issue.suggestion}[/muted]")


def register_validate_metadata_parser(subparsers) -> None:
    """Register the validate-metadata subcommand."""
    parser = subparsers.add_parser(
        "validate-metadata",
        help="Validate Prometheus rule metadata (labels, annotations, URLs)",
    )
    parser.add_argument(
        "file_path",
        help="Path to alerts YAML file or directory",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict validation (requires runbook_url, team, service)",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="Check if runbook URLs are accessible (makes HTTP requests)",
    )
    parser.add_argument(
        "--use-promruval",
        action="store_true",
        help="Also run promruval if available",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output with suggestions",
    )


def handle_validate_metadata_command(args) -> int:
    """Handle the validate-metadata subcommand."""
    return validate_metadata_command(
        file_path=args.file_path,
        strict=getattr(args, "strict", False),
        check_urls=getattr(args, "check_urls", False),
        use_promruval=getattr(args, "use_promruval", False),
        verbose=getattr(args, "verbose", False),
    )
