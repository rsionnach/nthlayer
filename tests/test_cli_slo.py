"""Tests for CLI SLO commands.

Tests for nthlayer slo commands including show, list, collect, and blame.
"""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.cli.slo import (
    _parse_window_minutes,
    _print_slo_result,
    handle_slo_command,
    register_slo_parser,
    slo_blame_command,
    slo_collect_command,
    slo_list_command,
    slo_show_command,
)


@pytest.fixture
def service_with_slos():
    """Create a service file with SLOs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "test-service.yaml"
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
      window: 30d
      indicator:
        type: availability
        query: sum(rate(http_requests_total{service="${service}",status!~"5.."}[5m])) / sum(rate(http_requests_total{service="${service}"}[5m]))
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 7d
      indicator:
        type: latency
        query: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="${service}"}[5m])) by (le))
""")
        yield str(service_file)


@pytest.fixture
def service_without_slos():
    """Create a service file without SLOs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "minimal-service.yaml"
        service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
        yield str(service_file)


@pytest.fixture
def services_directory():
    """Create a directory structure with multiple services."""
    with tempfile.TemporaryDirectory() as tmpdir:
        services_dir = Path(tmpdir) / "services"
        services_dir.mkdir()

        # Service 1 with SLOs
        svc1 = services_dir / "service-a.yaml"
        svc1.write_text("""
service:
  name: service-a
  team: team-a
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
""")

        # Service 2 with SLOs
        svc2 = services_dir / "service-b.yaml"
        svc2.write_text("""
service:
  name: service-b
  team: team-b
  tier: critical
  type: api

resources:
  - kind: SLO
    name: latency
    spec:
      objective: 99.0
      window: 7d
""")

        yield tmpdir


class TestSloShowCommand:
    """Tests for slo_show_command function."""

    def test_shows_slo_details(self, service_with_slos, capsys):
        """Test showing SLO details."""
        result = slo_show_command(
            service="test-service",
            service_file=service_with_slos,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "availability" in captured.out
        assert "99.9" in captured.out

    def test_shows_error_budget(self, service_with_slos, capsys):
        """Test showing error budget calculation."""
        result = slo_show_command(
            service="test-service",
            service_file=service_with_slos,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "Error Budget" in captured.out or "minutes" in captured.out

    def test_service_file_not_found(self, capsys):
        """Test error when service file not found."""
        result = slo_show_command(
            service="nonexistent",
            service_file="/nonexistent/service.yaml",
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_no_slos_defined(self, service_without_slos, capsys):
        """Test message when no SLOs defined."""
        result = slo_show_command(
            service="minimal-service",
            service_file=service_without_slos,
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "No SLOs defined" in captured.out

    def test_shows_indicator_type(self, service_with_slos, capsys):
        """Test showing indicator type."""
        slo_show_command(
            service="test-service",
            service_file=service_with_slos,
        )

        captured = capsys.readouterr()
        assert "availability" in captured.out or "Indicator" in captured.out

    def test_truncates_long_queries(self, capsys):
        """Test that long queries are truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "test.yaml"
            long_query = "a" * 100
            service_file.write_text(f"""
service:
  name: test
  team: test
  tier: standard
  type: api

resources:
  - kind: SLO
    name: test-slo
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: custom
        query: {long_query}
""")

            slo_show_command("test", service_file=str(service_file))

            captured = capsys.readouterr()
            # Should be truncated with ...
            assert "..." in captured.out or len(long_query) not in captured.out


class TestSloListCommand:
    """Tests for slo_list_command function."""

    def test_lists_slos_from_services_dir(self, services_directory, capsys, monkeypatch):
        """Test listing SLOs from services directory."""
        monkeypatch.chdir(services_directory)

        result = slo_list_command()

        assert result == 0
        captured = capsys.readouterr()
        assert "service-a" in captured.out or "availability" in captured.out

    def test_no_slos_found(self, capsys, monkeypatch):
        """Test message when no SLOs found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            result = slo_list_command()

            assert result == 0
            captured = capsys.readouterr()
            assert "No SLOs found" in captured.out

    def test_shows_total_count(self, services_directory, capsys, monkeypatch):
        """Test showing total SLO count."""
        monkeypatch.chdir(services_directory)

        slo_list_command()

        captured = capsys.readouterr()
        assert "Total" in captured.out


class TestSloCollectCommand:
    """Tests for slo_collect_command function."""

    @patch("nthlayer.cli.slo._collect_slo_metrics")
    @patch("nthlayer.cli.slo.parse_service_file")
    def test_collects_metrics(self, mock_parse, mock_collect, service_with_slos, capsys):
        """Test collecting metrics from Prometheus."""
        ctx = MagicMock()
        ctx.name = "test-service"

        slo = MagicMock()
        slo.kind = "SLO"
        slo.name = "availability"
        slo.spec = {"objective": 99.9, "window": "30d"}

        mock_parse.return_value = (ctx, [slo])
        mock_collect.return_value = [
            {
                "name": "availability",
                "objective": 99.9,
                "window": "30d",
                "total_budget_minutes": 43.2,
                "current_sli": 99.95,
                "burned_minutes": 21.6,
                "percent_consumed": 50.0,
                "status": "HEALTHY",
                "error": None,
            }
        ]

        result = slo_collect_command(
            service="test-service",
            prometheus_url="http://prometheus:9090",
            service_file=service_with_slos,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "HEALTHY" in captured.out or "availability" in captured.out

    @patch("nthlayer.cli.slo.parse_service_file")
    def test_service_file_not_found(self, mock_parse, capsys):
        """Test error when service file not found."""
        mock_parse.side_effect = FileNotFoundError("File not found")

        result = slo_collect_command(
            service="nonexistent",
            service_file="/nonexistent/file.yaml",
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    @patch("nthlayer.cli.slo.parse_service_file")
    def test_no_slos_defined(self, mock_parse, capsys):
        """Test error when no SLOs defined."""
        ctx = MagicMock()
        ctx.name = "test"
        mock_parse.return_value = (ctx, [])

        result = slo_collect_command(
            service="test",
            service_file="test.yaml",
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "No SLOs" in captured.out

    @patch.dict("os.environ", {"NTHLAYER_PROMETHEUS_URL": "http://env-prom:9090"})
    @patch("nthlayer.cli.slo._collect_slo_metrics")
    @patch("nthlayer.cli.slo.parse_service_file")
    def test_uses_env_prometheus_url(self, mock_parse, mock_collect, capsys):
        """Test using Prometheus URL from environment."""
        ctx = MagicMock()
        ctx.name = "test"
        slo = MagicMock()
        slo.kind = "SLO"
        slo.name = "test"
        slo.spec = {}

        mock_parse.return_value = (ctx, [slo])
        mock_collect.return_value = []

        slo_collect_command(
            service="test",
            service_file="test.yaml",
        )

        captured = capsys.readouterr()
        assert "env-prom" in captured.out

    @patch("nthlayer.cli.slo._collect_slo_metrics")
    @patch("nthlayer.cli.slo.parse_service_file")
    def test_shows_healthy_count(self, mock_parse, mock_collect, capsys):
        """Test showing healthy SLO count."""
        ctx = MagicMock()
        ctx.name = "test"

        slo1 = MagicMock()
        slo1.kind = "SLO"
        slo1.name = "slo1"
        slo1.spec = {}

        mock_parse.return_value = (ctx, [slo1])
        mock_collect.return_value = [
            {
                "name": "slo1",
                "status": "HEALTHY",
                "objective": 99.9,
                "window": "30d",
                "current_sli": None,
                "error": None,
            }
        ]

        slo_collect_command(
            service="test",
            service_file="test.yaml",
        )

        captured = capsys.readouterr()
        assert "1/1" in captured.out or "healthy" in captured.out.lower()


class TestSloBlameCommand:
    """Tests for slo_blame_command function."""

    def test_no_database_configured(self, capsys):
        """Test message when database not configured."""
        with patch.dict("os.environ", {}, clear=True):
            result = slo_blame_command(service="test")

        assert result == 1
        captured = capsys.readouterr()
        assert "Database not configured" in captured.out

    def test_shows_setup_instructions(self, capsys):
        """Test showing setup instructions when no database."""
        with patch.dict("os.environ", {}, clear=True):
            slo_blame_command(service="test")

        captured = capsys.readouterr()
        assert "DATABASE_URL" in captured.out
        assert "ArgoCD" in captured.out or "deployment" in captured.out.lower()

    @patch.dict("os.environ", {"NTHLAYER_DATABASE_URL": "postgresql://test"})
    def test_no_correlations_found(self, capsys):
        """Test message when no correlations found (stub implementation)."""
        result = slo_blame_command(service="test")

        assert result == 0
        captured = capsys.readouterr()
        assert "No deployment correlations found" in captured.out

    @patch.dict("os.environ", {"NTHLAYER_DATABASE_URL": "postgresql://test"})
    def test_uses_custom_days(self, capsys):
        """Test using custom lookback days."""
        slo_blame_command(service="test", days=14)

        captured = capsys.readouterr()
        assert "14" in captured.out

    @patch.dict("os.environ", {"NTHLAYER_DATABASE_URL": "postgresql://test"})
    def test_shows_service_name(self, capsys):
        """Test that service name is shown in output."""
        slo_blame_command(service="payment-api")

        captured = capsys.readouterr()
        assert "payment-api" in captured.out

    @patch.dict("os.environ", {"NTHLAYER_DATABASE_URL": "postgresql://test"})
    def test_shows_confidence_threshold(self, capsys):
        """Test that confidence threshold is shown."""
        slo_blame_command(service="test", min_confidence=0.75)

        captured = capsys.readouterr()
        assert "75%" in captured.out


class TestParseWindowMinutes:
    """Tests for _parse_window_minutes function."""

    def test_days(self):
        """Test parsing days."""
        assert _parse_window_minutes("30d") == 30 * 24 * 60
        assert _parse_window_minutes("7d") == 7 * 24 * 60

    def test_hours(self):
        """Test parsing hours."""
        assert _parse_window_minutes("24h") == 24 * 60
        assert _parse_window_minutes("1h") == 60

    def test_weeks(self):
        """Test parsing weeks."""
        assert _parse_window_minutes("1w") == 7 * 24 * 60
        assert _parse_window_minutes("2w") == 14 * 24 * 60

    def test_default(self):
        """Test default value for unknown format (not ending in d/h/w)."""
        assert _parse_window_minutes("30m") == 30 * 24 * 60
        assert _parse_window_minutes("unknown") == 30 * 24 * 60


class TestPrintSloResult:
    """Tests for _print_slo_result function."""

    def test_healthy_result(self, capsys):
        """Test printing healthy result."""
        result = {
            "name": "availability",
            "objective": 99.9,
            "window": "30d",
            "total_budget_minutes": 43.2,
            "current_sli": 99.95,
            "burned_minutes": 21.6,
            "percent_consumed": 50.0,
            "status": "HEALTHY",
            "error": None,
        }

        _print_slo_result(result)

        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "availability" in captured.out

    def test_exhausted_result(self, capsys):
        """Test printing exhausted result."""
        result = {
            "name": "latency",
            "objective": 99.0,
            "window": "7d",
            "total_budget_minutes": 100.8,
            "current_sli": 98.0,
            "burned_minutes": 201.6,
            "percent_consumed": 200.0,
            "status": "EXHAUSTED",
            "error": None,
        }

        _print_slo_result(result)

        captured = capsys.readouterr()
        assert "[X]" in captured.out

    def test_error_result(self, capsys):
        """Test printing result with error."""
        result = {
            "name": "test",
            "objective": 99.9,
            "window": "30d",
            "total_budget_minutes": 43.2,
            "current_sli": None,
            "burned_minutes": None,
            "percent_consumed": None,
            "status": "ERROR",
            "error": "Connection refused",
        }

        _print_slo_result(result)

        captured = capsys.readouterr()
        assert "Connection refused" in captured.out


class TestRegisterSloParser:
    """Tests for register_slo_parser function."""

    def test_registers_slo_subcommand(self):
        """Test that slo subcommand is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_slo_parser(subparsers)

        args = parser.parse_args(["slo", "show", "test-service"])
        assert args.service == "test-service"

    def test_registers_list_command(self):
        """Test that list command is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_slo_parser(subparsers)

        args = parser.parse_args(["slo", "list"])
        assert args.slo_command == "list"

    def test_registers_collect_command(self):
        """Test that collect command is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_slo_parser(subparsers)

        args = parser.parse_args(
            ["slo", "collect", "my-service", "--prometheus-url", "http://prom:9090"]
        )
        assert args.service == "my-service"
        assert args.prometheus_url == "http://prom:9090"

    def test_registers_blame_command(self):
        """Test that blame command is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_slo_parser(subparsers)

        args = parser.parse_args(
            ["slo", "blame", "my-service", "--days", "14", "--min-confidence", "0.7"]
        )
        assert args.service == "my-service"
        assert args.days == 14
        assert args.min_confidence == 0.7


class TestHandleSloCommand:
    """Tests for handle_slo_command function."""

    @patch("nthlayer.cli.slo.slo_show_command")
    def test_handles_show_command(self, mock_show):
        """Test handling show command."""
        mock_show.return_value = 0

        args = argparse.Namespace(
            slo_command="show",
            service="test",
            file=None,
        )

        result = handle_slo_command(args)

        assert result == 0
        mock_show.assert_called_once()

    @patch("nthlayer.cli.slo.slo_list_command")
    def test_handles_list_command(self, mock_list):
        """Test handling list command."""
        mock_list.return_value = 0

        args = argparse.Namespace(slo_command="list")

        result = handle_slo_command(args)

        assert result == 0
        mock_list.assert_called_once()

    @patch("nthlayer.cli.slo.slo_collect_command")
    def test_handles_collect_command(self, mock_collect):
        """Test handling collect command."""
        mock_collect.return_value = 0

        args = argparse.Namespace(
            slo_command="collect",
            service="test",
            prometheus_url="http://prom:9090",
            file=None,
        )

        result = handle_slo_command(args)

        assert result == 0
        mock_collect.assert_called_once()

    @patch("nthlayer.cli.slo.slo_blame_command")
    def test_handles_blame_command(self, mock_blame):
        """Test handling blame command."""
        mock_blame.return_value = 0

        args = argparse.Namespace(
            slo_command="blame",
            service="test",
            days=7,
            min_confidence=0.5,
        )

        result = handle_slo_command(args)

        assert result == 0
        mock_blame.assert_called_once()

    def test_handles_no_subcommand(self, capsys):
        """Test handling when no subcommand specified."""
        args = argparse.Namespace(slo_command=None)

        result = handle_slo_command(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.out


class TestCollectSloMetrics:
    """Tests for _collect_slo_metrics async function."""

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_healthy_slo(self, mock_provider_class):
        """Test collecting healthy SLO metrics."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.9995)
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up{service='$service'}"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["name"] == "availability"
        assert results[0]["status"] == "HEALTHY"
        assert results[0]["current_sli"] is not None

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_warning_status(self, mock_provider_class):
        """Test collecting SLO with warning status."""
        from nthlayer.cli.slo import _collect_slo_metrics

        # For 99.9% objective, error budget = 0.1%
        # For 60% consumed: SLI = 1 - (0.001 * 0.6) = 0.9994
        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.9994)
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] == "WARNING"

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_critical_status(self, mock_provider_class):
        """Test collecting SLO with critical status."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.9992)  # ~80% budget consumed
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] in ["CRITICAL", "WARNING"]

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_exhausted_status(self, mock_provider_class):
        """Test collecting SLO with exhausted budget."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.98)  # 2% error = exhausted
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] == "EXHAUSTED"

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_no_data(self, mock_provider_class):
        """Test collecting SLO when no data returned."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.0)
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] == "NO_DATA"

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_no_query(self, mock_provider_class):
        """Test collecting SLO with no query defined."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {"objective": 99.9, "window": "30d", "indicator": {}}

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] == "NO_QUERY"
        assert results[0]["error"] == "No query defined in SLO indicator"

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_prometheus_error(self, mock_provider_class):
        """Test collecting SLO with Prometheus error."""
        from nthlayer.cli.slo import _collect_slo_metrics
        from nthlayer.providers.prometheus import PrometheusProviderError

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(side_effect=PrometheusProviderError("Query failed"))
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        results = await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        assert len(results) == 1
        assert results[0]["status"] == "ERROR"
        assert "Query failed" in results[0]["error"]

    @pytest.mark.asyncio
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_service_substitution(self, mock_provider_class):
        """Test that service name is substituted in query."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.999)
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up{service='${service}'}"},
        }

        await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="my-service",
        )

        # Verify that service was substituted
        call_args = mock_provider.get_sli_value.call_args
        assert "my-service" in call_args[0][0]

    @pytest.mark.asyncio
    @patch.dict(
        "os.environ",
        {
            "NTHLAYER_METRICS_USER": "admin",
            "NTHLAYER_METRICS_PASSWORD": "secret",
        },
    )
    @patch("nthlayer.providers.prometheus.PrometheusProvider")
    async def test_auth_credentials(self, mock_provider_class):
        """Test collecting SLO with authentication credentials."""
        from nthlayer.cli.slo import _collect_slo_metrics

        mock_provider = MagicMock()
        mock_provider.get_sli_value = AsyncMock(return_value=0.999)
        mock_provider_class.return_value = mock_provider

        mock_slo = MagicMock()
        mock_slo.name = "availability"
        mock_slo.spec = {
            "objective": 99.9,
            "window": "30d",
            "indicator": {"query": "up"},
        }

        await _collect_slo_metrics(
            slo_resources=[mock_slo],
            prometheus_url="http://localhost:9090",
            service_name="test-service",
        )

        # Verify auth credentials were passed
        mock_provider_class.assert_called_once_with(
            "http://localhost:9090",
            username="admin",
            password="secret",
        )


class TestSloShowCommandAutoDiscovery:
    """Tests for service file auto-discovery in slo_show_command."""

    def test_finds_service_in_services_dir(self, capsys, monkeypatch):
        """Test finding service file in services/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            services_dir = Path(tmpdir) / "services"
            services_dir.mkdir()

            service_file = services_dir / "my-service.yaml"
            service_file.write_text("""
service:
  name: my-service
  team: test
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            result = slo_show_command(service="my-service", service_file=None)

        assert result == 0

    def test_finds_service_in_examples_dir(self, capsys, monkeypatch):
        """Test finding service file in examples/services/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            examples_dir = Path(tmpdir) / "examples" / "services"
            examples_dir.mkdir(parents=True)

            service_file = examples_dir / "example-service.yaml"
            service_file.write_text("""
service:
  name: example-service
  team: test
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            result = slo_show_command(service="example-service", service_file=None)

        assert result == 0

    def test_service_not_found_anywhere(self, capsys, monkeypatch):
        """Test when service file is not found in any location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            result = slo_show_command(service="nonexistent-service", service_file=None)

        assert result == 1
        captured = capsys.readouterr()
        assert "No service file found" in captured.out


class TestSloCollectCommandAutoDiscovery:
    """Tests for service file auto-discovery in slo_collect_command."""

    @patch("nthlayer.cli.slo._collect_slo_metrics")
    @patch("nthlayer.cli.slo.asyncio.run")
    def test_finds_service_in_services_dir(self, mock_run, mock_collect, capsys, monkeypatch):
        """Test finding service file in services/ directory."""
        mock_run.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            services_dir = Path(tmpdir) / "services"
            services_dir.mkdir()

            service_file = services_dir / "collect-service.yaml"
            service_file.write_text("""
service:
  name: collect-service
  team: test
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            result = slo_collect_command(
                service="collect-service",
                prometheus_url="http://localhost:9090",
                service_file=None,
            )

        assert result == 0

    def test_service_not_found_anywhere(self, capsys, monkeypatch):
        """Test when service file is not found in any location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            result = slo_collect_command(
                service="nonexistent",
                prometheus_url="http://localhost:9090",
                service_file=None,
            )

        assert result == 1
        captured = capsys.readouterr()
        assert "No service file found" in captured.out


class TestSloCollectPrometheusError:
    """Tests for Prometheus error handling in slo_collect_command."""

    @patch("nthlayer.cli.slo.asyncio.run")
    @patch("nthlayer.cli.slo.parse_service_file")
    def test_connection_error(self, mock_parse, mock_run, capsys):
        """Test handling Prometheus connection error."""
        ctx = MagicMock()
        ctx.name = "test"

        slo = MagicMock()
        slo.kind = "SLO"
        slo.name = "test"
        slo.spec = {}

        mock_parse.return_value = (ctx, [slo])
        mock_run.side_effect = ConnectionError("Connection refused")

        result = slo_collect_command(
            service="test",
            prometheus_url="http://localhost:9090",
            service_file="test.yaml",
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "Error querying Prometheus" in captured.out
        assert "NTHLAYER_PROMETHEUS_URL" in captured.out
