# NthLayer Dependency Discovery & Identity Resolution Spec

## Overview

**Feature Name:** Dependency Discovery Engine
**Status:** Proposed
**Target Release:** v0.3.0 (after Drift Detection)

### Problem Statement

NthLayer's dependency-aware features (SLO feasibility validation, blast radius analysis) require knowledge of service dependencies. Manual declaration in `service.yaml` doesn't scale:

- N services × M dependencies = O(N×M) YAML maintenance
- Always stale, always incomplete
- Requires tribal knowledge
- Teams forget to update

### Solution

Discover dependencies automatically from existing systems that already know them:

- Service discovery systems (Consul, ZooKeeper, Eureka)
- Developer portals (Cortex.io, Backstage)
- Observability platforms (Prometheus, tracing)
- Cloud infrastructure (Kubernetes, AWS Cloud Map)

**Key principle:** Discover, don't declare. Manual declarations become overrides for edge cases.

### The Identity Challenge

Different systems use different identifiers for the same service:

| System | payment-api might be... |
|--------|-------------------------|
| Kubernetes | `payment-api`, `payments/payment-api` |
| Consul | `payment-api-prod`, `dc1.payment-api` |
| Backstage | `component:default/payment-api` |
| Cortex.io | `payment-api` (tag), `srv-12345` (ID) |
| Prometheus | `job="payment-api"`, `service="payments"` |
| Eureka | `PAYMENT-API` (uppercase) |
| ZooKeeper | `/services/com.acme.payment-api` |

The Identity Resolver normalizes these into canonical identities.

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Discovery Providers                            │
├───────────┬───────────┬───────────┬───────────┬───────────┬────────────────┤
│  Consul   │ ZooKeeper │ Cortex.io │ Backstage │Prometheus │  Kubernetes    │
│  Eureka   │   etcd    │           │           │  Tracing  │  Cloud Map     │
└─────┬─────┴─────┬─────┴─────┬─────┴─────┬─────┴─────┬─────┴───────┬────────┘
      │           │           │           │           │             │
      └───────────┴───────────┴─────┬─────┴───────────┴─────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │   Identity Resolver   │
                        │                       │
                        │ • Normalize names     │
                        │ • Match aliases       │
                        │ • Correlate attrs     │
                        │ • Resolve conflicts   │
                        └───────────┬───────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │   Dependency Graph    │
                        │   (Unified View)      │
                        └───────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │validate-slo │ │blast-radius │ │  portfolio  │
            │             │ │             │ │  --deps     │
            └─────────────┘ └─────────────┘ └─────────────┘
```

### Module Structure

```
src/nthlayer/
├── identity/                           # NEW PACKAGE
│   ├── __init__.py
│   ├── resolver.py                     # Core identity resolution
│   ├── models.py                       # ServiceIdentity, IdentityMatch
│   ├── normalizer.py                   # Name normalization rules
│   ├── ownership.py                    # OwnershipResolver, models
│   ├── store.py                        # Identity cache management
│   │
│   └── ownership_providers/            # Ownership provider implementations
│       ├── __init__.py
│       ├── pagerduty.py                # PagerDuty (pdpyras)
│       ├── opsgenie.py                 # OpsGenie (opsgenie-sdk)
│       ├── github.py                   # GitHub CODEOWNERS (PyGithub)
│       ├── slack.py                    # Slack channels (slack-sdk)
│       ├── aws.py                      # AWS tags (boto3)
│       └── kubernetes.py               # K8s labels (kubernetes-client)
│
├── dependencies/                       # NEW PACKAGE
│   ├── __init__.py
│   ├── discovery.py                    # Discovery orchestrator
│   ├── graph.py                        # DependencyGraph model
│   ├── models.py                       # DiscoveredDependency, etc.
│   │
│   └── providers/                      # Provider implementations
│       ├── __init__.py
│       ├── base.py                     # BaseDepProvider ABC
│       ├── consul.py                   # HashiCorp Consul
│       ├── zookeeper.py                # Apache ZooKeeper
│       ├── eureka.py                   # Netflix Eureka
│       ├── etcd.py                     # etcd v3
│       ├── cortex_portal.py            # Cortex.io developer portal
│       ├── backstage.py                # Backstage catalog
│       ├── prometheus.py               # Prometheus metrics
│       ├── kubernetes.py               # Kubernetes API
│       ├── cloudmap.py                 # AWS Cloud Map
│       └── tracing.py                  # Tempo/Jaeger traces
│
├── cli/
│   ├── deps.py                         # NEW: `nthlayer deps` command
│   ├── identity.py                     # NEW: `nthlayer identity` command
│   ├── ownership.py                    # NEW: `nthlayer ownership` command
│   ├── validate_slo.py                 # NEW: `nthlayer validate-slo`
│   └── blast_radius.py                 # NEW: `nthlayer blast-radius`
```

---

## Dependencies (Python Packages)

### Required Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    # Existing NthLayer dependencies...

    # Identity & Discovery
    "cachetools>=5.3.0",              # TTL cache for identity resolution
    "httpx>=0.25.0",                  # Async HTTP client for REST APIs
]

[project.optional-dependencies]
# Provider-specific dependencies (install as needed)
discovery-consul = [
    "python-consul2>=0.1.5",          # HashiCorp Consul client
]
discovery-zookeeper = [
    "kazoo>=2.9.0",                    # Apache ZooKeeper client
]
discovery-eureka = [
    "py-eureka-client>=0.11.0",       # Netflix Eureka client
]
discovery-etcd = [
    "etcd3>=0.12.0",                   # etcd v3 client
]
discovery-kubernetes = [
    "kubernetes>=28.0.0",              # Official K8s Python client
]
discovery-aws = [
    "boto3>=1.34.0",                   # AWS SDK
]
discovery-tracing = [
    "opentelemetry-api>=1.20.0",      # OTel for trace parsing
]

# Ownership provider dependencies
ownership-pagerduty = [
    "pdpyras>=5.2.0",                  # PagerDuty Python SDK
]
ownership-opsgenie = [
    "opsgenie-sdk>=2.1.0",            # OpsGenie Python SDK
]
ownership-github = [
    "PyGithub>=2.1.0",                 # GitHub Python SDK
]
ownership-slack = [
    "slack-sdk>=3.23.0",              # Slack Python SDK
]

# All providers
discovery-all = [
    "python-consul2>=0.1.5",
    "kazoo>=2.9.0",
    "py-eureka-client>=0.11.0",
    "etcd3>=0.12.0",
    "kubernetes>=28.0.0",
    "boto3>=1.34.0",
    "opentelemetry-api>=1.20.0",
    "pdpyras>=5.2.0",
    "opsgenie-sdk>=2.1.0",
    "PyGithub>=2.1.0",
    "slack-sdk>=3.23.0",
]
```

### Installation

```bash
# Core only (Prometheus + Backstage/Cortex via HTTP)
pip install nthlayer

# With specific providers
pip install nthlayer[discovery-consul,discovery-kubernetes]

# With ownership providers
pip install nthlayer[ownership-pagerduty,ownership-slack]

# All providers
pip install nthlayer[discovery-all]
```

---

## Data Models

### Ownership Models

```python
# src/nthlayer/identity/ownership.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OwnershipSource(Enum):
    """Sources of ownership attribution, ranked by confidence."""
    DECLARED = "declared"           # service.yaml explicit declaration
    PAGERDUTY = "pagerduty"         # PagerDuty service ownership
    OPSGENIE = "opsgenie"           # OpsGenie service ownership
    DEVELOPER_PORTAL = "portal"     # Cortex.io / Backstage
    ONCALL = "oncall"               # Current on-call schedule
    CODEOWNERS = "codeowners"       # GitHub/GitLab CODEOWNERS file
    CLOUD_TAGS = "cloud_tags"       # AWS/GCP/Azure resource tags
    KUBERNETES = "kubernetes"       # K8s labels/annotations
    SLACK_CHANNEL = "slack"         # Slack channel naming convention
    GIT_ACTIVITY = "git_activity"   # Most active contributors
    COST_CENTER = "cost_center"     # FinOps attribution


@dataclass
class OwnershipSignal:
    """A single ownership signal from a source."""
    source: OwnershipSource
    owner: str
    confidence: float
    metadata: dict = field(default_factory=dict)


@dataclass
class OwnershipAttribution:
    """Resolved ownership for a service."""

    service: str

    # Primary owner (team or individual)
    owner: str | None = None
    owner_type: str = "team"  # "team", "individual", "group"

    # Confidence and source
    confidence: float = 0.0
    source: OwnershipSource | None = None

    # All discovered ownership signals
    signals: list[OwnershipSignal] = field(default_factory=list)

    # Contact information
    slack_channel: str | None = None
    email: str | None = None
    pagerduty_escalation: str | None = None
    opsgenie_team: str | None = None
```

### Ownership Attribution Sources

Beyond repo owner, NthLayer discovers ownership from multiple sources:

| Source | Attribute | Confidence | Notes |
|--------|-----------|------------|-------|
| **Explicit in service.yaml** | `team`, `owner` | 1.0 | User-declared, always wins |
| **PagerDuty** | Service → Escalation Policy → Team | 0.95 | Who gets paged = who owns it |
| **OpsGenie** | Service → Team | 0.9 | Alternative to PagerDuty |
| **Developer portal** | Cortex.io/Backstage owner field | 0.9 | Curated catalog data |
| **CODEOWNERS** | GitHub/GitLab CODEOWNERS file | 0.85 | Explicit code ownership |
| **Cloud tags** | AWS `team`, `cost-center`, GCP labels | 0.8 | Often mandated by FinOps |
| **Kubernetes labels** | `owner`, `team`, `app.kubernetes.io/managed-by` | 0.75 | If standardized |
| **Slack channel** | `#team-payments-alerts` | 0.6 | Channel naming conventions |
| **Git activity** | Most frequent contributors | 0.4 | Fallback proxy signal |

### Core Models

```python
# src/nthlayer/dependencies/models.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DependencyType(Enum):
    """Classification of dependency relationships."""
    SERVICE = "service"           # Service-to-service call
    DATASTORE = "datastore"       # Database, cache, storage
    QUEUE = "queue"               # Message queue, event stream
    EXTERNAL = "external"         # Third-party API
    INFRASTRUCTURE = "infra"      # Internal infra (config, secrets)


class DependencyDirection(Enum):
    """Direction of dependency relationship."""
    UPSTREAM = "upstream"         # Services this service calls
    DOWNSTREAM = "downstream"     # Services that call this service


@dataclass
class DiscoveredDependency:
    """A dependency discovered from a provider."""
    source_service: str               # Service that has the dependency
    target_service: str               # Service being depended on
    provider: str                     # Provider that discovered this

    dep_type: DependencyType = DependencyType.SERVICE
    confidence: float = 0.5           # 0.0 - 1.0

    # Provider-specific metadata
    metadata: dict = field(default_factory=dict)

    # Discovery timestamp
    discovered_at: datetime = field(default_factory=datetime.utcnow)

    # Raw identifiers before resolution
    raw_source: str | None = None
    raw_target: str | None = None


@dataclass
class ResolvedDependency:
    """A dependency with resolved canonical identities."""
    source: "ServiceIdentity"
    target: "ServiceIdentity"
    dep_type: DependencyType

    # Aggregated confidence from all providers
    confidence: float

    # All providers that reported this dependency
    providers: list[str] = field(default_factory=list)

    # Combined metadata from all providers
    metadata: dict = field(default_factory=dict)


@dataclass
class DependencyGraph:
    """Complete dependency graph for analysis."""
    services: dict[str, "ServiceIdentity"]
    edges: list[ResolvedDependency]

    # Graph metadata
    built_at: datetime = field(default_factory=datetime.utcnow)
    providers_used: list[str] = field(default_factory=list)

    def get_upstream(self, service: str) -> list[ResolvedDependency]:
        """Get all services this service depends on."""
        return [e for e in self.edges if e.source.canonical_name == service]

    def get_downstream(self, service: str) -> list[ResolvedDependency]:
        """Get all services that depend on this service."""
        return [e for e in self.edges if e.target.canonical_name == service]

    def get_transitive_upstream(
        self,
        service: str,
        max_depth: int = 10
    ) -> list[tuple[ResolvedDependency, int]]:
        """Get all transitive dependencies with depth."""
        result = []
        visited = set()

        def traverse(svc: str, depth: int):
            if depth > max_depth or svc in visited:
                return
            visited.add(svc)

            for dep in self.get_upstream(svc):
                result.append((dep, depth))
                traverse(dep.target.canonical_name, depth + 1)

        traverse(service, 1)
        return result

    def get_transitive_downstream(
        self,
        service: str,
        max_depth: int = 10
    ) -> list[tuple[ResolvedDependency, int]]:
        """Get all services transitively depending on this service."""
        result = []
        visited = set()

        def traverse(svc: str, depth: int):
            if depth > max_depth or svc in visited:
                return
            visited.add(svc)

            for dep in self.get_downstream(svc):
                result.append((dep, depth))
                traverse(dep.source.canonical_name, depth + 1)

        traverse(service, 1)
        return result
```

### Identity Models

```python
# src/nthlayer/identity/models.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ServiceIdentity:
    """Canonical identity for a service across all providers."""

    canonical_name: str                           # Normalized, canonical name

    # All known names/aliases for this service
    aliases: set[str] = field(default_factory=set)

    # Provider-specific identifiers
    # e.g., {"consul": "pay-api-prod", "cortex.io": "srv-123"}
    external_ids: dict[str, str] = field(default_factory=dict)

    # Attributes for correlation (owner, repo, etc.)
    attributes: dict[str, any] = field(default_factory=dict)

    # Resolution confidence (0.0 - 1.0)
    confidence: float = 1.0

    # Source of truth
    # "declared" = from service.yaml, "discovered" = from providers
    source: str = "discovered"

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)

    def matches(self, name: str, provider: str | None = None) -> bool:
        """Check if a name matches this identity."""
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
        from nthlayer.identity.normalizer import normalize_service_name
        if normalize_service_name(name) == self.canonical_name:
            return True

        return False

    def merge_from(self, other: "ServiceIdentity") -> None:
        """Merge another identity into this one."""
        self.aliases.update(other.aliases)
        self.aliases.add(other.canonical_name)
        self.external_ids.update(other.external_ids)
        self.attributes.update(other.attributes)
        self.last_seen = datetime.utcnow()

        # Keep higher confidence
        if other.confidence > self.confidence:
            self.confidence = other.confidence


@dataclass
class IdentityMatch:
    """Result of an identity resolution attempt."""

    query: str                        # Original query string
    provider: str | None              # Provider context

    identity: ServiceIdentity | None  # Resolved identity (None if no match)

    match_type: str                   # How it was matched
    # "exact", "alias", "external_id", "normalized", "fuzzy", "attribute"

    confidence: float                 # Match confidence

    # Alternative matches if ambiguous
    alternatives: list[tuple[ServiceIdentity, float]] = field(default_factory=list)
```

---

## Identity Resolver

### Normalizer

```python
# src/nthlayer/identity/normalizer.py

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
        pattern=r'[-_]?(prod|production|staging|stage|dev|development|qa|uat|test)$',
        replacement='',
        description='Remove environment suffixes'
    ),
    NormalizationRule(
        pattern=r'[-_]?v\d+$',
        replacement='',
        description='Remove version suffixes'
    ),
    NormalizationRule(
        pattern=r'^(com|org|io|net)\.[^.]+\.',
        replacement='',
        description='Remove Java package prefixes'
    ),
    NormalizationRule(
        pattern=r'[-_]?(service|svc|api|srv|app)$',
        replacement='',
        description='Remove common type suffixes'
    ),
    NormalizationRule(
        pattern=r'^(service|svc|api|srv|app)[-_]',
        replacement='',
        description='Remove common type prefixes'
    ),
]


def normalize_service_name(
    name: str,
    rules: list[NormalizationRule] | None = None
) -> str:
    """
    Normalize a service name to canonical form.

    Examples:
        payment-api-prod → payment
        com.acme.payment-service → payment
        PAYMENT-API → payment
        payment-api-v2 → payment
    """
    if rules is None:
        rules = DEFAULT_RULES

    # Lowercase
    normalized = name.lower()

    # Apply rules in order
    for rule in rules:
        normalized = re.sub(rule.pattern, rule.replacement, normalized, flags=re.IGNORECASE)

    # Normalize separators to hyphens
    normalized = re.sub(r'[._]', '-', normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip('-')

    # Collapse multiple hyphens
    normalized = re.sub(r'-+', '-', normalized)

    return normalized


def extract_from_pattern(
    raw: str,
    pattern: str,
    group: str = "name"
) -> str | None:
    """
    Extract service name from provider-specific pattern.

    Examples:
        extract_from_pattern(
            "component:default/payment-api",
            r"^component:(?P<namespace>[^/]+)/(?P<name>.+)$",
            "name"
        ) → "payment-api"
    """
    match = re.match(pattern, raw)
    if match:
        try:
            return match.group(group)
        except IndexError:
            pass
    return None
```

### Core Resolver

```python
# src/nthlayer/identity/resolver.py

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional
from cachetools import TTLCache

from nthlayer.identity.models import ServiceIdentity, IdentityMatch
from nthlayer.identity.normalizer import normalize_service_name


@dataclass
class IdentityResolver:
    """
    Resolves service identities across multiple providers.

    Resolution strategies (in priority order):
    1. Explicit external ID match
    2. Exact canonical name match
    3. Alias match
    4. Normalized name match
    5. Fuzzy string match
    6. Attribute correlation
    """

    # Known identities (canonical_name -> ServiceIdentity)
    identities: dict[str, ServiceIdentity] = field(default_factory=dict)

    # Configuration
    fuzzy_threshold: float = 0.85
    correlation_config: dict = field(default_factory=lambda: {
        "strong_attrs": ["repo", "repository", "github_url"],
        "weak_attrs": ["owner", "team", "slack_channel"],
        "strong_match_count": 1,
        "weak_match_count": 2,
    })

    # Explicit mappings for known mismatches
    # Format: "raw_name@provider" -> "canonical_name"
    explicit_mappings: dict[str, str] = field(default_factory=dict)

    # Resolution cache
    _cache: TTLCache = field(default_factory=lambda: TTLCache(maxsize=1000, ttl=300))

    def resolve(
        self,
        raw_name: str,
        provider: str | None = None,
        attributes: dict | None = None,
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
        attributes: dict | None,
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
        normalized: str
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

        if best_score >= self.fuzzy_threshold:
            return (best_identity, best_score)
        return None

    def _correlate_attributes(
        self,
        attributes: dict
    ) -> ServiceIdentity | None:
        """Find identity by matching attributes."""
        config = self.correlation_config

        for identity in self.identities.values():
            strong_matches = 0
            weak_matches = 0

            # Check strong attributes
            for attr in config["strong_attrs"]:
                if (attr in attributes and
                    attr in identity.attributes and
                    attributes[attr] and
                    attributes[attr] == identity.attributes[attr]):
                    strong_matches += 1

            # Check weak attributes
            for attr in config["weak_attrs"]:
                if (attr in attributes and
                    attr in identity.attributes and
                    attributes[attr] and
                    attributes[attr] == identity.attributes[attr]):
                    weak_matches += 1

            # Match if enough correlations
            if (strong_matches >= config["strong_match_count"] or
                weak_matches >= config["weak_match_count"]):
                return identity

        return None

    def register(
        self,
        identity: ServiceIdentity,
        merge_existing: bool = True
    ) -> ServiceIdentity:
        """
        Register a known identity.

        If merge_existing is True and identity exists, merges instead of replacing.
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
        attributes: dict | None = None,
    ) -> ServiceIdentity:
        """
        Resolve or create identity from discovered service.

        Updates existing identity with new information, or creates new one.
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

    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._cache.clear()
```

---

## Provider Base Class

```python
# src/nthlayer/dependencies/providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from nthlayer.dependencies.models import DiscoveredDependency


@dataclass
class ProviderHealth:
    """Health status of a provider."""
    healthy: bool
    message: str
    latency_ms: float | None = None


class BaseDepProvider(ABC):
    """
    Abstract base class for dependency discovery providers.

    All providers must implement:
    - discover(): Find dependencies for a specific service
    - list_services(): List all known services
    - health_check(): Verify provider connectivity

    Providers should:
    - Use official SDKs where available
    - Handle authentication via environment variables or config
    - Return raw names (identity resolution happens later)
    - Include confidence scores based on data quality
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for identification."""
        pass

    @abstractmethod
    async def discover(
        self,
        service: str
    ) -> list[DiscoveredDependency]:
        """
        Discover dependencies for a service.

        Args:
            service: Service name (may be raw or canonical)

        Returns:
            List of discovered dependencies
        """
        pass

    @abstractmethod
    async def list_services(self) -> list[str]:
        """
        List all services known to this provider.

        Returns:
            List of service names (raw, provider-specific)
        """
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """
        Check provider connectivity and health.

        Returns:
            ProviderHealth status
        """
        pass

    async def get_service_attributes(
        self,
        service: str
    ) -> dict:
        """
        Get service attributes for identity correlation.

        Override in subclasses that have rich metadata.

        Returns:
            Dict of attributes (owner, repo, team, etc.)
        """
        return {}

    async def discover_all(self) -> AsyncIterator[DiscoveredDependency]:
        """
        Discover all dependencies for all services.

        Default implementation iterates list_services().
        Override for providers with bulk discovery APIs.
        """
        services = await self.list_services()
        for service in services:
            deps = await self.discover(service)
            for dep in deps:
                yield dep
```

---

## Provider Implementations

### HashiCorp Consul

```python
# src/nthlayer/dependencies/providers/consul.py

"""
HashiCorp Consul dependency provider.

Uses python-consul2 SDK: https://github.com/poppyred/python-consul2

Discovers:
- Service registrations from catalog
- Connect intentions (service-to-service policies)
- Service health status
- KV metadata (optional)
"""

from dataclasses import dataclass, field
import time

import consul.aio  # python-consul2 async client

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class ConsulDepProvider(BaseDepProvider):
    """
    Discover dependencies from HashiCorp Consul.

    Configuration:
        host: Consul host (default: localhost)
        port: Consul port (default: 8500)
        token: ACL token (optional)
        scheme: http or https (default: http)
        dc: Datacenter (optional, uses agent's DC if not set)

    Environment variables:
        CONSUL_HTTP_ADDR: host:port
        CONSUL_HTTP_TOKEN: ACL token
        CONSUL_DATACENTER: Datacenter
    """

    host: str = "localhost"
    port: int = 8500
    token: str | None = None
    scheme: str = "http"
    dc: str | None = None

    # Optional: KV path for explicit dependency declarations
    kv_dependency_prefix: str | None = "service-dependencies/"

    _client: consul.aio.Consul | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "consul"

    def _get_client(self) -> consul.aio.Consul:
        """Get or create Consul client."""
        if self._client is None:
            self._client = consul.aio.Consul(
                host=self.host,
                port=self.port,
                token=self.token,
                scheme=self.scheme,
                dc=self.dc,
            )
        return self._client

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Consul Connect intentions and KV."""
        deps = []
        client = self._get_client()

        # 1. Get Connect intentions where this service is the source
        # (services this service is allowed to call)
        try:
            _, intentions = await client.connect.intentions.list()

            for intention in intentions or []:
                # Intentions where this service is the source
                if intention.get("SourceName") == service:
                    target = intention.get("DestinationName")
                    if target and target != "*":
                        deps.append(DiscoveredDependency(
                            source_service=service,
                            target_service=target,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.9,  # High - explicit policy
                            metadata={
                                "intention_action": intention.get("Action"),
                                "intention_id": intention.get("ID"),
                                "description": intention.get("Description"),
                            },
                            raw_source=service,
                            raw_target=target,
                        ))

                # Intentions where this service is the destination (dependents)
                if intention.get("DestinationName") == service:
                    source = intention.get("SourceName")
                    if source and source != "*":
                        deps.append(DiscoveredDependency(
                            source_service=source,
                            target_service=service,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.9,
                            metadata={
                                "intention_action": intention.get("Action"),
                                "direction": "inbound",
                            },
                            raw_source=source,
                            raw_target=service,
                        ))
        except Exception as e:
            # Connect intentions may not be enabled
            pass

        # 2. Check KV for explicit dependency declarations
        if self.kv_dependency_prefix:
            try:
                _, data = await client.kv.get(
                    f"{self.kv_dependency_prefix}{service}",
                    recurse=False,
                )

                if data and data.get("Value"):
                    import json
                    dep_list = json.loads(data["Value"].decode())

                    for dep in dep_list:
                        dep_name = dep if isinstance(dep, str) else dep.get("name")
                        dep_type = DependencyType.SERVICE

                        if isinstance(dep, dict):
                            type_str = dep.get("type", "service").lower()
                            dep_type = DependencyType(type_str) if type_str in DependencyType.__members__.values() else DependencyType.SERVICE

                        deps.append(DiscoveredDependency(
                            source_service=service,
                            target_service=dep_name,
                            provider=self.name,
                            dep_type=dep_type,
                            confidence=0.85,
                            metadata={"source": "kv"},
                            raw_source=service,
                            raw_target=dep_name,
                        ))
            except Exception:
                pass

        return deps

    async def list_services(self) -> list[str]:
        """List all services registered in Consul catalog."""
        client = self._get_client()

        _, services = await client.catalog.services()

        # Filter out Consul internal service
        return [name for name in services.keys() if name != "consul"]

    async def health_check(self) -> ProviderHealth:
        """Check Consul connectivity."""
        client = self._get_client()

        start = time.time()
        try:
            _, leader = await client.status.leader()
            latency = (time.time() - start) * 1000

            if leader:
                return ProviderHealth(
                    healthy=True,
                    message=f"Connected to Consul, leader: {leader}",
                    latency_ms=latency,
                )
            else:
                return ProviderHealth(
                    healthy=False,
                    message="Consul has no leader",
                    latency_ms=latency,
                )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Consul connection failed: {str(e)}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service metadata from Consul catalog."""
        client = self._get_client()

        _, services = await client.catalog.service(service)

        if not services:
            return {}

        # Get metadata from first instance
        instance = services[0]
        meta = instance.get("ServiceMeta", {})

        return {
            "consul_service_id": instance.get("ServiceID"),
            "consul_node": instance.get("Node"),
            "address": instance.get("ServiceAddress") or instance.get("Address"),
            "port": instance.get("ServicePort"),
            "tags": instance.get("ServiceTags", []),
            # Common metadata fields
            "owner": meta.get("owner"),
            "team": meta.get("team"),
            "repo": meta.get("repo") or meta.get("repository"),
            "version": meta.get("version"),
        }
```

### Apache ZooKeeper

```python
# src/nthlayer/dependencies/providers/zookeeper.py

"""
Apache ZooKeeper dependency provider.

Uses Kazoo SDK: https://kazoo.readthedocs.io/

Discovers:
- Service registrations under configurable paths
- Kafka consumer group → topic relationships
- Custom dependency metadata in znodes
"""

from dataclasses import dataclass, field
import json
import time
from contextlib import asynccontextmanager

from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class ZooKeeperDepProvider(BaseDepProvider):
    """
    Discover dependencies from Apache ZooKeeper.

    Configuration:
        hosts: ZooKeeper connection string (e.g., "zk1:2181,zk2:2181")
        service_path: Path prefix for service registration (default: /services)
        kafka_consumers_path: Path for Kafka consumer groups (default: /consumers)

    Environment variables:
        ZOOKEEPER_HOSTS: Connection string

    Expected znode structure:
        /services/{service_name}/metadata -> JSON with dependencies
        /services/{service_name}/instances/{instance_id} -> Instance data
    """

    hosts: str = "localhost:2181"
    service_path: str = "/services"
    kafka_consumers_path: str = "/consumers"
    timeout: float = 10.0

    @property
    def name(self) -> str:
        return "zookeeper"

    @asynccontextmanager
    async def _get_client(self):
        """Context manager for ZooKeeper client."""
        # Kazoo is synchronous, but we wrap it for consistency
        client = KazooClient(hosts=self.hosts, timeout=self.timeout)
        client.start()
        try:
            yield client
        finally:
            client.stop()

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from ZooKeeper metadata and Kafka consumers."""
        deps = []

        async with self._get_client() as zk:
            # 1. Check service metadata for explicit dependencies
            deps.extend(self._get_metadata_deps(zk, service))

            # 2. Check Kafka consumer groups
            deps.extend(self._get_kafka_deps(zk, service))

        return deps

    def _get_metadata_deps(
        self,
        zk: KazooClient,
        service: str
    ) -> list[DiscoveredDependency]:
        """Get dependencies declared in service metadata znode."""
        deps = []
        metadata_path = f"{self.service_path}/{service}/metadata"

        try:
            data, stat = zk.get(metadata_path)
            if data:
                metadata = json.loads(data.decode())

                # Check common dependency fields
                for key in ["dependencies", "requires", "upstreams", "depends_on"]:
                    if key in metadata:
                        dep_list = metadata[key]
                        if isinstance(dep_list, str):
                            dep_list = [d.strip() for d in dep_list.split(",")]

                        for dep_name in dep_list:
                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=dep_name,
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.8,
                                metadata={"source": "metadata_znode"},
                                raw_source=service,
                                raw_target=dep_name,
                            ))
        except NoNodeError:
            pass
        except json.JSONDecodeError:
            pass

        return deps

    def _get_kafka_deps(
        self,
        zk: KazooClient,
        service: str
    ) -> list[DiscoveredDependency]:
        """
        Discover Kafka topic dependencies from consumer groups.

        Looks for consumer groups matching the service name pattern.
        """
        deps = []

        try:
            if not zk.exists(self.kafka_consumers_path):
                return deps

            groups = zk.get_children(self.kafka_consumers_path)

            for group in groups:
                # Match groups that contain the service name
                # Common patterns: "payment-api", "payment-api-consumer", "payment-api-group"
                service_lower = service.lower()
                group_lower = group.lower()

                if service_lower in group_lower or group_lower in service_lower:
                    # Get topics this group consumes
                    offsets_path = f"{self.kafka_consumers_path}/{group}/offsets"

                    if zk.exists(offsets_path):
                        topics = zk.get_children(offsets_path)

                        for topic in topics:
                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=f"kafka:{topic}",
                                provider=self.name,
                                dep_type=DependencyType.QUEUE,
                                confidence=0.75,
                                metadata={
                                    "consumer_group": group,
                                    "kafka_topic": topic,
                                },
                                raw_source=service,
                                raw_target=topic,
                            ))
        except NoNodeError:
            pass

        return deps

    async def list_services(self) -> list[str]:
        """List all services registered in ZooKeeper."""
        async with self._get_client() as zk:
            try:
                if zk.exists(self.service_path):
                    return zk.get_children(self.service_path)
            except NoNodeError:
                pass

        return []

    async def health_check(self) -> ProviderHealth:
        """Check ZooKeeper connectivity."""
        start = time.time()

        try:
            async with self._get_client() as zk:
                # Simple existence check
                zk.exists("/")
                latency = (time.time() - start) * 1000

                return ProviderHealth(
                    healthy=True,
                    message="Connected to ZooKeeper",
                    latency_ms=latency,
                )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"ZooKeeper connection failed: {str(e)}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from ZooKeeper metadata."""
        async with self._get_client() as zk:
            metadata_path = f"{self.service_path}/{service}/metadata"

            try:
                data, _ = zk.get(metadata_path)
                if data:
                    metadata = json.loads(data.decode())
                    return {
                        "owner": metadata.get("owner"),
                        "team": metadata.get("team"),
                        "repo": metadata.get("repo"),
                        "version": metadata.get("version"),
                    }
            except (NoNodeError, json.JSONDecodeError):
                pass

        return {}
```

### Netflix Eureka

```python
# src/nthlayer/dependencies/providers/eureka.py

"""
Netflix Eureka dependency provider.

Uses py-eureka-client SDK: https://github.com/keijack/py-eureka-client

Discovers:
- All registered applications
- Instance metadata containing dependency hints
- Service health status
"""

from dataclasses import dataclass
import time

import py_eureka_client.eureka_client as eureka

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class EurekaDepProvider(BaseDepProvider):
    """
    Discover dependencies from Netflix Eureka.

    Configuration:
        eureka_url: Eureka server URL (e.g., http://eureka:8761/eureka)

    Environment variables:
        EUREKA_SERVER_URL: Server URL

    Note: Eureka doesn't natively track dependencies. This provider:
    1. Lists all registered services
    2. Extracts dependencies from instance metadata
    3. Uses common metadata conventions (dependencies, requires, etc.)
    """

    eureka_url: str = "http://localhost:8761/eureka"

    _client: eureka.EurekaClient | None = None

    @property
    def name(self) -> str:
        return "eureka"

    def _get_client(self) -> eureka.EurekaClient:
        """Get Eureka client (creates on first use)."""
        if self._client is None:
            self._client = eureka.EurekaClient(
                eureka_server=self.eureka_url,
                app_name="nthlayer-discovery",  # Required but we don't register
            )
        return self._client

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Eureka instance metadata."""
        deps = []
        client = self._get_client()

        # Eureka uses uppercase app names
        app_name = service.upper()

        try:
            # Get application instances
            app = client.get_application(app_name)

            if not app:
                return deps

            # Check each instance for dependency metadata
            for instance in app.instances:
                metadata = instance.metadata or {}

                # Check common metadata fields
                for key in ["dependencies", "requires", "upstreams"]:
                    if key in metadata:
                        dep_str = metadata[key]
                        dep_list = [d.strip() for d in dep_str.split(",")]

                        for dep_name in dep_list:
                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=dep_name.lower(),  # Normalize
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.75,
                                metadata={
                                    "source": "instance_metadata",
                                    "instance_id": instance.instance_id,
                                },
                                raw_source=app_name,
                                raw_target=dep_name,
                            ))

                # Only need deps from one instance
                break

        except Exception:
            pass

        return deps

    async def list_services(self) -> list[str]:
        """List all applications registered in Eureka."""
        client = self._get_client()

        try:
            apps = client.get_applications()

            if apps and apps.applications:
                # Return lowercase normalized names
                return [app.name.lower() for app in apps.applications]
        except Exception:
            pass

        return []

    async def health_check(self) -> ProviderHealth:
        """Check Eureka connectivity."""
        client = self._get_client()

        start = time.time()
        try:
            apps = client.get_applications()
            latency = (time.time() - start) * 1000

            app_count = len(apps.applications) if apps and apps.applications else 0

            return ProviderHealth(
                healthy=True,
                message=f"Connected to Eureka, {app_count} applications",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Eureka connection failed: {str(e)}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Eureka metadata."""
        client = self._get_client()
        app_name = service.upper()

        try:
            app = client.get_application(app_name)

            if app and app.instances:
                instance = app.instances[0]
                metadata = instance.metadata or {}

                return {
                    "eureka_app_name": app.name,
                    "eureka_instance_id": instance.instance_id,
                    "owner": metadata.get("owner"),
                    "team": metadata.get("team"),
                    "repo": metadata.get("repo"),
                    "version": metadata.get("version"),
                }
        except Exception:
            pass

        return {}
```

### etcd

```python
# src/nthlayer/dependencies/providers/etcd.py

"""
etcd v3 dependency provider.

Uses etcd3 SDK: https://github.com/kragniz/python-etcd3

Discovers:
- Service registrations under configurable prefix
- Kubernetes service data (if etcd is K8s backing store)
"""

from dataclasses import dataclass
import json
import time

import etcd3

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class EtcdDepProvider(BaseDepProvider):
    """
    Discover dependencies from etcd v3.

    Configuration:
        host: etcd host (default: localhost)
        port: etcd port (default: 2379)
        ca_cert: CA certificate path for TLS (optional)
        cert_key: Client key path for mTLS (optional)
        cert_cert: Client cert path for mTLS (optional)
        service_prefix: Key prefix for services (default: /services/)

    Environment variables:
        ETCD_HOST: Host
        ETCD_PORT: Port
        ETCD_CA_CERT: CA cert path
    """

    host: str = "localhost"
    port: int = 2379
    ca_cert: str | None = None
    cert_key: str | None = None
    cert_cert: str | None = None
    service_prefix: str = "/services/"

    _client: etcd3.Etcd3Client | None = None

    @property
    def name(self) -> str:
        return "etcd"

    def _get_client(self) -> etcd3.Etcd3Client:
        """Get or create etcd client."""
        if self._client is None:
            self._client = etcd3.client(
                host=self.host,
                port=self.port,
                ca_cert=self.ca_cert,
                cert_key=self.cert_key,
                cert_cert=self.cert_cert,
            )
        return self._client

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from etcd service data."""
        deps = []
        client = self._get_client()

        # Get service key
        service_key = f"{self.service_prefix}{service}"

        try:
            value, metadata = client.get(service_key)

            if value:
                data = json.loads(value.decode())

                # Check for dependencies in service data
                for key in ["dependencies", "requires", "upstreams"]:
                    if key in data:
                        dep_list = data[key]
                        if isinstance(dep_list, str):
                            dep_list = [d.strip() for d in dep_list.split(",")]

                        for dep in dep_list:
                            dep_name = dep if isinstance(dep, str) else dep.get("name")

                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=dep_name,
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.8,
                                metadata={"source": "etcd_key"},
                                raw_source=service,
                                raw_target=dep_name,
                            ))
        except Exception:
            pass

        return deps

    async def list_services(self) -> list[str]:
        """List all services with keys under service prefix."""
        client = self._get_client()
        services = []

        try:
            # Get all keys with prefix
            for value, metadata in client.get_prefix(self.service_prefix):
                key = metadata.key.decode()
                # Extract service name from key
                service_name = key.replace(self.service_prefix, "").split("/")[0]
                if service_name and service_name not in services:
                    services.append(service_name)
        except Exception:
            pass

        return services

    async def health_check(self) -> ProviderHealth:
        """Check etcd connectivity."""
        client = self._get_client()

        start = time.time()
        try:
            # Simple status check
            status = client.status()
            latency = (time.time() - start) * 1000

            return ProviderHealth(
                healthy=True,
                message=f"Connected to etcd, leader: {status.leader}",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"etcd connection failed: {str(e)}",
            )
```

### Cortex.io Developer Portal

```python
# src/nthlayer/dependencies/providers/cortex_portal.py

"""
Cortex.io developer portal dependency provider.

Uses Cortex.io REST API: https://api.cortex.io/docs

Cortex.io is a developer portal (similar to Backstage) that tracks:
- Service catalog with ownership
- Dependencies between services
- Scorecards for production readiness
- Integration data (PagerDuty, GitHub, etc.)
"""

from dataclasses import dataclass
import time

import httpx

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class CortexPortalDepProvider(BaseDepProvider):
    """
    Discover dependencies from Cortex.io developer portal.

    Configuration:
        api_key: Cortex.io API key (required)
        base_url: API base URL (default: https://api.cortex.io)

    Environment variables:
        CORTEX_API_KEY: API key
    """

    api_key: str = ""
    base_url: str = "https://api.cortex.io"

    @property
    def name(self) -> str:
        return "cortex.io"

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Cortex.io catalog."""
        deps = []

        async with httpx.AsyncClient() as client:
            # Get service with dependencies
            response = await client.get(
                f"{self.base_url}/api/v1/catalog/{service}",
                headers=self._headers,
            )

            if response.status_code == 404:
                # Try searching by name
                service_data = await self._search_service(client, service)
            elif response.status_code == 200:
                service_data = response.json()
            else:
                return deps

            if not service_data:
                return deps

            # Extract dependencies
            for dep in service_data.get("dependencies", []):
                dep_type = self._map_dependency_type(dep.get("type"))

                deps.append(DiscoveredDependency(
                    source_service=service,
                    target_service=dep["tag"],
                    provider=self.name,
                    dep_type=dep_type,
                    confidence=0.9,  # High - explicit declaration
                    metadata={
                        "cortex_id": dep.get("id"),
                        "description": dep.get("description"),
                        "method": dep.get("method"),
                    },
                    raw_source=service_data.get("tag", service),
                    raw_target=dep["tag"],
                ))

            # Get reverse dependencies (dependents)
            dependents_response = await client.get(
                f"{self.base_url}/api/v1/catalog/{service_data.get('tag', service)}/dependents",
                headers=self._headers,
            )

            if dependents_response.status_code == 200:
                for dep in dependents_response.json().get("dependents", []):
                    deps.append(DiscoveredDependency(
                        source_service=dep["tag"],
                        target_service=service,
                        provider=self.name,
                        dep_type=DependencyType.SERVICE,
                        confidence=0.9,
                        metadata={"direction": "inbound"},
                        raw_source=dep["tag"],
                        raw_target=service_data.get("tag", service),
                    ))

        return deps

    async def _search_service(
        self,
        client: httpx.AsyncClient,
        query: str
    ) -> dict | None:
        """Search for service by name."""
        response = await client.get(
            f"{self.base_url}/api/v1/catalog",
            params={"search": query, "pageSize": 5},
            headers=self._headers,
        )

        if response.status_code == 200:
            entities = response.json().get("entities", [])
            if entities:
                return entities[0]
        return None

    def _map_dependency_type(self, cortex_type: str | None) -> DependencyType:
        """Map Cortex.io dependency type to internal type."""
        mapping = {
            "service": DependencyType.SERVICE,
            "database": DependencyType.DATASTORE,
            "queue": DependencyType.QUEUE,
            "cache": DependencyType.DATASTORE,
            "api": DependencyType.EXTERNAL,
            "external": DependencyType.EXTERNAL,
        }
        return mapping.get(cortex_type or "", DependencyType.SERVICE)

    async def list_services(self) -> list[str]:
        """List all services in Cortex.io catalog."""
        services = []
        next_cursor = None

        async with httpx.AsyncClient() as client:
            while True:
                params = {"pageSize": 100}
                if next_cursor:
                    params["nextCursor"] = next_cursor

                response = await client.get(
                    f"{self.base_url}/api/v1/catalog",
                    params=params,
                    headers=self._headers,
                )

                if response.status_code != 200:
                    break

                data = response.json()

                for entity in data.get("entities", []):
                    services.append(entity["tag"])

                next_cursor = data.get("nextCursor")
                if not next_cursor:
                    break

        return services

    async def health_check(self) -> ProviderHealth:
        """Check Cortex.io API connectivity."""
        start = time.time()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/catalog",
                    params={"pageSize": 1},
                    headers=self._headers,
                )

                latency = (time.time() - start) * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        healthy=True,
                        message="Connected to Cortex.io",
                        latency_ms=latency,
                    )
                elif response.status_code == 401:
                    return ProviderHealth(
                        healthy=False,
                        message="Cortex.io authentication failed",
                        latency_ms=latency,
                    )
                else:
                    return ProviderHealth(
                        healthy=False,
                        message=f"Cortex.io returned {response.status_code}",
                        latency_ms=latency,
                    )
            except Exception as e:
                return ProviderHealth(
                    healthy=False,
                    message=f"Cortex.io connection failed: {str(e)}",
                )

    async def get_service_attributes(self, service: str) -> dict:
        """Get rich service attributes from Cortex.io."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/catalog/{service}",
                headers=self._headers,
            )

            if response.status_code != 200:
                return {}

            data = response.json()

            # Extract attributes for identity correlation
            return {
                "cortex_tag": data.get("tag"),
                "cortex_id": data.get("id"),
                "name": data.get("name"),
                "description": data.get("description"),
                "owner": data.get("owner", {}).get("email"),
                "team": data.get("owner", {}).get("name"),
                "repo": data.get("git", {}).get("repository"),
                "slack_channel": data.get("slack", {}).get("channel"),
                "pagerduty_service": data.get("pagerduty", {}).get("serviceId"),
                "tier": self._infer_tier(data),
            }

    def _infer_tier(self, data: dict) -> str | None:
        """Infer service tier from Cortex scorecards."""
        for scorecard in data.get("scorecards", []):
            if scorecard.get("tag") in ["reliability", "production-readiness", "tier"]:
                level = scorecard.get("level", {}).get("name", "").lower()
                if level in ["gold", "platinum", "level-3", "level-4", "critical"]:
                    return "critical"
                elif level in ["silver", "level-2", "standard"]:
                    return "standard"
                elif level in ["bronze", "level-1", "low"]:
                    return "low"
        return None
```

### Backstage

```python
# src/nthlayer/dependencies/providers/backstage.py

"""
Backstage developer portal dependency provider.

Uses Backstage Catalog REST API: https://backstage.io/docs/features/software-catalog/software-catalog-api

Discovers:
- Entities from software catalog
- dependsOn/dependencyOf relations
- Rich metadata for identity correlation
"""

from dataclasses import dataclass
import time

import httpx

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class BackstageDepProvider(BaseDepProvider):
    """
    Discover dependencies from Backstage software catalog.

    Configuration:
        base_url: Backstage backend URL (e.g., http://backstage:7007)
        auth_token: Bearer token for authentication (optional)

    Environment variables:
        BACKSTAGE_URL: Backend URL
        BACKSTAGE_AUTH_TOKEN: Auth token
    """

    base_url: str = "http://localhost:7007"
    auth_token: str | None = None

    @property
    def name(self) -> str:
        return "backstage"

    @property
    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Backstage catalog relations."""
        deps = []

        async with httpx.AsyncClient() as client:
            # Get entity by name (try component kind first)
            entity = await self._get_entity(client, "component", service)

            if not entity:
                # Try other kinds
                for kind in ["service", "api", "resource"]:
                    entity = await self._get_entity(client, kind, service)
                    if entity:
                        break

            if not entity:
                return deps

            # Extract dependencies from relations
            for relation in entity.get("relations", []):
                rel_type = relation.get("type", "")
                target_ref = relation.get("targetRef", "")

                if rel_type == "dependsOn":
                    # This service depends on target
                    target_name = self._parse_entity_ref(target_ref)
                    dep_type = self._infer_type_from_ref(target_ref)

                    deps.append(DiscoveredDependency(
                        source_service=service,
                        target_service=target_name,
                        provider=self.name,
                        dep_type=dep_type,
                        confidence=0.9,
                        metadata={
                            "backstage_ref": target_ref,
                            "relation_type": rel_type,
                        },
                        raw_source=self._get_entity_ref(entity),
                        raw_target=target_ref,
                    ))

                elif rel_type == "dependencyOf":
                    # Target depends on this service
                    source_name = self._parse_entity_ref(target_ref)

                    deps.append(DiscoveredDependency(
                        source_service=source_name,
                        target_service=service,
                        provider=self.name,
                        dep_type=DependencyType.SERVICE,
                        confidence=0.9,
                        metadata={
                            "backstage_ref": target_ref,
                            "relation_type": rel_type,
                            "direction": "inbound",
                        },
                        raw_source=target_ref,
                        raw_target=self._get_entity_ref(entity),
                    ))

        return deps

    async def _get_entity(
        self,
        client: httpx.AsyncClient,
        kind: str,
        name: str,
        namespace: str = "default"
    ) -> dict | None:
        """Get entity by kind, namespace, and name."""
        response = await client.get(
            f"{self.base_url}/api/catalog/entities/by-name/{kind}/{namespace}/{name}",
            headers=self._headers,
        )

        if response.status_code == 200:
            return response.json()
        return None

    def _parse_entity_ref(self, ref: str) -> str:
        """
        Parse entity reference to extract name.

        Format: [<kind>:][<namespace>/]<name>
        Examples:
            component:default/payment-api → payment-api
            payment-api → payment-api
            resource:default/postgresql → postgresql
        """
        # Remove kind prefix
        if ":" in ref:
            ref = ref.split(":", 1)[1]

        # Remove namespace prefix
        if "/" in ref:
            ref = ref.split("/", 1)[1]

        return ref

    def _get_entity_ref(self, entity: dict) -> str:
        """Get full entity reference."""
        kind = entity.get("kind", "component").lower()
        namespace = entity.get("metadata", {}).get("namespace", "default")
        name = entity.get("metadata", {}).get("name", "")
        return f"{kind}:{namespace}/{name}"

    def _infer_type_from_ref(self, ref: str) -> DependencyType:
        """Infer dependency type from entity reference."""
        if ref.startswith("resource:"):
            name_lower = ref.lower()
            if any(db in name_lower for db in ["postgres", "mysql", "mongo", "redis", "cache"]):
                return DependencyType.DATASTORE
            elif any(q in name_lower for q in ["kafka", "rabbitmq", "sqs", "queue"]):
                return DependencyType.QUEUE
        elif ref.startswith("api:"):
            return DependencyType.EXTERNAL

        return DependencyType.SERVICE

    async def list_services(self) -> list[str]:
        """List all component entities from Backstage."""
        services = []

        async with httpx.AsyncClient() as client:
            # Query for component entities
            response = await client.get(
                f"{self.base_url}/api/catalog/entities",
                params={"filter": "kind=component"},
                headers=self._headers,
            )

            if response.status_code == 200:
                for entity in response.json():
                    name = entity.get("metadata", {}).get("name")
                    if name:
                        services.append(name)

        return services

    async def health_check(self) -> ProviderHealth:
        """Check Backstage connectivity."""
        start = time.time()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/catalog/entities",
                    params={"filter": "kind=component", "limit": 1},
                    headers=self._headers,
                )

                latency = (time.time() - start) * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        healthy=True,
                        message="Connected to Backstage",
                        latency_ms=latency,
                    )
                else:
                    return ProviderHealth(
                        healthy=False,
                        message=f"Backstage returned {response.status_code}",
                        latency_ms=latency,
                    )
            except Exception as e:
                return ProviderHealth(
                    healthy=False,
                    message=f"Backstage connection failed: {str(e)}",
                )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Backstage entity."""
        async with httpx.AsyncClient() as client:
            entity = await self._get_entity(client, "component", service)

            if not entity:
                return {}

            metadata = entity.get("metadata", {})
            spec = entity.get("spec", {})
            annotations = metadata.get("annotations", {})

            return {
                "backstage_ref": self._get_entity_ref(entity),
                "name": metadata.get("name"),
                "description": metadata.get("description"),
                "owner": spec.get("owner"),
                "team": spec.get("owner"),
                "repo": annotations.get("github.com/project-slug"),
                "pagerduty_service": annotations.get("pagerduty.com/service-id"),
                "tier": spec.get("tier") or self._infer_tier_from_lifecycle(spec),
            }

    def _infer_tier_from_lifecycle(self, spec: dict) -> str | None:
        """Infer tier from lifecycle."""
        lifecycle = spec.get("lifecycle", "").lower()
        if lifecycle == "production":
            return "standard"
        elif lifecycle == "experimental":
            return "low"
        return None
```

### Prometheus

```python
# src/nthlayer/dependencies/providers/prometheus.py

"""
Prometheus metrics dependency provider.

Uses prometheus-api-client: https://github.com/4n4nd/prometheus-api-client-python

Discovers dependencies by querying inter-service call metrics:
- Istio/Envoy metrics
- OpenTelemetry HTTP client metrics
- Generic service-to-service metrics
"""

from dataclasses import dataclass
import time

from prometheus_api_client import PrometheusConnect

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class PrometheusDepProvider(BaseDepProvider):
    """
    Discover dependencies from Prometheus service metrics.

    Configuration:
        url: Prometheus URL
        auth: Tuple of (username, password) for basic auth (optional)
        headers: Additional headers (e.g., for bearer token auth)
        disable_ssl: Disable SSL verification

    Environment variables:
        PROMETHEUS_URL: Server URL
        PROMETHEUS_USER: Basic auth username
        PROMETHEUS_PASSWORD: Basic auth password

    Discovery queries (customizable):
        - Istio request metrics
        - OpenTelemetry HTTP client metrics
        - Generic http_client_* metrics
    """

    url: str = "http://localhost:9090"
    auth: tuple[str, str] | None = None
    headers: dict | None = None
    disable_ssl: bool = False

    # Customizable discovery queries
    # Format: (query_template, source_label, target_label, min_rate)
    discovery_queries: list[tuple[str, str, str, float]] = None

    _client: PrometheusConnect | None = None

    def __post_init__(self):
        if self.discovery_queries is None:
            self.discovery_queries = [
                # Istio/Envoy service mesh
                (
                    'sum by (source_workload, destination_workload) '
                    '(rate(istio_requests_total[1h]))',
                    'source_workload',
                    'destination_workload',
                    0.01,  # Min 0.01 req/sec
                ),
                # OpenTelemetry semantic conventions
                (
                    'sum by (service_name, peer_service) '
                    '(rate(http_client_duration_seconds_count[1h]))',
                    'service_name',
                    'peer_service',
                    0.01,
                ),
                # Generic HTTP client metrics
                (
                    'sum by (service, target_service) '
                    '(rate(http_client_requests_total[1h]))',
                    'service',
                    'target_service',
                    0.01,
                ),
                # gRPC client metrics
                (
                    'sum by (grpc_service, grpc_target) '
                    '(rate(grpc_client_handled_total[1h]))',
                    'grpc_service',
                    'grpc_target',
                    0.01,
                ),
            ]

    @property
    def name(self) -> str:
        return "prometheus"

    def _get_client(self) -> PrometheusConnect:
        """Get or create Prometheus client."""
        if self._client is None:
            self._client = PrometheusConnect(
                url=self.url,
                headers=self.headers or {},
                disable_ssl=self.disable_ssl,
            )

            # Add basic auth if provided
            if self.auth:
                self._client._session.auth = self.auth

        return self._client

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Prometheus metrics."""
        deps = []
        client = self._get_client()

        for query_template, source_label, target_label, min_rate in self.discovery_queries:
            try:
                result = client.custom_query(query=query_template)

                for item in result:
                    metric = item.get("metric", {})
                    value = float(item.get("value", [0, 0])[1])

                    source = metric.get(source_label, "")
                    target = metric.get(target_label, "")

                    if not source or not target:
                        continue

                    # Check if this service is involved
                    service_lower = service.lower()
                    source_lower = source.lower()
                    target_lower = target.lower()

                    # Service is source (outbound dependency)
                    if service_lower in source_lower or source_lower in service_lower:
                        # Confidence based on request rate
                        confidence = min(0.9, 0.5 + (value / 10))  # Higher rate = higher confidence

                        deps.append(DiscoveredDependency(
                            source_service=source,
                            target_service=target,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=confidence if value >= min_rate else 0.4,
                            metadata={
                                "query": query_template[:50],
                                "rate_per_sec": value,
                            },
                            raw_source=source,
                            raw_target=target,
                        ))

                    # Service is target (inbound dependency)
                    if service_lower in target_lower or target_lower in service_lower:
                        confidence = min(0.9, 0.5 + (value / 10))

                        deps.append(DiscoveredDependency(
                            source_service=source,
                            target_service=target,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=confidence if value >= min_rate else 0.4,
                            metadata={
                                "direction": "inbound",
                                "rate_per_sec": value,
                            },
                            raw_source=source,
                            raw_target=target,
                        ))

            except Exception:
                # Query may not exist in this Prometheus
                continue

        return deps

    async def list_services(self) -> list[str]:
        """List all services from common label values."""
        client = self._get_client()
        services = set()

        # Try common service label names
        for label in ["service", "service_name", "app", "job"]:
            try:
                values = client.get_label_values(label)
                services.update(values)
            except Exception:
                continue

        return list(services)

    async def health_check(self) -> ProviderHealth:
        """Check Prometheus connectivity."""
        client = self._get_client()

        start = time.time()
        try:
            # Simple query to verify connectivity
            result = client.custom_query(query="up")
            latency = (time.time() - start) * 1000

            return ProviderHealth(
                healthy=True,
                message=f"Connected to Prometheus, {len(result)} targets",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Prometheus connection failed: {str(e)}",
            )
```

### Kubernetes

```python
# src/nthlayer/dependencies/providers/kubernetes.py

"""
Kubernetes dependency provider.

Uses official kubernetes-client: https://github.com/kubernetes-client/python

Discovers:
- Services and their selectors
- NetworkPolicies (allowed egress)
- Istio VirtualServices and DestinationRules
- Service mesh configurations
"""

from dataclasses import dataclass
import time

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class KubernetesDepProvider(BaseDepProvider):
    """
    Discover dependencies from Kubernetes API.

    Configuration:
        kubeconfig: Path to kubeconfig file (optional, uses default if not set)
        context: Kubernetes context to use (optional)
        namespace: Namespace to scan (None = all namespaces)
        include_istio: Include Istio CRDs in discovery

    Environment variables:
        KUBECONFIG: Path to kubeconfig
        KUBERNETES_CONTEXT: Context name
    """

    kubeconfig: str | None = None
    context: str | None = None
    namespace: str | None = None
    include_istio: bool = True

    _core_api: client.CoreV1Api | None = None
    _networking_api: client.NetworkingV1Api | None = None
    _custom_api: client.CustomObjectsApi | None = None

    @property
    def name(self) -> str:
        return "kubernetes"

    def _load_config(self):
        """Load Kubernetes configuration."""
        try:
            if self.kubeconfig:
                config.load_kube_config(
                    config_file=self.kubeconfig,
                    context=self.context,
                )
            else:
                # Try in-cluster config first, fall back to kubeconfig
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config(context=self.context)
        except Exception as e:
            raise RuntimeError(f"Failed to load Kubernetes config: {e}")

    def _get_core_api(self) -> client.CoreV1Api:
        if self._core_api is None:
            self._load_config()
            self._core_api = client.CoreV1Api()
        return self._core_api

    def _get_networking_api(self) -> client.NetworkingV1Api:
        if self._networking_api is None:
            self._load_config()
            self._networking_api = client.NetworkingV1Api()
        return self._networking_api

    def _get_custom_api(self) -> client.CustomObjectsApi:
        if self._custom_api is None:
            self._load_config()
            self._custom_api = client.CustomObjectsApi()
        return self._custom_api

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Kubernetes resources."""
        deps = []

        # 1. Get NetworkPolicy egress rules
        deps.extend(await self._discover_from_network_policies(service))

        # 2. Get Istio configurations
        if self.include_istio:
            deps.extend(await self._discover_from_istio(service))

        return deps

    async def _discover_from_network_policies(
        self,
        service: str
    ) -> list[DiscoveredDependency]:
        """Extract dependencies from NetworkPolicy egress rules."""
        deps = []
        api = self._get_networking_api()

        try:
            if self.namespace:
                policies = api.list_namespaced_network_policy(self.namespace)
            else:
                policies = api.list_network_policy_for_all_namespaces()

            for policy in policies.items:
                # Check if policy applies to our service
                pod_selector = policy.spec.pod_selector.match_labels or {}

                # Simple check - service name in labels
                applies = any(
                    service.lower() in str(v).lower()
                    for v in pod_selector.values()
                )

                if not applies:
                    continue

                # Extract egress targets
                for egress in policy.spec.egress or []:
                    for to in egress.to or []:
                        if to.pod_selector and to.pod_selector.match_labels:
                            for label_val in to.pod_selector.match_labels.values():
                                deps.append(DiscoveredDependency(
                                    source_service=service,
                                    target_service=label_val,
                                    provider=self.name,
                                    dep_type=DependencyType.SERVICE,
                                    confidence=0.85,
                                    metadata={
                                        "source": "network_policy",
                                        "policy_name": policy.metadata.name,
                                    },
                                    raw_source=service,
                                    raw_target=label_val,
                                ))

        except ApiException:
            pass

        return deps

    async def _discover_from_istio(
        self,
        service: str
    ) -> list[DiscoveredDependency]:
        """Extract dependencies from Istio VirtualServices."""
        deps = []
        api = self._get_custom_api()

        try:
            if self.namespace:
                vs_list = api.list_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=self.namespace,
                    plural="virtualservices",
                )
            else:
                vs_list = api.list_cluster_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    plural="virtualservices",
                )

            for vs in vs_list.get("items", []):
                # Check if VS applies to this service
                hosts = vs.get("spec", {}).get("hosts", [])

                if not any(service.lower() in h.lower() for h in hosts):
                    continue

                # Extract route destinations
                for http in vs.get("spec", {}).get("http", []):
                    for route in http.get("route", []):
                        dest = route.get("destination", {})
                        dest_host = dest.get("host", "")

                        if dest_host and dest_host != service:
                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=dest_host,
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.9,
                                metadata={
                                    "source": "istio_virtualservice",
                                    "vs_name": vs.get("metadata", {}).get("name"),
                                },
                                raw_source=service,
                                raw_target=dest_host,
                            ))

        except ApiException:
            # Istio CRDs may not be installed
            pass

        return deps

    async def list_services(self) -> list[str]:
        """List all Kubernetes Services."""
        api = self._get_core_api()
        services = []

        try:
            if self.namespace:
                svc_list = api.list_namespaced_service(self.namespace)
            else:
                svc_list = api.list_service_for_all_namespaces()

            for svc in svc_list.items:
                name = svc.metadata.name
                ns = svc.metadata.namespace

                # Skip kube-system services
                if ns == "kube-system":
                    continue

                services.append(f"{ns}/{name}" if not self.namespace else name)

        except ApiException:
            pass

        return services

    async def health_check(self) -> ProviderHealth:
        """Check Kubernetes connectivity."""
        api = self._get_core_api()

        start = time.time()
        try:
            api.get_api_versions()
            latency = (time.time() - start) * 1000

            return ProviderHealth(
                healthy=True,
                message="Connected to Kubernetes",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Kubernetes connection failed: {str(e)}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Kubernetes labels/annotations."""
        api = self._get_core_api()

        # Parse namespace/name if present
        if "/" in service:
            namespace, name = service.split("/", 1)
        else:
            namespace = self.namespace or "default"
            name = service

        try:
            svc = api.read_namespaced_service(name, namespace)

            labels = svc.metadata.labels or {}
            annotations = svc.metadata.annotations or {}

            return {
                "kubernetes_name": name,
                "kubernetes_namespace": namespace,
                "owner": labels.get("owner") or annotations.get("owner"),
                "team": labels.get("team") or annotations.get("team"),
                "repo": annotations.get("repo") or annotations.get("github.com/repository"),
                "version": labels.get("version") or labels.get("app.kubernetes.io/version"),
            }

        except ApiException:
            return {}
```

### AWS Cloud Map

```python
# src/nthlayer/dependencies/providers/cloudmap.py

"""
AWS Cloud Map dependency provider.

Uses boto3 SDK: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/servicediscovery.html

Discovers:
- Services registered in Cloud Map namespaces
- Instance attributes containing dependency hints
- Service tags
"""

from dataclasses import dataclass
import time

import boto3
from botocore.exceptions import ClientError

from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth
from nthlayer.dependencies.models import DiscoveredDependency, DependencyType


@dataclass
class CloudMapDepProvider(BaseDepProvider):
    """
    Discover dependencies from AWS Cloud Map.

    Configuration:
        namespace_id: Cloud Map namespace ID (ns-xxxxxxxxx)
        region: AWS region
        profile: AWS profile name (optional)

    Environment variables:
        AWS_REGION: Region
        AWS_PROFILE: Profile
        CLOUDMAP_NAMESPACE_ID: Namespace ID

    Dependency convention:
        - Service tag "dependencies" = "svc1,svc2,svc3"
        - Instance attribute "dependencies" = "svc1,svc2"
    """

    namespace_id: str = ""
    region: str = "us-east-1"
    profile: str | None = None

    _client = None

    @property
    def name(self) -> str:
        return "aws_cloudmap"

    def _get_client(self):
        """Get or create Cloud Map client."""
        if self._client is None:
            session = boto3.Session(
                region_name=self.region,
                profile_name=self.profile,
            )
            self._client = session.client("servicediscovery")
        return self._client

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Cloud Map service tags and attributes."""
        deps = []
        client = self._get_client()

        # Find service by name
        service_data = await self._find_service(service)

        if not service_data:
            return deps

        service_id = service_data["Id"]

        # 1. Check service tags for dependencies
        try:
            tags_response = client.list_tags_for_resource(
                ResourceARN=service_data["Arn"]
            )

            tags = {t["Key"]: t["Value"] for t in tags_response.get("Tags", [])}

            if "dependencies" in tags:
                for dep in tags["dependencies"].split(","):
                    dep = dep.strip()
                    if dep:
                        deps.append(DiscoveredDependency(
                            source_service=service,
                            target_service=dep,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.85,
                            metadata={"source": "service_tag"},
                            raw_source=service,
                            raw_target=dep,
                        ))

        except ClientError:
            pass

        # 2. Check instance attributes
        try:
            instances_response = client.list_instances(ServiceId=service_id)

            for instance in instances_response.get("Instances", []):
                attrs = instance.get("Attributes", {})

                if "dependencies" in attrs:
                    for dep in attrs["dependencies"].split(","):
                        dep = dep.strip()
                        if dep:
                            deps.append(DiscoveredDependency(
                                source_service=service,
                                target_service=dep,
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.8,
                                metadata={
                                    "source": "instance_attribute",
                                    "instance_id": instance["Id"],
                                },
                                raw_source=service,
                                raw_target=dep,
                            ))

                # Only need one instance's attrs
                break

        except ClientError:
            pass

        return deps

    async def _find_service(self, service_name: str) -> dict | None:
        """Find service by name in namespace."""
        client = self._get_client()

        try:
            paginator = client.get_paginator("list_services")

            for page in paginator.paginate(
                Filters=[
                    {"Name": "NAMESPACE_ID", "Values": [self.namespace_id]},
                ]
            ):
                for svc in page.get("Services", []):
                    if svc["Name"] == service_name:
                        return svc

        except ClientError:
            pass

        return None

    async def list_services(self) -> list[str]:
        """List all services in Cloud Map namespace."""
        client = self._get_client()
        services = []

        try:
            paginator = client.get_paginator("list_services")

            for page in paginator.paginate(
                Filters=[
                    {"Name": "NAMESPACE_ID", "Values": [self.namespace_id]},
                ]
            ):
                for svc in page.get("Services", []):
                    services.append(svc["Name"])

        except ClientError:
            pass

        return services

    async def health_check(self) -> ProviderHealth:
        """Check Cloud Map connectivity."""
        client = self._get_client()

        start = time.time()
        try:
            client.get_namespace(Id=self.namespace_id)
            latency = (time.time() - start) * 1000

            return ProviderHealth(
                healthy=True,
                message="Connected to AWS Cloud Map",
                latency_ms=latency,
            )
        except ClientError as e:
            return ProviderHealth(
                healthy=False,
                message=f"Cloud Map error: {e.response['Error']['Message']}",
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Cloud Map connection failed: {str(e)}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Cloud Map tags."""
        client = self._get_client()
        service_data = await self._find_service(service)

        if not service_data:
            return {}

        try:
            tags_response = client.list_tags_for_resource(
                ResourceARN=service_data["Arn"]
            )

            tags = {t["Key"]: t["Value"] for t in tags_response.get("Tags", [])}

            return {
                "cloudmap_service_id": service_data["Id"],
                "cloudmap_arn": service_data["Arn"],
                "owner": tags.get("owner"),
                "team": tags.get("team"),
                "repo": tags.get("repo"),
            }

        except ClientError:
            return {}
```

---

## Ownership Providers

Ownership providers discover who owns a service from various sources. These integrate with the dependency discovery to provide complete service context.

### PagerDuty Ownership

```python
# src/nthlayer/identity/ownership_providers/pagerduty.py

"""
PagerDuty ownership provider.

Uses pdpyras SDK: https://github.com/PagerDuty/pdpyras

Ownership chain: Service → Escalation Policy → Schedule → Team
"""

from dataclasses import dataclass

import pdpyras

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class PagerDutyOwnershipProvider:
    """
    Discover ownership from PagerDuty.

    Configuration:
        api_key: PagerDuty API key (read-only scope sufficient)

    Environment variables:
        PAGERDUTY_API_KEY: API key
    """

    api_key: str = ""

    async def get_ownership(self, service: str) -> OwnershipSignal | None:
        """
        Get ownership by tracing PagerDuty service → escalation policy → team.

        This is the highest-confidence signal: who gets paged owns the service.
        """
        session = pdpyras.APISession(self.api_key)

        try:
            # Search for service by name
            services = list(session.iter_all(
                'services',
                params={'query': service}
            ))

            for svc in services:
                # Fuzzy match on service name
                if service.lower() in svc['name'].lower():
                    # Get escalation policy
                    ep_ref = svc.get('escalation_policy', {})
                    ep_id = ep_ref.get('id')

                    if not ep_id:
                        continue

                    ep = session.rget(f'/escalation_policies/{ep_id}')

                    # Extract team from escalation rules
                    for rule in ep.get('escalation_rules', []):
                        for target in rule.get('targets', []):
                            # Check for team target
                            if target['type'] == 'team_reference':
                                return OwnershipSignal(
                                    source=OwnershipSource.PAGERDUTY,
                                    owner=target['summary'],
                                    confidence=0.95,
                                    metadata={
                                        'pagerduty_service_id': svc['id'],
                                        'pagerduty_service_name': svc['name'],
                                        'escalation_policy_id': ep_id,
                                        'escalation_policy_name': ep['name'],
                                    }
                                )

                            # Check for schedule → team
                            if target['type'] == 'schedule_reference':
                                schedule = session.rget(f"/schedules/{target['id']}")
                                teams = schedule.get('teams', [])

                                if teams:
                                    return OwnershipSignal(
                                        source=OwnershipSource.PAGERDUTY,
                                        owner=teams[0]['summary'],
                                        confidence=0.95,
                                        metadata={
                                            'pagerduty_service_id': svc['id'],
                                            'escalation_policy_name': ep['name'],
                                            'schedule_name': schedule['name'],
                                        }
                                    )

                    # Fallback: use escalation policy name as owner hint
                    return OwnershipSignal(
                        source=OwnershipSource.PAGERDUTY,
                        owner=ep['name'].replace('-escalation', '').replace('-policy', ''),
                        confidence=0.8,
                        metadata={
                            'pagerduty_service_id': svc['id'],
                            'inferred_from': 'escalation_policy_name',
                        }
                    )

        except pdpyras.PDClientError:
            pass

        return None

    async def get_escalation_policy(self, service: str) -> dict | None:
        """Get full escalation policy details for a service."""
        session = pdpyras.APISession(self.api_key)

        try:
            services = list(session.iter_all('services', params={'query': service}))

            for svc in services:
                if service.lower() in svc['name'].lower():
                    ep_id = svc.get('escalation_policy', {}).get('id')
                    if ep_id:
                        return session.rget(f'/escalation_policies/{ep_id}')
        except:
            pass

        return None
```

### OpsGenie Ownership

```python
# src/nthlayer/identity/ownership_providers/opsgenie.py

"""
OpsGenie ownership provider.

Uses opsgenie-sdk: https://github.com/opsgenie/opsgenie-python-sdk

Ownership: Service → Team mapping
"""

from dataclasses import dataclass

import opsgenie_sdk
from opsgenie_sdk.rest import ApiException

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class OpsGenieOwnershipProvider:
    """
    Discover ownership from OpsGenie.

    Configuration:
        api_key: OpsGenie API key

    Environment variables:
        OPSGENIE_API_KEY: API key
    """

    api_key: str = ""

    def _get_configuration(self) -> opsgenie_sdk.Configuration:
        conf = opsgenie_sdk.Configuration()
        conf.api_key['Authorization'] = f'GenieKey {self.api_key}'
        return conf

    async def get_ownership(self, service: str) -> OwnershipSignal | None:
        """Get ownership from OpsGenie service → team mapping."""
        conf = self._get_configuration()

        try:
            service_api = opsgenie_sdk.ServiceApi(opsgenie_sdk.ApiClient(conf))

            # List all services and find match
            response = service_api.list_services()

            for svc in response.data:
                if service.lower() in svc.name.lower():
                    if svc.team_id:
                        # Get team details
                        team_api = opsgenie_sdk.TeamApi(opsgenie_sdk.ApiClient(conf))
                        team = team_api.get_team(identifier=svc.team_id)

                        return OwnershipSignal(
                            source=OwnershipSource.OPSGENIE,
                            owner=team.data.name,
                            confidence=0.9,
                            metadata={
                                'opsgenie_service_id': svc.id,
                                'opsgenie_service_name': svc.name,
                                'opsgenie_team_id': svc.team_id,
                            }
                        )

        except ApiException:
            pass

        return None

    async def get_on_call(self, team: str) -> list[str]:
        """Get current on-call users for a team."""
        conf = self._get_configuration()

        try:
            schedule_api = opsgenie_sdk.ScheduleApi(opsgenie_sdk.ApiClient(conf))
            who_is_on_call = schedule_api.get_on_calls(
                identifier=team,
                identifier_type='name'
            )

            return [p.name for p in who_is_on_call.data.on_call_participants]

        except ApiException:
            return []
```

### GitHub CODEOWNERS

```python
# src/nthlayer/identity/ownership_providers/github.py

"""
GitHub ownership provider.

Uses PyGithub SDK: https://github.com/PyGithub/PyGithub

Sources:
- CODEOWNERS file
- Repository owner/organization
- Most active contributors (fallback)
"""

from dataclasses import dataclass
import re

from github import Github
from github.GithubException import GithubException

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class GitHubOwnershipProvider:
    """
    Discover ownership from GitHub.

    Configuration:
        token: GitHub personal access token or app token

    Environment variables:
        GITHUB_TOKEN: Token
    """

    token: str = ""

    def _get_client(self) -> Github:
        return Github(self.token)

    async def get_ownership_from_codeowners(
        self,
        repo: str
    ) -> OwnershipSignal | None:
        """
        Parse CODEOWNERS for default owner.

        CODEOWNERS format:
            * @org/platform-team
            /src/payments/ @org/payments-team
            *.js @org/frontend-team
        """
        g = self._get_client()

        try:
            repo_obj = g.get_repo(repo)

            # Try common CODEOWNERS locations
            codeowners_paths = [
                'CODEOWNERS',
                '.github/CODEOWNERS',
                'docs/CODEOWNERS',
            ]

            for path in codeowners_paths:
                try:
                    content = repo_obj.get_contents(path)
                    codeowners_text = content.decoded_content.decode()

                    # Parse for default owner (line starting with *)
                    for line in codeowners_text.split('\n'):
                        line = line.strip()

                        # Skip comments and empty lines
                        if not line or line.startswith('#'):
                            continue

                        # Match default owner pattern: * @owner
                        if line.startswith('*'):
                            parts = line.split()
                            if len(parts) >= 2:
                                # Clean up @org/team format
                                owner = parts[1].lstrip('@')

                                # Extract team name from org/team
                                if '/' in owner:
                                    owner = owner.split('/')[-1]

                                return OwnershipSignal(
                                    source=OwnershipSource.CODEOWNERS,
                                    owner=owner,
                                    confidence=0.85,
                                    metadata={
                                        'codeowners_path': path,
                                        'codeowners_entry': line,
                                        'repository': repo,
                                    }
                                )

                except GithubException:
                    continue

        except GithubException:
            pass

        return None

    async def get_ownership_from_repo(self, repo: str) -> OwnershipSignal | None:
        """Get ownership from repository owner/organization."""
        g = self._get_client()

        try:
            repo_obj = g.get_repo(repo)

            # Check if owned by organization
            if repo_obj.organization:
                return OwnershipSignal(
                    source=OwnershipSource.CODEOWNERS,
                    owner=repo_obj.organization.login,
                    confidence=0.5,  # Low - org != team
                    metadata={
                        'repository': repo,
                        'organization': repo_obj.organization.login,
                        'inferred_from': 'repository_organization',
                    }
                )

        except GithubException:
            pass

        return None

    async def get_ownership_from_activity(
        self,
        repo: str
    ) -> OwnershipSignal | None:
        """
        Fallback: infer ownership from most active contributors.

        Low confidence - active contributor ≠ owner.
        """
        g = self._get_client()

        try:
            repo_obj = g.get_repo(repo)

            # Get top contributors
            contributors = list(repo_obj.get_contributors()[:5])

            if contributors:
                top = contributors[0]

                return OwnershipSignal(
                    source=OwnershipSource.GIT_ACTIVITY,
                    owner=top.login,
                    confidence=0.4,
                    metadata={
                        'repository': repo,
                        'contributor_commits': top.contributions,
                        'is_proxy_signal': True,
                        'warning': 'Inferred from git activity, may not be actual owner',
                    }
                )

        except GithubException:
            pass

        return None
```

### Slack Channel Convention

```python
# src/nthlayer/identity/ownership_providers/slack.py

"""
Slack ownership provider.

Uses slack-sdk: https://github.com/slackapi/python-slack-sdk

Infers ownership from channel naming conventions.
"""

from dataclasses import dataclass
import re

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class SlackOwnershipProvider:
    """
    Discover ownership from Slack channel naming conventions.

    Configuration:
        token: Slack bot token (requires channels:read scope)
        patterns: List of (pattern, confidence) tuples

    Environment variables:
        SLACK_BOT_TOKEN: Bot token

    Common patterns:
        - #team-payments
        - #payments-alerts
        - #platform-oncall
    """

    token: str = ""
    patterns: list[tuple[str, float]] = None

    def __post_init__(self):
        if self.patterns is None:
            self.patterns = [
                ("team-{service}", 0.7),
                ("{service}-team", 0.7),
                ("{service}-oncall", 0.65),
                ("{service}-alerts", 0.6),
                ("{service}-eng", 0.6),
                ("{service}-dev", 0.55),
            ]

    def _get_client(self) -> WebClient:
        return WebClient(token=self.token)

    async def get_ownership(self, service: str) -> OwnershipSignal | None:
        """Get ownership from Slack channel naming conventions."""
        client = self._get_client()

        try:
            # Get all public channels
            result = client.conversations_list(
                types="public_channel",
                limit=1000,
                exclude_archived=True,
            )

            service_lower = service.lower()
            best_match = None
            best_confidence = 0

            for channel in result.get('channels', []):
                channel_name = channel['name'].lower()

                # Check each pattern
                for pattern, confidence in self.patterns:
                    # Convert pattern to regex
                    regex_pattern = pattern.replace('{service}', r'[\w-]*' + re.escape(service_lower) + r'[\w-]*')

                    if re.match(regex_pattern, channel_name):
                        if confidence > best_confidence:
                            # Extract team name from channel
                            team = self._extract_team_from_channel(channel_name, service_lower)

                            best_match = OwnershipSignal(
                                source=OwnershipSource.SLACK_CHANNEL,
                                owner=team,
                                confidence=confidence,
                                metadata={
                                    'slack_channel': f"#{channel['name']}",
                                    'channel_id': channel['id'],
                                    'pattern_matched': pattern,
                                }
                            )
                            best_confidence = confidence

            return best_match

        except SlackApiError:
            pass

        return None

    def _extract_team_from_channel(self, channel_name: str, service: str) -> str:
        """Extract team name from channel name."""
        # Remove common suffixes
        team = channel_name
        for suffix in ['-alerts', '-oncall', '-eng', '-dev', '-team']:
            team = team.replace(suffix, '')

        # Remove common prefixes
        for prefix in ['team-']:
            if team.startswith(prefix):
                team = team[len(prefix):]

        return team

    async def get_channel_for_service(self, service: str) -> str | None:
        """Find the most relevant Slack channel for a service."""
        signal = await self.get_ownership(service)
        if signal:
            return signal.metadata.get('slack_channel')
        return None
```

### AWS Resource Tags

```python
# src/nthlayer/identity/ownership_providers/aws.py

"""
AWS ownership provider.

Uses boto3 SDK: https://boto3.amazonaws.com/

Sources:
- Resource tags (Team, Owner, CostCenter)
- Resource Groups Tagging API
"""

from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class AWSOwnershipProvider:
    """
    Discover ownership from AWS resource tags.

    Configuration:
        region: AWS region
        profile: AWS profile name (optional)
        tag_keys: List of tag keys to check for ownership

    Environment variables:
        AWS_REGION: Region
        AWS_PROFILE: Profile
    """

    region: str = "us-east-1"
    profile: str | None = None
    tag_keys: list[str] = None

    def __post_init__(self):
        if self.tag_keys is None:
            self.tag_keys = [
                'Team', 'team',
                'Owner', 'owner',
                'Squad', 'squad',
                'CostCenter', 'cost-center',
                'Department', 'department',
            ]

    def _get_client(self, service: str = 'resourcegroupstaggingapi'):
        session = boto3.Session(
            region_name=self.region,
            profile_name=self.profile,
        )
        return session.client(service)

    async def get_ownership(self, service: str) -> OwnershipSignal | None:
        """Get ownership from AWS resource tags."""
        client = self._get_client()

        try:
            # Search for resources tagged with service name
            paginator = client.get_paginator('get_resources')

            # Try different tag filters
            tag_filters = [
                [{'Key': 'Service', 'Values': [service]}],
                [{'Key': 'service', 'Values': [service]}],
                [{'Key': 'Name', 'Values': [f'*{service}*']}],
                [{'Key': 'Application', 'Values': [service]}],
            ]

            for filters in tag_filters:
                try:
                    for page in paginator.paginate(TagFilters=filters):
                        for resource in page.get('ResourceTagMappingList', []):
                            tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}

                            # Check ownership tags
                            for key in self.tag_keys:
                                if key in tags and tags[key]:
                                    return OwnershipSignal(
                                        source=OwnershipSource.CLOUD_TAGS,
                                        owner=tags[key],
                                        confidence=0.8,
                                        metadata={
                                            'aws_resource_arn': resource['ResourceARN'],
                                            'tag_key': key,
                                            'tag_value': tags[key],
                                            'all_tags': tags,
                                        }
                                    )
                except ClientError:
                    continue

        except ClientError:
            pass

        return None

    async def get_cost_center(self, service: str) -> str | None:
        """Get cost center for a service from AWS tags."""
        client = self._get_client()

        try:
            paginator = client.get_paginator('get_resources')

            for page in paginator.paginate(
                TagFilters=[{'Key': 'Service', 'Values': [service]}]
            ):
                for resource in page.get('ResourceTagMappingList', []):
                    tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}

                    for key in ['CostCenter', 'cost-center', 'cost_center']:
                        if key in tags:
                            return tags[key]

        except ClientError:
            pass

        return None
```

### Kubernetes Labels Ownership

```python
# src/nthlayer/identity/ownership_providers/kubernetes.py

"""
Kubernetes ownership provider.

Uses kubernetes-client: https://github.com/kubernetes-client/python

Sources:
- Service labels and annotations
- Deployment labels and annotations
- Namespace labels
"""

from dataclasses import dataclass

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class KubernetesOwnershipProvider:
    """
    Discover ownership from Kubernetes labels/annotations.

    Configuration:
        kubeconfig: Path to kubeconfig (optional)
        context: Kubernetes context (optional)
        namespace: Default namespace
        label_keys: Labels to check for ownership

    Environment variables:
        KUBECONFIG: Path to kubeconfig
        KUBERNETES_CONTEXT: Context name
    """

    kubeconfig: str | None = None
    context: str | None = None
    namespace: str = "default"
    label_keys: list[str] = None

    def __post_init__(self):
        if self.label_keys is None:
            self.label_keys = [
                'team',
                'owner',
                'app.kubernetes.io/managed-by',
                'app.kubernetes.io/part-of',
                'backstage.io/owner',
                'maintainer',
            ]

    def _load_config(self):
        try:
            if self.kubeconfig:
                config.load_kube_config(
                    config_file=self.kubeconfig,
                    context=self.context,
                )
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config(context=self.context)
        except Exception as e:
            raise RuntimeError(f"Failed to load Kubernetes config: {e}")

    async def get_ownership(self, service: str) -> OwnershipSignal | None:
        """Get ownership from Kubernetes labels/annotations."""
        self._load_config()
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()

        # Try Service first
        signal = await self._get_ownership_from_service(v1, service)
        if signal:
            return signal

        # Try Deployment
        signal = await self._get_ownership_from_deployment(apps_v1, service)
        if signal:
            return signal

        # Try Namespace labels as fallback
        signal = await self._get_ownership_from_namespace(v1, service)
        if signal:
            return signal

        return None

    async def _get_ownership_from_service(
        self,
        v1: client.CoreV1Api,
        service: str
    ) -> OwnershipSignal | None:
        """Get ownership from Service resource."""
        try:
            svc = v1.read_namespaced_service(service, self.namespace)
            return self._extract_ownership(
                svc.metadata.labels or {},
                svc.metadata.annotations or {},
                'service',
                service,
            )
        except ApiException:
            return None

    async def _get_ownership_from_deployment(
        self,
        apps_v1: client.AppsV1Api,
        service: str
    ) -> OwnershipSignal | None:
        """Get ownership from Deployment resource."""
        try:
            deployment = apps_v1.read_namespaced_deployment(service, self.namespace)
            return self._extract_ownership(
                deployment.metadata.labels or {},
                deployment.metadata.annotations or {},
                'deployment',
                service,
            )
        except ApiException:
            return None

    async def _get_ownership_from_namespace(
        self,
        v1: client.CoreV1Api,
        service: str
    ) -> OwnershipSignal | None:
        """Get ownership from Namespace labels (fallback)."""
        try:
            ns = v1.read_namespace(self.namespace)
            signal = self._extract_ownership(
                ns.metadata.labels or {},
                ns.metadata.annotations or {},
                'namespace',
                self.namespace,
            )

            # Lower confidence for namespace-level ownership
            if signal:
                signal.confidence *= 0.8
                signal.metadata['note'] = 'Inherited from namespace'

            return signal
        except ApiException:
            return None

    def _extract_ownership(
        self,
        labels: dict,
        annotations: dict,
        resource_type: str,
        resource_name: str,
    ) -> OwnershipSignal | None:
        """Extract ownership from labels and annotations."""
        # Check both labels and annotations
        for source in [labels, annotations]:
            for key in self.label_keys:
                if key in source and source[key]:
                    return OwnershipSignal(
                        source=OwnershipSource.KUBERNETES,
                        owner=source[key],
                        confidence=0.75,
                        metadata={
                            'kubernetes_resource_type': resource_type,
                            'kubernetes_resource_name': resource_name,
                            'kubernetes_namespace': self.namespace,
                            'label_key': key,
                        }
                    )

        return None
```

---

## Ownership Resolver

```python
# src/nthlayer/identity/ownership.py

"""
Ownership resolver that aggregates signals from multiple providers.
"""

from dataclasses import dataclass, field
import asyncio
from typing import Protocol

from cachetools import TTLCache


class OwnershipProvider(Protocol):
    """Protocol for ownership providers."""
    async def get_ownership(self, service: str) -> OwnershipSignal | None: ...


@dataclass
class OwnershipResolver:
    """
    Resolves service ownership by querying multiple sources.

    Resolution priority:
    1. Explicit declaration in service.yaml
    2. PagerDuty/OpsGenie (who gets paged = who owns)
    3. Developer portal (Cortex.io/Backstage)
    4. CODEOWNERS
    5. Cloud resource tags
    6. Kubernetes labels
    7. Slack channel conventions
    8. Git activity (fallback)
    """

    providers: list[OwnershipProvider] = field(default_factory=list)

    # Source priority weights
    source_weights: dict[OwnershipSource, float] = field(default_factory=lambda: {
        OwnershipSource.DECLARED: 1.0,
        OwnershipSource.PAGERDUTY: 0.95,
        OwnershipSource.OPSGENIE: 0.9,
        OwnershipSource.DEVELOPER_PORTAL: 0.9,
        OwnershipSource.CODEOWNERS: 0.85,
        OwnershipSource.CLOUD_TAGS: 0.8,
        OwnershipSource.KUBERNETES: 0.75,
        OwnershipSource.SLACK_CHANNEL: 0.6,
        OwnershipSource.COST_CENTER: 0.7,
        OwnershipSource.GIT_ACTIVITY: 0.4,
    })

    # Minimum confidence to accept attribution
    confidence_threshold: float = 0.5

    # Default owner if nothing found
    default_owner: str | None = None

    # Cache
    cache_ttl: int = 300
    _cache: TTLCache = field(default_factory=lambda: TTLCache(maxsize=500, ttl=300))

    async def resolve(
        self,
        service: str,
        declared_owner: str | None = None,
        repo: str | None = None,
    ) -> OwnershipAttribution:
        """
        Resolve ownership from all available sources.

        Args:
            service: Service name
            declared_owner: Owner from service.yaml (highest priority)
            repo: Repository for CODEOWNERS lookup

        Returns:
            OwnershipAttribution with resolved owner and all signals
        """
        cache_key = f"owner:{service}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        signals = []

        # 1. Check explicit declaration first
        if declared_owner:
            signals.append(OwnershipSignal(
                source=OwnershipSource.DECLARED,
                owner=declared_owner,
                confidence=1.0,
                metadata={'source': 'service.yaml'}
            ))

        # 2. Query all providers in parallel
        tasks = [provider.get_ownership(service) for provider in self.providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, OwnershipSignal):
                signals.append(result)

        # 3. Rank signals by weighted confidence
        signals.sort(
            key=lambda s: s.confidence * self.source_weights.get(s.source, 0.5),
            reverse=True
        )

        # 4. Select best signal above threshold
        best = None
        for signal in signals:
            weighted = signal.confidence * self.source_weights.get(signal.source, 0.5)
            if weighted >= self.confidence_threshold:
                best = signal
                break

        # 5. Build attribution
        attribution = OwnershipAttribution(
            service=service,
            owner=best.owner if best else self.default_owner,
            confidence=best.confidence if best else 0.0,
            source=best.source if best else None,
            signals=signals,
            slack_channel=self._find_slack_channel(signals),
            pagerduty_escalation=self._find_pagerduty_escalation(signals),
        )

        self._cache[cache_key] = attribution
        return attribution

    def _find_slack_channel(self, signals: list[OwnershipSignal]) -> str | None:
        """Extract Slack channel from signals."""
        for signal in signals:
            if 'slack_channel' in signal.metadata:
                return signal.metadata['slack_channel']
        return None

    def _find_pagerduty_escalation(self, signals: list[OwnershipSignal]) -> str | None:
        """Extract PagerDuty escalation policy from signals."""
        for signal in signals:
            if signal.source == OwnershipSource.PAGERDUTY:
                return signal.metadata.get('escalation_policy_name')
        return None

    async def get_teams_for_services(
        self,
        services: list[str]
    ) -> dict[str, OwnershipAttribution]:
        """Bulk resolve ownership for multiple services."""
        tasks = [self.resolve(svc) for svc in services]
        results = await asyncio.gather(*tasks)
        return dict(zip(services, results))
```

---

## Discovery Orchestrator

```python
# src/nthlayer/dependencies/discovery.py

"""
Discovery orchestrator that coordinates multiple providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from cachetools import TTLCache

from nthlayer.dependencies.providers.base import BaseDepProvider
from nthlayer.dependencies.models import (
    DiscoveredDependency,
    ResolvedDependency,
    DependencyGraph,
    DependencyType,
)
from nthlayer.identity.resolver import IdentityResolver


@dataclass
class DiscoveryOrchestrator:
    """
    Orchestrates dependency discovery across multiple providers.

    Responsibilities:
    - Run providers in parallel
    - Merge and deduplicate results
    - Resolve identities
    - Build unified dependency graph
    """

    providers: list[BaseDepProvider] = field(default_factory=list)
    identity_resolver: IdentityResolver = field(default_factory=IdentityResolver)

    # Provider priority for confidence scoring
    provider_priority: dict[str, float] = field(default_factory=lambda: {
        "declared": 1.0,
        "consul": 0.9,
        "cortex.io": 0.9,
        "backstage": 0.9,
        "kubernetes": 0.85,
        "prometheus": 0.75,
        "zookeeper": 0.8,
        "eureka": 0.75,
        "etcd": 0.8,
        "aws_cloudmap": 0.85,
    })

    # Cache for discovery results
    cache_ttl: int = 300  # 5 minutes
    _cache: TTLCache = field(default_factory=lambda: TTLCache(maxsize=500, ttl=300))

    async def discover_for_service(
        self,
        service: str,
        use_cache: bool = True,
    ) -> list[ResolvedDependency]:
        """
        Discover and resolve dependencies for a single service.

        Args:
            service: Service name (canonical or raw)
            use_cache: Whether to use cached results

        Returns:
            List of resolved dependencies
        """
        cache_key = f"deps:{service}"

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # Run all providers in parallel
        tasks = [
            provider.discover(service)
            for provider in self.providers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all discovered dependencies
        all_deps: list[DiscoveredDependency] = []

        for result in results:
            if isinstance(result, Exception):
                continue
            all_deps.extend(result)

        # Resolve identities and merge
        resolved = self._resolve_and_merge(all_deps)

        if use_cache:
            self._cache[cache_key] = resolved

        return resolved

    async def build_full_graph(
        self,
        services: list[str] | None = None,
    ) -> DependencyGraph:
        """
        Build complete dependency graph for all or specified services.

        Args:
            services: List of services to include (None = all discovered)

        Returns:
            Complete DependencyGraph
        """
        # Get list of services if not provided
        if services is None:
            services = await self._discover_all_services()

        # Discover dependencies for each service
        all_resolved: list[ResolvedDependency] = []

        # Batch discovery to avoid overwhelming providers
        batch_size = 10
        for i in range(0, len(services), batch_size):
            batch = services[i:i + batch_size]
            tasks = [self.discover_for_service(svc) for svc in batch]
            results = await asyncio.gather(*tasks)

            for deps in results:
                all_resolved.extend(deps)

        # Deduplicate edges
        seen = set()
        unique_edges = []

        for dep in all_resolved:
            key = (dep.source.canonical_name, dep.target.canonical_name, dep.dep_type)
            if key not in seen:
                seen.add(key)
                unique_edges.append(dep)

        return DependencyGraph(
            services=dict(self.identity_resolver.identities),
            edges=unique_edges,
            built_at=datetime.utcnow(),
            providers_used=[p.name for p in self.providers],
        )

    async def _discover_all_services(self) -> list[str]:
        """Discover all services from all providers."""
        all_services = set()

        tasks = [provider.list_services() for provider in self.providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            all_services.update(result)

        return list(all_services)

    def _resolve_and_merge(
        self,
        deps: list[DiscoveredDependency]
    ) -> list[ResolvedDependency]:
        """Resolve identities and merge duplicate dependencies."""
        # Group by (source, target) after resolution
        grouped: dict[tuple[str, str, DependencyType], list[DiscoveredDependency]] = {}

        for dep in deps:
            # Resolve source identity
            source_identity = self.identity_resolver.register_from_discovery(
                raw_name=dep.raw_source or dep.source_service,
                provider=dep.provider,
            )

            # Resolve target identity
            target_identity = self.identity_resolver.register_from_discovery(
                raw_name=dep.raw_target or dep.target_service,
                provider=dep.provider,
            )

            key = (
                source_identity.canonical_name,
                target_identity.canonical_name,
                dep.dep_type,
            )

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(dep)

        # Merge grouped dependencies
        resolved = []

        for (source_name, target_name, dep_type), deps_group in grouped.items():
            # Calculate aggregated confidence
            # Multiple providers reporting same dep = higher confidence
            providers = list(set(d.provider for d in deps_group))

            base_confidence = max(d.confidence for d in deps_group)
            multi_source_boost = min(0.1 * (len(providers) - 1), 0.2)
            final_confidence = min(1.0, base_confidence + multi_source_boost)

            # Merge metadata
            merged_metadata = {}
            for dep in deps_group:
                merged_metadata.update(dep.metadata)
            merged_metadata["providers"] = providers

            resolved.append(ResolvedDependency(
                source=self.identity_resolver.identities[source_name],
                target=self.identity_resolver.identities[target_name],
                dep_type=dep_type,
                confidence=final_confidence,
                providers=providers,
                metadata=merged_metadata,
            ))

        return resolved

    async def health_check_all(self) -> dict[str, "ProviderHealth"]:
        """Check health of all providers."""
        results = {}

        tasks = [(p.name, p.health_check()) for p in self.providers]

        for name, task in tasks:
            try:
                results[name] = await task
            except Exception as e:
                from nthlayer.dependencies.providers.base import ProviderHealth
                results[name] = ProviderHealth(
                    healthy=False,
                    message=f"Health check failed: {str(e)}",
                )

        return results
```

---

## Configuration

```yaml
# nthlayer.yaml
discovery:
  # Enable/disable dependency providers
  providers:
    consul:
      enabled: true
      host: ${CONSUL_HOST:-localhost}
      port: ${CONSUL_PORT:-8500}
      token: ${CONSUL_HTTP_TOKEN}
      dc: ${CONSUL_DATACENTER}

    zookeeper:
      enabled: false
      hosts: ${ZOOKEEPER_HOSTS:-localhost:2181}
      service_path: /services
      kafka_consumers_path: /consumers

    eureka:
      enabled: false
      url: ${EUREKA_SERVER_URL:-http://localhost:8761/eureka}

    etcd:
      enabled: false
      host: ${ETCD_HOST:-localhost}
      port: ${ETCD_PORT:-2379}
      service_prefix: /services/

    cortex_portal:
      enabled: true
      api_key: ${CORTEX_API_KEY}
      base_url: ${CORTEX_URL:-https://api.cortex.io}

    backstage:
      enabled: true
      base_url: ${BACKSTAGE_URL:-http://localhost:7007}
      auth_token: ${BACKSTAGE_AUTH_TOKEN}

    prometheus:
      enabled: true
      url: ${PROMETHEUS_URL:-http://localhost:9090}

    kubernetes:
      enabled: true
      context: ${KUBERNETES_CONTEXT}
      namespace: ${KUBERNETES_NAMESPACE}
      include_istio: true

    aws_cloudmap:
      enabled: false
      namespace_id: ${CLOUDMAP_NAMESPACE_ID}
      region: ${AWS_REGION:-us-east-1}

  # Identity resolution settings
  identity:
    fuzzy_threshold: 0.85

    correlation:
      strong_attrs: [repo, repository, github_url]
      weak_attrs: [owner, team, slack_channel]

    # Explicit mappings for known mismatches
    explicit_mappings:
      "pay-api@consul": payment-api
      "PAYMENT-SERVICE@eureka": payment-api

  # Cache settings
  cache_ttl: 300  # seconds

# Ownership provider configuration
ownership:
  # Minimum confidence to accept attribution
  confidence_threshold: 0.5

  # Default owner if nothing found
  default_owner: platform-team

  providers:
    pagerduty:
      enabled: true
      api_key: ${PAGERDUTY_API_KEY}

    opsgenie:
      enabled: false
      api_key: ${OPSGENIE_API_KEY}

    github:
      enabled: true
      token: ${GITHUB_TOKEN}
      check_codeowners: true

    slack:
      enabled: true
      token: ${SLACK_BOT_TOKEN}
      # Channel naming patterns for ownership inference
      patterns:
        - pattern: "team-{service}"
          confidence: 0.7
        - pattern: "{service}-oncall"
          confidence: 0.65
        - pattern: "{service}-alerts"
          confidence: 0.6

    aws:
      enabled: true
      region: ${AWS_REGION:-us-east-1}
      # Tag keys to check for ownership
      tag_keys:
        - Team
        - team
        - Owner
        - owner
        - Squad
        - CostCenter

    kubernetes:
      enabled: true
      # Labels/annotations to check for ownership
      label_keys:
        - team
        - owner
        - app.kubernetes.io/managed-by
        - backstage.io/owner
```

---

## CLI Commands

### `nthlayer deps`

```
$ nthlayer deps payment-api

Dependency Discovery: payment-api
Providers: consul ✓ | backstage ✓ | prometheus ✓ | kubernetes ✓

Upstream (payment-api depends on):
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
│ Service        │ Type       │ Confidence  │ Sources                      │
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ user-service   │ service    │ ██████████  │ consul, backstage, prometheus│
│ postgresql     │ datastore  │ █████████░  │ consul, backstage            │
│ redis          │ datastore  │ ████████░░  │ prometheus                   │
│ kafka:orders   │ queue      │ ███████░░░  │ zookeeper                    │
└────────────────┴────────────┴─────────────┴──────────────────────────────┘

Downstream (services depending on payment-api):
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
│ Service        │ Confidence │ Impact                                     │
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ checkout-api   │ ██████████ │ critical (tier: critical)                  │
│ order-service  │ █████████░ │ critical (tier: critical)                  │
│ admin-api      │ ███████░░░ │ low (tier: low)                            │
└────────────────┴────────────┴────────────────────────────────────────────┘
```

### `nthlayer identity`

```
$ nthlayer identity list

Service Identities (47 services)
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
│ Canonical         │ Sources  │ Aliases                                  │
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ payment-api       │ 5        │ pay-api, PAYMENT-SERVICE, srv-12345      │
│ user-service      │ 4        │ users, user-svc                          │
└───────────────────┴──────────┴──────────────────────────────────────────┘

$ nthlayer identity resolve pay-api --provider consul

Resolution: pay-api (from consul)
  ✓ Normalized match → payment-api
  Confidence: 0.85

$ nthlayer identity map "api-gateway@consul" gateway-api
Mapped: api-gateway@consul → gateway-api
```

### `nthlayer ownership`

```
$ nthlayer ownership payment-api

Ownership Attribution: payment-api

┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
│ Source            │ Owner             │ Confidence  │ Details                │
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ pagerduty         │ payments-team     │ ██████████  │ via escalation policy  │
│ backstage         │ payments-team     │ █████████░  │ catalog owner field    │
│ codeowners        │ platform/payments │ ████████░░  │ CODEOWNERS default     │
│ slack             │ payments          │ ██████░░░░  │ #team-payments         │
│ aws_tags          │ payments-squad    │ ██████░░░░  │ Team tag               │
└───────────────────┴───────────────────┴─────────────┴────────────────────────┘

Resolved Owner: payments-team (via pagerduty, confidence: 0.95)

Contact:
  Slack: #team-payments
  PagerDuty: payments-escalation-policy
```

### `nthlayer portfolio --with-owners`

```
$ nthlayer portfolio --with-owners

NthLayer Portfolio - Reliability Overview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
│ Service        │ Tier     │ Budget  │ Owner           │ Source            │
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ payment-api    │ critical │ 72%     │ payments-team   │ pagerduty         │
│ user-service   │ critical │ 91%     │ identity-squad  │ backstage         │
│ order-worker   │ standard │ 45%     │ orders-team     │ codeowners        │
│ analytics-api  │ low      │ 23%     │ data-eng        │ aws_tags          │
│ legacy-svc     │ low      │ 88%     │ platform-team   │ default (unknown) │
└────────────────┴──────────┴─────────┴─────────────────┴───────────────────┘

Summary: 5 services | 3 teams | 1 unowned
```

### `nthlayer validate-slo`

```
$ nthlayer validate-slo payment-api

Validating SLO feasibility for payment-api...
Resolving dependencies... found 4

Target: 99.95% availability

Dependency chain:
  payment-api (99.95% target)
  ├── user-service (99.90%)
  ├── postgresql (99.95% assumed)
  ├── redis (99.90%)
  └── stripe-api (99.95% declared)

Analysis:
  Serial availability: 99.70%
  With circuit breakers: 99.85%

⚠️  Target 99.95% may be infeasible
    Achievable ceiling: ~99.85%

Recommendations:
  1. Reduce target to 99.9%
  2. Add graceful degradation for stripe-api
```

### `nthlayer blast-radius`

```
$ nthlayer blast-radius user-service

Blast Radius Analysis: user-service
Owner: identity-squad (via pagerduty)

Direct dependents (6 services):
  → payment-api (critical) - owner: payments-team
  → order-service (critical) - owner: orders-team
  → checkout-api (critical) - owner: checkout-squad
  → notification-service (standard) - owner: comms-team
  → analytics-worker (low) - owner: data-eng
  → admin-api (low) - owner: platform-team

Transitive impact (12 services total):
  Depth 1: 6 services
  Depth 2: 4 services
  Depth 3: 2 services

If user-service drops to 99.0% for 1 hour:
  Org-wide SLO impact: -0.15%
  Critical services affected: 3
  Teams to notify: 4

Teams affected:
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
│ Team            │ Services        │ Contact                  │
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ payments-team   │ payment-api     │ #team-payments           │
│ orders-team     │ order-service   │ #orders-oncall           │
│ checkout-squad  │ checkout-api    │ @checkout-squad          │
│ comms-team      │ notification-svc│ #comms-alerts            │
└─────────────────┴─────────────────┴──────────────────────────┘
```

### `nthlayer blast-radius --notify`

```
$ nthlayer blast-radius user-service --notify

[same output as above]

Would notify 4 teams via Slack:
  • #team-payments
  • #orders-oncall
  • #comms-alerts
  • (checkout-squad via @mention)

Proceed? [y/N] y

✓ Notifications sent to 4 channels
```

---

## Testing Strategy

### Unit Tests

```python
# tests/identity/test_resolver.py

def test_normalize_removes_env_suffix():
    assert normalize_service_name("payment-api-prod") == "payment-api"
    assert normalize_service_name("payment-api-staging") == "payment-api"

def test_resolve_by_external_id():
    resolver = IdentityResolver()
    resolver.register(ServiceIdentity(
        canonical_name="payment-api",
        external_ids={"consul": "pay-api-prod"},
    ))

    match = resolver.resolve("pay-api-prod", provider="consul")

    assert match.identity is not None
    assert match.identity.canonical_name == "payment-api"
    assert match.match_type == "external_id"

def test_fuzzy_match_above_threshold():
    resolver = IdentityResolver(fuzzy_threshold=0.8)
    resolver.register(ServiceIdentity(canonical_name="payment-api"))

    match = resolver.resolve("payment-ap")  # Typo

    assert match.identity is not None
    assert match.match_type == "fuzzy"
```

### Integration Tests

```python
# tests/providers/test_consul_integration.py

@pytest.mark.integration
async def test_consul_discover_intentions(consul_container):
    provider = ConsulDepProvider(
        host=consul_container.host,
        port=consul_container.port,
    )

    # Setup: Create test services and intentions
    # ...

    deps = await provider.discover("test-service")

    assert len(deps) > 0
    assert any(d.target_service == "database" for d in deps)
```

---

## Summary

This spec provides:

1. **Identity Resolution**: Normalizes service names across providers using explicit mappings, fuzzy matching, and attribute correlation.

2. **10 Dependency Provider Implementations** using official SDKs:
   - Consul (python-consul2)
   - ZooKeeper (kazoo)
   - Eureka (py-eureka-client)
   - etcd (etcd3)
   - Cortex.io (httpx REST)
   - Backstage (httpx REST)
   - Prometheus (prometheus-api-client)
   - Kubernetes (kubernetes-client)
   - AWS Cloud Map (boto3)

3. **6 Ownership Provider Implementations** using official SDKs:
   - PagerDuty (pdpyras)
   - OpsGenie (opsgenie-sdk)
   - GitHub CODEOWNERS (PyGithub)
   - Slack channel conventions (slack-sdk)
   - AWS resource tags (boto3)
   - Kubernetes labels (kubernetes-client)

4. **Ownership Resolution Priority**:
   - Explicit declaration (service.yaml) → highest
   - PagerDuty/OpsGenie (who gets paged = who owns) → very high
   - Developer portal (Cortex.io/Backstage) → high
   - CODEOWNERS → high
   - Cloud tags → medium
   - Kubernetes labels → medium
   - Slack channel conventions → lower
   - Git activity → fallback only

5. **Stateless Design**: All discovery happens at runtime with short-lived caches.

6. **CLI Commands**: `deps`, `identity`, `ownership`, `validate-slo`, `blast-radius`, `portfolio --with-owners`

7. **Extensible Architecture**: New providers can be added by implementing `BaseDepProvider` or `OwnershipProvider`.

**Estimated Implementation: 12-16 days**
- Identity resolver: 2 days
- Dependency provider implementations: 6-8 days (parallelizable)
- Ownership provider implementations: 3-4 days (parallelizable)
- CLI commands: 2-3 days
- Testing: 2-3 days
