"""
Ownership resolution for services.

Aggregates ownership signals from multiple sources (PagerDuty, Backstage,
Kubernetes, CODEOWNERS, etc.) with confidence-weighted ranking.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nthlayer.identity.ownership_providers.base import BaseOwnershipProvider


class OwnershipSource(Enum):
    """Sources of ownership attribution, ranked by default confidence."""

    DECLARED = "declared"  # service.yaml explicit declaration (1.0)
    PAGERDUTY = "pagerduty"  # PagerDuty service ownership (0.95)
    OPSGENIE = "opsgenie"  # OpsGenie service ownership (0.90)
    BACKSTAGE = "backstage"  # Backstage/Cortex catalog (0.90)
    CODEOWNERS = "codeowners"  # GitHub/GitLab CODEOWNERS (0.85)
    CLOUD_TAGS = "cloud_tags"  # AWS/GCP/Azure resource tags (0.80)
    KUBERNETES = "kubernetes"  # K8s labels/annotations (0.75)
    SLACK_CHANNEL = "slack"  # Slack channel naming (0.60)
    COST_CENTER = "cost_center"  # FinOps attribution (0.70)
    GIT_ACTIVITY = "git_activity"  # Most active contributors (0.40)


# Default confidence scores per source
DEFAULT_CONFIDENCE: dict[OwnershipSource, float] = {
    OwnershipSource.DECLARED: 1.0,
    OwnershipSource.PAGERDUTY: 0.95,
    OwnershipSource.OPSGENIE: 0.90,
    OwnershipSource.BACKSTAGE: 0.90,
    OwnershipSource.CODEOWNERS: 0.85,
    OwnershipSource.CLOUD_TAGS: 0.80,
    OwnershipSource.KUBERNETES: 0.75,
    OwnershipSource.COST_CENTER: 0.70,
    OwnershipSource.SLACK_CHANNEL: 0.60,
    OwnershipSource.GIT_ACTIVITY: 0.40,
}


@dataclass
class OwnershipSignal:
    """A single ownership signal from a source."""

    source: OwnershipSource
    owner: str
    confidence: float
    owner_type: str = "team"  # "team", "individual", "group"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source": self.source.value,
            "owner": self.owner,
            "confidence": self.confidence,
            "owner_type": self.owner_type,
            "metadata": self.metadata,
        }


@dataclass
class OwnershipAttribution:
    """Resolved ownership for a service."""

    service: str
    owner: str | None = None
    owner_type: str = "team"
    confidence: float = 0.0
    source: OwnershipSource | None = None
    signals: list[OwnershipSignal] = field(default_factory=list)

    # Contact information aggregated from signals
    slack_channel: str | None = None
    email: str | None = None
    pagerduty_escalation: str | None = None
    opsgenie_team: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "service": self.service,
            "owner": self.owner,
            "owner_type": self.owner_type,
            "confidence": self.confidence,
            "source": self.source.value if self.source else None,
            "signals": [s.to_dict() for s in self.signals],
            "contact": {
                "slack_channel": self.slack_channel,
                "email": self.email,
                "pagerduty_escalation": self.pagerduty_escalation,
                "opsgenie_team": self.opsgenie_team,
            },
        }


@dataclass
class OwnershipResolver:
    """
    Resolves service ownership from multiple sources.

    Aggregates ownership signals from various providers and ranks them
    by confidence to determine the canonical owner.
    """

    providers: list[BaseOwnershipProvider] = field(default_factory=list)

    def add_provider(self, provider: BaseOwnershipProvider) -> None:
        """Add an ownership provider."""
        self.providers.append(provider)

    async def resolve(
        self,
        service: str,
        declared_owner: str | None = None,
        declared_team: str | None = None,
    ) -> OwnershipAttribution:
        """
        Resolve ownership by querying all providers and ranking signals.

        Algorithm:
        1. Add declared owner signal if present (confidence 1.0)
        2. Query all providers concurrently
        3. Collect all signals
        4. Rank by confidence, select highest
        5. Aggregate contact info from all signals

        Args:
            service: Service name to resolve ownership for
            declared_owner: Explicit owner from service.yaml (email/contact)
            declared_team: Explicit team from service.yaml

        Returns:
            OwnershipAttribution with resolved owner and all signals
        """
        signals: list[OwnershipSignal] = []

        # Add declared signals (highest priority)
        if declared_team:
            signals.append(
                OwnershipSignal(
                    source=OwnershipSource.DECLARED,
                    owner=declared_team,
                    confidence=1.0,
                    owner_type="team",
                    metadata={"field": "team"},
                )
            )
        elif declared_owner:
            # Owner without team - treat as individual
            signals.append(
                OwnershipSignal(
                    source=OwnershipSource.DECLARED,
                    owner=declared_owner,
                    confidence=1.0,
                    owner_type="individual",
                    metadata={"field": "owner"},
                )
            )

        # Query all providers concurrently
        if self.providers:
            tasks = [provider.get_owner(service) for provider in self.providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, OwnershipSignal):
                    signals.append(result)
                # Silently ignore exceptions - providers may fail

        # Build attribution
        attribution = OwnershipAttribution(
            service=service,
            signals=sorted(signals, key=lambda s: s.confidence, reverse=True),
        )

        # Select highest confidence signal as resolved owner
        if signals:
            best = max(signals, key=lambda s: s.confidence)
            attribution.owner = best.owner
            attribution.owner_type = best.owner_type
            attribution.confidence = best.confidence
            attribution.source = best.source

        # Aggregate contact info from all signals
        self._aggregate_contact_info(attribution)

        return attribution

    def _aggregate_contact_info(self, attribution: OwnershipAttribution) -> None:
        """Extract contact information from all signals."""
        for signal in attribution.signals:
            metadata = signal.metadata

            # PagerDuty escalation
            if signal.source == OwnershipSource.PAGERDUTY and "escalation_policy" in metadata:
                attribution.pagerduty_escalation = metadata["escalation_policy"]

            # OpsGenie team
            if signal.source == OwnershipSource.OPSGENIE and "team_id" in metadata:
                attribution.opsgenie_team = metadata.get("team_name", metadata["team_id"])

            # Slack channel (from various sources)
            if "slack_channel" in metadata and not attribution.slack_channel:
                attribution.slack_channel = metadata["slack_channel"]

            # Email (from various sources)
            if "email" in metadata and not attribution.email:
                attribution.email = metadata["email"]

            # Infer Slack channel from team name if not found
            if not attribution.slack_channel and attribution.owner:
                attribution.slack_channel = f"#team-{attribution.owner}"


def create_demo_attribution() -> OwnershipAttribution:
    """Create demo ownership attribution for testing."""
    return OwnershipAttribution(
        service="payment-api",
        owner="payments-team",
        owner_type="team",
        confidence=1.0,
        source=OwnershipSource.DECLARED,
        signals=[
            OwnershipSignal(
                source=OwnershipSource.DECLARED,
                owner="payments-team",
                confidence=1.0,
                owner_type="team",
                metadata={"field": "team"},
            ),
            OwnershipSignal(
                source=OwnershipSource.PAGERDUTY,
                owner="payments-team",
                confidence=0.95,
                owner_type="team",
                metadata={"escalation_policy": "payments-escalation"},
            ),
            OwnershipSignal(
                source=OwnershipSource.BACKSTAGE,
                owner="team-payments",
                confidence=0.90,
                owner_type="team",
                metadata={"namespace": "default"},
            ),
            OwnershipSignal(
                source=OwnershipSource.CODEOWNERS,
                owner="@acme/payments",
                confidence=0.85,
                owner_type="group",
                metadata={"file": ".github/CODEOWNERS"},
            ),
            OwnershipSignal(
                source=OwnershipSource.KUBERNETES,
                owner="payments",
                confidence=0.75,
                owner_type="team",
                metadata={"label": "team=payments", "namespace": "default"},
            ),
        ],
        slack_channel="#team-payments",
        pagerduty_escalation="payments-escalation",
    )
