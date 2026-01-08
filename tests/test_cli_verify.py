"""Tests for CLI verify command.

Tests for nthlayer verify command including metric verification,
contract validation, and error handling.
"""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.verify import (
    _demo_verify_output,
    _print_exporter_guidance,
    _print_verification_results,
    handle_verify_command,
    register_verify_parser,
    verify_command,
)


@pytest.fixture
def sample_service_yaml():
    """Create a sample service YAML file for testing."""
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
""")
        yield str(service_file)


@pytest.fixture
def service_context():
    """Create a mock service context."""
    ctx = MagicMock()
    ctx.name = "test-service"
    ctx.team = "platform"
    return ctx


@pytest.fixture
def metric_contract():
    """Create a mock metric contract."""
    contract = MagicMock()
    metric1 = MagicMock()
    metric1.name = "http_requests_total"
    metric1.is_critical = True

    metric2 = MagicMock()
    metric2.name = "cache_hits_total"
    metric2.is_critical = False

    contract.metrics = [metric1, metric2]
    return contract


@pytest.fixture
def empty_contract():
    """Create an empty metric contract."""
    contract = MagicMock()
    contract.metrics = []
    return contract


@pytest.fixture
def successful_verification_result():
    """Create a successful verification result."""
    result = MagicMock()

    metric1 = MagicMock()
    metric1.name = "http_requests_total"
    metric1.is_critical = True

    metric2 = MagicMock()
    metric2.name = "cache_hits_total"
    metric2.is_critical = False

    result1 = MagicMock()
    result1.metric = metric1
    result1.exists = True
    result1.error = None

    result2 = MagicMock()
    result2.metric = metric2
    result2.exists = True
    result2.error = None

    result.results = [result1, result2]
    result.verified_count = 2
    result.missing_critical = []
    result.missing_optional = []
    result.all_verified = True
    result.critical_verified = True
    result.exit_code = 0
    return result


@pytest.fixture
def partial_verification_result():
    """Create a verification result with missing metrics."""
    result = MagicMock()

    metric1 = MagicMock()
    metric1.name = "http_requests_total"
    metric1.is_critical = True

    metric2 = MagicMock()
    metric2.name = "missing_metric"
    metric2.is_critical = True

    result1 = MagicMock()
    result1.metric = metric1
    result1.exists = True
    result1.error = None

    result2 = MagicMock()
    result2.metric = metric2
    result2.exists = False
    result2.error = None

    result.results = [result1, result2]
    result.verified_count = 1
    result.missing_critical = [result2]
    result.missing_optional = []
    result.all_verified = False
    result.critical_verified = False
    result.exit_code = 2
    return result


class TestVerifyCommand:
    """Tests for verify_command function."""

    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_successful_verification(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
        successful_verification_result,
    ):
        """Test successful metric verification."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = True
        mock_verifier.verify_contract.return_value = successful_verification_result
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 0

    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_critical_metrics_missing(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
        partial_verification_result,
    ):
        """Test verification with missing critical metrics returns 2."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = True
        mock_verifier.verify_contract.return_value = partial_verification_result
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 2

    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_no_fail_mode_returns_0(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
        partial_verification_result,
    ):
        """Test that fail_on_missing=False always returns 0."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = True
        mock_verifier.verify_contract.return_value = partial_verification_result
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
            fail_on_missing=False,
        )

        assert result == 0

    def test_no_prometheus_url_returns_error(self, sample_service_yaml):
        """Test that missing Prometheus URL returns exit code 2."""
        # Ensure env var is not set
        with patch.dict("os.environ", {}, clear=True):
            result = verify_command(
                service_file=sample_service_yaml,
                prometheus_url=None,
            )

        assert result == 2

    @patch.dict("os.environ", {"PROMETHEUS_URL": "http://from-env:9090"})
    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_uses_env_var_for_url(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
        successful_verification_result,
    ):
        """Test that PROMETHEUS_URL env var is used."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = True
        mock_verifier.verify_contract.return_value = successful_verification_result
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url=None,
        )

        assert result == 0
        mock_verifier_class.assert_called_with(prometheus_url="http://from-env:9090")

    @patch("nthlayer.cli.verify.parse_service_file")
    def test_invalid_service_file_returns_error(self, mock_parse, sample_service_yaml):
        """Test that invalid service file returns exit code 2."""
        mock_parse.side_effect = FileNotFoundError("File not found")

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 2

    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_connection_failure_returns_error(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
    ):
        """Test that connection failure returns exit code 2."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = False
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 2

    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_empty_contract_returns_success(
        self,
        mock_parse,
        mock_extract,
        sample_service_yaml,
        service_context,
        empty_contract,
    ):
        """Test that empty contract returns exit code 0."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = empty_contract

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
        )

        assert result == 0

    def test_demo_mode(self, sample_service_yaml, capsys):
        """Test demo mode returns exit code 1."""
        result = verify_command(
            service_file=sample_service_yaml,
            demo=True,
        )

        assert result == 1
        captured = capsys.readouterr()
        assert "Verification" in captured.out
        assert "demo" not in captured.out.lower()  # Demo flag not shown

    @patch("nthlayer.cli.verify.MetricVerifier")
    @patch("nthlayer.cli.verify.extract_metric_contract")
    @patch("nthlayer.cli.verify.parse_service_file")
    def test_with_environment_parameter(
        self,
        mock_parse,
        mock_extract,
        mock_verifier_class,
        sample_service_yaml,
        service_context,
        metric_contract,
        successful_verification_result,
    ):
        """Test verification with environment parameter."""
        mock_parse.return_value = (service_context, [])
        mock_extract.return_value = metric_contract

        mock_verifier = MagicMock()
        mock_verifier.test_connection.return_value = True
        mock_verifier.verify_contract.return_value = successful_verification_result
        mock_verifier_class.return_value = mock_verifier

        result = verify_command(
            service_file=sample_service_yaml,
            prometheus_url="http://prometheus:9090",
            environment="staging",
        )

        assert result == 0
        # Check environment was passed to parse_service_file
        mock_parse.assert_called_with(sample_service_yaml, environment="staging")


class TestPrintVerificationResults:
    """Tests for _print_verification_results function."""

    def test_all_verified(self, successful_verification_result, capsys):
        """Test output when all metrics verified."""
        _print_verification_results(successful_verification_result)

        captured = capsys.readouterr()
        assert "verified" in captured.out.lower()

    def test_critical_missing(self, partial_verification_result, capsys):
        """Test output when critical metrics missing."""
        _print_verification_results(partial_verification_result)

        captured = capsys.readouterr()
        assert "MISSING" in captured.out or "missing" in captured.out.lower()

    def test_shows_summary(self, successful_verification_result, capsys):
        """Test that summary is shown."""
        _print_verification_results(successful_verification_result)

        captured = capsys.readouterr()
        assert "Summary" in captured.out
        assert "Total" in captured.out

    def test_shows_recommendations_for_missing(self, partial_verification_result, capsys):
        """Test that recommendations shown for missing metrics."""
        _print_verification_results(partial_verification_result)

        captured = capsys.readouterr()
        assert "Recommendations" in captured.out or "blocking" in captured.out.lower()


class TestDemoVerifyOutput:
    """Tests for _demo_verify_output function."""

    def test_demo_with_service_file(self, sample_service_yaml, capsys):
        """Test demo output uses service name from file."""
        result = _demo_verify_output(sample_service_yaml)

        assert result == 1
        captured = capsys.readouterr()
        assert "test-service" in captured.out

    def test_demo_with_environment(self, sample_service_yaml, capsys):
        """Test demo output shows environment."""
        result = _demo_verify_output(sample_service_yaml, environment="staging")

        assert result == 1
        captured = capsys.readouterr()
        assert "staging" in captured.out

    def test_demo_with_missing_file(self, capsys):
        """Test demo output with nonexistent file uses default name."""
        result = _demo_verify_output("/nonexistent/file.yaml")

        assert result == 1
        captured = capsys.readouterr()
        assert "checkout-service" in captured.out  # Default name


class TestPrintExporterGuidance:
    """Tests for _print_exporter_guidance function."""

    @patch("nthlayer.verification.exporter_guidance.detect_missing_exporters")
    @patch("nthlayer.verification.exporter_guidance.format_exporter_guidance")
    def test_prints_guidance_when_missing(self, mock_format, mock_detect, capsys):
        """Test that exporter guidance is printed."""
        mock_detect.return_value = {"postgresql": ["pg_stat_activity_count"]}
        mock_format.return_value = ["Install postgresql exporter"]

        _print_exporter_guidance(["pg_stat_activity_count"])

        captured = capsys.readouterr()
        assert "postgresql" in captured.out.lower() or "Install" in captured.out

    @patch("nthlayer.verification.exporter_guidance.detect_missing_exporters")
    def test_no_output_when_no_missing(self, mock_detect, capsys):
        """Test no output when no missing exporters detected."""
        mock_detect.return_value = {}

        _print_exporter_guidance([])

        captured = capsys.readouterr()
        assert captured.out == ""


class TestRegisterVerifyParser:
    """Tests for register_verify_parser function."""

    def test_registers_subparser(self):
        """Test that verify subparser is registered."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        register_verify_parser(subparsers)

        # Should be able to parse verify command
        args = parser.parse_args(["verify", "test.yaml"])
        assert args.service_file == "test.yaml"

    def test_accepts_prometheus_url_option(self):
        """Test that --prometheus-url option is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_verify_parser(subparsers)

        args = parser.parse_args(["verify", "test.yaml", "--prometheus-url", "http://prom:9090"])
        assert args.prometheus_url == "http://prom:9090"

    def test_accepts_env_option(self):
        """Test that --env option is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_verify_parser(subparsers)

        args = parser.parse_args(["verify", "test.yaml", "--env", "staging"])
        assert args.environment == "staging"

    def test_accepts_no_fail_flag(self):
        """Test that --no-fail flag is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_verify_parser(subparsers)

        args = parser.parse_args(["verify", "test.yaml", "--no-fail"])
        assert args.no_fail is True

    def test_accepts_demo_flag(self):
        """Test that --demo flag is accepted."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_verify_parser(subparsers)

        args = parser.parse_args(["verify", "test.yaml", "--demo"])
        assert args.demo is True


class TestHandleVerifyCommand:
    """Tests for handle_verify_command function."""

    @patch("nthlayer.cli.verify.verify_command")
    def test_passes_args_correctly(self, mock_command):
        """Test that args are passed correctly to command."""
        mock_command.return_value = 0

        args = argparse.Namespace(
            service_file="test.yaml",
            prometheus_url="http://prom:9090",
            environment="staging",
            no_fail=False,
            demo=False,
        )

        result = handle_verify_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            service_file="test.yaml",
            prometheus_url="http://prom:9090",
            environment="staging",
            fail_on_missing=True,
            demo=False,
        )

    @patch("nthlayer.cli.verify.verify_command")
    def test_no_fail_inverts_to_fail_on_missing(self, mock_command):
        """Test that --no-fail sets fail_on_missing=False."""
        mock_command.return_value = 0

        args = argparse.Namespace(
            service_file="test.yaml",
            prometheus_url=None,
            environment=None,
            no_fail=True,
            demo=False,
        )

        handle_verify_command(args)

        call_args = mock_command.call_args
        assert call_args.kwargs["fail_on_missing"] is False

    @patch("nthlayer.cli.verify.verify_command")
    def test_handles_missing_optional_args(self, mock_command):
        """Test that missing optional args are handled."""
        mock_command.return_value = 0

        # Create args without optional fields
        args = argparse.Namespace(service_file="test.yaml")

        result = handle_verify_command(args)

        assert result == 0
        mock_command.assert_called_once_with(
            service_file="test.yaml",
            prometheus_url=None,
            environment=None,
            fail_on_missing=True,
            demo=False,
        )
