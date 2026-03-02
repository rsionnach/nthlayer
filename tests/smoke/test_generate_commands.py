"""Smoke tests for generate-* CLI commands (all --dry-run)."""

from __future__ import annotations

import pytest

from _helpers import CHECKOUT_SERVICE, run_nthlayer

pytestmark = pytest.mark.smoke


class TestGenerateSlo:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-slo", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateAlerts:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-alerts", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateDashboard:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-dashboard", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateRecordingRules:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-recording-rules", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateLokiAlerts:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-loki-alerts", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateBackstage:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-backstage", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result


class TestGenerateDocs:
    def test_dry_run(self) -> None:
        result = run_nthlayer("generate-docs", CHECKOUT_SERVICE, "--dry-run")
        assert result.exit_code == 0, result
