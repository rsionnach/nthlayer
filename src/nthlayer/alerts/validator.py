"""
Alert Validation and Fixing

Validates alert rules and fixes common issues from upstream templates:
1. Label references in annotations that don't exist in PromQL output
2. Missing or zero 'for' duration causing false positives on restart
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .models import AlertRule


@dataclass
class ValidationResult:
    """Result of alert validation."""

    is_valid: bool
    issues: list[str]
    fixes_applied: list[str]


def extract_promql_output_labels(expr: str) -> set[str] | None:
    """
    Extract labels that will be present in PromQL query output.

    Returns:
        Set of label names, or None if labels cannot be determined
        (meaning all labels are preserved).

    Rules:
        - `sum by (a, b)` -> only a, b preserved
        - `sum without (a, b)` -> all except a, b preserved (returns None)
        - `count()` with no by/without -> no labels preserved
        - No aggregation -> all labels preserved (returns None)
    """
    # Pattern for aggregation with by() clause
    agg_funcs = r"sum|avg|min|max|count|group|stddev|stdvar|topk|bottomk|quantile"
    by_pattern = rf"\b({agg_funcs})\s*(?:by\s*\(([^)]*)\))"

    # Pattern for aggregation with without() clause
    without_pattern = rf"\b({agg_funcs})\s*without\s*\(([^)]*)\)"

    # Pattern for aggregation with no grouping (removes all labels)
    bare_agg_pattern = r"\b(sum|avg|min|max|count|group|stddev|stdvar)\s*\("

    # Check for by() - only these labels preserved
    by_matches = re.findall(by_pattern, expr, re.IGNORECASE)
    if by_matches:
        # Collect all labels from all by() clauses
        labels = set()
        for _, label_list in by_matches:
            for label in label_list.split(","):
                label = label.strip()
                if label:
                    labels.add(label)
        return labels if labels else set()

    # Check for without() - we can't determine exact output, return None
    # but note which labels are removed
    without_matches = re.findall(without_pattern, expr, re.IGNORECASE)
    if without_matches:
        # Return special marker indicating some labels are removed
        removed = set()
        for _, label_list in without_matches:
            for label in label_list.split(","):
                label = label.strip()
                if label:
                    removed.add(label)
        # Return the removed labels as negative indicator
        return {f"!{lbl}" for lbl in removed}

    # Check for bare aggregation (no by/without) - removes all labels
    bare_matches = re.findall(bare_agg_pattern, expr, re.IGNORECASE)
    if bare_matches:
        # Check if there's actually a by/without somewhere we missed
        if "by" not in expr.lower() and "without" not in expr.lower():
            return set()  # Empty set = no labels

    # No aggregation found, all labels preserved
    return None


def extract_annotation_label_refs(annotations: dict[str, str]) -> set[str]:
    """
    Extract label references from annotation templates.

    Finds patterns like {{ $labels.instance }} or {{ $labels.job }}
    """
    label_pattern = r"\{\{\s*\$labels\.(\w+)\s*\}\}"

    labels = set()
    for value in annotations.values():
        matches = re.findall(label_pattern, value)
        labels.update(matches)

    return labels


def fix_annotation_label_refs(
    annotations: dict[str, str],
    available_labels: set[str] | None,
) -> tuple[dict[str, str], list[str]]:
    """
    Fix invalid label references in annotations.

    Args:
        annotations: Original annotations dict
        available_labels: Set of available labels, or None if all available

    Returns:
        Tuple of (fixed annotations, list of fixes applied)
    """
    if available_labels is None:
        return annotations.copy(), []

    # Handle without() case - labels starting with ! are removed
    removed_labels = {lbl[1:] for lbl in available_labels if lbl.startswith("!")}
    if removed_labels:
        # For without(), we know these specific labels are removed
        available_labels = None  # Can't determine exact output
        unavailable = removed_labels
    else:
        unavailable = None

    label_pattern = r"\{\{\s*\$labels\.(\w+)\s*\}\}"
    fixed = {}
    fixes = []

    for key, value in annotations.items():
        new_value = value

        def make_replacer(annotation_key: str) -> Callable[[re.Match], str]:
            """Create a replacer function that captures the annotation key."""

            def replace_label(match: re.Match) -> str:
                label = match.group(1)

                # Check if label is unavailable
                is_unavailable = False
                if unavailable and label in unavailable:
                    is_unavailable = True
                elif available_labels is not None and label not in available_labels:
                    is_unavailable = True

                if is_unavailable:
                    fixes.append(f"Removed {{{{ $labels.{label} }}}} from {annotation_key}")
                    return f"[{label} unavailable]"

                return match.group(0)

            return replace_label

        new_value = re.sub(label_pattern, make_replacer(key), value)
        fixed[key] = new_value

    return fixed, fixes


def validate_and_fix_alert(alert: "AlertRule") -> tuple["AlertRule", ValidationResult]:
    """
    Validate an alert rule and fix common issues.

    Fixes:
    1. Label references in annotations that won't exist in query output
    2. 'for: 0m' duration changed to minimum safe value

    Args:
        alert: AlertRule to validate and fix

    Returns:
        Tuple of (fixed AlertRule, ValidationResult)
    """
    from .models import AlertRule

    issues = []
    fixes = []

    # Start with copies
    new_annotations = alert.annotations.copy()
    new_duration = alert.duration

    # Fix 1: Check and fix label references
    available_labels = extract_promql_output_labels(alert.expr)
    referenced_labels = extract_annotation_label_refs(alert.annotations)

    if available_labels is not None and referenced_labels:
        # Check for without() case
        removed_labels = {lbl[1:] for lbl in available_labels if lbl.startswith("!")}

        if removed_labels:
            # without() case - check if any referenced labels are in removed set
            invalid_refs = referenced_labels & removed_labels
            if invalid_refs:
                issues.append(
                    f"Labels {invalid_refs} referenced but removed by without() aggregation"
                )
                new_annotations, label_fixes = fix_annotation_label_refs(
                    alert.annotations, available_labels
                )
                fixes.extend(label_fixes)
        elif not available_labels:
            # Empty set - aggregation removes all labels
            if referenced_labels:
                issues.append(
                    f"Labels {referenced_labels} referenced but aggregation removes all labels"
                )
                new_annotations, label_fixes = fix_annotation_label_refs(
                    alert.annotations, available_labels
                )
                fixes.extend(label_fixes)
        else:
            # by() case - only these labels available
            invalid_refs = referenced_labels - available_labels
            if invalid_refs:
                issues.append(
                    f"Labels {invalid_refs} referenced but not in by() clause: {available_labels}"
                )
                new_annotations, label_fixes = fix_annotation_label_refs(
                    alert.annotations, available_labels
                )
                fixes.extend(label_fixes)

    # Fix 2: Ensure minimum 'for' duration
    if alert.duration in ("0m", "0s", ""):
        issues.append(f"Duration '{alert.duration}' may cause false positives on restart")
        new_duration = "1m"
        fixes.append(f"Changed 'for' from '{alert.duration}' to '1m'")

    # Create fixed alert if any changes
    if fixes:
        fixed_alert = AlertRule(
            name=alert.name,
            expr=alert.expr,
            duration=new_duration,
            severity=alert.severity,
            summary=alert.summary,
            description=alert.description,
            labels=alert.labels.copy(),
            annotations=new_annotations,
            technology=alert.technology,
            category=alert.category,
        )
    else:
        fixed_alert = alert

    result = ValidationResult(
        is_valid=len(issues) == 0,
        issues=issues,
        fixes_applied=fixes,
    )

    return fixed_alert, result
