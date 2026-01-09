"""
Backstage dependency provider.

Discovers service dependencies from Backstage catalog entities via REST API.

Supports:
- Explicit dependencies from spec.dependsOn (0.95 confidence)
- API consumption from spec.consumesApis (0.90 confidence)
- Ownership extraction from spec.owner
- Downstream discovery via reverse lookups

Environment variables:
- NTHLAYER_BACKSTAGE_URL: Backstage base URL
- NTHLAYER_BACKSTAGE_TOKEN: Bearer token for authentication
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from nthlayer.dependencies.models import (
    DependencyType,
    DiscoveredDependency,
)
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth


class BackstageDepProviderError(Exception):
    """Backstage provider error."""

    pass


@dataclass
class BackstageDepProvider(BaseDepProvider):
    """
    Dependency provider that discovers dependencies from Backstage catalog.

    Queries the Backstage catalog API to find:
    - Explicit dependencies declared in spec.dependsOn
    - API consumption declared in spec.consumesApis
    - Ownership information from spec.owner

    Attributes:
        url: Backstage base URL (e.g., https://backstage.example.com)
        token: Bearer token for authentication (optional)
        namespace: Filter entities by namespace (optional)
        timeout: Request timeout in seconds
    """

    url: str
    token: str | None = None
    namespace: str | None = None
    timeout: float = 30.0

    # Private fields
    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False, compare=False)

    @property
    def name(self) -> str:
        """Provider name."""
        return "backstage"

    def _ensure_initialized(self) -> None:
        """Initialize HTTP client if not already done."""
        if self._initialized:
            return

        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.AsyncClient(
            base_url=self.url.rstrip("/"),
            headers=headers,
            timeout=self.timeout,
        )
        self._initialized = True

    async def _close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._initialized = False

    async def _query_entities(
        self,
        kind: str | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query catalog entities.

        Args:
            kind: Filter by entity kind (Component, Resource, API, etc.)
            namespace: Filter by namespace

        Returns:
            List of entity dictionaries
        """
        self._ensure_initialized()
        assert self._client is not None

        params: list[tuple[str, str | int | float | bool | None]] = []
        if kind:
            params.append(("filter", f"kind={kind}"))
        if namespace or self.namespace:
            ns = namespace or self.namespace
            params.append(("filter", f"metadata.namespace={ns}"))

        try:
            response = await self._client.get("/api/catalog/entities", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise BackstageDepProviderError(
                    f"Authentication failed: {e.response.status_code}"
                ) from e
            raise BackstageDepProviderError(f"Catalog query failed: {e}") from e
        except httpx.RequestError as e:
            raise BackstageDepProviderError(f"Request failed: {e}") from e

    async def _get_entity(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
    ) -> dict[str, Any] | None:
        """
        Get a specific entity by kind, namespace, and name.

        Args:
            kind: Entity kind
            name: Entity name
            namespace: Entity namespace

        Returns:
            Entity dictionary or None if not found
        """
        self._ensure_initialized()
        assert self._client is not None

        try:
            response = await self._client.get(
                f"/api/catalog/entities/by-name/{kind}/{namespace}/{name}"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise BackstageDepProviderError(f"Entity lookup failed: {e}") from e
        except httpx.RequestError as e:
            raise BackstageDepProviderError(f"Request failed: {e}") from e

    def _parse_entity_ref(self, ref: str) -> tuple[str, str | None, str]:
        """
        Parse a Backstage entity reference.

        Formats:
        - kind:name -> (kind, None, name)
        - kind:namespace/name -> (kind, namespace, name)

        Args:
            ref: Entity reference string

        Returns:
            Tuple of (kind, namespace, name)
        """
        # Match kind:namespace/name or kind:name
        match = re.match(r"^([^:]+):(?:([^/]+)/)?(.+)$", ref)
        if not match:
            # Fallback: treat as component:name
            return ("component", None, ref)

        kind, namespace, name = match.groups()
        return (kind.lower(), namespace, name)

    def _infer_dependency_type(self, kind: str, name: str) -> DependencyType:
        """
        Infer dependency type from entity kind and name.

        Args:
            kind: Entity kind
            name: Entity name

        Returns:
            Inferred DependencyType
        """
        kind_lower = kind.lower()

        # Resource types
        if kind_lower == "resource":
            name_lower = name.lower()
            if any(db in name_lower for db in ("postgres", "mysql", "mongo", "redis")):
                return DependencyType.DATASTORE
            if any(q in name_lower for q in ("kafka", "rabbitmq", "sqs", "pubsub")):
                return DependencyType.QUEUE
            return DependencyType.INFRASTRUCTURE

        # API types
        if kind_lower == "api":
            return DependencyType.SERVICE

        # Component is a service
        if kind_lower == "component":
            return DependencyType.SERVICE

        # External systems
        if kind_lower in ("system", "domain"):
            return DependencyType.EXTERNAL

        return DependencyType.SERVICE

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover upstream dependencies for a service.

        Queries Backstage for the service entity and extracts:
        - spec.dependsOn references
        - spec.consumesApis references

        Args:
            service: Service name to find dependencies for

        Returns:
            List of discovered dependencies
        """
        deps: list[DiscoveredDependency] = []

        # Try to find the entity
        entity = await self._get_entity("component", service, self.namespace or "default")

        # Also try without namespace filter
        if not entity and self.namespace:
            entity = await self._get_entity("component", service, "default")

        if not entity:
            # Try searching by name
            entities = await self._query_entities(kind="Component")
            for e in entities:
                if e.get("metadata", {}).get("name") == service:
                    entity = e
                    break

        if not entity:
            return deps

        spec = entity.get("spec", {})
        metadata = entity.get("metadata", {})
        entity_namespace = metadata.get("namespace", "default")

        # Extract dependencies from spec.dependsOn
        depends_on = spec.get("dependsOn", [])
        for ref in depends_on:
            kind, ns, name = self._parse_entity_ref(ref)
            dep_type = self._infer_dependency_type(kind, name)

            deps.append(
                DiscoveredDependency(
                    source_service=service,
                    target_service=name,
                    provider=self.name,
                    dep_type=dep_type,
                    confidence=0.95,
                    metadata={
                        "source": "spec.dependsOn",
                        "kind": kind,
                        "namespace": ns or entity_namespace,
                        "ref": ref,
                    },
                    raw_source=service,
                    raw_target=ref,
                )
            )

        # Extract dependencies from spec.consumesApis
        consumes_apis = spec.get("consumesApis", [])
        for ref in consumes_apis:
            kind, ns, name = self._parse_entity_ref(ref)

            deps.append(
                DiscoveredDependency(
                    source_service=service,
                    target_service=name,
                    provider=self.name,
                    dep_type=DependencyType.SERVICE,
                    confidence=0.90,
                    metadata={
                        "source": "spec.consumesApis",
                        "kind": kind,
                        "namespace": ns or entity_namespace,
                        "ref": ref,
                    },
                    raw_source=service,
                    raw_target=ref,
                )
            )

        return self._deduplicate(deps)

    async def discover_downstream(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover downstream dependencies (what calls this service).

        Queries all components and finds those with dependsOn containing this service.

        Args:
            service: Service name to find dependents for

        Returns:
            List of discovered dependencies
        """
        deps: list[DiscoveredDependency] = []

        # Query all components
        entities = await self._query_entities(kind="Component")

        for entity in entities:
            spec = entity.get("spec", {})
            metadata = entity.get("metadata", {})
            entity_name = metadata.get("name", "")
            entity_namespace = metadata.get("namespace", "default")

            # Skip self
            if entity_name == service:
                continue

            # Check dependsOn
            depends_on = spec.get("dependsOn", [])
            for ref in depends_on:
                kind, ns, name = self._parse_entity_ref(ref)
                if name == service:
                    deps.append(
                        DiscoveredDependency(
                            source_service=entity_name,
                            target_service=service,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.95,
                            metadata={
                                "source": "spec.dependsOn",
                                "dependent": entity_name,
                                "namespace": entity_namespace,
                            },
                            raw_source=entity_name,
                            raw_target=ref,
                        )
                    )

            # Check consumesApis
            consumes_apis = spec.get("consumesApis", [])
            for ref in consumes_apis:
                kind, ns, name = self._parse_entity_ref(ref)
                if name == service:
                    deps.append(
                        DiscoveredDependency(
                            source_service=entity_name,
                            target_service=service,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.90,
                            metadata={
                                "source": "spec.consumesApis",
                                "dependent": entity_name,
                                "namespace": entity_namespace,
                            },
                            raw_source=entity_name,
                            raw_target=ref,
                        )
                    )

        return self._deduplicate(deps)

    async def list_services(self) -> list[str]:
        """
        List all services in Backstage catalog.

        Returns:
            List of service names
        """
        entities = await self._query_entities(kind="Component")

        services: list[str] = []
        for entity in entities:
            name = entity.get("metadata", {}).get("name")
            if name:
                services.append(name)

        return sorted(set(services))

    async def health_check(self) -> ProviderHealth:
        """
        Check Backstage API connectivity.

        Returns:
            Provider health status
        """
        self._ensure_initialized()
        assert self._client is not None

        try:
            # Query entities with limit to check connectivity
            response = await self._client.get(
                "/api/catalog/entities",
                params=[("limit", "1")],
            )
            response.raise_for_status()

            return ProviderHealth(
                healthy=True,
                message=f"Connected to Backstage catalog at {self.url}",
            )
        except httpx.HTTPStatusError as e:
            return ProviderHealth(
                healthy=False,
                message=f"HTTP error {e.response.status_code}: {self.url}",
            )
        except httpx.RequestError as e:
            return ProviderHealth(
                healthy=False,
                message=f"Connection failed: {e}",
            )

    async def get_service_attributes(self, service: str) -> dict[str, Any]:
        """
        Get service attributes including ownership.

        Args:
            service: Service name

        Returns:
            Dictionary of attributes
        """
        entity = await self._get_entity("component", service, self.namespace or "default")

        if not entity:
            return {}

        metadata = entity.get("metadata", {})
        spec = entity.get("spec", {})

        return {
            "name": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "uid": metadata.get("uid"),
            "owner": spec.get("owner"),
            "type": spec.get("type"),
            "lifecycle": spec.get("lifecycle"),
            "system": spec.get("system"),
            "tags": metadata.get("tags", []),
            "annotations": metadata.get("annotations", {}),
        }

    def _deduplicate(self, deps: list[DiscoveredDependency]) -> list[DiscoveredDependency]:
        """
        Deduplicate dependencies, keeping highest confidence.

        Args:
            deps: List of dependencies

        Returns:
            Deduplicated list
        """
        seen: dict[str, DiscoveredDependency] = {}

        for dep in deps:
            key = f"{dep.source_service}:{dep.target_service}:{dep.dep_type.value}"

            if key not in seen or dep.confidence > seen[key].confidence:
                seen[key] = dep

        return list(seen.values())
