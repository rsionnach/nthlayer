"""
Prometheus metric discovery for the Metrics Recommendation Engine.

Wraps the existing discovery client to provide metric name lists
for the recommendation engine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nthlayer.discovery.models import DiscoveryResult

logger = logging.getLogger(__name__)


def discover_service_metrics(
    prometheus_url: str,
    service_name: str,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
    selector_label: str = "service",
) -> list[str]:
    """
    Discover all metrics for a service from Prometheus.

    Uses the existing MetricDiscoveryClient to query Prometheus
    and returns a list of metric names.

    Args:
        prometheus_url: Prometheus server URL
        service_name: Name of the service to discover metrics for
        username: Optional HTTP basic auth username
        password: Optional HTTP basic auth password
        bearer_token: Optional bearer token for authentication
        selector_label: Label to use for service selection (default: 'service')

    Returns:
        List of metric names discovered for the service
    """
    from nthlayer.discovery.client import MetricDiscoveryClient

    client = MetricDiscoveryClient(
        prometheus_url=prometheus_url,
        username=username,
        password=password,
        bearer_token=bearer_token,
    )

    selector = f'{{{selector_label}="{service_name}"}}'
    logger.info(f"Discovering metrics for {service_name} with selector: {selector}")

    try:
        result = client.discover(selector)
        metric_names = [m.name for m in result.metrics]
        logger.info(f"Discovered {len(metric_names)} metrics for {service_name}")
        return metric_names
    except Exception as e:
        logger.warning(f"Failed to discover metrics: {e}")
        return []


def discover_metrics_with_details(
    prometheus_url: str,
    service_name: str,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
    selector_label: str = "service",
) -> "DiscoveryResult | None":
    """
    Discover metrics with full details (type, labels, etc.).

    Returns the complete DiscoveryResult for detailed analysis.

    Args:
        prometheus_url: Prometheus server URL
        service_name: Name of the service
        username: Optional HTTP basic auth username
        password: Optional HTTP basic auth password
        bearer_token: Optional bearer token for authentication
        selector_label: Label to use for service selection

    Returns:
        DiscoveryResult with full metric details, or None on failure
    """
    from nthlayer.discovery.client import MetricDiscoveryClient

    client = MetricDiscoveryClient(
        prometheus_url=prometheus_url,
        username=username,
        password=password,
        bearer_token=bearer_token,
    )

    selector = f'{{{selector_label}="{service_name}"}}'

    try:
        return client.discover(selector)
    except Exception as e:
        logger.warning(f"Failed to discover metrics with details: {e}")
        return None


def discover_all_metrics(
    prometheus_url: str,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
) -> list[str]:
    """
    Discover all available metrics in Prometheus.

    Useful for listing what metrics exist without filtering by service.

    Args:
        prometheus_url: Prometheus server URL
        username: Optional HTTP basic auth username
        password: Optional HTTP basic auth password
        bearer_token: Optional bearer token for authentication

    Returns:
        List of all metric names in Prometheus
    """
    import requests
    from requests.auth import HTTPBasicAuth

    url = f"{prometheus_url.rstrip('/')}/api/v1/label/__name__/values"
    auth = HTTPBasicAuth(username, password) if username and password else None
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            return data.get("data", [])
        return []
    except Exception as e:
        logger.warning(f"Failed to discover all metrics: {e}")
        return []
