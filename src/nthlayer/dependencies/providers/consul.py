"""
Consul dependency provider.

Discovers service dependencies from Consul service catalog and Connect mesh.

Supports:
- Service catalog discovery via /v1/catalog/services (0.90 confidence)
- Health endpoint metadata via /v1/health/service (0.85 confidence)
- Connect intentions for explicit mesh dependencies (0.95 confidence)
- Service tags for dependency hints (0.80 confidence)

Environment variables:
- NTHLAYER_CONSUL_URL: Consul HTTP API URL
- NTHLAYER_CONSUL_TOKEN: ACL token for authentication
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from nthlayer.dependencies.models import (
    DependencyType,
    DiscoveredDependency,
)
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth


class ConsulDepProviderError(Exception):
    """Consul provider error."""

    pass


@dataclass
class ConsulDepProvider(BaseDepProvider):
    """
    Dependency provider that discovers dependencies from Consul.

    Queries the Consul HTTP API to find:
    - Registered services in the catalog
    - Service health and metadata
    - Connect mesh intentions (explicit dependencies)
    - Service tags containing dependency hints

    Attributes:
        url: Consul HTTP API URL (e.g., http://localhost:8500)
        token: ACL token for authentication (optional)
        datacenter: Filter by datacenter (optional)
        namespace: Filter by namespace (Enterprise only, optional)
        timeout: Request timeout in seconds
    """

    url: str = "http://localhost:8500"
    token: str | None = None
    datacenter: str | None = None
    namespace: str | None = None
    timeout: float = 30.0

    # Private fields
    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False, compare=False)

    @property
    def name(self) -> str:
        """Provider name."""
        return "consul"

    def _ensure_initialized(self) -> None:
        """Initialize HTTP client if not already done."""
        if self._initialized:
            return

        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Consul-Token"] = self.token

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

    def _build_params(self) -> dict[str, str]:
        """Build common query parameters."""
        params: dict[str, str] = {}
        if self.datacenter:
            params["dc"] = self.datacenter
        if self.namespace:
            params["ns"] = self.namespace
        return params

    async def _get_catalog_services(self) -> dict[str, list[str]]:
        """
        Get all services from the catalog.

        Returns:
            Dict mapping service name to list of tags
        """
        self._ensure_initialized()
        assert self._client is not None

        params = self._build_params()

        try:
            response = await self._client.get("/v1/catalog/services", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ConsulDepProviderError(
                    f"Authentication failed: {e.response.status_code}"
                ) from e
            raise ConsulDepProviderError(f"Catalog query failed: {e}") from e
        except httpx.RequestError as e:
            raise ConsulDepProviderError(f"Request failed: {e}") from e

    async def _get_service_health(self, service: str) -> list[dict[str, Any]]:
        """
        Get health information for a service.

        Args:
            service: Service name

        Returns:
            List of service health entries
        """
        self._ensure_initialized()
        assert self._client is not None

        params = self._build_params()

        try:
            response = await self._client.get(f"/v1/health/service/{service}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise ConsulDepProviderError(f"Health query failed: {e}") from e
        except httpx.RequestError as e:
            raise ConsulDepProviderError(f"Request failed: {e}") from e

    async def _get_connect_intentions(self, service: str | None = None) -> list[dict[str, Any]]:
        """
        Get Connect intentions (mesh dependencies).

        Args:
            service: Optional service name to filter by

        Returns:
            List of intention objects
        """
        self._ensure_initialized()
        assert self._client is not None

        params = self._build_params()

        try:
            if service:
                # Get intentions for specific service
                response = await self._client.get(
                    "/v1/connect/intentions/match",
                    params={**params, "by": "source", "name": service},
                )
            else:
                # Get all intentions
                response = await self._client.get("/v1/connect/intentions", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Connect may not be enabled
                return []
            if e.response.status_code in (401, 403):
                raise ConsulDepProviderError(
                    f"Authentication failed: {e.response.status_code}"
                ) from e
            raise ConsulDepProviderError(f"Intentions query failed: {e}") from e
        except httpx.RequestError as e:
            raise ConsulDepProviderError(f"Request failed: {e}") from e

    def _parse_dependency_tags(self, tags: list[str]) -> list[tuple[str, DependencyType]]:
        """
        Parse service tags for dependency hints.

        Supported tag formats:
        - upstream:service-name
        - depends-on:service-name
        - db:database-name
        - queue:queue-name

        Args:
            tags: List of service tags

        Returns:
            List of (target_name, dep_type) tuples
        """
        deps: list[tuple[str, DependencyType]] = []

        for tag in tags:
            tag_lower = tag.lower()

            # upstream:service-name or depends-on:service-name
            if tag_lower.startswith(("upstream:", "depends-on:")):
                target = tag.split(":", 1)[1]
                deps.append((target, DependencyType.SERVICE))

            # db:name or database:name
            elif tag_lower.startswith(("db:", "database:")):
                target = tag.split(":", 1)[1]
                deps.append((target, DependencyType.DATASTORE))

            # queue:name or mq:name
            elif tag_lower.startswith(("queue:", "mq:")):
                target = tag.split(":", 1)[1]
                deps.append((target, DependencyType.QUEUE))

            # external:name
            elif tag_lower.startswith("external:"):
                target = tag.split(":", 1)[1]
                deps.append((target, DependencyType.EXTERNAL))

        return deps

    def _infer_dependency_type(self, service_name: str) -> DependencyType:
        """
        Infer dependency type from service name.

        Args:
            service_name: Service name

        Returns:
            Inferred DependencyType
        """
        name_lower = service_name.lower()

        # Database patterns
        if any(
            db in name_lower
            for db in ("postgres", "mysql", "mongo", "redis", "elastic", "cassandra")
        ):
            return DependencyType.DATASTORE

        # Queue patterns
        if any(q in name_lower for q in ("kafka", "rabbitmq", "sqs", "nats", "pulsar")):
            return DependencyType.QUEUE

        return DependencyType.SERVICE

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover upstream dependencies for a service.

        Discovers from:
        - Service tags with dependency hints
        - Connect intentions (if enabled)

        Args:
            service: Service name to find dependencies for

        Returns:
            List of discovered dependencies
        """
        deps: list[DiscoveredDependency] = []

        # Get service health info (includes tags and metadata)
        health_entries = await self._get_service_health(service)

        if health_entries:
            # Extract tags from service entries
            all_tags: set[str] = set()
            for entry in health_entries:
                svc = entry.get("Service", {})
                tags = svc.get("Tags", [])
                all_tags.update(tags)

            # Parse dependency tags
            tag_deps = self._parse_dependency_tags(list(all_tags))
            for target, dep_type in tag_deps:
                deps.append(
                    DiscoveredDependency(
                        source_service=service,
                        target_service=target,
                        provider=self.name,
                        dep_type=dep_type,
                        confidence=0.80,
                        metadata={
                            "source": "service_tag",
                            "datacenter": self.datacenter,
                        },
                        raw_source=service,
                        raw_target=target,
                    )
                )

            # Extract dependencies from service metadata
            for entry in health_entries:
                svc = entry.get("Service", {})
                meta = svc.get("Meta", {})

                # Check for explicit dependency metadata
                if "dependencies" in meta:
                    dep_list = meta["dependencies"]
                    if isinstance(dep_list, str):
                        dep_list = [d.strip() for d in dep_list.split(",")]
                    for target in dep_list:
                        if target:
                            deps.append(
                                DiscoveredDependency(
                                    source_service=service,
                                    target_service=target,
                                    provider=self.name,
                                    dep_type=self._infer_dependency_type(target),
                                    confidence=0.85,
                                    metadata={
                                        "source": "service_meta",
                                        "datacenter": self.datacenter,
                                    },
                                    raw_source=service,
                                    raw_target=target,
                                )
                            )

        # Discover from Connect intentions
        intention_deps = await self._discover_from_intentions(service)
        deps.extend(intention_deps)

        return self._deduplicate(deps)

    async def _discover_from_intentions(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover dependencies from Connect intentions.

        Args:
            service: Source service name

        Returns:
            List of discovered dependencies from intentions
        """
        deps: list[DiscoveredDependency] = []

        try:
            # Get intentions where this service is the source
            intentions = await self._get_connect_intentions(service)

            # intentions can be a dict with service names as keys when using match API
            if isinstance(intentions, dict):
                # Format: {"destination": [intentions...]}
                for destination, intention_list in intentions.items():
                    for intention in intention_list:
                        action = intention.get("Action", "allow")
                        if action == "allow":
                            deps.append(
                                DiscoveredDependency(
                                    source_service=service,
                                    target_service=destination,
                                    provider=self.name,
                                    dep_type=DependencyType.SERVICE,
                                    confidence=0.95,
                                    metadata={
                                        "source": "connect_intention",
                                        "action": action,
                                        "datacenter": self.datacenter,
                                    },
                                    raw_source=service,
                                    raw_target=destination,
                                )
                            )
            elif isinstance(intentions, list):
                for intention in intentions:
                    source_name = intention.get("SourceName", "")
                    dest_name = intention.get("DestinationName", "")
                    action = intention.get("Action", "allow")

                    # Only include allow intentions where we're the source
                    if source_name == service and action == "allow" and dest_name:
                        deps.append(
                            DiscoveredDependency(
                                source_service=service,
                                target_service=dest_name,
                                provider=self.name,
                                dep_type=DependencyType.SERVICE,
                                confidence=0.95,
                                metadata={
                                    "source": "connect_intention",
                                    "action": action,
                                    "datacenter": self.datacenter,
                                },
                                raw_source=service,
                                raw_target=dest_name,
                            )
                        )

        except ConsulDepProviderError:
            # Connect may not be enabled, that's ok
            pass

        return deps

    async def discover_downstream(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover downstream dependencies (what calls this service).

        Uses Connect intentions to find services allowed to call this one.

        Args:
            service: Service name to find dependents for

        Returns:
            List of discovered dependencies
        """
        deps: list[DiscoveredDependency] = []

        try:
            # Get all intentions
            intentions = await self._get_connect_intentions()

            for intention in intentions:
                source_name = intention.get("SourceName", "")
                dest_name = intention.get("DestinationName", "")
                action = intention.get("Action", "allow")

                # Include intentions where we're the destination
                if dest_name == service and action == "allow" and source_name:
                    deps.append(
                        DiscoveredDependency(
                            source_service=source_name,
                            target_service=service,
                            provider=self.name,
                            dep_type=DependencyType.SERVICE,
                            confidence=0.95,
                            metadata={
                                "source": "connect_intention",
                                "action": action,
                                "datacenter": self.datacenter,
                            },
                            raw_source=source_name,
                            raw_target=service,
                        )
                    )

        except ConsulDepProviderError:
            # Connect may not be enabled
            pass

        return self._deduplicate(deps)

    async def list_services(self) -> list[str]:
        """
        List all services in Consul catalog.

        Returns:
            List of service names
        """
        catalog = await self._get_catalog_services()
        # Exclude Consul itself
        services = [name for name in catalog.keys() if name != "consul"]
        return sorted(services)

    async def health_check(self) -> ProviderHealth:
        """
        Check Consul API connectivity.

        Returns:
            Provider health status
        """
        self._ensure_initialized()
        assert self._client is not None

        try:
            # Check leader status
            response = await self._client.get("/v1/status/leader")
            response.raise_for_status()

            leader = response.text.strip().strip('"')
            if leader:
                return ProviderHealth(
                    healthy=True,
                    message=f"Connected to Consul at {self.url} (leader: {leader})",
                )
            else:
                return ProviderHealth(
                    healthy=False,
                    message="Consul cluster has no leader",
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
        Get service attributes from Consul.

        Args:
            service: Service name

        Returns:
            Dictionary of attributes
        """
        health_entries = await self._get_service_health(service)

        if not health_entries:
            return {}

        # Aggregate from first healthy entry
        entry = health_entries[0]
        svc = entry.get("Service", {})
        node = entry.get("Node", {})

        return {
            "name": svc.get("Service"),
            "id": svc.get("ID"),
            "address": svc.get("Address"),
            "port": svc.get("Port"),
            "tags": svc.get("Tags", []),
            "meta": svc.get("Meta", {}),
            "datacenter": node.get("Datacenter"),
            "node": node.get("Node"),
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
