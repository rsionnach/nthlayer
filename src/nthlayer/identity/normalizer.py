"""
Service name normalization for identity resolution.

Normalizes service names from different providers to a canonical form
by removing environment suffixes, version numbers, and common prefixes/suffixes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class NormalizationRule:
    """A single normalization rule."""

    pattern: str
    replacement: str
    description: str


# Default normalization rules (applied in order)
DEFAULT_RULES = [
    NormalizationRule(
        pattern=r"[-_]?(prod|production|staging|stage|dev|development|qa|uat|test)$",
        replacement="",
        description="Remove environment suffixes",
    ),
    NormalizationRule(
        pattern=r"[-_]?v\d+$",
        replacement="",
        description="Remove version suffixes",
    ),
    NormalizationRule(
        pattern=r"^(com|org|io|net)\.[^.]+\.",
        replacement="",
        description="Remove Java package prefixes",
    ),
    NormalizationRule(
        pattern=r"[-_]?(service|svc|api|srv|app)$",
        replacement="",
        description="Remove common type suffixes",
    ),
    NormalizationRule(
        pattern=r"^(service|svc|api|srv|app)[-_]",
        replacement="",
        description="Remove common type prefixes",
    ),
]


def normalize_service_name(
    name: str,
    rules: list[NormalizationRule] | None = None,
) -> str:
    """
    Normalize a service name to canonical form.

    Examples:
        payment-api-prod → payment
        com.acme.payment-service → payment
        PAYMENT-API → payment
        payment-api-v2 → payment
        svc-payment → payment

    Args:
        name: Raw service name from any provider
        rules: Optional custom normalization rules

    Returns:
        Normalized canonical name
    """
    if rules is None:
        rules = DEFAULT_RULES

    # Lowercase
    normalized = name.lower()

    # Apply rules in order
    for rule in rules:
        normalized = re.sub(rule.pattern, rule.replacement, normalized, flags=re.IGNORECASE)

    # Normalize separators to hyphens
    normalized = re.sub(r"[._]", "-", normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip("-")

    # Collapse multiple hyphens
    normalized = re.sub(r"-+", "-", normalized)

    return normalized


def extract_from_pattern(
    raw: str,
    pattern: str,
    group: str = "name",
) -> str | None:
    """
    Extract service name from provider-specific pattern.

    Examples:
        extract_from_pattern(
            "component:default/payment-api",
            r"^component:(?P<namespace>[^/]+)/(?P<name>.+)$",
            "name"
        ) → "payment-api"

    Args:
        raw: Raw identifier string
        pattern: Regex pattern with named groups
        group: Name of group to extract

    Returns:
        Extracted string or None if no match
    """
    match = re.match(pattern, raw)
    if match:
        try:
            return match.group(group)
        except IndexError:
            pass
    return None


# Provider-specific extraction patterns
PROVIDER_PATTERNS = {
    "backstage": r"^(?:component|service|api):(?P<namespace>[^/]+)/(?P<name>.+)$",
    "kubernetes": r"^(?P<namespace>[^/]+)/(?P<name>.+)$",
    "consul": r"^(?:dc\d+\.)?(?P<name>.+?)(?:-(?:prod|staging|dev))?$",
    "eureka": r"^(?P<name>.+)$",  # Eureka uses uppercase, normalize later
}


def extract_service_name(raw: str, provider: str) -> str:
    """
    Extract and normalize service name from provider-specific format.

    Args:
        raw: Raw identifier from provider
        provider: Provider name (backstage, kubernetes, consul, etc.)

    Returns:
        Extracted and normalized service name
    """
    # Try provider-specific pattern
    pattern = PROVIDER_PATTERNS.get(provider.lower())
    if pattern:
        extracted = extract_from_pattern(raw, pattern, "name")
        if extracted:
            return normalize_service_name(extracted)

    # Fallback to direct normalization
    return normalize_service_name(raw)
