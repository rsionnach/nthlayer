"""
Kubernetes ownership provider.

Extracts ownership from Kubernetes resource labels and annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource
from nthlayer.identity.ownership_providers.base import (
    BaseOwnershipProvider,
    OwnershipProviderHealth,
)

# Labels to check for ownership (in priority order)
OWNER_LABELS = [
    "owner",
    "team",
    "app.kubernetes.io/managed-by",
    "app.kubernetes.io/part-of",
]

# Annotations to check
OWNER_ANNOTATIONS = [
    "owner",
    "team",
    "nthlayer.io/owner",
    "nthlayer.io/team",
]


@dataclass
class KubernetesOwnershipProvider(BaseOwnershipProvider):
    """
    Ownership provider that queries Kubernetes resources.

    Checks deployment/service labels for ownership information.

    Attributes:
        namespace: Kubernetes namespace to search (None = all)
    """

    namespace: str | None = None

    # Internal provider instance (KubernetesDepProvider, typed as Any to avoid import)
    _provider: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "kubernetes"

    @property
    def source(self) -> OwnershipSource:
        return OwnershipSource.KUBERNETES

    @property
    def default_confidence(self) -> float:
        return 0.75

    def _get_provider(self) -> Any:
        """Lazy-load the Kubernetes dependency provider."""
        if self._provider is None:
            from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

            self._provider = KubernetesDepProvider(
                namespace=self.namespace,
            )
        return self._provider

    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """Get ownership from Kubernetes resource labels."""
        provider = self._get_provider()

        try:
            # Use get_service_attributes to get labels/annotations
            attrs = await provider.get_service_attributes(service)

            if not attrs:
                return None

            labels = attrs.get("labels", {})
            annotations = attrs.get("annotations", {})

            # Check labels first
            for label_key in OWNER_LABELS:
                if label_key in labels:
                    owner = labels[label_key]
                    return OwnershipSignal(
                        source=self.source,
                        owner=owner,
                        confidence=self.default_confidence,
                        owner_type="team",
                        metadata={
                            "label": f"{label_key}={owner}",
                            "namespace": attrs.get("namespace", "default"),
                        },
                    )

            # Check annotations
            for annotation_key in OWNER_ANNOTATIONS:
                if annotation_key in annotations:
                    owner = annotations[annotation_key]
                    return OwnershipSignal(
                        source=self.source,
                        owner=owner,
                        confidence=self.default_confidence * 0.9,  # Slightly lower for annotations
                        owner_type="team",
                        metadata={
                            "annotation": f"{annotation_key}={owner}",
                            "namespace": attrs.get("namespace", "default"),
                        },
                    )

            return None

        except Exception:
            # Provider errors are handled gracefully
            return None

    async def health_check(self) -> OwnershipProviderHealth:
        """Check Kubernetes API connectivity."""
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
