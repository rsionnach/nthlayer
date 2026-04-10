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


class TestValidateSloLive:
    def test_live_slo_validation(self) -> None:
        """Validate SLO PromQL queries against live Prometheus."""
        result = run_nthlayer("validate-slo", CHECKOUT_SERVICE, "--prometheus-url", PROMETHEUS_URL)
        # 0 = all metrics found, 1 = some missing — both acceptable for smoke
        assert result.exit_code in (0, 1), result


# --- Deployment Gate (Live) ---
# TestCheckDeployLive removed in B3 — check-deploy now lives in nthlayer-observe.


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
