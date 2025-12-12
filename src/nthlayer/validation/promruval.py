"""
Optional promruval binary integration.

promruval is a Prometheus/Thanos/Mimir/Loki rule validator with 40+ validators.
When installed, NthLayer can use it for comprehensive validation beyond pint.

Installation:
    brew install fusakla/tap/promruval
    # or download from https://github.com/FUSAKLA/promruval/releases

See: https://github.com/FUSAKLA/promruval
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from nthlayer.validation.metadata import Severity, ValidationIssue, ValidationResult


@dataclass
class PromruvalConfig:
    """Configuration for promruval validation."""

    # Validation config file path
    config_path: Path | None = None

    # Enable/disable specific validators
    enabled_validators: list[str] = field(default_factory=list)
    disabled_validators: list[str] = field(default_factory=list)

    # Output format
    output_format: str = "json"  # json, yaml, text


class PromruvalLinter:
    """
    Wrapper around FUSAKLA's promruval Prometheus rule validator.

    promruval provides 40+ validators for Prometheus/Thanos/Mimir/Loki rules:
    - hasLabels, hasAnnotations
    - labelMatchesRegexp, annotationMatchesRegexp
    - expressionDoesNotUseOlderDataThan
    - expressionWithNoMetricName
    - alertHasRunbook, annotationIsValidURL
    - and many more...

    Example:
        linter = PromruvalLinter()
        if linter.is_available:
            result = linter.validate_file("alerts.yaml")
            for issue in result.issues:
                print(f"{issue.severity}: {issue.message}")
    """

    def __init__(self, config: PromruvalConfig | None = None):
        self.config = config or PromruvalConfig()
        self._promruval_path = shutil.which("promruval")

    @property
    def is_available(self) -> bool:
        """Check if promruval is installed."""
        return self._promruval_path is not None

    def get_version(self) -> str | None:
        """Get promruval version string."""
        if not self.is_available:
            return None
        try:
            result = subprocess.run(
                [self._promruval_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # promruval version output varies
            match = re.search(r"v?([\d.]+)", result.stdout)
            return match.group(1) if match else result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return None

    def validate_file(self, file_path: Path | str) -> ValidationResult:
        """
        Validate a Prometheus rules file using promruval.

        Args:
            file_path: Path to YAML file containing Prometheus rules

        Returns:
            ValidationResult with any issues found
        """
        file_path = Path(file_path)
        result = ValidationResult(file_path=file_path)

        if not self.is_available:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    rule_name="",
                    validator="promruval",
                    message="promruval not installed. Install: brew install fusakla/tap/promruval",
                )
            )
            return result

        if not file_path.exists():
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="promruval",
                    message=f"File not found: {file_path}",
                )
            )
            return result

        # Build promruval command
        cmd = [self._promruval_path, "validate"]

        # Add config if specified
        if self.config.config_path and self.config.config_path.exists():
            cmd.extend(["--config", str(self.config.config_path)])

        # Output format
        cmd.extend(["--output", self.config.output_format])

        # Add file to validate
        cmd.append(str(file_path))

        try:
            proc_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse output based on format
            if self.config.output_format == "json":
                issues = self._parse_json_output(proc_result.stdout, proc_result.stderr)
            else:
                issues = self._parse_text_output(proc_result.stdout + proc_result.stderr)

            result.issues.extend(issues)

        except subprocess.TimeoutExpired:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="promruval",
                    message="promruval timed out after 60 seconds",
                )
            )
        except subprocess.SubprocessError as e:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="promruval",
                    message=f"promruval failed: {e}",
                )
            )

        return result

    def _parse_json_output(self, stdout: str, stderr: str) -> list[ValidationIssue]:
        """Parse promruval JSON output."""
        issues = []

        if not stdout.strip():
            return issues

        try:
            data = json.loads(stdout)

            # promruval JSON format varies, handle common structures
            if isinstance(data, list):
                for item in data:
                    issues.append(self._item_to_issue(item))
            elif isinstance(data, dict):
                if "errors" in data:
                    for err in data["errors"]:
                        issues.append(self._item_to_issue(err))
                if "warnings" in data:
                    for warn in data["warnings"]:
                        issue = self._item_to_issue(warn)
                        issue.severity = Severity.WARNING
                        issues.append(issue)

        except json.JSONDecodeError:
            # Fall back to text parsing
            issues = self._parse_text_output(stdout + stderr)

        return issues

    def _item_to_issue(self, item: dict) -> ValidationIssue:
        """Convert a promruval result item to ValidationIssue."""
        severity_str = item.get("severity", item.get("level", "error")).lower()
        if severity_str in ("error", "fatal", "bug"):
            severity = Severity.ERROR
        elif severity_str == "warning":
            severity = Severity.WARNING
        else:
            severity = Severity.INFO

        return ValidationIssue(
            severity=severity,
            rule_name=item.get("rule", item.get("alert", "")),
            validator=f"promruval/{item.get('validator', 'unknown')}",
            message=item.get("message", item.get("error", str(item))),
            line=item.get("line"),
        )

    def _parse_text_output(self, output: str) -> list[ValidationIssue]:
        """Parse promruval text output."""
        issues = []

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            # Determine severity from content
            severity = Severity.WARNING
            if any(word in line.lower() for word in ["error", "fatal", "invalid"]):
                severity = Severity.ERROR

            issues.append(
                ValidationIssue(
                    severity=severity,
                    rule_name="",
                    validator="promruval",
                    message=line,
                )
            )

        return issues

    def list_validators(self) -> list[str]:
        """List available promruval validators."""
        if not self.is_available:
            return []

        try:
            result = subprocess.run(
                [self._promruval_path, "validation-docs"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Parse validator names from output
            validators = []
            for line in result.stdout.split("\n"):
                # Look for validator names (typically formatted as headers or list items)
                if line.strip().startswith("- ") or line.strip().startswith("* "):
                    validators.append(line.strip()[2:].split()[0])
            return validators
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return []


def is_promruval_available() -> bool:
    """Check if promruval is installed."""
    return shutil.which("promruval") is not None


def validate_with_promruval(
    file_path: str | Path,
    config_path: str | Path | None = None,
) -> ValidationResult:
    """
    Convenience function to validate with promruval.

    Args:
        file_path: Path to Prometheus/Loki rules file
        config_path: Optional promruval config file

    Returns:
        ValidationResult with any issues found
    """
    config = PromruvalConfig()
    if config_path:
        config.config_path = Path(config_path)

    linter = PromruvalLinter(config=config)
    return linter.validate_file(Path(file_path))
