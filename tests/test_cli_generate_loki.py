"""Tests for cli/generate_loki.py.

Tests for Loki LogQL alert generation CLI command.
"""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.generate_loki import (
    generate_loki_command,
    handle_loki_command,
    register_loki_parser,
)


@pytest.fixture
def service_with_dependencies():
    """Create service YAML with dependencies."""
    return """
service:
  name: payment-api
  team: payments-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
        - type: redis
"""


@pytest.fixture
def simple_service():
    """Create simple service YAML without dependencies."""
    return """
service:
  name: simple-api
  team: simple-team
  tier: tier-2
  type: api
"""


class TestGenerateLokiCommand:
    """Tests for generate_loki_command function."""

    def test_missing_service_file(self):
        """Test with non-existent service file."""
        result = generate_loki_command("/nonexistent/service.yaml")

        assert result == 1

    def test_invalid_yaml(self):
        """Test with invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.yaml"
            bad_file.write_text("not: valid: yaml: {{")

            result = generate_loki_command(str(bad_file))

        assert result == 1

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_dry_run(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test dry run mode."""
        # Setup mocks
        mock_context = MagicMock()
        mock_context.name = "payment-api"
        mock_context.type = "api"
        mock_context.tier = "tier-1"
        mock_context.team = "payments-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = ["postgres", "redis"]

        mock_alert1 = MagicMock()
        mock_alert1.category = "service"
        mock_alert2 = MagicMock()
        mock_alert2.category = "dependency"

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = [mock_alert1, mock_alert2]
        mock_generator.to_ruler_yaml.return_value = "groups:\n  - name: test\n    rules: []"
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file), dry_run=True)

        assert result == 0
        mock_generator.generate_for_service.assert_called_once()
        mock_generator.to_ruler_yaml.assert_called_once()
        mock_generator.write_ruler_file.assert_not_called()

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_generate_with_output(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test generating alerts with specific output path."""
        mock_context = MagicMock()
        mock_context.name = "payment-api"
        mock_context.type = "api"
        mock_context.tier = "tier-1"
        mock_context.team = "payments-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = ["postgres"]

        mock_alert = MagicMock()
        mock_alert.category = "service"

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = [mock_alert]
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            output_file = Path(tmpdir) / "alerts.yaml"

            result = generate_loki_command(str(service_file), output=str(output_file))

        assert result == 0
        mock_generator.write_ruler_file.assert_called_once()
        call_args = mock_generator.write_ruler_file.call_args
        assert call_args[0][1] == output_file

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_generate_default_output_path(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test generating alerts with default output path."""
        mock_context = MagicMock()
        mock_context.name = "payment-api"
        mock_context.type = "api"
        mock_context.tier = "tier-1"
        mock_context.team = "payments-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = []

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = []
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file))

        assert result == 0
        call_args = mock_generator.write_ruler_file.call_args
        # Default path should be generated/{service}/loki-alerts.yaml
        assert "payment-api" in str(call_args[0][1])

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_no_dependencies(self, mock_parse, mock_extract, mock_generator_class, simple_service):
        """Test generating alerts for service without dependencies."""
        mock_context = MagicMock()
        mock_context.name = "simple-api"
        mock_context.type = "api"
        mock_context.tier = "tier-2"
        mock_context.team = "simple-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = []

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = []
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(simple_service)

            result = generate_loki_command(str(service_file), dry_run=True)

        assert result == 0

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_dry_run_large_output(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test dry run with large YAML output (truncated)."""
        mock_context = MagicMock()
        mock_context.name = "payment-api"
        mock_context.type = "api"
        mock_context.tier = "tier-1"
        mock_context.team = "payments-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = ["postgres"]

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = []
        # Create a large YAML output (>2000 chars)
        mock_generator.to_ruler_yaml.return_value = "x" * 3000
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file), dry_run=True)

        assert result == 0

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_exception_handling(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test handling of exceptions during generation."""
        mock_parse.side_effect = ValueError("Invalid service configuration")

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file))

        assert result == 1

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_alert_breakdown(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test alert breakdown display."""
        mock_context = MagicMock()
        mock_context.name = "payment-api"
        mock_context.type = "api"
        mock_context.tier = "tier-1"
        mock_context.team = "payments-team"
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = ["postgres", "redis"]

        # Create mix of service and dependency alerts
        alerts = []
        for i in range(3):
            alert = MagicMock()
            alert.category = "service"
            alerts.append(alert)
        for i in range(5):
            alert = MagicMock()
            alert.category = "dependency"
            alerts.append(alert)

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = alerts
        mock_generator.to_ruler_yaml.return_value = "groups: []"
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file), dry_run=True)

        assert result == 0

    @patch("nthlayer.loki.LokiAlertGenerator")
    @patch("nthlayer.loki.generator.extract_dependencies_from_resources")
    @patch("nthlayer.specs.parser.parse_service_file")
    def test_no_team(
        self, mock_parse, mock_extract, mock_generator_class, service_with_dependencies
    ):
        """Test service without team."""
        mock_context = MagicMock()
        mock_context.name = "orphan-api"
        mock_context.type = "api"
        mock_context.tier = "tier-2"
        mock_context.team = None  # No team
        mock_parse.return_value = (mock_context, [])

        mock_extract.return_value = []

        mock_generator = MagicMock()
        mock_generator.generate_for_service.return_value = []
        mock_generator_class.return_value = mock_generator

        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(service_with_dependencies)

            result = generate_loki_command(str(service_file), dry_run=True)

        assert result == 0
        # Check that labels is empty dict when no team
        call_args = mock_generator.generate_for_service.call_args
        assert call_args[1]["labels"] == {}


class TestRegisterLokiParser:
    """Tests for register_loki_parser function."""

    def test_register_parser(self):
        """Test parser registration."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_loki_parser(subparsers)

        # Parse a test command
        args = parser.parse_args(["generate-loki-alerts", "test.yaml"])
        assert args.service_file == "test.yaml"
        assert args.output is None
        assert args.dry_run is False

    def test_register_parser_with_options(self):
        """Test parser registration with all options."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_loki_parser(subparsers)

        # Parse with all options
        args = parser.parse_args(
            [
                "generate-loki-alerts",
                "test.yaml",
                "--output",
                "output.yaml",
                "--dry-run",
            ]
        )
        assert args.service_file == "test.yaml"
        assert args.output == "output.yaml"
        assert args.dry_run is True

    def test_register_parser_short_options(self):
        """Test parser registration with short options."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_loki_parser(subparsers)

        # Parse with short options
        args = parser.parse_args(
            [
                "generate-loki-alerts",
                "test.yaml",
                "-o",
                "output.yaml",
            ]
        )
        assert args.output == "output.yaml"


class TestHandleLokiCommand:
    """Tests for handle_loki_command function."""

    @patch("nthlayer.cli.generate_loki.generate_loki_command")
    def test_handle_command(self, mock_generate):
        """Test handle_loki_command."""
        mock_generate.return_value = 0

        args = MagicMock()
        args.service_file = "test.yaml"
        args.output = "output.yaml"
        args.dry_run = True

        result = handle_loki_command(args)

        assert result == 0
        mock_generate.assert_called_once_with(
            service_file="test.yaml",
            output="output.yaml",
            dry_run=True,
        )

    @patch("nthlayer.cli.generate_loki.generate_loki_command")
    def test_handle_command_missing_attrs(self, mock_generate):
        """Test handle_loki_command with missing optional attrs."""
        mock_generate.return_value = 0

        args = MagicMock(spec=["service_file"])  # Only service_file attr
        args.service_file = "test.yaml"

        result = handle_loki_command(args)

        assert result == 0
        mock_generate.assert_called_once_with(
            service_file="test.yaml",
            output=None,
            dry_run=False,
        )
