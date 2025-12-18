"""
Prometheus metric verifier.

Verifies that declared metrics exist in a target Prometheus instance.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .models import (
    ContractVerificationResult,
    DeclaredMetric,
    MetricContract,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class MetricVerifier:
    """
    Verifies metrics exist in Prometheus.

    Uses the Prometheus API to check if metrics exist for a given service.
    """

    def __init__(
        self,
        prometheus_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize verifier.

        Args:
            prometheus_url: Prometheus server URL
            username: Optional HTTP basic auth username
            password: Optional HTTP basic auth password
            timeout: Request timeout in seconds
        """
        self.prometheus_url = prometheus_url.rstrip("/")
        self.auth = (username, password) if username and password else None
        self.timeout = timeout

        # Try environment variables if auth not provided
        if not self.auth:
            env_user = os.environ.get("PROMETHEUS_USERNAME")
            env_pass = os.environ.get("PROMETHEUS_PASSWORD")
            if env_user and env_pass:
                self.auth = (env_user, env_pass)

    def verify_contract(
        self,
        contract: MetricContract,
    ) -> ContractVerificationResult:
        """
        Verify all metrics in a contract exist.

        Args:
            contract: The metric contract to verify

        Returns:
            ContractVerificationResult with results for each metric
        """
        result = ContractVerificationResult(
            service_name=contract.service_name,
            target_url=self.prometheus_url,
        )

        for metric in contract.metrics:
            verification = self.verify_metric(metric, contract.service_name)
            result.results.append(verification)

        return result

    def verify_metric(
        self,
        metric: DeclaredMetric,
        service_name: str,
    ) -> VerificationResult:
        """
        Verify a single metric exists in Prometheus.

        Uses the series API to check if the metric exists with the service label.

        Args:
            metric: The declared metric to verify
            service_name: Service name to filter by

        Returns:
            VerificationResult indicating if the metric exists
        """
        try:
            # Query the series API
            exists, sample_labels = self._check_metric_exists(metric.name, service_name)

            return VerificationResult(
                metric=metric,
                exists=exists,
                sample_labels=sample_labels,
            )

        except Exception as e:
            logger.warning(f"Error verifying metric {metric.name}: {e}")
            return VerificationResult(
                metric=metric,
                exists=False,
                error=str(e),
            )

    def _check_metric_exists(
        self,
        metric_name: str,
        service_name: str,
    ) -> tuple[bool, Optional[dict]]:
        """
        Check if a metric exists in Prometheus.

        First tries with service label, then without if that fails.

        Args:
            metric_name: Name of the metric
            service_name: Service name to filter by

        Returns:
            Tuple of (exists, sample_labels)
        """
        # Try with service label first
        selector = f'{metric_name}{{service="{service_name}"}}'
        exists, labels = self._query_series(selector)

        if exists:
            return True, labels

        # Try without service label (metric might use different label)
        selector = f"{metric_name}"
        exists, labels = self._query_series(selector)

        return exists, labels

    def _query_series(self, selector: str) -> tuple[bool, Optional[dict]]:
        """
        Query Prometheus series API.

        Args:
            selector: Prometheus selector (e.g., 'metric_name{service="foo"}')

        Returns:
            Tuple of (exists, sample_labels)
        """
        url = f"{self.prometheus_url}/api/v1/series"
        params: dict[str, str | int] = {"match[]": selector, "limit": 1}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, auth=self.auth)
                response.raise_for_status()
                data = response.json()

                if data.get("status") == "success":
                    series = data.get("data", [])
                    if series:
                        # Return first series as sample
                        sample = series[0]
                        # Remove __name__ from labels
                        labels = {k: v for k, v in sample.items() if k != "__name__"}
                        return True, labels

                return False, None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False, None
            raise
        except httpx.ConnectError as e:
            raise ConnectionError(f"Cannot connect to Prometheus at {self.prometheus_url}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Timeout connecting to Prometheus at {self.prometheus_url}") from e

    def test_connection(self) -> bool:
        """
        Test connection to Prometheus.

        Returns:
            True if connection successful
        """
        try:
            url = f"{self.prometheus_url}/api/v1/status/buildinfo"
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, auth=self.auth)
                return response.status_code == 200
        except Exception:
            return False
