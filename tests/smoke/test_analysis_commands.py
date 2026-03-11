"""Smoke tests for analysis CLI commands (check-deploy, topology, recommend-metrics)."""

from __future__ import annotations

import pytest

from _helpers import CHECKOUT_SERVICE, run_nthlayer

pytestmark = pytest.mark.smoke


class TestCheckDeploy:
    def test_demo_does_not_crash(self) -> None:
        """Demo mode exits 0 (pass) or 1 (warning) — both are valid, not a crash."""
        result = run_nthlayer("check-deploy", CHECKOUT_SERVICE, "--demo")
        assert result.exit_code in (0, 1), result

    def test_demo_blocked_exits_2(self) -> None:
        result = run_nthlayer("check-deploy", CHECKOUT_SERVICE, "--demo-blocked")
        assert result.exit_code == 2, result


class TestTopologyExport:
    def test_json_format(self) -> None:
        result = run_nthlayer("topology", "export", "--demo", "--format", "json")
        assert result.exit_code == 0, result

    def test_mermaid_format(self) -> None:
        result = run_nthlayer("topology", "export", "--demo", "--format", "mermaid")
        assert result.exit_code == 0, result


class TestRecommendMetrics:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("recommend-metrics", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result
