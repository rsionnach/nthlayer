"""
etcd dependency provider.

Discovers service dependencies from etcd key-value store.

Supports:
- Service registration under configurable prefix (0.85 confidence)
- JSON metadata with dependency lists (0.80 confidence)
- Typed dependency declarations (0.85 confidence)

Environment variables:
- NTHLAYER_ETCD_HOST: etcd host
- NTHLAYER_ETCD_PORT: etcd port
- NTHLAYER_ETCD_PREFIX: Service key prefix

Requires optional dependency: etcd3
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

# Optional etcd3 import
try:
    import etcd3

    ETCD3_AVAILABLE = True
except ImportError:
    ETCD3_AVAILABLE = False
    etcd3 = None  # type: ignore


class EtcdDepProviderError(Exception):
    """etcd provider error."""

    pass


@dataclass
class EtcdDepProvider(BaseDepProvider):
    """
    Dependency provider that discovers dependencies from etcd.

    Queries etcd key-value store to find:
    - Registered services under the prefix path
    - Service metadata with dependency declarations
    - Explicit dependency lists in JSON values

    Expected key structure:
    /services/<service-name> -> JSON payload

    Expected value format:
    {
        "name": "service-name",
        "endpoints": ["10.0.0.1:8080"],
        "dependencies": ["dep1", "dep2"],
        "metadata": {...}
    }

    Attributes:
        host: etcd host (default: localhost)
        port: etcd port (default: 2379)
        prefix: Service key prefix (default: /services)
        username: Username for authentication (optional)
        password: Password for authentication (optional)
        timeout: Connection timeout in seconds
    """

    host: str = "localhost"
    port: int = 2379
    prefix: str = "/services"
    username: str | None = None
    password: str | None = None
    timeout: float = 30.0

    # Private fields
    _client: Any = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate etcd3 is available."""
        if not ETCD3_AVAILABLE:
            raise EtcdDepProviderError(
                "etcd3 library is required for etcd provider. " "Install with: pip install etcd3"
            )

    @property
    def name(self) -> str:
        """Provider name."""
        return "etcd"

    def _ensure_initialized(self) -> None:
        """Initialize etcd client if not already done."""
        if self._initialized:
            return

        if not ETCD3_AVAILABLE:
            raise EtcdDepProviderError("etcd3 library not available")

        self._client = etcd3.client(
            host=self.host,
            port=self.port,
            user=self.username,
            password=self.password,
            timeout=self.timeout,
        )
        self._initialized = True

    async def _close(self) -> None:
        """Close etcd client."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False

    def _get_service_key(self, service: str) -> str:
        """Get the key path for a service."""
        prefix = self.prefix.rstrip("/")
        return f"{prefix}/{service}"

    def _parse_service_data(self, data: bytes | str | None) -> dict[str, Any]:
        """
        Parse service JSON data.

        Args:
            data: Raw key value

        Returns:
            Parsed service dictionary
        """
        try:
            if not data:
                return {}
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
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

    def _parse_dependencies(self, service_data: dict[str, Any]) -> list[tuple[str, DependencyType]]:
        """
        Parse dependencies from service data.

        Args:
            service_data: Parsed service JSON

        Returns:
            List of (target_name, dep_type) tuples
        """
        deps: list[tuple[str, DependencyType]] = []

        # Check for dependencies list
        dependencies = service_data.get("dependencies", [])
        if isinstance(dependencies, str):
            dependencies = [d.strip() for d in dependencies.split(",")]

        for dep in dependencies:
            if dep:
                deps.append((dep, self._infer_dependency_type(dep)))

        # Check for typed dependencies
        for dep_type, key in [
            (DependencyType.DATASTORE, "databases"),
            (DependencyType.DATASTORE, "datastores"),
            (DependencyType.QUEUE, "queues"),
            (DependencyType.QUEUE, "messaging"),
            (DependencyType.EXTERNAL, "external"),
            (DependencyType.EXTERNAL, "external_apis"),
            (DependencyType.SERVICE, "services"),
            (DependencyType.SERVICE, "upstream"),
        ]:
            type_deps = service_data.get(key, [])
            if isinstance(type_deps, str):
                type_deps = [d.strip() for d in type_deps.split(",")]
            for dep in type_deps:
                if dep:
                    deps.append((dep, dep_type))

        return deps

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """
        Discover upstream dependencies for a service.

        Reads service key from etcd and extracts dependencies from JSON value.

        Args:
            service: Service name to find dependencies for

        Returns:
            List of discovered dependencies
        """
        self._ensure_initialized()
        deps: list[DiscoveredDependency] = []

        try:
            key = self._get_service_key(service)
            value, metadata = self._client.get(key)

            if not value:
                return deps

            service_data = self._parse_service_data(value)

            if not service_data:
                return deps

            # Parse dependencies
            parsed_deps = self._parse_dependencies(service_data)

            for target, dep_type in parsed_deps:
                # Determine confidence based on source
                confidence = 0.85 if dep_type != DependencyType.SERVICE else 0.80

                deps.append(
                    DiscoveredDependency(
                        source_service=service,
                        target_service=target,
                        provider=self.name,
                        dep_type=dep_type,
                        confidence=confidence,
                        metadata={
                            "source": "etcd_key",
                            "key": key,
                        },
                        raw_source=service,
                        raw_target=target,
                    )
                )

        except Exception as e:
            if "connection" in str(e).lower():
                raise EtcdDepProviderError(f"etcd connection error: {e}") from e
            # Key not found or other non-fatal errors
            pass

        return self._deduplicate(deps)

    async def list_services(self) -> list[str]:
        """
        List all services in etcd registry.

        Returns:
            List of service names
        """
        self._ensure_initialized()

        try:
            prefix = self.prefix.rstrip("/") + "/"
            services: list[str] = []

            # Get all keys with prefix
            for _, metadata in self._client.get_prefix(prefix):
                if metadata and metadata.key:
                    key = metadata.key
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")

                    # Extract service name from key
                    # Key format: /services/service-name or /services/service-name/sub
                    relative = key[len(prefix) :]
                    if "/" in relative:
                        # Get top-level service name
                        service_name = relative.split("/")[0]
                    else:
                        service_name = relative

                    if service_name and not service_name.startswith("_"):
                        services.append(service_name)

            return sorted(set(services))

        except Exception as e:
            raise EtcdDepProviderError(f"etcd error: {e}") from e

    async def health_check(self) -> ProviderHealth:
        """
        Check etcd connectivity.

        Returns:
            Provider health status
        """
        if not ETCD3_AVAILABLE:
            return ProviderHealth(
                healthy=False,
                message="etcd3 library not installed",
            )

        try:
            self._ensure_initialized()

            # Check cluster health by getting status
            status = self._client.status()

            if status:
                leader = getattr(status, "leader", None)
                version = getattr(status, "version", "unknown")
                return ProviderHealth(
                    healthy=True,
                    message=f"Connected to etcd at {self.host}:{self.port} "
                    f"(version: {version}, leader: {leader})",
                )
            else:
                return ProviderHealth(
                    healthy=False,
                    message="etcd cluster status unavailable",
                )

        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"etcd connection failed: {e}",
            )

    async def get_service_attributes(self, service: str) -> dict[str, Any]:
        """
        Get service attributes from etcd.

        Args:
            service: Service name

        Returns:
            Dictionary of attributes
        """
        self._ensure_initialized()

        try:
            key = self._get_service_key(service)
            value, metadata = self._client.get(key)

            if not value:
                return {}

            service_data = self._parse_service_data(value)

            return {
                "name": service_data.get("name", service),
                "key": key,
                "endpoints": service_data.get("endpoints", []),
                "metadata": service_data.get("metadata", {}),
                "version": metadata.version if metadata else None,
                "mod_revision": metadata.mod_revision if metadata else None,
            }

        except Exception:
            return {}

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
