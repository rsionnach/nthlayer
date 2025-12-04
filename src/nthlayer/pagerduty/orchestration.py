"""
PagerDuty Event Orchestration management.

Creates service-level event orchestration rules for alert routing overrides.
Uses service-level orchestrations which are available on all PagerDuty plans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RoutingRule:
    """A single routing rule for event orchestration."""

    label: str
    condition_field: str  # e.g., "event.custom_details.routing"
    condition_value: str  # e.g., "sre"
    escalation_policy_id: str


@dataclass
class OrchestrationResult:
    """Result of orchestration setup."""

    success: bool
    orchestration_id: str | None = None
    rules_created: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class EventOrchestrationManager:
    """
    Manages PagerDuty Event Orchestration rules.

    Creates service-level orchestrations to route alerts based on
    custom details (like routing: sre) to different escalation policies.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.pagerduty.com",
        timeout: float = 30.0,
    ):
        """
        Initialize the orchestration manager.

        Args:
            api_key: PagerDuty API key
            base_url: PagerDuty API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Token token={self.api_key}",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "EventOrchestrationManager":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def setup_service_orchestration(
        self,
        service_id: str,
        routing_rules: list[RoutingRule],
    ) -> OrchestrationResult:
        """
        Set up event orchestration for a service.

        Creates routing rules to override escalation policies based on
        alert metadata (e.g., routing: sre in custom_details).

        Args:
            service_id: PagerDuty service ID
            routing_rules: List of routing rules to create

        Returns:
            OrchestrationResult with status
        """
        if not routing_rules:
            return OrchestrationResult(
                success=True,
                warnings=["No routing rules provided, skipping orchestration setup"],
            )

        try:
            # Get or create service orchestration
            orchestration = self._get_or_create_service_orchestration(service_id)
            if not orchestration:
                return OrchestrationResult(
                    success=False,
                    error="Failed to get or create service orchestration",
                )

            orchestration_id = orchestration["id"]

            # Update the orchestration with routing rules
            result = self._update_orchestration_rules(orchestration_id, service_id, routing_rules)

            return OrchestrationResult(
                success=result["success"],
                orchestration_id=orchestration_id,
                rules_created=len(routing_rules) if result["success"] else 0,
                error=result.get("error"),
            )

        except httpx.HTTPStatusError as e:
            return OrchestrationResult(
                success=False,
                error=f"PagerDuty API error: {e.response.status_code} - {e.response.text}",
            )
        except Exception as e:
            return OrchestrationResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    def _get_or_create_service_orchestration(self, service_id: str) -> dict[str, Any] | None:
        """
        Get existing service orchestration or create a new one.

        Args:
            service_id: PagerDuty service ID

        Returns:
            Orchestration data or None if failed
        """
        # Try to get existing orchestration
        try:
            response = self.client.get(f"/event_orchestrations/services/{service_id}")
            if response.status_code == 200:
                return response.json().get("orchestration_path", {})
        except httpx.HTTPStatusError:
            pass

        # Create new orchestration
        # Note: Service orchestrations are created automatically when
        # you first access them, but we need to set up the initial structure
        try:
            # First access creates the orchestration
            response = self.client.get(f"/event_orchestrations/services/{service_id}")
            response.raise_for_status()
            return response.json().get("orchestration_path", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get/create orchestration: {e}")
            return None

    def _update_orchestration_rules(
        self,
        orchestration_id: str,
        service_id: str,
        routing_rules: list[RoutingRule],
    ) -> dict[str, Any]:
        """
        Update orchestration with routing rules.

        Args:
            orchestration_id: Orchestration ID
            service_id: Service ID
            routing_rules: Rules to add

        Returns:
            Dict with success status and optional error
        """
        # Build rule sets
        rules = []
        for rule in routing_rules:
            rules.append(
                {
                    "label": rule.label,
                    "conditions": [
                        {
                            "expression": (
                                f"{rule.condition_field} matches '{rule.condition_value}'"
                            ),
                        }
                    ],
                    "actions": {
                        "escalation_policy": {
                            "id": rule.escalation_policy_id,
                            "type": "escalation_policy_reference",
                        },
                    },
                }
            )

        orchestration_payload = {
            "orchestration_path": {
                "sets": [
                    {
                        "id": "routing-overrides",
                        "rules": rules,
                    }
                ],
                "catch_all": {
                    "actions": {}  # Use service default escalation
                },
            }
        }

        try:
            response = self.client.put(
                f"/event_orchestrations/services/{service_id}",
                json=orchestration_payload,
            )
            response.raise_for_status()
            return {"success": True}
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"Failed to update orchestration: {e.response.text}",
            }

    def create_sre_routing_rule(
        self,
        sre_escalation_policy_id: str,
        label: str = "Route to SRE",
    ) -> RoutingRule:
        """
        Create a standard SRE routing rule.

        Routes alerts with routing=sre to the SRE escalation policy.

        Args:
            sre_escalation_policy_id: ID of SRE escalation policy
            label: Rule label

        Returns:
            RoutingRule for SRE routing
        """
        return RoutingRule(
            label=label,
            condition_field="event.custom_details.routing",
            condition_value="sre",
            escalation_policy_id=sre_escalation_policy_id,
        )

    def get_routing_rules_from_alerts(
        self,
        alerts: list[dict[str, Any]],
        sre_escalation_policy_id: str,
        team_escalation_policy_id: str,
    ) -> list[RoutingRule]:
        """
        Generate routing rules from alert definitions.

        Args:
            alerts: List of alert definitions with optional 'routing' field
            sre_escalation_policy_id: ID of SRE escalation policy
            team_escalation_policy_id: ID of team escalation policy

        Returns:
            List of routing rules for alerts with routing overrides
        """
        rules = []
        sre_alerts = [a for a in alerts if a.get("routing") == "sre"]

        if sre_alerts:
            # Create a single rule for all SRE-routed alerts
            rules.append(
                RoutingRule(
                    label="Route to SRE (routing override)",
                    condition_field="event.custom_details.routing",
                    condition_value="sre",
                    escalation_policy_id=sre_escalation_policy_id,
                )
            )

        # Could also create rules for specific alert names if needed
        # for alert in alerts:
        #     if alert.get("routing") == "sre":
        #         rules.append(RoutingRule(
        #             label=f"Route {alert['name']} to SRE",
        #             condition_field="event.custom_details.alert_name",
        #             condition_value=alert["name"],
        #             escalation_policy_id=sre_escalation_policy_id,
        #         ))

        return rules
