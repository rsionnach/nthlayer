"""Tier 2 smoke tests — require Synology Prometheus/Grafana (skipped by default)."""

from __future__ import annotations

import os

import pytest

from _helpers import CHECKOUT_SERVICE, run_nthlayer

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.synology,
    pytest.mark.skipif(
        not os.environ.get("NTHLAYER_PROMETHEUS_URL"),
        reason="NTHLAYER_PROMETHEUS_URL not set — Synology tests skipped",
    ),
]


class TestVerify:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("verify", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result


class TestDrift:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("drift", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result
