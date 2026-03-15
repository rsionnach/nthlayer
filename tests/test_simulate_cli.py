"""Tests for simulate CLI command."""

from __future__ import annotations


from nthlayer.cli.simulate import simulate_command


class TestSimulateCommand:
    def test_demo_mode_returns_zero(self):
        result = simulate_command(
            manifest_file="dummy.yaml",
            demo=True,
            output_format="json",
        )
        assert result == 0

    def test_demo_mode_table_returns_zero(self):
        result = simulate_command(
            manifest_file="dummy.yaml",
            demo=True,
            output_format="table",
        )
        assert result == 0

    def test_missing_manifest_returns_error(self):
        result = simulate_command(
            manifest_file="/nonexistent/path.yaml",
            demo=False,
            output_format="table",
        )
        assert result == 2
