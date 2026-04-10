"""Smoke tests for nthlayer simulate CLI command."""

from __future__ import annotations

import pytest
from _helpers import run_nthlayer

pytestmark = pytest.mark.smoke


class TestSimulateDemo:
    def test_simulate_demo_table(self):
        result = run_nthlayer("simulate", "dummy.yaml", "--demo")
        assert result.exit_code == 0
        assert "checkout-service" in result.stdout

    def test_simulate_demo_json(self):
        result = run_nthlayer("simulate", "dummy.yaml", "--demo", "--format", "json")
        assert result.exit_code == 0
        assert '"target_service"' in result.stdout
        assert '"p_meeting_sla"' in result.stdout
