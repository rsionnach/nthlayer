"""
PagerDuty resource management.

Creates and manages Teams, Schedules, Escalation Policies, and Services
with tier-based defaults and team-prefixed naming.

Uses the official PagerDuty Python SDK (pagerduty>=6.0.0).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone as timezone_module
from typing import Any

import pagerduty
from pagerduty import RestApiV2Client

from nthlayer.pagerduty.defaults import (
    get_escalation_config,
    get_schedule_config,
    get_schedules_for_tier,
)
from nthlayer.pagerduty.naming import (
    get_escalation_policy_name,
    get_schedule_name,
    get_service_name,
    get_team_name,
)

logger = logging.getLogger(__name__)


class PagerDutyAPIError(Exception):
    """Raised when PagerDuty API returns an error."""

    pass


@dataclass
class ResourceResult:
    """Result of a resource creation/lookup operation."""

    success: bool
    resource_id: str | None = None
    resource_name: str | None = None
    created: bool = False
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SetupResult:
    """Result of full PagerDuty setup for a service."""

    success: bool
    team_id: str | None = None
    schedule_ids: dict[str, str] = field(default_factory=dict)
    escalation_policy_id: str | None = None
    service_id: str | None = None
    service_url: str | None = None
    created_resources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PagerDutyResourceManager:
    """
    Manages PagerDuty resources with tier-based defaults.

    Creates teams, schedules, escalation policies, and services
    following naming conventions and tier-appropriate configurations.

    Uses the official PagerDuty Python SDK.
    """

    def __init__(
        self,
        api_key: str,
        default_from: str = "nthlayer@example.com",
        timeout: float = 30.0,
    ):
        """
        Initialize the resource manager with official PagerDuty SDK.

        Args:
            api_key: PagerDuty API key (v2 REST API token)
            default_from: Email for 'From' header (required for write operations)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.default_from = default_from
        self.timeout = timeout
        self._client: RestApiV2Client | None = None
        self._default_user_id: str | None = None

    @property
    def client(self) -> RestApiV2Client:
        """Lazy-initialize official PagerDuty SDK client."""
        if self._client is None:
            self._client = RestApiV2Client(
                self.api_key,
                default_from=self.default_from,
            )
        return self._client

    def close(self) -> None:
        """Close the SDK client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "PagerDutyResourceManager":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get_default_user_id(self) -> str | None:
        """Get the first user's ID to use as placeholder in schedules."""
        if self._default_user_id is not None:
            return self._default_user_id

        try:
            response = self.client.get("/users", params={"limit": 1})
            response.raise_for_status()
            users = response.json().get("users", [])
            if users:
                self._default_user_id = users[0]["id"]
                return self._default_user_id
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None

    def setup_service(
        self,
        service_name: str,
        team: str,
        tier: str,
        support_model: str = "self",
        tz: str = "America/New_York",
        sre_escalation_policy_id: str | None = None,
    ) -> SetupResult:
        """
        Set up a complete PagerDuty configuration for a service.

        Creates (if not exist):
        1. Team
        2. Schedules (primary, secondary, manager based on tier)
        3. Escalation policy
        4. Service

        Args:
            service_name: Name of the service
            team: Team that owns the service
            tier: Service tier (critical, high, medium, low)
            support_model: Support model (self, shared, sre, business_hours)
            tz: Timezone for schedules
            sre_escalation_policy_id: ID of SRE escalation policy (for shared/sre models)

        Returns:
            SetupResult with all created/found resource IDs
        """
        result = SetupResult(success=True)

        try:
            # Step 1: Create or find team (required for service)
            team_result = self.ensure_team(team)
            if team_result.success:
                result.team_id = team_result.resource_id
                if team_result.created:
                    result.created_resources.append(f"team:{team_result.resource_name}")
                result.warnings.extend(team_result.warnings)

                # Add API key owner as team manager
                current_user_id = self.get_current_user_id()
                if current_user_id and result.team_id:
                    member_result = self.add_team_member(
                        team_id=result.team_id,
                        user_id=current_user_id,
                        role="manager",
                    )
                    if member_result.success:
                        result.created_resources.append("team_membership:manager")
                    else:
                        result.warnings.append(f"Team membership: {member_result.error}")
            else:
                result.warnings.append(f"Team creation failed: {team_result.error}")

            # Step 2: Create schedules for this tier (optional - continue if fails)
            schedule_types = get_schedules_for_tier(tier)
            schedule_failures = []
            for schedule_type in schedule_types:
                schedule_result = self.ensure_schedule(
                    team=team,
                    schedule_type=schedule_type,
                    tier=tier,
                    support_model=support_model,
                    timezone=tz,
                )
                if schedule_result.success:
                    result.schedule_ids[schedule_type] = schedule_result.resource_id or ""
                    if schedule_result.created:
                        result.created_resources.append(f"schedule:{schedule_result.resource_name}")
                    result.warnings.extend(schedule_result.warnings)
                else:
                    schedule_failures.append(f"{schedule_type}: {schedule_result.error}")

            if schedule_failures:
                result.warnings.append(f"Some schedules failed: {'; '.join(schedule_failures)}")

            # Step 3: Create escalation policy or use default
            ep_result = self.ensure_escalation_policy(
                team=team,
                tier=tier,
                schedule_ids=result.schedule_ids,
            )
            if ep_result.success:
                result.escalation_policy_id = ep_result.resource_id
                if ep_result.created:
                    result.created_resources.append(f"escalation_policy:{ep_result.resource_name}")
                result.warnings.extend(ep_result.warnings)
            else:
                # Try to find default escalation policy
                default_ep = self._find_escalation_policy("Default")
                if default_ep:
                    result.escalation_policy_id = default_ep["id"]
                    result.warnings.append(
                        f"Custom escalation policy failed ({ep_result.error}), "
                        "using 'Default' policy"
                    )
                else:
                    result.errors.append(f"Escalation policy failed: {ep_result.error}")

            # Step 4: Create service (requires escalation policy)
            if result.escalation_policy_id:
                service_result = self.ensure_service(
                    service_name=service_name,
                    escalation_policy_id=result.escalation_policy_id,
                    team_id=result.team_id or "",
                    tier=tier,
                )
                if service_result.success:
                    result.service_id = service_result.resource_id
                    if service_result.created:
                        result.created_resources.append(f"service:{service_result.resource_name}")
                    result.warnings.extend(service_result.warnings)
                else:
                    result.errors.append(f"Service creation failed: {service_result.error}")
            else:
                result.errors.append("Cannot create service: no escalation policy available")

            # Get service URL
            if result.service_id:
                service_data = self._find_service_by_id(result.service_id)
                if service_data:
                    result.service_url = service_data.get("html_url")

            # Set overall success based on whether service was created
            result.success = result.service_id is not None

        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            result.success = False
            status = getattr(e.response, "status_code", "unknown")
            result.errors.append(f"PagerDuty API error: {status}")
        except Exception as e:
            result.success = False
            result.errors.append(f"Unexpected error: {e}")

        return result

    def ensure_team(self, team: str) -> ResourceResult:
        """
        Ensure a team exists, creating if necessary.

        Args:
            team: Team identifier

        Returns:
            ResourceResult with team ID
        """
        team_name = get_team_name(team)

        # Check if exists
        existing = self._find_team(team_name)
        if existing:
            return ResourceResult(
                success=True,
                resource_id=existing["id"],
                resource_name=team_name,
                created=False,
                warnings=[f"Using existing team '{team_name}'"],
            )

        # Create new team
        try:
            response = self.client.post(
                "/teams",
                json={
                    "team": {
                        "name": team_name,
                        "description": f"Team {team_name} - managed by NthLayer",
                    }
                },
            )
            response.raise_for_status()
            data = response.json()["team"]
            return ResourceResult(
                success=True,
                resource_id=data["id"],
                resource_name=team_name,
                created=True,
            )
        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            error_text = getattr(e.response, "text", str(e))
            return ResourceResult(
                success=False,
                error=f"Failed to create team: {error_text}",
            )

    def get_current_user_id(self) -> str | None:
        """
        Get the user ID associated with the API key.

        Uses the first user in the account as a fallback since
        PagerDuty API tokens don't have a direct /me endpoint.
        """
        return self.get_default_user_id()

    def add_team_member(
        self,
        team_id: str,
        user_id: str,
        role: str = "manager",
    ) -> ResourceResult:
        """
        Add a user to a team with the specified role.

        Args:
            team_id: PagerDuty team ID
            user_id: PagerDuty user ID
            role: Team role (manager, observer, responder)

        Returns:
            ResourceResult indicating success/failure
        """
        try:
            # PagerDuty uses PUT for adding/updating team membership
            logger.debug(f"PUT /teams/{team_id}/users/{user_id} with role={role}")
            response = self.client.put(
                f"/teams/{team_id}/users/{user_id}",
                json={"role": role},
            )
            response.raise_for_status()
            return ResourceResult(
                success=True,
                resource_id=user_id,
                resource_name=f"team_member:{role}",
                created=True,
            )
        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            # Check if user is already a member (409 Conflict)
            if getattr(e.response, "status_code", None) == 409:
                return ResourceResult(
                    success=True,
                    resource_id=user_id,
                    resource_name=f"team_member:{role}",
                    created=False,
                    warnings=["User already member of team"],
                )
            err_text = getattr(e.response, "text", str(e))
            return ResourceResult(
                success=False,
                error=f"Failed to add team member: {err_text}",
            )
        except Exception as e:
            return ResourceResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    def ensure_schedule(
        self,
        team: str,
        schedule_type: str,
        tier: str,
        support_model: str,
        timezone: str,
    ) -> ResourceResult:
        """
        Ensure a schedule exists, creating if necessary.

        Args:
            team: Team identifier
            schedule_type: Type of schedule (primary, secondary, manager)
            tier: Service tier
            support_model: Support model
            timezone: Timezone for schedule

        Returns:
            ResourceResult with schedule ID
        """
        schedule_name = get_schedule_name(team, schedule_type)
        config = get_schedule_config(tier, support_model, schedule_type, timezone)

        # Check if exists
        existing = self._find_schedule(schedule_name)
        if existing:
            return ResourceResult(
                success=True,
                resource_id=existing["id"],
                resource_name=schedule_name,
                created=False,
                warnings=[f"Using existing schedule '{schedule_name}'"],
            )

        # Create new schedule
        now = datetime.now(tz=timezone_module.utc)
        start_time = now.replace(
            hour=config.handoff_hour,
            minute=config.handoff_minute,
            second=0,
            microsecond=0,
        )

        # Get a default user for the schedule (PagerDuty requires at least one user)
        default_user_id = self.get_default_user_id()
        if not default_user_id:
            return ResourceResult(
                success=False,
                error="No users found in PagerDuty - cannot create schedule",
            )

        schedule_payload: dict[str, Any] = {
            "schedule": {
                "name": schedule_name,
                "type": "schedule",
                "time_zone": timezone,
                "description": f"{schedule_type.title()} on-call for {team} - managed by NthLayer",
                "schedule_layers": [
                    {
                        "name": f"{schedule_type.title()} Layer",
                        "start": start_time.isoformat(),
                        "rotation_virtual_start": start_time.isoformat(),
                        "rotation_turn_length_seconds": config.rotation_length_seconds,
                        "users": [{"user": {"id": default_user_id, "type": "user_reference"}}],
                    }
                ],
            }
        }

        try:
            response = self.client.post("/schedules", json=schedule_payload)
            response.raise_for_status()
            data = response.json()["schedule"]
            return ResourceResult(
                success=True,
                resource_id=data["id"],
                resource_name=schedule_name,
                created=True,
                warnings=[
                    f"Schedule '{schedule_name}' created with placeholder user "
                    "- update rotation as needed"
                ],
            )
        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            error_text = getattr(e.response, "text", str(e))
            return ResourceResult(
                success=False,
                error=f"Failed to create schedule: {error_text}",
            )

    def ensure_escalation_policy(
        self,
        team: str,
        tier: str,
        schedule_ids: dict[str, str],
    ) -> ResourceResult:
        """
        Ensure an escalation policy exists, creating if necessary.

        Args:
            team: Team identifier
            tier: Service tier
            schedule_ids: Map of schedule type to schedule ID

        Returns:
            ResourceResult with escalation policy ID
        """
        policy_name = get_escalation_policy_name(team)
        config = get_escalation_config(tier, team=team)

        # Check if exists
        existing = self._find_escalation_policy(policy_name)
        if existing:
            return ResourceResult(
                success=True,
                resource_id=existing["id"],
                resource_name=policy_name,
                created=False,
                warnings=[f"Using existing escalation policy '{policy_name}'"],
            )

        # Build escalation rules
        escalation_rules = []
        cumulative_delay = 0

        for rule in config.rules:
            schedule_id = schedule_ids.get(rule.target_name)
            if not schedule_id:
                continue

            cumulative_delay += rule.delay_minutes
            escalation_rules.append(
                {
                    "escalation_delay_in_minutes": rule.delay_minutes,
                    "targets": [
                        {
                            "id": schedule_id,
                            "type": "schedule_reference",
                        }
                    ],
                }
            )

        if not escalation_rules:
            return ResourceResult(
                success=False,
                error="No valid escalation rules could be created (no schedules found)",
            )

        policy_payload = {
            "escalation_policy": {
                "name": policy_name,
                "description": f"Escalation policy for {team} - managed by NthLayer",
                "escalation_rules": escalation_rules,
                "num_loops": config.num_loops,
            }
        }

        try:
            response = self.client.post("/escalation_policies", json=policy_payload)
            response.raise_for_status()
            data = response.json()["escalation_policy"]
            return ResourceResult(
                success=True,
                resource_id=data["id"],
                resource_name=policy_name,
                created=True,
            )
        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            error_text = getattr(e.response, "text", str(e))
            return ResourceResult(
                success=False,
                error=f"Failed to create escalation policy: {error_text}",
            )

    def ensure_service(
        self,
        service_name: str,
        escalation_policy_id: str,
        team_id: str,
        tier: str,
    ) -> ResourceResult:
        """
        Ensure a service exists, creating if necessary.

        Args:
            service_name: Service name
            escalation_policy_id: ID of escalation policy to use
            team_id: ID of team to assign service to
            tier: Service tier (determines urgency)

        Returns:
            ResourceResult with service ID
        """
        pd_service_name = get_service_name(service_name)
        config = get_escalation_config(tier)

        # Check if exists
        existing = self._find_service(pd_service_name)
        if existing:
            return ResourceResult(
                success=True,
                resource_id=existing["id"],
                resource_name=pd_service_name,
                created=False,
                warnings=[f"Using existing service '{pd_service_name}'"],
            )

        service_payload = {
            "service": {
                "name": pd_service_name,
                "description": f"Service {pd_service_name} - managed by NthLayer",
                "escalation_policy": {
                    "id": escalation_policy_id,
                    "type": "escalation_policy_reference",
                },
                "alert_creation": "create_alerts_and_incidents",
                "incident_urgency_rule": {
                    "type": "constant",
                    "urgency": config.urgency,
                },
                "teams": [
                    {
                        "id": team_id,
                        "type": "team_reference",
                    }
                ],
            }
        }

        try:
            response = self.client.post("/services", json=service_payload)
            response.raise_for_status()
            data = response.json()["service"]
            return ResourceResult(
                success=True,
                resource_id=data["id"],
                resource_name=pd_service_name,
                created=True,
            )
        except (pagerduty.HttpError, pagerduty.ServerHttpError) as e:
            error_text = getattr(e.response, "text", str(e))
            return ResourceResult(
                success=False,
                error=f"Failed to create service: {error_text}",
            )

    def _find_team(self, team_name: str) -> dict[str, Any] | None:
        """Find team by name."""
        try:
            response = self.client.get("/teams", params={"query": team_name})
            response.raise_for_status()
            for team in response.json().get("teams", []):
                if team["name"].lower() == team_name.lower():
                    return team
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None

    def _find_schedule(self, schedule_name: str) -> dict[str, Any] | None:
        """Find schedule by name."""
        try:
            response = self.client.get("/schedules", params={"query": schedule_name})
            response.raise_for_status()
            for schedule in response.json().get("schedules", []):
                if schedule["name"].lower() == schedule_name.lower():
                    return schedule
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None

    def _find_escalation_policy(self, policy_name: str) -> dict[str, Any] | None:
        """Find escalation policy by name."""
        try:
            response = self.client.get("/escalation_policies", params={"query": policy_name})
            response.raise_for_status()
            for policy in response.json().get("escalation_policies", []):
                if policy["name"].lower() == policy_name.lower():
                    return policy
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None

    def _find_service(self, service_name: str) -> dict[str, Any] | None:
        """Find service by name."""
        try:
            response = self.client.get("/services", params={"query": service_name})
            response.raise_for_status()
            for service in response.json().get("services", []):
                if service["name"].lower() == service_name.lower():
                    return service
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None

    def _find_service_by_id(self, service_id: str) -> dict[str, Any] | None:
        """Find service by ID."""
        try:
            response = self.client.get(f"/services/{service_id}")
            response.raise_for_status()
            return response.json().get("service")
        except (pagerduty.HttpError, pagerduty.ServerHttpError):
            pass
        return None
