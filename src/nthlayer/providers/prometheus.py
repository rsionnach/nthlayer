"""
Prometheus provider for querying metrics.

Implements provider interface for Prometheus/VictoriaMetrics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from nthlayer.providers.base import Provider, ProviderHealth, ProviderResourceSchema

DEFAULT_USER_AGENT = "nthlayer-provider-prometheus/0.1.0"


class PrometheusProviderError(RuntimeError):
    """Raised when Prometheus provider encounters an error."""


class PrometheusProvider(Provider):
    """Prometheus metrics provider."""

    name = "prometheus"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._timeout = timeout
        self._user_agent = user_agent

    async def aclose(self) -> None:
        """Close provider (for symmetry with other providers)."""
        return None

    async def health_check(self) -> ProviderHealth:
        """Check if Prometheus is reachable."""
        try:
            await self._request("GET", "/api/v1/query", params={"query": "up"})
            return ProviderHealth(status="healthy")
        except PrometheusProviderError as exc:
            return ProviderHealth(status="unreachable", details=str(exc))

    async def resources(self) -> list[ProviderResourceSchema]:
        """Return list of supported resources."""
        return []  # Prometheus doesn't use plan/apply pattern

    async def query(self, query: str, time: datetime | None = None) -> dict[str, Any]:
        """
        Execute instant query at a specific time.
        
        Args:
            query: PromQL query string
            time: Query evaluation time (defaults to now)
            
        Returns:
            Query result from Prometheus
        """
        params = {"query": query}
        
        if time is not None:
            params["time"] = time.timestamp()
        
        result = await self._request("GET", "/api/v1/query", params=params)
        return result

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "5m",
    ) -> dict[str, Any]:
        """
        Execute range query over a time period.
        
        Args:
            query: PromQL query string
            start: Start time
            end: End time
            step: Query resolution (e.g., "5m", "1h")
            
        Returns:
            Query result from Prometheus with time series data
        """
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }
        
        result = await self._request("GET", "/api/v1/query_range", params=params)
        return result

    async def get_sli_value(
        self,
        query: str,
        time: datetime | None = None,
    ) -> float:
        """
        Get SLI value from a query (simplified, returns single value).
        
        Args:
            query: PromQL query that returns a single metric value
            time: Evaluation time (defaults to now)
            
        Returns:
            SLI value as float (0.0-1.0)
        """
        result = await self.query(query, time)
        
        # Extract value from result
        data = result.get("data", {})
        result_data = data.get("result", [])
        
        if not result_data:
            return 0.0
        
        # Get first result's value
        value_data = result_data[0].get("value", [])
        
        if len(value_data) < 2:
            return 0.0
        
        try:
            return float(value_data[1])
        except (ValueError, TypeError):
            return 0.0

    async def get_sli_time_series(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "5m",
    ) -> list[dict[str, Any]]:
        """
        Get time series of SLI values.
        
        Args:
            query: PromQL query
            start: Start time
            end: End time
            step: Query resolution
            
        Returns:
            List of {timestamp, sli_value, duration_seconds} dicts
        """
        result = await self.query_range(query, start, end, step)
        
        # Parse result
        data = result.get("data", {})
        result_data = data.get("result", [])
        
        if not result_data:
            return []
        
        # Extract time series values
        values = result_data[0].get("values", [])
        
        measurements = []
        for i, value_pair in enumerate(values):
            if len(value_pair) < 2:
                continue
            
            timestamp_unix = value_pair[0]
            sli_value = float(value_pair[1])
            
            timestamp = datetime.fromtimestamp(timestamp_unix)
            
            # Calculate duration (time to next measurement or step size)
            if i < len(values) - 1:
                next_timestamp_unix = values[i + 1][0]
                duration_seconds = next_timestamp_unix - timestamp_unix
            else:
                # Last point: use step size
                duration_seconds = self._parse_step_to_seconds(step)
            
            measurements.append({
                "timestamp": timestamp,
                "sli_value": sli_value,
                "duration_seconds": duration_seconds,
            })
        
        return measurements

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute HTTP request to Prometheus."""
        url = f"{self._base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("User-Agent", self._user_agent)

        async def _call() -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        **kwargs,
                    )
                    resp.raise_for_status()
                    
                    data = resp.json()
                    
                    # Check Prometheus API status
                    status = data.get("status")
                    if status != "success":
                        error = data.get("error", "Unknown error")
                        raise PrometheusProviderError(f"Prometheus API error: {error}")
                    
                    return data
            except httpx.HTTPError as exc:
                raise PrometheusProviderError(str(exc)) from exc

        return await _call()

    def _parse_step_to_seconds(self, step: str) -> float:
        """Parse Prometheus step string to seconds."""
        # Simple parser for common formats: 5m, 1h, 30s
        if step.endswith("s"):
            return float(step[:-1])
        elif step.endswith("m"):
            return float(step[:-1]) * 60
        elif step.endswith("h"):
            return float(step[:-1]) * 3600
        elif step.endswith("d"):
            return float(step[:-1]) * 86400
        else:
            # Default to 5 minutes
            return 300.0
