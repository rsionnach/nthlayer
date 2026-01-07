"""Tests for demo app password security validation.

These tests verify that the demo app requires proper password configuration
and rejects insecure defaults at startup.
"""

import runpy
import sys

import pytest

# Skip all tests if flask is not installed (it's an optional dependency)
pytest.importorskip("flask", reason="flask is required for demo app tests")


def _run_app(monkeypatch, password: str | None, username: str = "nthlayer") -> dict:
    """Run the demo app with specified credentials.

    Args:
        monkeypatch: pytest monkeypatch fixture
        password: Password to set, or None to unset
        username: Username to set

    Returns:
        Module globals if successful
    """
    monkeypatch.setenv("METRICS_USERNAME", username)
    if password is None:
        monkeypatch.delenv("METRICS_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("METRICS_PASSWORD", password)

    # Clear any cached module to force re-import
    if "demo.fly-app.app" in sys.modules:
        del sys.modules["demo.fly-app.app"]

    return runpy.run_path("demo/fly-app/app.py")


def test_demo_app_raises_when_password_missing(monkeypatch):
    """Demo app should fail at startup if METRICS_PASSWORD is not set."""
    with pytest.raises(RuntimeError) as exc_info:
        _run_app(monkeypatch, None)

    assert "METRICS_PASSWORD environment variable must be set" in str(exc_info.value)


def test_demo_app_rejects_default_password(monkeypatch):
    """Demo app should reject the insecure default password 'demo'."""
    with pytest.raises(RuntimeError) as exc_info:
        _run_app(monkeypatch, "demo")

    assert "cannot be 'demo'" in str(exc_info.value)
    assert "insecure" in str(exc_info.value)


def test_demo_app_accepts_non_default_password(monkeypatch):
    """Demo app should accept a non-default secure password."""
    result = _run_app(monkeypatch, "supers3cret!")

    assert result["METRICS_PASSWORD"] == "supers3cret!"
    assert result["METRICS_USERNAME"] == "nthlayer"


def test_demo_app_accepts_custom_username(monkeypatch):
    """Demo app should accept custom username via environment variable."""
    result = _run_app(monkeypatch, "mypassword", username="customuser")

    assert result["METRICS_USERNAME"] == "customuser"
    assert result["METRICS_PASSWORD"] == "mypassword"
