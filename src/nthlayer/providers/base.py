from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ProviderResourceSchema:
    """Schema metadata describing a provider-managed resource."""

    name: str
    description: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class PlanChange:
    """Represents a single change detected during planning."""

    action: Literal["create", "update", "delete"]
    details: dict[str, Any]


@dataclass(frozen=True)
class PlanResult:
    """Plan result summarising pending changes."""

    changes: list[PlanChange]
    metadata: dict[str, Any] | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


@dataclass(frozen=True)
class ProviderHealth:
    status: Literal["healthy", "degraded", "unreachable"]
    details: str | None = None


class ProviderResource(Protocol):
    """Contract for provider-managed resources."""

    def schema(self) -> ProviderResourceSchema:
        ...

    async def plan(self, desired_state: dict[str, Any]) -> PlanResult:
        ...

    async def apply(
        self,
        desired_state: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> None:
        ...

    async def drift(self, desired_state: dict[str, Any]) -> PlanResult:
        ...


class Provider(Protocol):
    """Minimal provider interface exposed to NthLayer core."""

    name: str

    async def health_check(self) -> ProviderHealth:
        ...

    async def resources(self) -> list[ProviderResourceSchema]:
        ...
