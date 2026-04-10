"""Smoke tests for plan and apply commands with artifact validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from _helpers import CHECKOUT_SERVICE, run_nthlayer

pytestmark = pytest.mark.smoke


class TestPlan:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("plan", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result


class TestApply:
    def test_produces_output(self, output_dir: Path) -> None:
        result = run_nthlayer("apply", CHECKOUT_SERVICE, "--output-dir", str(output_dir))
        assert result.exit_code == 0, result

        output_files = list(output_dir.rglob("*"))
        assert len(output_files) >= 1, f"Expected at least 1 output file, got: {output_files}"

    def test_dashboard_json_valid(self, output_dir: Path) -> None:
        result = run_nthlayer("apply", CHECKOUT_SERVICE, "--output-dir", str(output_dir))
        assert result.exit_code == 0, result

        dashboards = list(output_dir.rglob("dashboard*.json"))
        for dashboard in dashboards:
            data = json.loads(dashboard.read_text())
            assert isinstance(data, dict), f"{dashboard.name} is not a JSON object"

    def test_alerts_yaml_valid(self, output_dir: Path) -> None:
        result = run_nthlayer("apply", CHECKOUT_SERVICE, "--output-dir", str(output_dir))
        assert result.exit_code == 0, result

        alert_files = list(output_dir.rglob("alerts*.yaml"))
        for alert_file in alert_files:
            data = yaml.safe_load(alert_file.read_text())
            assert isinstance(data, dict), f"{alert_file.name} is not a YAML mapping"
            assert "groups" in data, f"{alert_file.name} missing 'groups' key"
