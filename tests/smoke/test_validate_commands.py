"""Smoke tests for validation CLI commands."""

from __future__ import annotations

import pytest

from _helpers import CHECKOUT_SERVICE, PAYMENT_API_OPENSRM, run_nthlayer

pytestmark = pytest.mark.smoke


class TestValidateSpec:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("validate-spec", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result

    def test_opensrm_manifest_reports_errors(self) -> None:
        """OpenSRM manifest has validation errors — verify the command runs and reports them."""
        result = run_nthlayer("validate-spec", PAYMENT_API_OPENSRM)
        assert result.exit_code == 2, result
        assert "errors" in result.stdout.lower(), result


class TestValidate:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("validate", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result


class TestValidateMetadata:
    def test_checkout_service(self) -> None:
        result = run_nthlayer("validate-metadata", CHECKOUT_SERVICE)
        assert result.exit_code == 0, result


class TestValidateSlo:
    def test_demo_mode(self) -> None:
        """Demo mode may return 0 (pass) or 1 (warning) — both are valid."""
        result = run_nthlayer("validate-slo", CHECKOUT_SERVICE, "--demo")
        assert result.exit_code in (0, 1), result
