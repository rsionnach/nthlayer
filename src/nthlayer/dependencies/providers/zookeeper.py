"""
Zookeeper dependency provider.

Discovers service dependencies from Zookeeper-based service registries.

Supports:
- Curator-style service discovery (0.90 confidence)
- Service ZNode metadata with dependencies (0.85 confidence)
- Connection strings and endpoints (0.75 confidence)

Environment variables:
- NTHLAYER_ZOOKEEPER_HOSTS: Zookeeper connection string
- NTHLAYER_ZOOKEEPER_ROOT: Service registry root path

Requires optional dependency: kazoo
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from nthlayer.dependencies.models import (
    DependencyType,
    DiscoveredDependency,
)
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth

# Optional kazoo import
try:
    from kazoo.client import KazooClient, KazooState
    from kazoo.exceptions import NoNodeError, ZookeeperError

    KAZOO_AVAILABLE = True
except ImportError:
    KAZOO_AVAILABLE = False
    KazooClient = None  # type: ignore
    KazooState = None  # type: ignore
    NoNodeError = Exception  # type: ignore
    ZookeeperError = Exception  # type: ignore


class ZookeeperDepProviderError(Exception):
    """Zookeeper provider error."""

    pass


@dataclass
class ZookeeperDepProvider(BaseDepProvider):
    """
    Dependency provider that discovers dependencies from Zookeeper.

    Queries Zookeeper znodes to find:
    - Registered services under the root path
    - Service instance metadata (Curator format)
    - Explicit dependency declarations in service data

    Supports Curator-style service discovery format:
    /services/<service-name>/instances/<instance-id>

    Attributes:
        hosts: Zookeeper connection string (e.g., localhost:2181)
        root_path: Service registry root path (default: /services)
        timeout: Connection timeout in seconds
        auth: Optional tuple of (scheme, credential) for auth
    """

    hosts: str = "localhost:2181"
    root_path: str = "/services"
    timeout: float = 30.0
    auth: tuple[str, str] | None = None

    # Private fields
    _client: Any = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate kazoo is available."""
        if not KAZOO_AVAILABLE:
            raise ZookeeperDepProviderError(
                "kazoo library is required for Zookeeper provider. "
                "Install with: pip install kazoo"
            )

    @property
    def name(self) -> str:
        """Provider name."""
        return "zookeeper"

    def _ensure_initialized(self) -> None:
        """Initialize Zookeeper client if not already done."""
        if self._initialized:
            return

        if not KAZOO_AVAILABLE:
            raise ZookeeperDepProviderError("kazoo library not available")

        self._client = KazooClient(
            hosts=self.hosts,
            timeout=self.timeout,
        )

        if self.auth:
            self._client.add_auth(self.auth[0], self.auth[1])

        self._client.start(timeout=self.timeout)
        self._initialized = True

    async def _close(self) -> None:
        """Close Zookeeper client."""
        if self._client:
            self._client.stop()
            self._client.close()
            self._client = None
            self._initialized = False

    def _get_service_path(self, service: str) -> str:
        """Get the ZNode path for a service."""
        root = self.root_path.rstrip("/")
        return f"{root}/{service}"

    def _get_instances_path(self, service: str) -> str:
        """Get the instances path for a service."""
        return f"{self._get_service_path(service)}/instances"

    def _parse_curator_instance(self, data: bytes) -> dict[str, Any]:
        """
        Parse Curator ServiceInstance JSON format.

        Expected format:
        {
            "name": "service-name",
            "id": "instance-id",
            "address": "10.0.0.1",
            "port": 8080,
            "payload": {
                "dependencies": ["dep1", "dep2"],
                "metadata": {...}
            }
        }

        Args:
            data: Raw ZNode data

        Returns:
            Parsed instance dictionary
        """
        try:
            if not data:
                return {}
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

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

    def _parse_dependencies_from_payload(
        self, payload: dict[str, Any]
    ) -> list[tuple[str, DependencyType]]:
        """
        Parse dependencies from Curator payload.

        Args:
            payload: Instance payload dictionary

        Returns:
            List of (target_name, dep_type) tuples
        """
        deps: list[tuple[str, DependencyType]] = []

        # Check for explicit dependencies list
        dependencies = payload.get("dependencies", [])
        if isinstance(dependencies, str):
            dependencies = [d.strip() for d in dependencies.split(",")]

        for dep in dependencies:
            if dep:
                deps.append((dep, self._infer_dependency_type(dep)))

        # Check for typed dependencies
        for dep_type, key in [
            (DependencyType.DATASTORE, "databases"),
            (DependencyType.QUEUE, "queues"),
            (DependencyType.EXTERNAL, "external"),
        ]:
            type_deps = payload.get(key, [])
            if isinstance(type_deps, str):
                type_deps = [d.strip() for d in type_deps.split(",")]
            for dep in type_deps:
                if dep:
                    deps.append((dep, dep_type))

        return deps

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover upstream dependencies for a service.

        Reads service instances from Zookeeper and extracts dependencies
        from the Curator-style payload.

        Args:
            service: Service name to find dependencies for

        Returns:
            List of discovered dependencies
        """
        self._ensure_initialized()
        deps: list[DiscoveredDependency] = []

        try:
            # Check if service exists
            service_path = self._get_service_path(service)
            if not self._client.exists(service_path):
                return deps

            # Try to read service-level metadata first
            data, _ = self._client.get(service_path)
            if data:
                service_data = self._parse_curator_instance(data)
                payload = service_data.get("payload", service_data)
                payload_deps = self._parse_dependencies_from_payload(payload)
                for target, dep_type in payload_deps:
                    deps.append(
                        DiscoveredDependency(
                            source_service=service,
                            target_service=target,
                            provider=self.name,
                            dep_type=dep_type,
                            confidence=0.85,
                            metadata={
                                "source": "service_znode",
                                "path": service_path,
                            },
                            raw_source=service,
                            raw_target=target,
                        )
                    )

            # Try to read instance-level metadata
            instances_path = self._get_instances_path(service)
            if self._client.exists(instances_path):
                instances = self._client.get_children(instances_path)
                for instance_id in instances:
                    instance_path = f"{instances_path}/{instance_id}"
                    data, _ = self._client.get(instance_path)
                    instance_data = self._parse_curator_instance(data)

                    # Extract dependencies from payload
                    payload = instance_data.get("payload", {})
                    payload_deps = self._parse_dependencies_from_payload(payload)

                    for target, dep_type in payload_deps:
                        deps.append(
                            DiscoveredDependency(
                                source_service=service,
                                target_service=target,
                                provider=self.name,
                                dep_type=dep_type,
                                confidence=0.90,
                                metadata={
                                    "source": "curator_instance",
                                    "instance_id": instance_id,
                                    "path": instance_path,
                                },
                                raw_source=service,
                                raw_target=target,
                            )
                        )

        except NoNodeError:
            pass
        except ZookeeperError as e:
            raise ZookeeperDepProviderError(f"Zookeeper error: {e}") from e

        return self._deduplicate(deps)

    async def list_services(self) -> list[str]:
        """
        List all services in Zookeeper registry.

        Returns:
            List of service names
        """
        self._ensure_initialized()

        try:
            root = self.root_path.rstrip("/")
            if not self._client.exists(root):
                return []

            children = self._client.get_children(root)
            # Filter out non-service znodes (like "instances" paths at wrong level)
            services = [
                child for child in children if not child.startswith("_") and child != "instances"
            ]
            return sorted(services)

        except NoNodeError:
            return []
        except ZookeeperError as e:
            raise ZookeeperDepProviderError(f"Zookeeper error: {e}") from e

    async def health_check(self) -> ProviderHealth:
        """
        Check Zookeeper connectivity.

        Returns:
            Provider health status
        """
        if not KAZOO_AVAILABLE:
            return ProviderHealth(
                healthy=False,
                message="kazoo library not installed",
            )

        try:
            self._ensure_initialized()

            # Check if connected
            state = self._client.state
            if state == KazooState.CONNECTED:
                return ProviderHealth(
                    healthy=True,
                    message=f"Connected to Zookeeper at {self.hosts}",
                )
            else:
                return ProviderHealth(
                    healthy=False,
                    message=f"Zookeeper state: {state}",
                )

        except ZookeeperError as e:
            return ProviderHealth(
                healthy=False,
                message=f"Zookeeper error: {e}",
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Connection failed: {e}",
            )

    async def get_service_attributes(self, service: str) -> dict[str, Any]:
        """
        Get service attributes from Zookeeper.

        Args:
            service: Service name

        Returns:
            Dictionary of attributes
        """
        self._ensure_initialized()

        try:
            service_path = self._get_service_path(service)
            if not self._client.exists(service_path):
                return {}

            # Get service znode data
            data, stat = self._client.get(service_path)
            service_data = self._parse_curator_instance(data)

            # Get instance count
            instances_path = self._get_instances_path(service)
            instance_count = 0
            instances: list[dict[str, Any]] = []

            if self._client.exists(instances_path):
                instance_ids = self._client.get_children(instances_path)
                instance_count = len(instance_ids)

                # Get first instance details
                if instance_ids:
                    first_instance_path = f"{instances_path}/{instance_ids[0]}"
                    instance_data, _ = self._client.get(first_instance_path)
                    instances.append(self._parse_curator_instance(instance_data))

            return {
                "name": service_data.get("name", service),
                "path": service_path,
                "instance_count": instance_count,
                "instances": instances,
                "metadata": service_data.get("payload", {}).get("metadata", {}),
                "created": stat.created if stat else None,
                "modified": stat.last_modified if stat else None,
            }

        except NoNodeError:
            return {}
        except ZookeeperError as e:
            raise ZookeeperDepProviderError(f"Zookeeper error: {e}") from e

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
