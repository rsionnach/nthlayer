"""
conftest/OPA policy validation for service specs.

Validates service.yaml files against Rego policies using either:
1. conftest binary (if installed) - full OPA capabilities
2. Native Python validation (fallback) - basic policy checks

Installation:
    brew install conftest
    # or download from https://github.com/open-policy-agent/conftest/releases
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nthlayer.core.tiers import VALID_TIERS
from nthlayer.slos.ceiling import validate_slo_ceiling
from nthlayer.validation.metadata import Severity, ValidationIssue, ValidationResult


@dataclass
class PolicyResult:
    """Result from a single policy check."""

    policy: str
    message: str
    severity: Severity
    metadata: dict[str, Any] = field(default_factory=dict)


class ConftestValidator:
    """
    Validate service specs using conftest/OPA policies.

    Uses conftest binary when available, falls back to native validation.
    """

    def __init__(self, policy_dir: Path | str | None = None):
        """
        Initialize validator.

        Args:
            policy_dir: Directory containing .rego policy files.
                       Defaults to 'policies/' in project root.
        """
        self._conftest_path = shutil.which("conftest")
        self.policy_dir = Path(policy_dir) if policy_dir else self._find_policy_dir()

    @property
    def is_conftest_available(self) -> bool:
        """Check if conftest is installed."""
        return self._conftest_path is not None

    def _find_policy_dir(self) -> Path:
        """Find the policies directory."""
        # Check common locations
        candidates = [
            Path("policies"),
            Path(__file__).parent.parent.parent.parent / "policies",
            Path.cwd() / "policies",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return Path("policies")

    def validate_file(self, file_path: Path | str) -> ValidationResult:
        """
        Validate a service spec file.

        Args:
            file_path: Path to service.yaml file

        Returns:
            ValidationResult with any policy violations
        """
        file_path = Path(file_path)
        result = ValidationResult(file_path=file_path)

        if not file_path.exists():
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="conftest",
                    message=f"File not found: {file_path}",
                )
            )
            return result

        if self.is_conftest_available and self.policy_dir.exists():
            return self._validate_with_conftest(file_path)
        else:
            return self._validate_native(file_path)

    def _validate_with_conftest(self, file_path: Path) -> ValidationResult:
        """Validate using conftest binary."""
        result = ValidationResult(file_path=file_path)
        assert self._conftest_path is not None  # Checked by is_available()

        cmd = [
            self._conftest_path,
            "test",
            str(file_path),
            "--policy",
            str(self.policy_dir),
            "--output",
            "json",
            "--all-namespaces",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse JSON output
            if proc.stdout.strip():
                try:
                    output = json.loads(proc.stdout)
                    for item in output:
                        # Process failures (deny rules)
                        for failure in item.get("failures", []):
                            result.issues.append(
                                ValidationIssue(
                                    severity=Severity.ERROR,
                                    rule_name=failure.get("query", ""),
                                    validator="conftest",
                                    message=failure.get("msg", str(failure)),
                                )
                            )
                        # Process warnings (warn rules)
                        for warning in item.get("warnings", []):
                            result.issues.append(
                                ValidationIssue(
                                    severity=Severity.WARNING,
                                    rule_name=warning.get("query", ""),
                                    validator="conftest",
                                    message=warning.get("msg", str(warning)),
                                )
                            )
                except json.JSONDecodeError:
                    # Fall back to parsing text output
                    result.issues.extend(self._parse_text_output(proc.stdout + proc.stderr))

            result.rules_checked = 1  # At least one file checked

        except subprocess.TimeoutExpired:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="conftest",
                    message="conftest timed out after 30 seconds",
                )
            )
        except subprocess.SubprocessError as e:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="",
                    validator="conftest",
                    message=f"conftest failed: {e}",
                )
            )

        return result

    def _parse_text_output(self, output: str) -> list[ValidationIssue]:
        """Parse conftest text output."""
        issues = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if "FAIL" in line or "fail" in line.lower():
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name="",
                        validator="conftest",
                        message=line,
                    )
                )
            elif "WARN" in line or "warn" in line.lower():
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name="",
                        validator="conftest",
                        message=line,
                    )
                )
        return issues

    def _validate_native(self, file_path: Path) -> ValidationResult:
        """
        Native Python validation when conftest is not available.

        Implements basic policy checks equivalent to the Rego policies.
        """
        result = ValidationResult(file_path=file_path)

        try:
            with open(file_path) as f:
                spec = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="yaml",
                    validator="native",
                    message=f"Invalid YAML: {e}",
                )
            )
            return result

        if not spec:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="empty",
                    validator="native",
                    message="File is empty or contains no valid YAML",
                )
            )
            return result

        # Service section checks
        service = spec.get("service", {})
        if not service:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="service.required",
                    validator="native",
                    message="service section is required",
                )
            )
        else:
            # Required fields
            for field in ["name", "team", "tier", "type"]:
                if not service.get(field):
                    result.issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            rule_name=f"service.{field}",
                            validator="native",
                            message=f"service.{field} is required",
                        )
                    )

            # Valid tier
            if service.get("tier") and service["tier"] not in VALID_TIERS:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name="service.tier.valid",
                        validator="native",
                        message=f"service.tier '{service['tier']}' is not a standard tier",
                    )
                )

            # Valid type
            valid_types = {"api", "worker", "stream", "web", "batch", "ml"}
            if service.get("type") and service["type"] not in valid_types:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name="service.type.valid",
                        validator="native",
                        message=f"service.type '{service['type']}' is not a standard type",
                    )
                )

        # Resources section checks
        resources = spec.get("resources", [])
        if not resources:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="resources.required",
                    validator="native",
                    message="resources section is required",
                )
            )
        else:
            # Check each resource has kind
            for i, resource in enumerate(resources):
                if not resource.get("kind"):
                    result.issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            rule_name="resource.kind",
                            validator="native",
                            message=f"resource {i} must have a 'kind' field",
                        )
                    )

            # Critical tier should have SLO
            if service.get("tier") == "critical":
                slo_resources = [r for r in resources if r.get("kind") == "SLO"]
                if not slo_resources:
                    result.issues.append(
                        ValidationIssue(
                            severity=Severity.WARNING,
                            rule_name="critical.slo",
                            validator="native",
                            message="critical tier services should have at least one SLO",
                        )
                    )

                pd_resources = [r for r in resources if r.get("kind") == "PagerDuty"]
                if not pd_resources:
                    result.issues.append(
                        ValidationIssue(
                            severity=Severity.WARNING,
                            rule_name="critical.pagerduty",
                            validator="native",
                            message="critical tier services should have PagerDuty integration",
                        )
                    )

            # SLO validation
            for resource in resources:
                if resource.get("kind") == "SLO":
                    self._validate_slo(resource, result, service)

            # SLO ceiling validation based on dependencies
            self._validate_slo_ceiling(spec, result, service)

        result.rules_checked = 1
        return result

    def _validate_slo(self, slo: dict, result: ValidationResult, service: dict) -> None:
        """Validate an SLO resource."""
        name = slo.get("name", "unnamed")
        spec = slo.get("spec", {})

        if not spec.get("objective"):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule_name="slo.objective",
                    validator="native",
                    message=f"SLO '{name}' is missing 'objective' in spec",
                )
            )
        else:
            objective = spec["objective"]
            if objective < 0 or objective > 100:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        rule_name="slo.objective.range",
                        validator="native",
                        message=f"SLO '{name}' objective must be between 0 and 100",
                    )
                )
            elif objective > 99.99:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name="slo.objective.aggressive",
                        validator="native",
                        message=f"SLO '{name}' has very aggressive objective ({objective}%)",
                    )
                )

        if not spec.get("window"):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="slo.window",
                    validator="native",
                    message=f"SLO '{name}' should specify a window (e.g., 30d)",
                )
            )

        # Critical tier availability check
        indicator = spec.get("indicator", {})
        if (
            service.get("tier") == "critical"
            and indicator.get("type") == "availability"
            and spec.get("objective", 100) < 99.9
        ):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule_name="slo.critical.availability",
                    validator="native",
                    message=f"Critical tier availability SLO '{name}' has low objective",
                )
            )

    def _validate_slo_ceiling(self, spec: dict, result: ValidationResult, service: dict) -> None:
        """
        Validate that SLO objectives don't exceed achievable ceiling.

        Based on Google SRE's "Rule of the Extra 9": your SLO cannot
        exceed the product of your dependencies' SLAs.

        This is OPT-IN: only runs if at least one dependency has an
        explicit `sla` field. Teams not ready for this can omit the field.
        """
        # Check each SLO against the ceiling
        resources = spec.get("resources", [])

        for resource in resources:
            if resource.get("kind") != "SLO":
                continue

            slo_name = resource.get("name", "unnamed")
            slo_spec = resource.get("spec", {})
            objective = slo_spec.get("objective")

            if objective is None:
                continue  # Skip if no objective (already flagged by other validation)

            # Validate against ceiling using the full spec
            ceiling_result = validate_slo_ceiling(objective, spec)

            # Skip if not opted in (no dependencies have sla field)
            if not ceiling_result.opted_in:
                continue

            if not ceiling_result.is_valid:
                # Target exceeds ceiling
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        rule_name="slo.ceiling.exceeded",
                        validator="native",
                        message=(
                            f"SLO '{slo_name}': {ceiling_result.message}. "
                            "Consider lowering target."
                        ),
                        suggestion=(
                            f"Max achievable: {ceiling_result.ceiling_slo:.2f}% based on: "
                            + ", ".join(
                                f"{d}={s:.2f}%" for d, s in ceiling_result.dependency_slas.items()
                            )
                        ),
                    )
                )
            elif ceiling_result.dependencies_missing_sla:
                # Some dependencies missing SLA (info, not warning)
                missing_list = ", ".join(ceiling_result.dependencies_missing_sla)
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        rule_name="slo.ceiling.partial",
                        validator="native",
                        message=(f"SLO '{slo_name}': {ceiling_result.message}"),
                        suggestion=f"Add 'sla' field to: {missing_list}",
                    )
                )
            elif ceiling_result.ceiling_slo - objective < 0.1:
                # Warn if very close to ceiling (less than 0.1% margin)
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        rule_name="slo.ceiling.tight_margin",
                        validator="native",
                        message=(
                            f"SLO '{slo_name}': target {objective:.2f}% has tight margin "
                            f"to ceiling {ceiling_result.ceiling_slo:.2f}%"
                        ),
                        suggestion="Consider lower target for application-level issues",
                    )
                )


def is_conftest_available() -> bool:
    """Check if conftest is installed."""
    return shutil.which("conftest") is not None


def validate_spec(
    file_path: str | Path,
    policy_dir: str | Path | None = None,
) -> ValidationResult:
    """
    Convenience function to validate a service spec.

    Args:
        file_path: Path to service.yaml file
        policy_dir: Optional policy directory

    Returns:
        ValidationResult with any policy violations
    """
    validator = ConftestValidator(policy_dir=policy_dir)
    return validator.validate_file(Path(file_path))
