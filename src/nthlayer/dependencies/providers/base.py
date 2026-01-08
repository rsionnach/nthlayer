"""
Base class for dependency discovery providers.

All dependency providers must implement discover(), list_services(),
and health_check() methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

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

    @abstractmethod
    async def discover(
        self,
        service: str,
    ) -> list[DiscoveredDependency]:
        """
        Discover dependencies for a service.

        Args:
            service: Service name (may be raw or canonical)

        Returns:
            List of discovered dependencies
        """

    @abstractmethod
    async def list_services(self) -> list[str]:
        """
        List all services known to this provider.

        Returns:
            List of service names (raw, provider-specific)
        """

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """
        Check provider connectivity and health.

        Returns:
            ProviderHealth status
        """

    async def get_service_attributes(
        self,
        service: str,
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
