"""Smoke tests for analysis CLI commands (topology, recommend-metrics).

Note: check-deploy smoke tests removed with the command itself in B3 — the
runtime deployment gate now lives in nthlayer-observe (`nthlayer-observe
check-deploy`).
"""

from __future__ import annotations

import pytest
from _helpers import CHECKOUT_SERVICE, run_nthlayer

pytestmark = pytest.mark.smoke


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
