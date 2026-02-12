"""
Policy condition evaluator.

Parses and evaluates condition strings against a context dictionary.
Supports a simple DSL for time, SLO, and service-based conditions.

Condition Language:
    # Comparisons
    hour >= 9
    budget_remaining < 20
    tier == 'critical'

    # Boolean operators
    hour >= 9 AND hour <= 17
    weekday OR environment == 'dev'
    NOT freeze_period

    # Parentheses
    (hour >= 9 AND hour <= 17) AND weekday

    # Built-in functions
    business_hours()
    freeze_period('2024-12-20', '2025-01-02')
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from nthlayer.policies.conditions import (
    is_business_hours,
    is_freeze_period,
    is_peak_traffic,
    is_weekday,
)


@dataclass
class PolicyContext:
    """Context for policy evaluation with service and SLO data."""

    # SLO metrics
    budget_remaining: float = 100.0
    budget_consumed: float = 0.0
    burn_rate: float = 1.0

    # Service info
    tier: str = "standard"
    environment: str = "prod"
    service: str = ""
    team: str = ""

    # Blast radius
    downstream_count: int = 0
    high_criticality_downstream: int = 0

    # Time (can be overridden for testing)
    now: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for evaluation."""
        now = self.now or datetime.now()

        return {
            # Time-based
            "hour": now.hour,
            "minute": now.minute,
            "weekday": now.weekday() < 5,
            "day_of_week": now.weekday(),
            "date": now.date().isoformat(),
            "month": now.month,
            "day": now.day,
            "year": now.year,
            # SLO-based
            "budget_remaining": self.budget_remaining,
            "budget_consumed": self.budget_consumed,
            "burn_rate": self.burn_rate,
            # Service-based
            "tier": self.tier,
            "environment": self.environment,
            "env": self.environment,
            "service": self.service,
            "team": self.team,
            "downstream_count": self.downstream_count,
            "high_criticality_downstream": self.high_criticality_downstream,
        }


@dataclass
class EvaluationResult:
    """Result of condition evaluation."""

    condition: str
    result: bool
    matched_rule: str | None = None
    context_snapshot: dict[str, Any] = field(default_factory=dict)


class ConditionEvaluator:
    """
    Evaluates policy conditions against a context.

    Supports a simple DSL with comparisons, boolean operators, and functions.
    """

    context: dict[str, Any]
    _policy_context: PolicyContext | None

    # Supported comparison operators
    OPERATORS: dict[str, Any] = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
    }

    # Built-in functions
    FUNCTIONS: dict[str, Callable[..., bool]] = {
        "business_hours": is_business_hours,
        "weekday": is_weekday,
        "freeze_period": is_freeze_period,
        "peak_traffic": is_peak_traffic,
    }

    def __init__(self, context: PolicyContext | dict[str, Any] | None = None):
        """
        Initialize evaluator with optional context.

        Args:
            context: PolicyContext or dict with evaluation context
        """
        if context is None:
            self.context = {}
        elif isinstance(context, PolicyContext):
            self.context = context.to_dict()
            self._policy_context = context
        else:
            self.context = context
            self._policy_context = None

    def evaluate(self, condition: str) -> bool:
        """
        Evaluate a condition string.

        Args:
            condition: Condition string like "hour >= 9 AND weekday"

        Returns:
            True if condition is met

        Examples:
            >>> evaluator.evaluate("hour >= 9 AND hour <= 17")
            True  # If current hour is between 9 and 17

            >>> evaluator.evaluate("budget_remaining < 20")
            False  # If budget_remaining is 50
        """
        if not condition or not condition.strip():
            return True  # Empty condition = always true

        # Normalize whitespace
        condition = " ".join(condition.split())

        try:
            return self._evaluate_expression(condition)
        except Exception:  # intentionally ignored: fail safe on parse error (condition not met)
            return False

    def _evaluate_expression(self, expr: str) -> bool:
        """Evaluate a boolean expression with AND/OR/NOT."""
        expr = expr.strip()

        # Handle parentheses first
        while "(" in expr:
            # Find innermost parentheses
            match = re.search(r"(?<!\w)\(([^()]+)\)", expr)
            if match:
                inner = match.group(1)
                result = self._evaluate_expression(inner)
                expr = expr[: match.start()] + str(result) + expr[match.end() :]
            else:
                break

        # Handle NOT
        if expr.upper().startswith("NOT "):
            return not self._evaluate_expression(expr[4:])

        # Handle OR (lowest precedence)
        if " OR " in expr.upper():
            parts = re.split(r"\s+OR\s+", expr, flags=re.IGNORECASE)
            return any(self._evaluate_expression(p) for p in parts)

        # Handle AND
        if " AND " in expr.upper():
            parts = re.split(r"\s+AND\s+", expr, flags=re.IGNORECASE)
            return all(self._evaluate_expression(p) for p in parts)

        # Handle boolean literals from parentheses resolution
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False

        # Handle function calls
        func_match = re.match(r"(\w+)\((.*)\)", expr)
        if func_match:
            return self._evaluate_function(func_match.group(1), func_match.group(2))

        # Handle simple comparisons
        return self._evaluate_comparison(expr)

    def _evaluate_comparison(self, expr: str) -> bool:
        """Evaluate a comparison like 'hour >= 9'."""
        # Try each operator
        for op, func in self.OPERATORS.items():
            if op in expr:
                parts = expr.split(op, 1)
                if len(parts) == 2:
                    left = self._resolve_value(parts[0].strip())
                    right = self._resolve_value(parts[1].strip())
                    return func(left, right)

        # Single variable (boolean check)
        value = self._resolve_value(expr)
        return bool(value)

    def _resolve_value(self, token: str) -> Any:
        """Resolve a token to its value."""
        token = token.strip()

        # String literal
        if (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            return token[1:-1]

        # Numeric literal
        try:
            if "." in token:
                return float(token)
            return int(token)
        except ValueError:
            pass

        # Boolean literal
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False

        # Context variable
        return self.context.get(token, False)

    def _evaluate_function(self, name: str, args_str: str) -> bool:
        """Evaluate a function call."""
        name = name.lower()

        if name not in self.FUNCTIONS:
            return False

        func = self.FUNCTIONS[name]

        # Parse arguments
        args = []
        if args_str.strip():
            # Split by comma, handling quoted strings
            raw_args = re.split(r",\s*(?=(?:[^']*'[^']*')*[^']*$)", args_str)
            for arg in raw_args:
                args.append(self._resolve_value(arg.strip()))

        # Get datetime from context if available
        now = None
        if self._policy_context:
            now = self._policy_context.now

        # Call function with appropriate args
        if name == "freeze_period" and len(args) >= 2:
            return func(args[0], args[1], now=now)
        elif name in ("business_hours", "weekday", "peak_traffic"):
            return func(now=now)

        return False

    def evaluate_all(
        self,
        conditions: list[dict[str, Any]],
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Evaluate multiple conditions and return the most restrictive match.

        Args:
            conditions: List of condition dicts with 'when', 'warning', 'blocking'

        Returns:
            Tuple of (should_apply, matched_condition)

        Example:
            >>> conditions = [
            ...     {"name": "peak", "when": "business_hours()", "blocking": 15},
            ...     {"name": "freeze", "when": "freeze_period(...)", "blocking": 100},
            ... ]
            >>> evaluator.evaluate_all(conditions)
            (True, {"name": "peak", ...})
        """
        matched = None

        for cond in conditions:
            when_clause = cond.get("when", "")
            if self.evaluate(when_clause):
                # Keep the most restrictive (highest blocking threshold)
                if matched is None:
                    matched = cond
                else:
                    curr_block = cond.get("blocking", 0)
                    prev_block = matched.get("blocking", 0)
                    if curr_block > prev_block:
                        matched = cond

        return (matched is not None, matched)
