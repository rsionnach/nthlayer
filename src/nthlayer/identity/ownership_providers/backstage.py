"""
Backstage ownership provider.

Extracts ownership from Backstage catalog entity owner field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource
from nthlayer.identity.ownership_providers.base import (
    BaseOwnershipProvider,
    OwnershipProviderHealth,
)


@dataclass
class BackstageOwnershipProvider(BaseOwnershipProvider):
    """
    Ownership provider that queries Backstage catalog.

    Wraps the existing BackstageDepProvider to extract spec.owner field.

    Attributes:
        url: Backstage base URL
        token: Bearer token for authentication (optional)
        namespace: Filter by namespace (optional)
    """

    url: str
    token: str | None = None
    namespace: str | None = None

    # Internal provider instance (BackstageDepProvider, typed as Any to avoid import)
    _provider: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "backstage"

    @property
    def source(self) -> OwnershipSource:
        return OwnershipSource.BACKSTAGE

    @property
    def default_confidence(self) -> float:
        return 0.90

    def _get_provider(self) -> Any:
        """Lazy-load the Backstage dependency provider."""
        if self._provider is None:
            from nthlayer.dependencies.providers.backstage import BackstageDepProvider

            self._provider = BackstageDepProvider(
                url=self.url,
                token=self.token,
                namespace=self.namespace,
            )
        return self._provider

    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """Get ownership from Backstage catalog."""
        provider = self._get_provider()

        try:
            # Use get_service_attributes which extracts owner
            attrs = await provider.get_service_attributes(service)

            if not attrs:
                return None

            owner = attrs.get("owner")
            if not owner:
                return None

            # Determine owner type from format
            owner_type = "team"
            if owner.startswith("user:"):
                owner_type = "individual"
                owner = owner.replace("user:", "").split("/")[-1]
            elif owner.startswith("group:"):
                owner_type = "group"
                owner = owner.replace("group:", "").split("/")[-1]

            return OwnershipSignal(
                source=self.source,
                owner=owner,
                confidence=self.default_confidence,
                owner_type=owner_type,
                metadata={
                    "namespace": attrs.get("namespace", "default"),
                    "lifecycle": attrs.get("lifecycle"),
                    "system": attrs.get("system"),
                },
            )

        except Exception:
            # Provider errors are handled gracefully
            return None

    async def health_check(self) -> OwnershipProviderHealth:
        """Check Backstage API connectivity."""
        provider = self._get_provider()

        try:
            health = await provider.health_check()
            return OwnershipProviderHealth(
                healthy=health.healthy,
                message=health.message,
                latency_ms=health.latency_ms,
            )
        except Exception as e:
            return OwnershipProviderHealth(
                healthy=False,
                message=f"Health check failed: {e}",
            )
