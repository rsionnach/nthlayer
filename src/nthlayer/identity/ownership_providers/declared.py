"""
Declared ownership provider.

Provides ownership from explicit service.yaml declarations.
This provider is used internally by the resolver for declared owners.
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
class DeclaredOwnershipProvider(BaseOwnershipProvider):
    """
    Ownership provider for explicit declarations.

    Used to wrap service.yaml team/owner fields as ownership signals.
    This is typically used internally by the resolver.

    Attributes:
        declarations: Dict mapping service name to owner info
    """

    declarations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "declared"

    @property
    def source(self) -> OwnershipSource:
        return OwnershipSource.DECLARED

    @property
    def default_confidence(self) -> float:
        return 1.0

    def set_declaration(
        self,
        service: str,
        team: str | None = None,
        owner: str | None = None,
    ) -> None:
        """
        Set a declaration for a service.

        Args:
            service: Service name
            team: Team name (takes precedence)
            owner: Owner email/contact
        """
        self.declarations[service] = {
            "team": team,
            "owner": owner,
        }

    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """Get ownership from declared values."""
        if service not in self.declarations:
            return None

        decl = self.declarations[service]
        team = decl.get("team")
        owner = decl.get("owner")

        if team:
            return OwnershipSignal(
                source=self.source,
                owner=team,
                confidence=self.default_confidence,
                owner_type="team",
                metadata={"field": "team"},
            )
        elif owner:
            return OwnershipSignal(
                source=self.source,
                owner=owner,
                confidence=self.default_confidence,
                owner_type="individual",
                metadata={"field": "owner"},
            )

        return None

    async def health_check(self) -> OwnershipProviderHealth:
        """Declared provider is always healthy."""
        return OwnershipProviderHealth(
            healthy=True,
            message="Declared provider ready",
        )
