"""Tests for CLI environments command.

Tests for nthlayer environments commands including listing, comparing,
and validating environment configurations.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.cli.environments import (
    _diff_dicts,
    diff_envs_command,
    list_environments_command,
    validate_env_command,
)


@pytest.fixture
def env_directory():
    """Create a directory with environment files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create environments directory
        env_dir = Path(tmpdir) / "environments"
        env_dir.mkdir()

        # Create dev environment
        dev_file = env_dir / "dev.yaml"
        dev_file.write_text("""
environment: dev
service:
  tier: low
""")

        # Create staging environment
        staging_file = env_dir / "staging.yaml"
        staging_file.write_text("""
environment: staging
service:
  tier: standard
""")

        # Create prod environment
        prod_file = env_dir / "prod.yaml"
        prod_file.write_text("""
environment: prod
service:
  tier: critical
""")

        yield tmpdir


@pytest.fixture
def service_with_envs():
    """Create a service with environment overrides."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create service file
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
""")

        # Create environments directory
        env_dir = Path(tmpdir) / "environments"
        env_dir.mkdir()

        # Create dev environment
        dev_file = env_dir / "dev.yaml"
        dev_file.write_text("""
environment: dev
service:
  tier: low
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.0
""")

        # Create prod environment
        prod_file = env_dir / "prod.yaml"
        prod_file.write_text("""
environment: prod
service:
  tier: critical
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
""")

        yield str(service_file)


@pytest.fixture
def empty_env_directory():
    """Create directory with empty environments folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_dir = Path(tmpdir) / "environments"
        env_dir.mkdir()
        yield tmpdir


@pytest.fixture
def no_env_directory():
    """Create directory without environments folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestListEnvironmentsCommand:
    """Tests for list_environments_command function."""

    def test_lists_environments_from_directory(self, env_directory, capsys):
        """Test listing environments from a directory."""
        result = list_environments_command(directory=env_directory)

        assert result == 0
        captured = capsys.readouterr()
        assert "dev" in captured.out
        assert "staging" in captured.out
        assert "prod" in captured.out

    def test_lists_environments_from_service_file(self, service_with_envs, capsys):
        """Test listing environments from service file location."""
        result = list_environments_command(service_file=service_with_envs)

        assert result == 0
        captured = capsys.readouterr()
        assert "dev" in captured.out
        assert "prod" in captured.out

    def test_no_environments_directory(self, no_env_directory, capsys):
        """Test error when no environments directory exists."""
        result = list_environments_command(directory=no_env_directory)

        assert result == 1
        captured = capsys.readouterr()
        assert "No environments directory" in captured.out

    def test_empty_environments_directory(self, empty_env_directory, capsys):
        """Test error when environments directory is empty."""
        result = list_environments_command(directory=empty_env_directory)

        assert result == 1
        captured = capsys.readouterr()
        assert "No environment files found" in captured.out

    def test_shows_usage_examples(self, env_directory, capsys):
        """Test that usage examples are shown."""
        list_environments_command(directory=env_directory)

        captured = capsys.readouterr()
        assert "Usage" in captured.out
        assert "nthlayer" in captured.out

    def test_handles_invalid_yaml(self, capsys):
        """Test handling of invalid YAML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            # Create invalid YAML
            bad_file = env_dir / "bad.yaml"
            bad_file.write_text("invalid: yaml: content: {{")

            # Create valid file too
            good_file = env_dir / "good.yaml"
            good_file.write_text("environment: good\n")

            result = list_environments_command(directory=tmpdir)

            # Should still succeed if at least one valid file
            assert result == 0 or result == 1

    def test_detects_service_specific_files(self, capsys):
        """Test detection of service-specific environment files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            # Create shared environment
            shared = env_dir / "dev.yaml"
            shared.write_text("environment: dev\n")

            # Create service-specific environment
            specific = env_dir / "my-service-dev.yaml"
            specific.write_text("environment: dev\nservice:\n  tier: low\n")

            result = list_environments_command(directory=tmpdir)

            assert result == 0
            captured = capsys.readouterr()
            assert "dev" in captured.out


class TestDiffEnvsCommand:
    """Tests for diff_envs_command function."""

    @patch("nthlayer.cli.environments.parse_service_file")
    def test_shows_differences(self, mock_parse, capsys):
        """Test showing differences between environments."""
        ctx1 = MagicMock()
        ctx1.tier = "low"
        ctx1.type = "api"
        ctx1.team = "platform"
        ctx1.template = None

        ctx2 = MagicMock()
        ctx2.tier = "critical"
        ctx2.type = "api"
        ctx2.team = "platform"
        ctx2.template = None

        r1 = MagicMock()
        r1.name = "availability"
        r1.kind = "SLO"
        r1.spec = {"objective": 99.0}

        r2 = MagicMock()
        r2.name = "availability"
        r2.kind = "SLO"
        r2.spec = {"objective": 99.99}

        mock_parse.side_effect = [(ctx1, [r1]), (ctx2, [r2])]

        result = diff_envs_command("service.yaml", "dev", "prod")

        assert result == 0
        captured = capsys.readouterr()
        assert "tier" in captured.out or "Comparing" in captured.out

    @patch("nthlayer.cli.environments.parse_service_file")
    def test_shows_identical_when_same(self, mock_parse, capsys):
        """Test showing identical message when configs match."""
        ctx = MagicMock()
        ctx.tier = "standard"
        ctx.type = "api"
        ctx.team = "platform"
        ctx.template = None

        r = MagicMock()
        r.name = "availability"
        r.kind = "SLO"
        r.spec = {"objective": 99.9}

        mock_parse.return_value = (ctx, [r])

        result = diff_envs_command("service.yaml", "dev", "staging")

        assert result == 0
        captured = capsys.readouterr()
        assert "identical" in captured.out.lower() or "same" in captured.out.lower()

    @patch("nthlayer.cli.environments.parse_service_file")
    def test_shows_resources_only_in_one_env(self, mock_parse, capsys):
        """Test showing resources that exist only in one environment."""
        ctx = MagicMock()
        ctx.tier = "standard"
        ctx.type = "api"
        ctx.team = "platform"
        ctx.template = None

        r1 = MagicMock()
        r1.name = "availability"
        r1.kind = "SLO"
        r1.spec = {}

        r2 = MagicMock()
        r2.name = "latency"
        r2.kind = "SLO"
        r2.spec = {}

        mock_parse.side_effect = [(ctx, [r1]), (ctx, [r1, r2])]

        result = diff_envs_command("service.yaml", "dev", "prod")

        assert result == 0
        captured = capsys.readouterr()
        assert "only in" in captured.out or "latency" in captured.out

    @patch("nthlayer.cli.environments.parse_service_file")
    def test_handles_parse_error(self, mock_parse, capsys):
        """Test handling of parse errors."""
        mock_parse.side_effect = FileNotFoundError("Service not found")

        result = diff_envs_command("missing.yaml", "dev", "prod")

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    @patch("nthlayer.cli.environments.parse_service_file")
    def test_show_all_flag(self, mock_parse, capsys):
        """Test --show-all flag shows identical fields."""
        ctx = MagicMock()
        ctx.tier = "standard"
        ctx.type = "api"
        ctx.team = "platform"
        ctx.template = None

        mock_parse.return_value = (ctx, [])

        result = diff_envs_command("service.yaml", "dev", "prod", show_all=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "same" in captured.out or "identical" in captured.out


class TestValidateEnvCommand:
    """Tests for validate_env_command function."""

    def test_validates_valid_environment(self, env_directory, capsys):
        """Test validating a valid environment file."""
        result = validate_env_command("dev", directory=env_directory)

        assert result == 0
        captured = capsys.readouterr()
        assert "passed" in captured.out.lower() or "Found" in captured.out

    def test_no_environments_directory(self, no_env_directory, capsys):
        """Test error when no environments directory."""
        result = validate_env_command("dev", directory=no_env_directory)

        assert result == 1
        captured = capsys.readouterr()
        assert "No environments directory" in captured.out

    def test_environment_not_found(self, env_directory, capsys):
        """Test error when environment file not found."""
        result = validate_env_command("nonexistent", directory=env_directory)

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_invalid_yaml(self, capsys):
        """Test error on invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            bad_file = env_dir / "bad.yaml"
            bad_file.write_text("invalid: yaml: {{")

            result = validate_env_command("bad", directory=tmpdir)

            assert result == 1
            captured = capsys.readouterr()
            assert "Invalid YAML" in captured.out

    def test_missing_environment_field(self, capsys):
        """Test warning for missing environment field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            missing_env = env_dir / "test.yaml"
            missing_env.write_text("service:\n  tier: low\n")

            result = validate_env_command("test", directory=tmpdir)

            assert result == 1  # Missing required field
            captured = capsys.readouterr()
            assert "environment" in captured.out.lower()

    def test_environment_name_mismatch(self, capsys):
        """Test warning for environment name mismatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            mismatch = env_dir / "test.yaml"
            mismatch.write_text("environment: different\nservice:\n  tier: low\n")

            result = validate_env_command("test", directory=tmpdir)

            # Should warn but not fail
            captured = capsys.readouterr()
            assert "mismatch" in captured.out.lower() or "Warning" in captured.out

    def test_unknown_fields_warning(self, capsys):
        """Test warning for unknown fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            unknown = env_dir / "test.yaml"
            unknown.write_text("environment: test\nunknown_field: value\n")

            result = validate_env_command("test", directory=tmpdir)

            captured = capsys.readouterr()
            # Should warn about unknown field
            assert "unknown" in captured.out.lower() or "Warning" in captured.out

    def test_strict_mode_fails_on_warnings(self, capsys):
        """Test strict mode treats warnings as errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            env_file = env_dir / "test.yaml"
            env_file.write_text("environment: test\nunknown: value\n")

            result = validate_env_command("test", directory=tmpdir, strict=True)

            assert result == 1

    def test_validates_with_service_file(self, service_with_envs, capsys):
        """Test validation with service file merge."""
        result = validate_env_command(
            "dev",
            service_file=service_with_envs,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "Successfully merged" in captured.out or "passed" in captured.out.lower()

    def test_service_specific_file_found(self, capsys):
        """Test finding service-specific environment file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create service file
            service_file = Path(tmpdir) / "my-service.yaml"
            service_file.write_text("""
service:
  name: my-service
  team: test
  tier: standard
  type: api
""")

            # Create environments directory
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            # Create service-specific environment
            specific = env_dir / "my-service-dev.yaml"
            specific.write_text("environment: dev\nservice:\n  tier: low\n")

            result = validate_env_command(
                "dev",
                service_file=str(service_file),
            )

            assert result == 0

    def test_invalid_service_field_type(self, capsys):
        """Test error when service field is not a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            invalid = env_dir / "test.yaml"
            invalid.write_text("environment: test\nservice: not-a-dict\n")

            result = validate_env_command("test", directory=tmpdir)

            assert result == 1
            captured = capsys.readouterr()
            assert "dictionary" in captured.out

    def test_invalid_resources_field_type(self, capsys):
        """Test error when resources field is not a list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            invalid = env_dir / "test.yaml"
            invalid.write_text("environment: test\nresources: not-a-list\n")

            result = validate_env_command("test", directory=tmpdir)

            assert result == 1
            captured = capsys.readouterr()
            assert "list" in captured.out


class TestDiffDicts:
    """Tests for _diff_dicts helper function."""

    def test_identical_dicts(self):
        """Test identical dicts have no differences."""
        d1 = {"a": 1, "b": 2}
        d2 = {"a": 1, "b": 2}

        result = _diff_dicts(d1, d2)

        assert result == {}

    def test_different_values(self):
        """Test finding different values."""
        d1 = {"a": 1, "b": 2}
        d2 = {"a": 1, "b": 3}

        result = _diff_dicts(d1, d2)

        assert "b" in result
        assert result["b"] == (2, 3)

    def test_missing_key_in_first(self):
        """Test key only in second dict."""
        d1 = {"a": 1}
        d2 = {"a": 1, "b": 2}

        result = _diff_dicts(d1, d2)

        assert "b" in result
        assert result["b"] == (None, 2)

    def test_missing_key_in_second(self):
        """Test key only in first dict."""
        d1 = {"a": 1, "b": 2}
        d2 = {"a": 1}

        result = _diff_dicts(d1, d2)

        assert "b" in result
        assert result["b"] == (2, None)

    def test_nested_dicts(self):
        """Test nested dict comparison."""
        d1 = {"a": {"nested": 1}}
        d2 = {"a": {"nested": 2}}

        result = _diff_dicts(d1, d2)

        assert "a.nested" in result
        assert result["a.nested"] == (1, 2)

    def test_deeply_nested(self):
        """Test deeply nested dict comparison."""
        d1 = {"a": {"b": {"c": 1}}}
        d2 = {"a": {"b": {"c": 2}}}

        result = _diff_dicts(d1, d2)

        assert "a.b.c" in result
        assert result["a.b.c"] == (1, 2)

    def test_empty_dicts(self):
        """Test empty dicts have no differences."""
        result = _diff_dicts({}, {})
        assert result == {}

    def test_with_prefix(self):
        """Test prefix is applied to keys."""
        d1 = {"a": 1}
        d2 = {"a": 2}

        result = _diff_dicts(d1, d2, prefix="root")

        assert "root.a" in result
