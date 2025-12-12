"""Validation module for linting and policy checking."""

from nthlayer.validation.metadata import (
    AlertForDuration,
    BaseValidator,
    HasRequiredAnnotations,
    HasRequiredLabels,
    LabelMatchesPattern,
    MetadataValidator,
    NoEmptyAnnotations,
    NoEmptyLabels,
    RangeQueryMaxDuration,
    RuleContext,
    RuleNamePattern,
    Severity,
    ValidationIssue,
    ValidationResult,
    ValidRunbookUrl,
    ValidSeverityLevel,
    validate_metadata,
)
from nthlayer.validation.promql import (
    LintIssue,
    LintResult,
    PintLinter,
    is_pint_available,
    lint_alerts_file,
)
from nthlayer.validation.promruval import (
    PromruvalConfig,
    PromruvalLinter,
    is_promruval_available,
    validate_with_promruval,
)

__all__ = [
    # PromQL linting (pint)
    "PintLinter",
    "LintResult",
    "LintIssue",
    "lint_alerts_file",
    "is_pint_available",
    # Metadata validation
    "MetadataValidator",
    "ValidationResult",
    "ValidationIssue",
    "Severity",
    "RuleContext",
    "BaseValidator",
    "HasRequiredLabels",
    "HasRequiredAnnotations",
    "LabelMatchesPattern",
    "ValidSeverityLevel",
    "ValidRunbookUrl",
    "RangeQueryMaxDuration",
    "AlertForDuration",
    "NoEmptyLabels",
    "NoEmptyAnnotations",
    "RuleNamePattern",
    "validate_metadata",
    # promruval integration
    "PromruvalLinter",
    "PromruvalConfig",
    "is_promruval_available",
    "validate_with_promruval",
]
