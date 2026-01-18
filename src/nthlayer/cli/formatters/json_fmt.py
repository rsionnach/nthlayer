"""
JSON output formatter for NthLayer CLI.

Produces structured JSON output for machine consumption and downstream automation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import ReliabilityReport


def format_json(report: ReliabilityReport) -> str:
    """
    Format reliability report as JSON.

    Output structure:
    {
        "version": "1.0",
        "timestamp": "2026-01-17T14:30:00Z",
        "service": "payment-api",
        "command": "plan",
        "checks": {...},
        "summary": {...}
    }
    """
    checks: dict[str, Any] = {}
    summary: dict[str, Any] = {
        "status": report.status.value,
        "errors": report.errors,
        "warnings": report.warnings,
        "passed": report.passed,
        "total": len(report.checks),
    }

    # Group checks by category
    for check in report.checks:
        check_key = _normalize_check_name(check.name)
        checks[check_key] = {
            "status": check.status.value,
            "message": check.message,
            **check.details,
        }

    # Add any extra summary data
    if report.summary:
        summary.update(report.summary)

    output: dict[str, Any] = {
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": report.service,
        "command": report.command,
        "checks": checks,
        "summary": summary,
    }

    # Add metadata if present
    if report.metadata:
        output["metadata"] = report.metadata

    return json.dumps(output, indent=2, sort_keys=True, default=str)


def _normalize_check_name(name: str) -> str:
    """Convert check name to snake_case key."""
    return name.lower().replace(" ", "_").replace("-", "_")
