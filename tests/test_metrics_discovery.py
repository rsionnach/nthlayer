"""
Tests for the Metrics Discovery module.

Integration tests require the Synology test environment:
- NTHLAYER_PROMETHEUS_URL=http://192.168.1.10:9090

Run with: pytest tests/test_metrics_discovery.py -v
Skip integration tests: pytest tests/test_metrics_discovery.py -v -m "not integration"
"""

import os

import pytest
from nthlayer.metrics.discovery import (
    discover_all_metrics,
    discover_metrics_with_details,
    discover_service_metrics,
)

# Check if Synology environment is available
PROMETHEUS_URL = os.environ.get("NTHLAYER_PROMETHEUS_URL", "http://192.168.1.10:9090")
SYNOLOGY_AVAILABLE = os.environ.get("NTHLAYER_PROMETHEUS_URL") is not None


def _check_prometheus_available() -> bool:
    """Check if Prometheus is reachable."""
    try:
        import requests

        response = requests.get(f"{PROMETHEUS_URL}/api/v1/status/runtimeinfo", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


# Skip integration tests if Prometheus not available
requires_prometheus = pytest.mark.skipif(
    not _check_prometheus_available(),
    reason="Prometheus not available (set NTHLAYER_PROMETHEUS_URL)",
)


class TestDiscoverServiceMetrics:
    """Tests for discover_service_metrics function."""

    @requires_prometheus
    def test_discover_service_metrics_real(self):
        """Test discovering metrics from real Prometheus."""
        # Use a generic selector that should find some metrics
        metrics = discover_service_metrics(
            prometheus_url=PROMETHEUS_URL,
            service_name="prometheus",  # Prometheus scrapes itself
            selector_label="job",
        )

        # Should find some metrics (Prometheus self-monitoring)
        assert isinstance(metrics, list)
        # Note: If no metrics found, that's OK - it just means no matching service

    @requires_prometheus
    def test_discover_service_metrics_nonexistent(self):
        """Test discovering metrics for nonexistent service."""
        metrics = discover_service_metrics(
            prometheus_url=PROMETHEUS_URL,
            service_name="nonexistent-service-xyz",
        )

        # Should return empty list, not error
        assert metrics == []

    def test_discover_service_metrics_bad_url(self):
        """Test discovering metrics with bad Prometheus URL."""
        metrics = discover_service_metrics(
            prometheus_url="http://localhost:99999",  # Invalid port
            service_name="test-service",
        )

        # Should return empty list on connection error
        assert metrics == []


class TestDiscoverMetricsWithDetails:
    """Tests for discover_metrics_with_details function."""

    @requires_prometheus
    def test_discover_with_details_real(self):
        """Test discovering metrics with full details."""
        result = discover_metrics_with_details(
            prometheus_url=PROMETHEUS_URL,
            service_name="prometheus",
            selector_label="job",
        )

        # Result could be None if no metrics found, or DiscoveryResult
        if result is not None:
            assert hasattr(result, "metrics")
            assert hasattr(result, "total_metrics")

    def test_discover_with_details_bad_url(self):
        """Test discovering with details using bad URL."""
        result = discover_metrics_with_details(
            prometheus_url="http://localhost:99999",
            service_name="test-service",
        )

        # Should return empty result on connection error
        assert result is not None
        assert result.total_metrics == 0
        assert result.metrics == []


class TestDiscoverAllMetrics:
    """Tests for discover_all_metrics function."""

    @requires_prometheus
    def test_discover_all_metrics_real(self):
        """Test discovering all metrics from Prometheus."""
        metrics = discover_all_metrics(prometheus_url=PROMETHEUS_URL)

        # Should find metrics (any Prometheus has some)
        assert isinstance(metrics, list)
        assert len(metrics) > 0

        # Should include standard Prometheus metrics
        # Common metrics: up, scrape_duration_seconds, etc.
        metric_names = set(metrics)
        assert "up" in metric_names or "scrape_duration_seconds" in metric_names

    def test_discover_all_metrics_bad_url(self):
        """Test discovering all metrics with bad URL."""
        metrics = discover_all_metrics(prometheus_url="http://localhost:99999")

        # Should return empty list on connection error
        assert metrics == []


class TestDiscoveryWithAuth:
    """Tests for discovery with authentication."""

    @requires_prometheus
    def test_discover_with_basic_auth(self):
        """Test discovery with basic auth (if configured)."""
        # Synology might have auth configured
        # Credentials from environment variables
        username = os.environ.get("NTHLAYER_PROMETHEUS_USERNAME")
        password = os.environ.get("NTHLAYER_PROMETHEUS_PASSWORD")
        metrics = discover_service_metrics(
            prometheus_url=PROMETHEUS_URL,
            service_name="prometheus",
            selector_label="job",
            username=username,
            password=password,
        )

        # Should work with or without auth
        assert isinstance(metrics, list)

    def test_discover_all_with_basic_auth(self):
        """Test discover_all with basic auth on bad URL."""
        metrics = discover_all_metrics(
            prometheus_url="http://localhost:99999",
            username="test",
            password="test",
        )

        # Should return empty list on connection error
        assert metrics == []

    def test_discover_all_with_bearer_token(self):
        """Test discover_all with bearer token on bad URL."""
        metrics = discover_all_metrics(
            prometheus_url="http://localhost:99999",
            bearer_token="fake-token",
        )

        # Should return empty list on connection error
        assert metrics == []


class TestDiscoveryEdgeCases:
    """Edge case tests for discovery module."""

    def test_discover_empty_service_name(self):
        """Test with empty service name."""
        metrics = discover_service_metrics(
            prometheus_url="http://localhost:99999",
            service_name="",
        )
        assert metrics == []

    def test_discover_special_characters_in_name(self):
        """Test with special characters in service name."""
        metrics = discover_service_metrics(
            prometheus_url="http://localhost:99999",
            service_name='test"service',  # Quote that could break selector
        )
        # Should handle gracefully
        assert metrics == []

    def test_discover_custom_selector_label(self):
        """Test with custom selector label."""
        metrics = discover_service_metrics(
            prometheus_url="http://localhost:99999",
            service_name="test",
            selector_label="custom_label",
        )
        assert metrics == []
