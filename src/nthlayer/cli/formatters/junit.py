"""
JUnit XML output formatter for NthLayer CLI.

Produces JUnit XML format compatible with CI systems like:
- Jenkins
- GitHub Actions
- GitLab CI
- CircleCI
- Azure DevOps
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from .models import CheckResult, ReliabilityReport

from .models import CheckStatus


def format_junit(report: ReliabilityReport) -> str:
    """
    Format reliability report as JUnit XML.

    Output structure:
    <testsuites>
      <testsuite name="payment-api" tests="5" failures="1" errors="0">
        <testcase name="SLO Feasibility" classname="payment-api.validate-slo">
          <failure message="...">...</failure>
        </testcase>
      </testsuite>
    </testsuites>
    """
    # Create root element
    testsuites = ET.Element("testsuites")
    testsuites.set("name", "NthLayer")
    testsuites.set("tests", str(len(report.checks)))
    testsuites.set("failures", str(report.errors))
    testsuites.set("errors", "0")  # We use failures, not errors
    testsuites.set("time", str(report.metadata.get("duration", 0)))

    # Create testsuite for this service
    testsuite = ET.SubElement(testsuites, "testsuite")
    testsuite.set("name", report.service)
    testsuite.set("tests", str(len(report.checks)))
    testsuite.set("failures", str(report.errors))
    testsuite.set("errors", "0")
    testsuite.set("skipped", str(sum(1 for c in report.checks if c.status == CheckStatus.SKIP)))
    testsuite.set("time", str(report.metadata.get("duration", 0)))

    # Add timestamp if available
    if "timestamp" in report.metadata:
        testsuite.set("timestamp", report.metadata["timestamp"])

    # Add testcases
    for check in report.checks:
        _add_testcase(testsuite, check, report.service, report.command)

    # Convert to string with XML declaration
    return _element_to_string(testsuites)


def _add_testcase(
    testsuite: ET.Element,
    check: CheckResult,
    service: str,
    command: str,
) -> None:
    """Add a testcase element for a check result."""
    testcase = ET.SubElement(testsuite, "testcase")
    testcase.set("name", check.name)
    testcase.set("classname", f"{service}.{command}")
    testcase.set("time", str(check.details.get("duration", 0)))

    if check.status == CheckStatus.FAIL:
        failure = ET.SubElement(testcase, "failure")
        failure.set("message", _escape_xml(check.message))
        failure.set("type", check.rule_id or "AssertionError")
        failure.text = _format_failure_details(check)

    elif check.status == CheckStatus.WARN:
        # JUnit doesn't have warnings, but we can use system-out
        system_out = ET.SubElement(testcase, "system-out")
        system_out.text = f"WARNING: {check.message}\n{_format_failure_details(check)}"

    elif check.status == CheckStatus.SKIP:
        skipped = ET.SubElement(testcase, "skipped")
        skipped.set("message", check.message or "Skipped")


def _format_failure_details(check: CheckResult) -> str:
    """Format check details for failure message body."""
    lines = [check.message, ""]

    if check.details:
        for key, value in check.details.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"  - {item}")
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")

    if check.location:
        lines.append(f"\nLocation: {check.location}")
        if check.line:
            lines.append(f"Line: {check.line}")

    return "\n".join(lines)


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return html.escape(text, quote=True)


def _element_to_string(element: ET.Element) -> str:
    """Convert ElementTree element to formatted XML string."""
    # Python's ElementTree doesn't have pretty print in older versions
    # We'll use a simple approach
    xml_str = ET.tostring(element, encoding="unicode")

    # Add XML declaration
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
