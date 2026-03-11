"""Tier 2 smoke tests — require Synology Prometheus/Grafana (skipped by default).

Run with: make smoke-full
Requires: NTHLAYER_PROMETHEUS_URL and optionally NTHLAYER_GRAFANA_URL + NTHLAYER_GRAFANA_API_KEY
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from _helpers import CHECKOUT_SERVICE, run_nthlayer

PROMETHEUS_URL = os.environ.get("NTHLAYER_PROMETHEUS_URL", "")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.synology,
    pytest.mark.skipif(
        not PROMETHEUS_URL,
        reason="NTHLAYER_PROMETHEUS_URL not set — Synology tests skipped",
    ),
]


# --- Metric Verification ---


class TestVerify:
    def test_checkout_service(self) -> None:
        """Verify declared metrics exist in Prometheus."""
        result = run_nthlayer("verify", CHECKOUT_SERVICE, "--prometheus-url", PROMETHEUS_URL)
        # 0 = all found, 1 = optional missing (warning) — both acceptable
        assert result.exit_code in (0, 1), result


class TestValidateSloLive:
    def test_live_slo_validation(self) -> None:
        """Validate SLO PromQL queries against live Prometheus."""
        result = run_nthlayer("validate-slo", CHECKOUT_SERVICE, "--prometheus-url", PROMETHEUS_URL)
        # 0 = all metrics found, 1 = some missing — both acceptable for smoke
        assert result.exit_code in (0, 1), result


# --- Drift Analysis ---


class TestDrift:
    def test_checkout_service(self) -> None:
        """Drift may fail with exit 2 if no SLO data exists for this service."""
        result = run_nthlayer("drift", CHECKOUT_SERVICE)
        # 0 = OK, 1 = warn, 2 = critical or no data — all valid for smoke
        assert result.exit_code in (0, 1, 2), result


# --- Deployment Gate (Live) ---


class TestCheckDeployLive:
    def test_live_deploy_check(self) -> None:
        """Check deployment gate against live Prometheus metrics."""
        result = run_nthlayer("check-deploy", CHECKOUT_SERVICE, "--prometheus-url", PROMETHEUS_URL)
        # 0 = approved, 1 = warning, 2 = blocked — all are valid live behavior
        assert result.exit_code in (0, 1, 2), result

    def test_live_deploy_with_drift(self) -> None:
        """Check deployment gate with drift analysis enabled."""
        result = run_nthlayer(
            "check-deploy", CHECKOUT_SERVICE, "--include-drift", "--prometheus-url", PROMETHEUS_URL
        )
        assert result.exit_code in (0, 1, 2), result


# --- Dashboard Push (requires Grafana) ---


needs_grafana = pytest.mark.skipif(
    not os.environ.get("NTHLAYER_GRAFANA_URL"),
    reason="NTHLAYER_GRAFANA_URL not set — Grafana push tests skipped",
)


@needs_grafana
class TestDashboardPush:
    def test_apply_push_grafana(self, tmp_path: Path) -> None:
        """Generate and push dashboard to live Grafana instance."""
        result = run_nthlayer(
            "apply",
            CHECKOUT_SERVICE,
            "--output-dir",
            str(tmp_path),
            "--push-grafana",
        )
        assert result.exit_code == 0, result

        # Verify dashboard was generated locally too
        dashboards = list(tmp_path.rglob("dashboard*.json"))
        assert len(dashboards) >= 1, f"No dashboard files generated in {tmp_path}"

    def test_generate_dashboard_with_discovery(self, tmp_path: Path) -> None:
        """Generate dashboard using live metric discovery from Prometheus."""
        result = run_nthlayer(
            "apply",
            CHECKOUT_SERVICE,
            "--output-dir",
            str(tmp_path),
            "--only",
            "dashboards",
            "--prometheus-url",
            PROMETHEUS_URL,
        )
        assert result.exit_code == 0, result

        # Verify dashboard JSON is valid
        dashboards = list(tmp_path.rglob("dashboard*.json"))
        for dashboard in dashboards:
            data = json.loads(dashboard.read_text())
            assert isinstance(data, dict), f"{dashboard.name} is not a JSON object"
