"""
Output formatters for NthLayer CLI commands.

Supports multiple output formats for CI/CD integration:
- table: Human-readable table format (default)
- json: Machine-readable JSON
- sarif: GitHub Code Scanning format
- junit: JUnit XML for CI test results
- markdown: PR comment format
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

# Import data models from models.py first (before formatter imports)
from .models import (
    CheckResult,
    CheckStatus,
    OutputFormat,
    ReliabilityReport,
    SARIF_RULES,
)

# Now import formatters (they import from .models, not from here)
from .json_fmt import format_json
from .junit import format_junit
from .markdown import format_markdown
from .sarif import format_sarif


class Formatter(Protocol):
    """Protocol for output formatters."""

    def format(self, report: ReliabilityReport) -> str:
        """Format report to string output."""
        ...


def format_report(
    report: ReliabilityReport,
    output_format: OutputFormat | str = OutputFormat.TABLE,
    output_file: Path | str | None = None,
) -> str:
    """
    Format a reliability report in the specified format.

    Args:
        report: The reliability report to format
        output_format: Output format (table, json, sarif, junit, markdown)
        output_file: Optional file path to write output to

    Returns:
        Formatted string output
    """
    if isinstance(output_format, str):
        output_format = OutputFormat(output_format)

    formatters = {
        OutputFormat.TABLE: _format_table,
        OutputFormat.JSON: format_json,
        OutputFormat.SARIF: format_sarif,
        OutputFormat.JUNIT: format_junit,
        OutputFormat.MARKDOWN: format_markdown,
    }

    formatter = formatters.get(output_format, _format_table)
    output = formatter(report)

    if output_file:
        Path(output_file).write_text(output)

    return output


def _format_table(report: ReliabilityReport) -> str:
    """Format report as human-readable table (default)."""
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append(f"NthLayer Reliability Check: {report.service}")
    lines.append(f"{'=' * 60}\n")

    status_icons = {
        CheckStatus.PASS: "✓",
        CheckStatus.WARN: "⚠",
        CheckStatus.FAIL: "✗",
        CheckStatus.SKIP: "○",
    }

    for check in report.checks:
        icon = status_icons.get(check.status, "?")
        status_str = check.status.value.upper()
        lines.append(f"  {icon} {check.name}: {status_str}")
        if check.message:
            lines.append(f"      {check.message}")

    lines.append(f"\n{'─' * 60}")
    lines.append(
        f"Summary: {report.passed} passed, {report.warnings} warnings, {report.errors} errors"
    )
    lines.append(f"Overall: {report.status.value.upper()}")
    lines.append("")

    return "\n".join(lines)


__all__ = [
    "OutputFormat",
    "CheckStatus",
    "CheckResult",
    "ReliabilityReport",
    "format_report",
    "format_json",
    "format_sarif",
    "format_junit",
    "format_markdown",
    "SARIF_RULES",
]
