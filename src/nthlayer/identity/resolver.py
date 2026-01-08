"""
Identity resolver for service name resolution.

Resolves service identities across multiple providers using various
matching strategies from exact matches to fuzzy matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from cachetools import TTLCache  # type: ignore[import-untyped]

from nthlayer.identity.models import IdentityMatch, ServiceIdentity
from nthlayer.identity.normalizer import normalize_service_name


@dataclass
class IdentityResolver:
    """
    Resolves service identities across multiple providers.

    Resolution strategies (in priority order):
    1. Explicit mapping match
    2. External ID match (provider-specific)
    3. Exact canonical name match
    4. Alias match
    5. Normalized name match
    6. Fuzzy string match
    7. Attribute correlation
    """

    # Known identities (canonical_name -> ServiceIdentity)
    identities: dict[str, ServiceIdentity] = field(default_factory=dict)

    # Configuration
    fuzzy_threshold: float = 0.85
    correlation_config: dict[str, Any] = field(
        default_factory=lambda: {
            "strong_attrs": ["repo", "repository", "github_url"],
            "weak_attrs": ["owner", "team", "slack_channel"],
            "strong_match_count": 1,
            "weak_match_count": 2,
        }
    )

    # Explicit mappings for known mismatches
    # Format: "raw_name@provider" -> "canonical_name"
    explicit_mappings: dict[str, str] = field(default_factory=dict)

    # Resolution cache
    _cache: TTLCache = field(default_factory=lambda: TTLCache(maxsize=1000, ttl=300))

    def resolve(
        self,
        raw_name: str,
        provider: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> IdentityMatch:
        """
        Resolve a raw service name to a canonical identity.

        Args:
            raw_name: Name as reported by provider
            provider: Provider name for context
            attributes: Additional attributes for correlation

        Returns:
            IdentityMatch with resolved identity or None
        """
        cache_key = f"{raw_name}@{provider or 'unknown'}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._resolve_internal(raw_name, provider, attributes)
        self._cache[cache_key] = result
        return result

    def _resolve_internal(
        self,
        raw_name: str,
        provider: str | None,
        attributes: dict[str, Any] | None,
    ) -> IdentityMatch:
        """Internal resolution logic."""
        # Strategy 1: Check explicit mappings
        mapping_key = f"{raw_name}@{provider}" if provider else raw_name
        if mapping_key in self.explicit_mappings:
            canonical = self.explicit_mappings[mapping_key]
            if canonical in self.identities:
                return IdentityMatch(
                    query=raw_name,
                    provider=provider,
                    identity=self.identities[canonical],
                    match_type="explicit_mapping",
                    confidence=1.0,
                )

        # Strategy 2: Check external ID for provider
        if provider:
            for identity in self.identities.values():
                if identity.external_ids.get(provider) == raw_name:
                    return IdentityMatch(
                        query=raw_name,
                        provider=provider,
                        identity=identity,
                        match_type="external_id",
                        confidence=0.95,
                    )

        # Strategy 3: Exact canonical match
        if raw_name in self.identities:
            return IdentityMatch(
                query=raw_name,
                provider=provider,
                identity=self.identities[raw_name],
                match_type="exact",
                confidence=1.0,
            )

        # Strategy 4: Alias match
        for identity in self.identities.values():
            if raw_name in identity.aliases:
                return IdentityMatch(
                    query=raw_name,
                    provider=provider,
                    identity=identity,
                    match_type="alias",
                    confidence=0.9,
                )

        # Strategy 5: Normalized match
        normalized = normalize_service_name(raw_name)
        if normalized in self.identities:
            return IdentityMatch(
                query=raw_name,
                provider=provider,
                identity=self.identities[normalized],
                match_type="normalized",
                confidence=0.85,
            )

        for identity in self.identities.values():
            if normalize_service_name(identity.canonical_name) == normalized:
                return IdentityMatch(
                    query=raw_name,
                    provider=provider,
                    identity=identity,
                    match_type="normalized",
                    confidence=0.85,
                )

        # Strategy 6: Fuzzy match
        fuzzy_match = self._fuzzy_match(normalized)
        if fuzzy_match:
            identity, score = fuzzy_match
            return IdentityMatch(
                query=raw_name,
                provider=provider,
                identity=identity,
                match_type="fuzzy",
                confidence=score,
            )

        # Strategy 7: Attribute correlation
        if attributes:
            correlated = self._correlate_attributes(attributes)
            if correlated:
                return IdentityMatch(
                    query=raw_name,
                    provider=provider,
                    identity=correlated,
                    match_type="attribute_correlation",
                    confidence=0.75,
                )

        # No match found
        return IdentityMatch(
            query=raw_name,
            provider=provider,
            identity=None,
            match_type="none",
            confidence=0.0,
        )

    def _fuzzy_match(
        self,
        normalized: str,
    ) -> tuple[ServiceIdentity, float] | None:
        """Find best fuzzy match above threshold."""
        best_score = 0.0
        best_identity = None

        for name, identity in self.identities.items():
            # Compare with canonical name
            score = SequenceMatcher(None, normalized, name).ratio()
            if score > best_score:
                best_score = score
                best_identity = identity

            # Compare with normalized aliases
            for alias in identity.aliases:
                alias_normalized = normalize_service_name(alias)
                score = SequenceMatcher(None, normalized, alias_normalized).ratio()
                if score > best_score:
                    best_score = score
                    best_identity = identity

        if best_score >= self.fuzzy_threshold and best_identity is not None:
            return (best_identity, best_score)
        return None

    def _correlate_attributes(
        self,
        attributes: dict[str, Any],
    ) -> ServiceIdentity | None:
        """Find identity by matching attributes."""
        config = self.correlation_config

        for identity in self.identities.values():
            strong_matches = 0
            weak_matches = 0

            # Check strong attributes
            for attr in config["strong_attrs"]:
                if (
                    attr in attributes
                    and attr in identity.attributes
                    and attributes[attr]
                    and attributes[attr] == identity.attributes[attr]
                ):
                    strong_matches += 1

            # Check weak attributes
            for attr in config["weak_attrs"]:
                if (
                    attr in attributes
                    and attr in identity.attributes
                    and attributes[attr]
                    and attributes[attr] == identity.attributes[attr]
                ):
                    weak_matches += 1

            # Match if enough correlations
            if (
                strong_matches >= config["strong_match_count"]
                or weak_matches >= config["weak_match_count"]
            ):
                return identity

        return None

    def register(
        self,
        identity: ServiceIdentity,
        merge_existing: bool = True,
    ) -> ServiceIdentity:
        """
        Register a known identity.

        If merge_existing is True and identity exists, merges instead of replacing.

        Args:
            identity: ServiceIdentity to register
            merge_existing: Whether to merge with existing identity

        Returns:
            The registered (or merged) identity
        """
        if merge_existing and identity.canonical_name in self.identities:
            existing = self.identities[identity.canonical_name]
            existing.merge_from(identity)
            return existing

        self.identities[identity.canonical_name] = identity
        return identity

    def register_from_discovery(
        self,
        raw_name: str,
        provider: str,
        attributes: dict[str, Any] | None = None,
    ) -> ServiceIdentity:
        """
        Resolve or create identity from discovered service.

        Updates existing identity with new information, or creates new one.

        Args:
            raw_name: Raw service name from provider
            provider: Provider name
            attributes: Optional service attributes

        Returns:
            The resolved or created identity
        """
        match = self.resolve(raw_name, provider, attributes)

        if match.identity:
            # Update existing with new information
            match.identity.aliases.add(raw_name)
            match.identity.external_ids[provider] = raw_name
            if attributes:
                match.identity.attributes.update(attributes)
            match.identity.last_seen = datetime.utcnow()
            return match.identity

        # Create new identity
        normalized = normalize_service_name(raw_name)
        new_identity = ServiceIdentity(
            canonical_name=normalized,
            aliases={raw_name},
            external_ids={provider: raw_name},
            attributes=attributes or {},
            source="discovered",
            confidence=0.7,
        )
        self.identities[normalized] = new_identity
        return new_identity

    def add_mapping(self, raw_name: str, canonical: str, provider: str | None = None) -> None:
        """
        Add explicit mapping from raw name to canonical name.

        Args:
            raw_name: Raw name as seen from provider
            canonical: Canonical name to map to
            provider: Optional provider context
        """
        mapping_key = f"{raw_name}@{provider}" if provider else raw_name
        self.explicit_mappings[mapping_key] = canonical
        self.clear_cache()

    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._cache.clear()

    def list_identities(self) -> list[ServiceIdentity]:
        """List all known identities."""
        return list(self.identities.values())

    def get_identity(self, canonical_name: str) -> ServiceIdentity | None:
        """Get identity by canonical name."""
        return self.identities.get(canonical_name)
