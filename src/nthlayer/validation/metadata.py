"""
Enhanced metadata validation for Prometheus/Loki rules.

Goes beyond PromQL syntax to validate:
- Required labels and annotations
- Label value patterns (regex validation)
- Runbook URL accessibility
- Range query vs data retention
- Thanos/Mimir/Loki specific requirements

Inspired by promruval but implemented natively in Python.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml


class Severity(Enum):
    """Validation issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation issue."""

    severity: Severity
    rule_name: str
    validator: str
    message: str
    line: int | None = None
    suggestion: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == Severity.ERROR

    @property
    def is_warning(self) -> bool:
        return self.severity == Severity.WARNING


@dataclass
class ValidationResult:
    """Result of validating a rules file."""

    file_path: Path
    issues: list[ValidationIssue] = field(default_factory=list)
    rules_checked: int = 0

    @property
    def passed(self) -> bool:
        return not any(issue.is_error for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_error)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_warning)


@dataclass
class RuleContext:
    """Context for a single rule being validated."""

    name: str
    expr: str
    labels: dict[str, str]
    annotations: dict[str, str]
    for_duration: str | None = None
    rule_type: str = "alert"  # "alert" or "recording"
    group_name: str | None = None
    line_number: int | None = None


class BaseValidator(ABC):
    """Base class for rule validators."""

    name: str = "base"
    description: str = "Base validator"

    @abstractmethod
    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        """Validate a rule and return any issues."""
        pass


class HasRequiredLabels(BaseValidator):
    """Validate that rules have required labels."""

    name = "hasRequiredLabels"
    description = "Check for required labels"

    def __init__(self, required_labels: list[str]):
        self.required_labels = required_labels

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        for label in self.required_labels:
            if label not in rule.labels:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Missing required label: {label}",
                        suggestion=f"Add '{label}' label to the rule",
                    )
                )
        return issues


class HasRequiredAnnotations(BaseValidator):
    """Validate that rules have required annotations."""

    name = "hasRequiredAnnotations"
    description = "Check for required annotations"

    def __init__(self, required_annotations: list[str]):
        self.required_annotations = required_annotations

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        for annotation in self.required_annotations:
            if annotation not in rule.annotations:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Missing required annotation: {annotation}",
                        suggestion=f"Add '{annotation}' annotation to the rule",
                    )
                )
        return issues


class LabelMatchesPattern(BaseValidator):
    """Validate that label values match expected patterns."""

    name = "labelMatchesPattern"
    description = "Check label values against regex patterns"

    def __init__(self, patterns: dict[str, str]):
        """
        Args:
            patterns: Dict of label name -> regex pattern
        """
        self.patterns = {k: re.compile(v) for k, v in patterns.items()}

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        for label, pattern in self.patterns.items():
            if label in rule.labels:
                value = rule.labels[label]
                if not pattern.match(value):
                    issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            rule_name=rule.name,
                            validator=self.name,
                            message=(
                                f"Label '{label}' value '{value}' doesn't match "
                                f"pattern '{pattern.pattern}'"
                            ),
                            suggestion=f"Update '{label}' to match required pattern",
                        )
                    )
        return issues


class ValidSeverityLevel(BaseValidator):
    """Validate severity label has valid value."""

    name = "validSeverityLevel"
    description = "Check severity label has valid value"

    VALID_SEVERITIES = {"critical", "warning", "info", "page", "ticket"}

    def __init__(self, valid_severities: set[str] | None = None):
        self.valid_severities = valid_severities or self.VALID_SEVERITIES

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        severity = rule.labels.get("severity")
        if severity and severity.lower() not in self.valid_severities:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name=rule.name,
                    validator=self.name,
                    message=(
                        f"Invalid severity '{severity}'. "
                        f"Must be one of: {', '.join(sorted(self.valid_severities))}"
                    ),
                    suggestion="Use a valid severity level",
                )
            )
        return issues


class ValidRunbookUrl(BaseValidator):
    """Validate runbook URLs are well-formed and optionally accessible."""

    name = "validRunbookUrl"
    description = "Check runbook_url is valid and accessible"

    def __init__(
        self,
        check_accessibility: bool = False,
        timeout: float = 5.0,
        allowed_schemes: set[str] | None = None,
    ):
        self.check_accessibility = check_accessibility
        self.timeout = timeout
        self.allowed_schemes = allowed_schemes or {"http", "https"}

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        runbook_url = rule.annotations.get("runbook_url") or rule.annotations.get("runbook")

        if not runbook_url:
            return issues

        # Check URL format
        try:
            parsed = urlparse(runbook_url)
            if not parsed.scheme:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Runbook URL missing scheme: {runbook_url}",
                        suggestion="Add http:// or https:// prefix",
                    )
                )
                return issues

            if parsed.scheme not in self.allowed_schemes:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Runbook URL uses non-standard scheme: {parsed.scheme}",
                    )
                )

            if not parsed.netloc:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Runbook URL missing host: {runbook_url}",
                    )
                )
                return issues

        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name=rule.name,
                    validator=self.name,
                    message=f"Invalid runbook URL format: {e}",
                )
            )
            return issues

        # Optionally check accessibility
        if self.check_accessibility and parsed.scheme in {"http", "https"}:
            try:
                response = httpx.head(runbook_url, timeout=self.timeout, follow_redirects=True)
                if response.status_code >= 400:
                    issues.append(
                        ValidationIssue(
                            severity=Severity.WARNING,
                            rule_name=rule.name,
                            validator=self.name,
                            message=f"Runbook URL returned {response.status_code}: {runbook_url}",
                            suggestion="Verify the runbook URL is correct and accessible",
                        )
                    )
            except httpx.TimeoutException:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Runbook URL timed out: {runbook_url}",
                    )
                )
            except httpx.RequestError as e:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Runbook URL unreachable: {e}",
                    )
                )

        return issues


class RangeQueryMaxDuration(BaseValidator):
    """Validate range queries don't exceed expected data retention."""

    name = "rangeQueryMaxDuration"
    description = "Check range queries against data retention limits"

    DURATION_PATTERN = re.compile(r"(\d+)(ms|s|m|h|d|w|y)")

    def __init__(self, max_duration: str = "15d"):
        """
        Args:
            max_duration: Maximum allowed range query duration (e.g., "15d", "30d")
        """
        self.max_duration_seconds = self._parse_duration(max_duration)

    def _parse_duration(self, duration: str) -> int:
        """Convert duration string to seconds."""
        multipliers = {
            "ms": 0.001,
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
            "y": 31536000,
        }
        match = self.DURATION_PATTERN.match(duration)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            return int(value * multipliers.get(unit, 1))
        return 0

    def _extract_ranges(self, expr: str) -> list[str]:
        """Extract range durations from PromQL expression."""
        # Match patterns like [5m], [1h], [7d]
        pattern = re.compile(r"\[(\d+(?:ms|s|m|h|d|w|y))\]")
        return pattern.findall(expr)

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        ranges = self._extract_ranges(rule.expr)

        for range_str in ranges:
            range_seconds = self._parse_duration(range_str)
            if range_seconds > self.max_duration_seconds:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name=rule.name,
                        validator=self.name,
                        message=(
                            f"Range query [{range_str}] may exceed data retention "
                            f"({self.max_duration_seconds // 86400}d)"
                        ),
                        suggestion="Reduce range duration or ensure data retention is sufficient",
                    )
                )

        return issues


class AlertForDuration(BaseValidator):
    """Validate alert 'for' duration is reasonable."""

    name = "alertForDuration"
    description = "Check alert 'for' duration is within bounds"

    DURATION_PATTERN = re.compile(r"(\d+)(ms|s|m|h|d)")

    def __init__(self, min_duration: str = "0s", max_duration: str = "1h"):
        self.min_seconds = self._parse_duration(min_duration)
        self.max_seconds = self._parse_duration(max_duration)

    def _parse_duration(self, duration: str) -> int:
        multipliers = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}
        match = self.DURATION_PATTERN.match(duration)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            return int(value * multipliers.get(unit, 1))
        return 0

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        if not rule.for_duration:
            return issues

        duration_seconds = self._parse_duration(rule.for_duration)

        if duration_seconds < self.min_seconds:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name=rule.name,
                    validator=self.name,
                    message=f"Alert 'for' duration {rule.for_duration} is very short",
                    suggestion="Consider increasing 'for' to reduce alert noise",
                )
            )

        if duration_seconds > self.max_seconds:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name=rule.name,
                    validator=self.name,
                    message=f"Alert 'for' duration {rule.for_duration} is very long",
                    suggestion="Long 'for' durations may delay critical alerts",
                )
            )

        return issues


class NoEmptyLabels(BaseValidator):
    """Validate that labels don't have empty values."""

    name = "noEmptyLabels"
    description = "Check for empty label values"

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        for label, value in rule.labels.items():
            if not value or not value.strip():
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Label '{label}' has empty value",
                        suggestion="Remove the label or provide a value",
                    )
                )
        return issues


class NoEmptyAnnotations(BaseValidator):
    """Validate that annotations don't have empty values."""

    name = "noEmptyAnnotations"
    description = "Check for empty annotation values"

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        for annotation, value in rule.annotations.items():
            if not value or not value.strip():
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name=rule.name,
                        validator=self.name,
                        message=f"Annotation '{annotation}' has empty value",
                        suggestion="Remove the annotation or provide a value",
                    )
                )
        return issues


class RuleNamePattern(BaseValidator):
    """Validate rule names follow naming convention."""

    name = "ruleNamePattern"
    description = "Check rule names match naming convention"

    def __init__(self, pattern: str = r"^[A-Z][a-zA-Z0-9_]+$"):
        self.pattern = re.compile(pattern)

    def validate(self, rule: RuleContext) -> list[ValidationIssue]:
        issues = []
        if not self.pattern.match(rule.name):
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name=rule.name,
                    validator=self.name,
                    message=f"Rule name '{rule.name}' doesn't match naming convention",
                    suggestion=f"Use pattern: {self.pattern.pattern}",
                )
            )
        return issues


class MetadataValidator:
    """
    Validate Prometheus/Loki rules against metadata requirements.

    Example:
        validator = MetadataValidator()
        validator.add_validator(HasRequiredLabels(["severity", "team"]))
        validator.add_validator(ValidRunbookUrl(check_accessibility=True))

        result = validator.validate_file("alerts.yaml")
        if not result.passed:
            for issue in result.issues:
                print(f"{issue.severity.value}: {issue.message}")
    """

    def __init__(self):
        self.validators: list[BaseValidator] = []

    def add_validator(self, validator: BaseValidator) -> "MetadataValidator":
        """Add a validator to the chain."""
        self.validators.append(validator)
        return self

    @classmethod
    def default(cls) -> "MetadataValidator":
        """Create validator with sensible defaults."""
        validator = cls()
        validator.add_validator(HasRequiredLabels(["severity"]))
        validator.add_validator(HasRequiredAnnotations(["summary", "description"]))
        validator.add_validator(ValidSeverityLevel())
        validator.add_validator(NoEmptyLabels())
        validator.add_validator(NoEmptyAnnotations())
        return validator

    @classmethod
    def strict(cls) -> "MetadataValidator":
        """Create validator with strict requirements."""
        validator = cls()
        validator.add_validator(HasRequiredLabels(["severity", "team", "service"]))
        validator.add_validator(HasRequiredAnnotations(["summary", "description", "runbook_url"]))
        validator.add_validator(ValidSeverityLevel())
        validator.add_validator(ValidRunbookUrl(check_accessibility=False))
        validator.add_validator(NoEmptyLabels())
        validator.add_validator(NoEmptyAnnotations())
        validator.add_validator(RangeQueryMaxDuration(max_duration="15d"))
        validator.add_validator(AlertForDuration(min_duration="0s", max_duration="1h"))
        return validator

    def validate_rule(self, rule: RuleContext) -> list[ValidationIssue]:
        """Validate a single rule against all validators."""
        issues = []
        for validator in self.validators:
            issues.extend(validator.validate(rule))
        return issues

    def validate_file(self, file_path: Path | str) -> ValidationResult:
        """Validate a Prometheus rules file."""
        file_path = Path(file_path)
        result = ValidationResult(file_path=file_path)

        if not file_path.exists():
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="file",
                    message=f"File not found: {file_path}",
                )
            )
            return result

        try:
            with open(file_path) as f:
                content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="yaml",
                    message=f"Invalid YAML: {e}",
                )
            )
            return result

        # Parse rules from Prometheus/Loki format
        rules = self._extract_rules(content)
        result.rules_checked = len(rules)

        for rule in rules:
            issues = self.validate_rule(rule)
            result.issues.extend(issues)

        return result

    def _extract_rules(self, content: dict[str, Any]) -> list[RuleContext]:
        """Extract rules from Prometheus/Loki YAML structure."""
        rules = []

        if not content:
            return rules

        groups = content.get("groups", [])
        for group in groups:
            group_name = group.get("name", "")
            for rule in group.get("rules", []):
                if "alert" in rule:
                    # Alert rule
                    rules.append(
                        RuleContext(
                            name=rule.get("alert", ""),
                            expr=rule.get("expr", ""),
                            labels=rule.get("labels", {}),
                            annotations=rule.get("annotations", {}),
                            for_duration=rule.get("for"),
                            rule_type="alert",
                            group_name=group_name,
                        )
                    )
                elif "record" in rule:
                    # Recording rule
                    rules.append(
                        RuleContext(
                            name=rule.get("record", ""),
                            expr=rule.get("expr", ""),
                            labels=rule.get("labels", {}),
                            annotations={},
                            rule_type="recording",
                            group_name=group_name,
                        )
                    )

        return rules


def validate_metadata(
    file_path: str | Path,
    strict: bool = False,
    check_urls: bool = False,
) -> ValidationResult:
    """
    Convenience function to validate a rules file.

    Args:
        file_path: Path to Prometheus/Loki rules file
        strict: Use strict validation (requires runbook_url, team, service)
        check_urls: Actually check if runbook URLs are accessible

    Returns:
        ValidationResult with any issues found
    """
    if strict:
        validator = MetadataValidator.strict()
        if check_urls:
            # Add URL accessibility check
            validator.add_validator(ValidRunbookUrl(check_accessibility=True))
    else:
        validator = MetadataValidator.default()

    return validator.validate_file(Path(file_path))
