"""
Identity models for service name resolution.

Provides canonical identity representation for services across
multiple providers with different naming conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ServiceIdentity:
    """Canonical identity for a service across all providers."""

    canonical_name: str  # Normalized, canonical name

    # All known names/aliases for this service
    aliases: set[str] = field(default_factory=set)

    # Provider-specific identifiers
    # e.g., {"consul": "pay-api-prod", "backstage": "component:default/payment-api"}
    external_ids: dict[str, str] = field(default_factory=dict)

    # Attributes for correlation (owner, repo, etc.)
    attributes: dict[str, Any] = field(default_factory=dict)

    # Resolution confidence (0.0 - 1.0)
    confidence: float = 1.0

    # Source of truth: "declared" = from service.yaml, "discovered" = from providers
    source: str = "discovered"

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)

    def matches(self, name: str, provider: str | None = None) -> bool:
        """Check if a name matches this identity."""
        from nthlayer.identity.normalizer import normalize_service_name

        # Check external ID for specific provider
        if provider and self.external_ids.get(provider) == name:
            return True

        # Check canonical name
        if name == self.canonical_name:
            return True

        # Check aliases
        if name in self.aliases:
            return True

        # Check normalized form
        if normalize_service_name(name) == self.canonical_name:
            return True

        return False

    def merge_from(self, other: ServiceIdentity) -> None:
        """Merge another identity into this one."""
        self.aliases.update(other.aliases)
        self.aliases.add(other.canonical_name)
        self.external_ids.update(other.external_ids)
        self.attributes.update(other.attributes)
        self.last_seen = datetime.utcnow()

        # Keep higher confidence
        if other.confidence > self.confidence:
            self.confidence = other.confidence

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "external_ids": self.external_ids,
            "attributes": self.attributes,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


@dataclass
class IdentityMatch:
    """Result of an identity resolution attempt."""

    query: str  # Original query string
    provider: str | None  # Provider context

    identity: ServiceIdentity | None  # Resolved identity (None if no match)

    match_type: str  # How it was matched
    # "exact", "alias", "external_id", "normalized", "fuzzy", "attribute", "none"

    confidence: float  # Match confidence

    # Alternative matches if ambiguous
    alternatives: list[tuple[ServiceIdentity, float]] = field(default_factory=list)

    @property
    def found(self) -> bool:
        """Whether a match was found."""
        return self.identity is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "query": self.query,
            "provider": self.provider,
            "identity": self.identity.to_dict() if self.identity else None,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "found": self.found,
            "alternatives": [
                {"identity": i.to_dict(), "confidence": c} for i, c in self.alternatives
            ],
        }
