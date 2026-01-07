"""Tests for SLO CLI commands.

Tests for nthlayer slo show/list/collect/blame commands.
"""

import tempfile
from pathlib import Path


class TestSloListCommand:
    """Tests for nthlayer slo list command."""

    def test_lists_slos_from_service_files(self):
        """Test that slo list finds SLOs in service files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create services directory with SLO resources
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            (services_dir / "payment-api.yaml").write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
  - kind: SLO
    name: latency-p95
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 95
        threshold_ms: 500
""")

            # Import and run command
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_list_command

                result = slo_list_command()
                assert result == 0
            finally:
                os.chdir(old_cwd)

    def test_handles_empty_services_directory(self):
        """Test graceful handling when no services exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_list_command

                result = slo_list_command()
                assert result == 0  # Returns 0 even when empty
            finally:
                os.chdir(old_cwd)


class TestSloShowCommand:
    """Tests for nthlayer slo show command."""

    def test_shows_slo_details(self):
        """Test that slo show displays SLO details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create service file
            services_dir = tmpdir / "services"
            services_dir.mkdir()

            service_file = services_dir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{status!~"5.."}[5m]))
          / sum(rate(http_requests_total[5m]))
""")

            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_show_command

                result = slo_show_command("payment-api")
                assert result == 0
            finally:
                os.chdir(old_cwd)

    def test_returns_error_for_missing_service(self):
        """Test error when service file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_show_command

                result = slo_show_command("nonexistent-service")
                assert result == 1
            finally:
                os.chdir(old_cwd)

    def test_shows_with_explicit_file(self):
        """Test slo show with explicit service file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "my-service.yaml"
            service_file.write_text("""
service:
  name: my-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 7d
""")

            from nthlayer.cli.slo import slo_show_command

            result = slo_show_command("my-service", service_file=str(service_file))
            assert result == 0

    def test_returns_error_for_no_slos(self):
        """Test error when service has no SLOs defined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            services_dir = tmpdir / "services"
            services_dir.mkdir()

            service_file = services_dir / "empty-service.yaml"
            service_file.write_text("""
service:
  name: empty-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: Dashboard
    name: main
""")

            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_show_command

                result = slo_show_command("empty-service")
                assert result == 1
            finally:
                os.chdir(old_cwd)


class TestSloCollectCommand:
    """Tests for nthlayer slo collect command."""

    def test_collect_returns_error_for_missing_service(self):
        """Test that collect returns error when service not found."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                from nthlayer.cli.slo import slo_collect_command

                result = slo_collect_command("nonexistent-service")
                assert result == 1
            finally:
                os.chdir(old_cwd)

    def test_collect_with_explicit_file(self):
        """Test that collect works with explicit file path."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-service.yaml"
            service_file.write_text("""
service:
  name: test-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 7d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{status!~"5.."}[5m]))
          / sum(rate(http_requests_total[5m]))
""")

            from nthlayer.cli.slo import slo_collect_command

            # Will try to query Prometheus and fail, but should return 0
            result = slo_collect_command(
                "test-service",
                prometheus_url="http://localhost:9999",  # Non-existent
                service_file=str(service_file),
            )
            # Returns 0 even with connection error (displays error in output)
            assert result == 0


class TestSloBlameCommand:
    """Tests for nthlayer slo blame command."""

    def test_blame_requires_database(self):
        """Test that blame returns error when database not configured."""
        import os

        from nthlayer.cli.slo import slo_blame_command

        # Ensure database URL is not set
        old_db_url = os.environ.pop("NTHLAYER_DATABASE_URL", None)
        try:
            result = slo_blame_command("payment-api")
            # Returns 1 when database not configured
            assert result == 1
        finally:
            if old_db_url is not None:
                os.environ["NTHLAYER_DATABASE_URL"] = old_db_url


class TestWindowParsing:
    """Tests for window duration parsing."""

    def test_parse_days(self):
        """Test parsing day windows."""
        from nthlayer.cli.slo import _parse_window_minutes

        assert _parse_window_minutes("30d") == 30 * 24 * 60
        assert _parse_window_minutes("7d") == 7 * 24 * 60

    def test_parse_hours(self):
        """Test parsing hour windows."""
        from nthlayer.cli.slo import _parse_window_minutes

        assert _parse_window_minutes("24h") == 24 * 60
        assert _parse_window_minutes("1h") == 60

    def test_parse_weeks(self):
        """Test parsing week windows."""
        from nthlayer.cli.slo import _parse_window_minutes

        assert _parse_window_minutes("1w") == 7 * 24 * 60
        assert _parse_window_minutes("4w") == 4 * 7 * 24 * 60

    def test_unknown_format_defaults(self):
        """Test unknown format returns 30 day default."""
        from nthlayer.cli.slo import _parse_window_minutes

        assert _parse_window_minutes("unknown") == 30 * 24 * 60


class TestHandleSloCommand:
    """Tests for the main command handler."""

    def test_unknown_command_returns_error(self):
        """Test that unknown subcommand returns error code."""
        import argparse

        from nthlayer.cli.slo import handle_slo_command

        args = argparse.Namespace(slo_command=None)
        result = handle_slo_command(args)
        assert result == 1

    def test_routes_to_list(self):
        """Test that list command is routed correctly."""
        import argparse
        import os
        import tempfile

        from nthlayer.cli.slo import handle_slo_command

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                args = argparse.Namespace(slo_command="list")
                result = handle_slo_command(args)
                assert result == 0
            finally:
                os.chdir(old_cwd)
