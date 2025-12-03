"""
Template variable substitution for service specs.

Supports variables like ${service}, ${team}, etc.
"""

from __future__ import annotations

import re
from typing import Any

# Pattern matches ${variable}
VARIABLE_PATTERN = re.compile(r"\$\{(\w+)\}")


def substitute_variables(value: Any, context: dict[str, Any]) -> Any:
    """
    Recursively substitute template variables in a value.
    
    Supports:
    - ${service}
    - ${team}
    - ${tier}
    - ${type}
    - ${env} (if environment specified)
    
    Args:
        value: Value to process (string, dict, list, or primitive)
        context: Variable context (service name, team, environment, etc.)
    
    Returns:
        Value with variables substituted
    
    Example:
        >>> context = {"service": "payment-api", "team": "payments", "env": "prod"}
        >>> substitute_variables("Service: ${service} (${env})", context)
        'Service: payment-api (prod)'
    """
    if isinstance(value, str):
        return _substitute_string(value, context)
    elif isinstance(value, dict):
        return {k: substitute_variables(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_variables(item, context) for item in value]
    else:
        # Primitives pass through unchanged
        return value


def _substitute_string(text: str, context: dict[str, Any]) -> str:
    """Substitute ${variable} patterns in a string."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = context.get(var_name)
        if value is None:
            # Variable not found - leave unchanged
            return match.group(0)
        return str(value)
    
    return VARIABLE_PATTERN.sub(replacer, text)


def validate_template_variables(value: Any) -> list[str]:
    """
    Validate template variables in a value.
    
    Returns list of unknown variables found.
    
    Args:
        value: Value to check
    
    Returns:
        List of unknown variable names
    
    Example:
        >>> validate_template_variables("${service} - ${unknown}")
        ['unknown']
    """
    valid_vars = {"service", "team", "tier", "type", "language", "framework", "env"}
    unknown = []
    
    if isinstance(value, str):
        for match in VARIABLE_PATTERN.finditer(value):
            var_name = match.group(1)
            if var_name not in valid_vars:
                unknown.append(var_name)
    
    elif isinstance(value, dict):
        for v in value.values():
            unknown.extend(validate_template_variables(v))
    
    elif isinstance(value, list):
        for item in value:
            unknown.extend(validate_template_variables(item))
    
    return list(set(unknown))
