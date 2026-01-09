"""
Base class for ownership providers.

All ownership providers must implement get_owner() and health_check() methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource


@dataclass
class OwnershipProviderHealth:
    """Health status of an ownership provider."""

    healthy: bool
    message: str
    latency_ms: float | None = None


class BaseOwnershipProvider(ABC):
    """
    Abstract base class for ownership providers.

    All providers must implement:
    - get_owner(): Get ownership signal for a service
    - health_check(): Verify provider connectivity
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for identification."""

    @property
    @abstractmethod
    def source(self) -> OwnershipSource:
        """The ownership source type."""

    @property
    @abstractmethod
    def default_confidence(self) -> float:
        """Default confidence score for this provider."""

    @abstractmethod
    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """
        Get ownership signal for a service.

        Args:
            service: Service name to look up

        Returns:
            OwnershipSignal if owner found, None otherwise
        """

    @abstractmethod
    async def health_check(self) -> OwnershipProviderHealth:
        """
        Check provider connectivity and health.

        Returns:
            OwnershipProviderHealth status
        """
