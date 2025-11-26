from __future__ import annotations

from typing import Any

import httpx
import structlog
from circuitbreaker import circuit
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


class RetryableHTTPError(Exception):
    """HTTP errors that should be retried."""


class PermanentHTTPError(Exception):
    """HTTP errors that should not be retried."""


def is_retryable_status(status_code: int) -> bool:
    """Determine if HTTP status code is retryable."""
    return status_code in (408, 429, 500, 502, 503, 504)


class BaseHTTPClient:
    """Base HTTP client with retry logic and circuit breaker."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_recovery_timeout = circuit_recovery_timeout

    def _headers(self) -> dict[str, str]:
        """Override to provide custom headers."""
        return {"Content-Type": "application/json"}

    @circuit(
        failure_threshold=5,
        recovery_timeout=60,
        expected_exception=RetryableHTTPError,
    )
    @retry(
        retry=retry_if_exception_type(RetryableHTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=1, max=30),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with retry and circuit breaker."""
        url = f"{self._base_url}{path}"
        req_headers = self._headers()
        if headers:
            req_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=req_headers,
                )

                if is_retryable_status(response.status_code):
                    logger.warning(
                        "http_retryable_error",
                        status=response.status_code,
                        method=method,
                        url=url,
                    )
                    raise RetryableHTTPError(f"HTTP {response.status_code}: {response.text}")

                response.raise_for_status()
                return response.json() if response.content else {}

        except httpx.HTTPStatusError as exc:
            if is_retryable_status(exc.response.status_code):
                raise RetryableHTTPError(str(exc)) from exc
            logger.error(
                "http_permanent_error",
                status=exc.response.status_code,
                method=method,
                url=url,
                error=str(exc),
            )
            raise PermanentHTTPError(str(exc)) from exc
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            logger.warning("http_network_error", method=method, url=url, error=str(exc))
            raise RetryableHTTPError(str(exc)) from exc
        except Exception as exc:
            logger.error("http_unexpected_error", method=method, url=url, error=str(exc))
            raise

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute GET request."""
        return await self._request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute POST request."""
        return await self._request("POST", path, json=json, headers=headers)

    async def put(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute PUT request."""
        return await self._request("PUT", path, json=json, headers=headers)

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute DELETE request."""
        return await self._request("DELETE", path, headers=headers)
