"""
PagerDuty integration for service setup.

Handles:
- Service creation with existence checks
- Escalation policy creation/linking
- Team detection and mapping
- Schedule creation (optional)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class PagerDutySetupResult:
    """Result of PagerDuty setup."""
    
    success: bool
    service_id: str | None = None
    service_url: str | None = None
    escalation_policy_id: str | None = None
    team_id: str | None = None
    created_service: bool = False
    created_escalation_policy: bool = False
    created_team: bool = False
    error: str | None = None
    warnings: list[str] | None = None


class PagerDutyClient:
    """
    PagerDuty API client for service setup.
    
    Handles service/escalation policy/team creation with intelligent defaults.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.pagerduty.com"):
        """
        Initialize PagerDuty client.
        
        Args:
            api_key: PagerDuty API key (user or service token)
            base_url: PagerDuty API base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Token token={api_key}",
                "Accept": "application/vnd.pagerduty+json;version=2",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    
    def setup_service(
        self,
        service_name: str,
        team_name: str | None = None,
        escalation_policy_name: str | None = None,
        escalation_policy_id: str | None = None,
        urgency: str = "high",
        auto_resolve_timeout: int | None = None,
        create_escalation_policy_config: dict[str, Any] | None = None,
    ) -> PagerDutySetupResult:
        """
        Setup PagerDuty service with all dependencies.
        
        Workflow:
        1. Check if service exists (by name)
        2. If not, create service (requires escalation policy)
        3. Handle escalation policy:
           - If escalation_policy_id provided → use it
           - If escalation_policy_name provided → find or create
           - If neither → create default policy
        4. If team_name provided → find or create team, add service
        
        Args:
            service_name: Service display name
            team_name: Team name (optional, for team mapping)
            escalation_policy_name: Escalation policy name (optional)
            escalation_policy_id: Escalation policy ID (optional, takes precedence)
            urgency: Service urgency (high or low)
            auto_resolve_timeout: Auto-resolve timeout in seconds
            create_escalation_policy_config: Config for creating new policy
        
        Returns:
            PagerDutySetupResult with IDs and status
        """
        warnings = []
        
        try:
            # Step 1: Check if service exists
            existing_service = self._find_service(service_name)
            if existing_service:
                return PagerDutySetupResult(
                    success=True,
                    service_id=existing_service["id"],
                    service_url=existing_service["html_url"],
                    escalation_policy_id=existing_service.get("escalation_policy", {}).get("id"),
                    created_service=False,
                    warnings=[f"Service '{service_name}' already exists, using existing"],
                )
            
            # Step 2: Handle escalation policy
            ep_id = escalation_policy_id
            created_ep = False
            
            if not ep_id and escalation_policy_name:
                # Try to find existing policy
                existing_ep = self._find_escalation_policy(escalation_policy_name)
                if existing_ep:
                    ep_id = existing_ep["id"]
                    warnings.append(f"Using existing escalation policy '{escalation_policy_name}'")
                else:
                    # Create new policy
                    if create_escalation_policy_config:
                        new_ep = self._create_escalation_policy(
                            escalation_policy_name,
                            create_escalation_policy_config,
                        )
                        ep_id = new_ep["id"]
                        created_ep = True
                    else:
                        return PagerDutySetupResult(
                            success=False,
                            error=f"Escalation policy '{escalation_policy_name}' not found and no config provided to create it",
                        )
            
            if not ep_id:
                # Create default escalation policy
                default_ep_name = f"{service_name}-escalation"
                new_ep = self._create_default_escalation_policy(default_ep_name)
                ep_id = new_ep["id"]
                created_ep = True
                warnings.append(f"Created default escalation policy '{default_ep_name}'")
            
            # Step 3: Create service
            service_config: dict[str, Any] = {
                "name": service_name,
                "escalation_policy": {
                    "id": ep_id,
                    "type": "escalation_policy_reference",
                },
                "alert_creation": "create_alerts_and_incidents",
                "incident_urgency_rule": {
                    "type": "constant",
                    "urgency": urgency,
                },
            }
            
            if auto_resolve_timeout:
                service_config["auto_resolve_timeout"] = auto_resolve_timeout
            
            response = self.client.post(
                "/services",
                json={"service": service_config},
            )
            response.raise_for_status()
            
            service = response.json()["service"]
            
            # Step 4: Handle team mapping
            team_id = None
            created_team = False
            
            if team_name:
                existing_team = self._find_team(team_name)
                if existing_team:
                    team_id = existing_team["id"]
                    # Add service to team
                    self._add_service_to_team(team_id, service["id"])
                    warnings.append(f"Added service to existing team '{team_name}'")
                else:
                    # Create team
                    new_team = self._create_team(team_name)
                    team_id = new_team["id"]
                    created_team = True
                    # Add service to team
                    self._add_service_to_team(team_id, service["id"])
                    warnings.append(f"Created team '{team_name}' and added service")
            
            return PagerDutySetupResult(
                success=True,
                service_id=service["id"],
                service_url=service["html_url"],
                escalation_policy_id=ep_id,
                team_id=team_id,
                created_service=True,
                created_escalation_policy=created_ep,
                created_team=created_team,
                warnings=warnings if warnings else None,
            )
        
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
            return PagerDutySetupResult(
                success=False,
                error=f"PagerDuty API error ({e.response.status_code}): {error_detail}",
            )
        except Exception as e:
            return PagerDutySetupResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )
    
    def _find_service(self, service_name: str) -> dict[str, Any] | None:
        """Find service by name."""
        response = self.client.get("/services", params={"query": service_name})
        response.raise_for_status()
        
        services = response.json()["services"]
        for service in services:
            if service["name"] == service_name:
                return service
        
        return None
    
    def _find_escalation_policy(self, policy_name: str) -> dict[str, Any] | None:
        """Find escalation policy by name."""
        response = self.client.get("/escalation_policies", params={"query": policy_name})
        response.raise_for_status()
        
        policies = response.json()["escalation_policies"]
        for policy in policies:
            if policy["name"] == policy_name:
                return policy
        
        return None
    
    def _create_escalation_policy(
        self,
        policy_name: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create escalation policy.
        
        Config should include:
        - escalation_rules: List of escalation rules
        """
        policy_config = {
            "name": policy_name,
            "escalation_rules": config.get("escalation_rules", []),
        }
        
        response = self.client.post(
            "/escalation_policies",
            json={"escalation_policy": policy_config},
        )
        response.raise_for_status()
        
        return response.json()["escalation_policy"]
    
    def _create_default_escalation_policy(self, policy_name: str) -> dict[str, Any]:
        """
        Create a default escalation policy.
        
        This is a fallback when no policy is specified.
        Requires at least one user - uses the API key owner.
        """
        # Get current user (API key owner)
        user_response = self.client.get("/users/me")
        user_response.raise_for_status()
        user = user_response.json()["user"]
        
        policy_config = {
            "name": policy_name,
            "escalation_rules": [
                {
                    "escalation_delay_in_minutes": 30,
                    "targets": [
                        {
                            "id": user["id"],
                            "type": "user_reference",
                        }
                    ],
                }
            ],
        }
        
        response = self.client.post(
            "/escalation_policies",
            json={"escalation_policy": policy_config},
        )
        response.raise_for_status()
        
        return response.json()["escalation_policy"]
    
    def _find_team(self, team_name: str) -> dict[str, Any] | None:
        """Find team by name."""
        response = self.client.get("/teams", params={"query": team_name})
        response.raise_for_status()
        
        teams = response.json()["teams"]
        for team in teams:
            if team["name"] == team_name:
                return team
        
        return None
    
    def _create_team(self, team_name: str) -> dict[str, Any]:
        """Create team."""
        team_config = {
            "name": team_name,
            "description": f"Team for {team_name} services",
        }
        
        response = self.client.post(
            "/teams",
            json={"team": team_config},
        )
        response.raise_for_status()
        
        return response.json()["team"]
    
    def _add_service_to_team(self, team_id: str, service_id: str) -> None:
        """Add service to team."""
        response = self.client.put(
            f"/teams/{team_id}/services/{service_id}",
        )
        response.raise_for_status()
    
    def close(self):
        """Close HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
