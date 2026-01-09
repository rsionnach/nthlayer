"""
PagerDuty ownership provider.

Extracts ownership from PagerDuty service → escalation policy → team chain.
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
class PagerDutyOwnershipProvider(BaseOwnershipProvider):
    """
    Ownership provider that queries PagerDuty.

    Traces: Service → Escalation Policy → Team
    "Who gets paged owns it"

    Attributes:
        api_token: PagerDuty API token
        base_url: PagerDuty API base URL (optional, for testing)
    """

    api_token: str | None = None
    base_url: str | None = None

    # Internal provider instance (PagerDutyProvider, typed as Any to avoid import)
    _provider: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "pagerduty"

    @property
    def source(self) -> OwnershipSource:
        return OwnershipSource.PAGERDUTY

    @property
    def default_confidence(self) -> float:
        return 0.95

    def _get_provider(self) -> Any:
        """Lazy-load the PagerDuty provider."""
        if self._provider is None:
            from nthlayer.providers.pagerduty import PagerDutyProvider

            kwargs: dict[str, Any] = {"api_token": self.api_token}
            if self.base_url:
                kwargs["base_url"] = self.base_url

            self._provider = PagerDutyProvider(**kwargs)
        return self._provider

    async def _find_service(self, service_name: str) -> dict[str, Any] | None:
        """Find a PagerDuty service by name."""
        provider = self._get_provider()

        try:
            # Search for services matching the name
            # PagerDuty API: GET /services?query=<name>
            response = await provider._request(
                "get",
                "/services",
                params={"query": service_name, "limit": 5},
            )

            services = response.get("services", [])

            # Find exact or close match
            for svc in services:
                if svc.get("name", "").lower() == service_name.lower():
                    return svc

            # Return first result if no exact match
            if services:
                return services[0]

            return None

        except Exception:
            return None

    async def _get_escalation_policy_team(
        self, escalation_policy_id: str
    ) -> tuple[str | None, str | None]:
        """Get team from escalation policy."""
        provider = self._get_provider()

        try:
            response = await provider._request(
                "get",
                f"/escalation_policies/{escalation_policy_id}",
            )

            policy = response.get("escalation_policy", {})
            policy_name = policy.get("name")

            # Get teams associated with policy
            teams = policy.get("teams", [])
            if teams:
                team = teams[0]
                return team.get("summary") or team.get("name"), policy_name

            # Fallback: extract team from policy name
            # Common pattern: "Team-Name Escalation" or "team-name-oncall"
            if policy_name:
                name = policy_name.lower()
                for suffix in [" escalation", "-escalation", "-oncall", " oncall"]:
                    if name.endswith(suffix):
                        team_name = policy_name[: -len(suffix)].strip()
                        return team_name, policy_name

            return None, policy_name

        except Exception:
            return None, None

    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """Get ownership from PagerDuty service."""
        if not self.api_token:
            return None

        # Find the service
        pd_service = await self._find_service(service)
        if not pd_service:
            return None

        # Get escalation policy
        escalation_policy = pd_service.get("escalation_policy", {})
        policy_id = escalation_policy.get("id")
        policy_name = escalation_policy.get("summary")

        if not policy_id:
            return None

        # Get team from escalation policy
        team_name, _ = await self._get_escalation_policy_team(policy_id)

        if team_name:
            return OwnershipSignal(
                source=self.source,
                owner=team_name,
                confidence=self.default_confidence,
                owner_type="team",
                metadata={
                    "service_id": pd_service.get("id"),
                    "service_name": pd_service.get("name"),
                    "escalation_policy": policy_name or policy_id,
                    "escalation_policy_id": policy_id,
                },
            )

        # Fallback: use escalation policy name as owner
        if policy_name:
            return OwnershipSignal(
                source=self.source,
                owner=policy_name,
                confidence=self.default_confidence * 0.9,  # Lower confidence for fallback
                owner_type="team",
                metadata={
                    "service_id": pd_service.get("id"),
                    "service_name": pd_service.get("name"),
                    "escalation_policy": policy_name,
                    "escalation_policy_id": policy_id,
                    "fallback": True,
                },
            )

        return None

    async def health_check(self) -> OwnershipProviderHealth:
        """Check PagerDuty API connectivity."""
        if not self.api_token:
            return OwnershipProviderHealth(
                healthy=False,
                message="No API token configured",
            )

        provider = self._get_provider()

        try:
            health = await provider.health_check()
            return OwnershipProviderHealth(
                healthy=health.status == "healthy",
                message=health.details if health.status != "healthy" else "Connected to PagerDuty",
            )
        except Exception as e:
            return OwnershipProviderHealth(
                healthy=False,
                message=f"Health check failed: {e}",
            )
