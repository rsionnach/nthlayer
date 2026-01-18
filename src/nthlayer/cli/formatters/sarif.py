"""
SARIF output formatter for NthLayer CLI.

Produces SARIF (Static Analysis Results Interchange Format) output
compatible with GitHub Code Scanning.

SARIF Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from __future__ import annotations

import json
from importlib.metadata import version as get_version
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import CheckResult, ReliabilityReport

from .models import SARIF_RULES, CheckStatus


def format_sarif(report: ReliabilityReport) -> str:
    """
    Format reliability report as SARIF 2.1.0.

    This format integrates with:
    - GitHub Code Scanning
    - GitHub Security tab
    - PR annotations
    """
    try:
        nthlayer_version = get_version("nthlayer")
    except Exception:
        nthlayer_version = "0.0.0"

    # Collect rules used in this report
    used_rules = _get_used_rules(report.checks)

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "NthLayer",
                        "version": nthlayer_version,
                        "informationUri": "https://github.com/rsionnach/nthlayer",
                        "rules": list(used_rules.values()),
                    }
                },
                "results": _build_results(report),
                "invocations": [
                    {
                        "executionSuccessful": report.status != CheckStatus.FAIL,
                        "toolExecutionNotifications": [],
                    }
                ],
            }
        ],
    }

    return json.dumps(sarif, indent=2, sort_keys=True)


def _get_used_rules(checks: list[CheckResult]) -> dict[str, dict[str, Any]]:
    """Get SARIF rule definitions for rules used in checks."""
    used_rules: dict[str, dict[str, Any]] = {}

    for check in checks:
        rule_id = check.rule_id or _infer_rule_id(check)
        if rule_id and rule_id in SARIF_RULES:
            used_rules[rule_id] = SARIF_RULES[rule_id]

    return used_rules


def _infer_rule_id(check: CheckResult) -> str | None:
    """Infer SARIF rule ID from check name."""
    name_lower = check.name.lower()

    if "slo" in name_lower and ("infeasible" in name_lower or "feasibility" in name_lower):
        return "NTHLAYER001"
    if "drift" in name_lower:
        return "NTHLAYER002"
    if "metric" in name_lower and "missing" in name_lower:
        return "NTHLAYER003"
    if "budget" in name_lower and ("exhaust" in name_lower or "depleted" in name_lower):
        return "NTHLAYER004"
    if "blast" in name_lower or "impact" in name_lower:
        return "NTHLAYER005"
    if "tier" in name_lower and "mismatch" in name_lower:
        return "NTHLAYER006"
    if "owner" in name_lower:
        return "NTHLAYER007"
    if "runbook" in name_lower:
        return "NTHLAYER008"

    return None


def _build_results(report: ReliabilityReport) -> list[dict[str, Any]]:
    """Build SARIF results array from check results."""
    results: list[dict[str, Any]] = []

    for check in report.checks:
        # Skip passed checks - SARIF is for findings
        if check.status == CheckStatus.PASS:
            continue

        rule_id = check.rule_id or _infer_rule_id(check)
        if not rule_id:
            # Generate a generic rule ID if we can't infer one
            rule_id = f"NTHLAYER{len(results) + 100:03d}"

        level = _status_to_sarif_level(check.status)

        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": check.message},
        }

        # Add location if available
        if check.location:
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": check.location},
                        "region": {"startLine": check.line or 1, "startColumn": 1},
                    }
                }
            ]

        # Add properties for extra context
        if check.details:
            result["properties"] = {
                "service": report.service,
                **check.details,
            }

        results.append(result)

    return results


def _status_to_sarif_level(status: CheckStatus) -> str:
    """Convert CheckStatus to SARIF level."""
    mapping = {
        CheckStatus.FAIL: "error",
        CheckStatus.WARN: "warning",
        CheckStatus.SKIP: "note",
        CheckStatus.PASS: "none",
    }
    return mapping.get(status, "note")
