"""
Mimir/Cortex Ruler API provider.

Push alert and recording rules to Mimir or Cortex via the Ruler API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_USER_AGENT = "nthlayer-provider-mimir/0.1.0"


class MimirRulerError(RuntimeError):
    """Raised when Mimir Ruler API encounters an error."""


@dataclass
class RulerPushResult:
    """Result of pushing rules to Mimir Ruler."""

    success: bool
    namespace: str
    status_code: int
    message: str
    groups_pushed: int = 0


class MimirRulerProvider:
    """
    Push alert rules to Mimir/Cortex Ruler API.

    The Ruler API accepts Prometheus-compatible rule groups and
    makes them available for evaluation.

    API endpoints:
        POST /api/v1/rules/{namespace} - Create/update rule groups
        DELETE /api/v1/rules/{namespace}/{groupName} - Delete rule group
        GET /api/v1/rules - List all rules
    """

    def __init__(
        self,
        ruler_url: str,
        *,
        tenant_id: str | None = None,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """
        Initialize Mimir Ruler provider.

        Args:
            ruler_url: Base URL of the Mimir Ruler API
            tenant_id: Tenant ID for multi-tenant setups (X-Scope-OrgID header)
            api_key: Bearer token for authentication
            username: Basic auth username
            password: Basic auth password
            timeout: Request timeout in seconds
            user_agent: User agent string
        """
        self._base_url = ruler_url.rstrip("/")
        self._tenant_id = tenant_id
        self._api_key = api_key
        self._timeout = timeout
        self._user_agent = user_agent
        self._auth = (username, password) if username and password else None

    async def push_rules(
        self,
        namespace: str,
        rules_yaml: str,
    ) -> RulerPushResult:
        """
        Push rule groups to a namespace.

        Args:
            namespace: Namespace to push rules to (e.g., service name)
            rules_yaml: YAML content of rule groups

        Returns:
            RulerPushResult with status

        Raises:
            MimirRulerError: If the API request fails
        """
        headers = self._build_headers()
        headers["Content-Type"] = "application/yaml"

        url = f"{self._base_url}/api/v1/rules/{namespace}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    content=rules_yaml,
                    headers=headers,
                    auth=self._auth,  # type: ignore[arg-type]
                )

                if response.status_code in (200, 202):
                    # Count groups in the YAML
                    groups_count = rules_yaml.count("- name:")
                    return RulerPushResult(
                        success=True,
                        namespace=namespace,
                        status_code=response.status_code,
                        message="Rules pushed successfully",
                        groups_pushed=groups_count,
                    )
                else:
                    error_text = response.text[:200] if response.text else "Unknown error"
                    return RulerPushResult(
                        success=False,
                        namespace=namespace,
                        status_code=response.status_code,
                        message=f"Failed to push rules: {error_text}",
                    )

        except httpx.ConnectError as e:
            raise MimirRulerError(f"Failed to connect to Mimir at {url}: {e}") from e
        except httpx.TimeoutException as e:
            raise MimirRulerError(f"Timeout connecting to Mimir at {url}: {e}") from e
        except httpx.HTTPError as e:
            raise MimirRulerError(f"HTTP error from Mimir: {e}") from e

    async def delete_rules(
        self,
        namespace: str,
        group_name: str | None = None,
    ) -> bool:
        """
        Delete rules from a namespace.

        Args:
            namespace: Namespace to delete from
            group_name: Specific group to delete (None = delete all in namespace)

        Returns:
            True if deletion succeeded

        Raises:
            MimirRulerError: If the API request fails
        """
        headers = self._build_headers()

        if group_name:
            url = f"{self._base_url}/api/v1/rules/{namespace}/{group_name}"
        else:
            url = f"{self._base_url}/api/v1/rules/{namespace}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.delete(
                    url,
                    headers=headers,
                    auth=self._auth,  # type: ignore[arg-type]
                )
                return response.status_code in (200, 202, 204)

        except httpx.HTTPError as e:
            raise MimirRulerError(f"Failed to delete rules: {e}") from e

    async def list_rules(self) -> dict[str, Any]:
        """
        List all rules across all namespaces.

        Returns:
            Dictionary of namespaces to rule groups

        Raises:
            MimirRulerError: If the API request fails
        """
        headers = self._build_headers()
        url = f"{self._base_url}/api/v1/rules"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    auth=self._auth,
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    raise MimirRulerError(
                        f"Failed to list rules: {response.status_code} {response.text[:200]}"
                    )

        except httpx.HTTPError as e:
            raise MimirRulerError(f"Failed to list rules: {e}") from e

    async def health_check(self) -> bool:
        """
        Check if Mimir Ruler is reachable.

        Returns:
            True if healthy
        """
        try:
            await self.list_rules()
            return True
        except MimirRulerError:
            return False

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "User-Agent": self._user_agent,
        }

        if self._tenant_id:
            headers["X-Scope-OrgID"] = self._tenant_id

        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        return headers
