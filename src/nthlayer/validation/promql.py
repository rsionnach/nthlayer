"""
PromQL linting using Cloudflare's pint.

pint is a Prometheus rule linter/validator that checks alerting and
recording rules for common issues, syntax errors, and best practices.

Installation:
    brew install cloudflare/cloudflare/pint
    # or download from https://github.com/cloudflare/pint/releases

Usage:
    from nthlayer.validation import lint_alerts_file, is_pint_available

    if is_pint_available():
        result = lint_alerts_file("generated/payment-api/alerts.yaml")
        if not result.passed:
            for issue in result.issues:
                print(f"{issue.severity.value}: {issue.message}")
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from nthlayer.validation.metadata import Severity


def _pint_severity_to_enum(pint_severity: str) -> Severity:
    """Convert pint severity string to Severity enum.

    pint uses: Bug, Warning, Information, Fatal
    We normalize to: ERROR, WARNING, INFO
    """
    mapping = {
        "bug": Severity.ERROR,
        "fatal": Severity.ERROR,
        "error": Severity.ERROR,
        "warning": Severity.WARNING,
        "information": Severity.INFO,
        "info": Severity.INFO,
    }
    return mapping.get(pint_severity.lower(), Severity.WARNING)


@dataclass
class LintIssue:
    """A single linting issue from pint."""

    severity: Severity  # Unified severity enum
    rule_name: str  # Name of the alert/recording rule
    check: str  # pint check that failed (e.g., "promql/syntax")
    message: str  # Human-readable description
    line: Optional[int] = None  # Line number if available

    @property
    def is_error(self) -> bool:
        """Return True if this is a blocking error."""
        return self.severity == Severity.ERROR

    @property
    def is_warning(self) -> bool:
        """Return True if this is a warning."""
        return self.severity == Severity.WARNING


@dataclass
class LintResult:
    """Result of linting a Prometheus rules file."""

    file_path: Path
    issues: List[LintIssue] = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = 0
    pint_version: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Return True if no blocking errors."""
        return not any(issue.is_error for issue in self.issues)

    @property
    def error_count(self) -> int:
        """Count of blocking errors."""
        return sum(1 for issue in self.issues if issue.is_error)

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for issue in self.issues if issue.is_warning)

    def summary(self) -> str:
        """Human-readable summary."""
        if self.passed and not self.issues:
            return f"✓ {self.file_path.name}: No issues found"
        elif self.passed:
            return f"⚠ {self.file_path.name}: {self.warning_count} warnings"
        else:
            return (
                f"✗ {self.file_path.name}: {self.error_count} errors, {self.warning_count} warnings"
            )


class PintLinter:
    """Wrapper around Cloudflare's pint Prometheus linter."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize pint linter.

        Args:
            config_path: Optional path to .pint.hcl configuration file.
                        If not provided, pint runs in offline mode.
        """
        self.config_path = config_path
        self._pint_path = shutil.which("pint")

    @property
    def is_available(self) -> bool:
        """Check if pint is installed and accessible."""
        return self._pint_path is not None

    def get_version(self) -> Optional[str]:
        """Get pint version string."""
        if not self.is_available or self._pint_path is None:
            return None
        try:
            result = subprocess.run(
                [self._pint_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # pint version output: "pint version X.Y.Z ..."
            match = re.search(r"version\s+([\d.]+)", result.stdout)
            return match.group(1) if match else result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return None

    def lint_file(self, file_path: Path) -> LintResult:
        """
        Lint a Prometheus rules file.

        Args:
            file_path: Path to YAML file containing Prometheus rules

        Returns:
            LintResult with any issues found
        """
        file_path = Path(file_path)

        if not self.is_available:
            return LintResult(
                file_path=file_path,
                issues=[
                    LintIssue(
                        severity=Severity.INFO,
                        rule_name="",
                        check="pint/not-installed",
                        message=(
                            "pint not installed. "
                            "Install: brew install cloudflare/cloudflare/pint"
                        ),
                    )
                ],
                exit_code=-1,
            )

        if not file_path.exists():
            return LintResult(
                file_path=file_path,
                issues=[
                    LintIssue(
                        severity=Severity.ERROR,
                        rule_name="",
                        check="file/not-found",
                        message=f"File not found: {file_path}",
                    )
                ],
                exit_code=1,
            )

        # Build pint command (we know _pint_path is not None from is_available check above)
        assert self._pint_path is not None
        cmd: List[str] = [self._pint_path, "lint"]

        # Add config if specified
        if self.config_path and self.config_path.exists():
            cmd.extend(["--config", str(self.config_path)])

        # Add file to lint
        cmd.append(str(file_path))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=file_path.parent,
            )

            issues = self._parse_output(result.stdout + result.stderr)

            return LintResult(
                file_path=file_path,
                issues=issues,
                raw_output=result.stdout + result.stderr,
                exit_code=result.returncode,
                pint_version=self.get_version(),
            )

        except subprocess.TimeoutExpired:
            return LintResult(
                file_path=file_path,
                issues=[
                    LintIssue(
                        severity=Severity.ERROR,
                        rule_name="",
                        check="pint/timeout",
                        message="pint timed out after 60 seconds",
                    )
                ],
                exit_code=1,
            )
        except subprocess.SubprocessError as e:
            return LintResult(
                file_path=file_path,
                issues=[
                    LintIssue(
                        severity=Severity.ERROR,
                        rule_name="",
                        check="pint/error",
                        message=f"pint failed: {e}",
                    )
                ],
                exit_code=1,
            )

    def _parse_output(self, output: str) -> List[LintIssue]:
        """Parse pint output into structured issues."""
        issues = []

        # pint output format varies, common patterns:
        # file.yaml:10 Warning: rule_name - check_name: message
        # file.yaml:10-15 Bug: rule_name (check_name) message

        # Pattern for standard pint output
        pattern = re.compile(
            r"(?P<file>[^:]+):(?P<line>\d+)(?:-\d+)?\s+"
            r"(?P<severity>Bug|Warning|Information|Fatal):\s+"
            r"(?P<rule>\S+)?\s*"
            r"(?:\((?P<check>[^)]+)\)|(?P<check2>\S+):)?\s*"
            r"(?P<message>.+)",
            re.MULTILINE,
        )

        for match in pattern.finditer(output):
            issues.append(
                LintIssue(
                    severity=_pint_severity_to_enum(match.group("severity")),
                    rule_name=match.group("rule") or "",
                    check=match.group("check") or match.group("check2") or "unknown",
                    message=match.group("message").strip(),
                    line=int(match.group("line")) if match.group("line") else None,
                )
            )

        # If no structured issues found but exit code indicates failure,
        # add raw output as an issue
        if not issues and output.strip():
            # Check for simple error messages
            for line in output.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("level="):
                    # Determine severity from content
                    severity = Severity.WARNING
                    if "error" in line.lower() or "fatal" in line.lower():
                        severity = Severity.ERROR

                    issues.append(
                        LintIssue(
                            severity=severity,
                            rule_name="",
                            check="pint/output",
                            message=line,
                        )
                    )

        return issues

    def lint_directory(self, dir_path: Path, pattern: str = "*.yaml") -> List[LintResult]:
        """Lint all matching files in a directory."""
        dir_path = Path(dir_path)
        results = []

        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                results.append(self.lint_file(file_path))

        return results


def is_pint_available() -> bool:
    """Check if pint is installed."""
    return shutil.which("pint") is not None


def lint_alerts_file(
    file_path: Union[str, Path],
    config_path: Union[str, Path, None] = None,
) -> LintResult:
    """
    Convenience function to lint a single alerts file.

    Args:
        file_path: Path to alerts YAML file
        config_path: Optional pint config file

    Returns:
        LintResult with any issues found
    """
    linter = PintLinter(config_path=Path(config_path) if config_path else None)
    return linter.lint_file(Path(file_path))


def print_lint_result(result: LintResult, verbose: bool = False) -> None:
    """Pretty-print lint result to console."""
    print(result.summary())

    if result.issues:
        for issue in result.issues:
            icon = "✗" if issue.is_error else "⚠" if issue.is_warning else "ℹ"
            line_info = f":{issue.line}" if issue.line else ""
            print(f"  {icon} [{issue.check}]{line_info} {issue.message}")

        if verbose and result.raw_output:
            print()
            print("Raw output:")
            print(result.raw_output)
