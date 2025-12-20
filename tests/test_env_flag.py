"""Tests for multi-environment support with --env flag."""

import tempfile
from pathlib import Path

import pytest
import yaml
from nthlayer.cli.generate import generate_slo_command
from nthlayer.specs.parser import parse_service_file


def test_env_flag_loads_environment_overrides():
    """Test that --env flag loads and merges environment-specific configuration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create base service file
        service_file = tmpdir / "payment-api.yaml"
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
      objective: 99.9
      window: 30d
        """)

        # Create environment directory
        env_dir = tmpdir / "environments"
        env_dir.mkdir()

        # Create dev environment override
        dev_env = env_dir / "dev.yaml"
        dev_env.write_text("""
environment: dev
service:
  tier: low
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.0
        """)

        # Parse without environment
        context_base, resources_base = parse_service_file(service_file)
        assert context_base.tier == "critical"
        assert resources_base[0].spec["objective"] == 99.9

        # Parse with dev environment
        context_dev, resources_dev = parse_service_file(service_file, environment="dev")
        assert context_dev.tier == "low"  # Overridden
        assert context_dev.environment == "dev"  # Set
        assert resources_dev[0].spec["objective"] == 99.0  # Overridden


def test_env_flag_in_slo_generator():
    """Test that generate-slo command accepts and uses environment parameter."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create service file
        service_file = tmpdir / "test-api.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        success_rate:
          total_query: "sum(rate(http_requests_total[5m]))"
          error_query: "sum(rate(http_requests_total{status=~'5..'}[5m]))"
        """)

        # Create environments
        env_dir = tmpdir / "environments"
        env_dir.mkdir()

        (env_dir / "dev.yaml").write_text("""
environment: dev
service:
  tier: low
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0
        """)

        output_dir = tmpdir / "generated"

        # Generate with dev environment
        result = generate_slo_command(
            str(service_file),
            output_dir=str(output_dir),
            format="sloth",
            environment="dev",
            dry_run=False,
        )

        assert result == 0

        # Check generated file has dev configuration
        generated_file = output_dir / "sloth" / "test-api.yaml"
        assert generated_file.exists()

        with open(generated_file) as f:
            sloth_spec = yaml.safe_load(f)

        assert sloth_spec["labels"]["tier"] == "low"
        assert sloth_spec["slos"][0]["objective"] == 95.0


def test_environment_not_found_uses_base():
    """Test that if environment file doesn't exist, uses base configuration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        service_file = tmpdir / "test-api.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: critical
  type: api
        """)

        # Request nonexistent environment - should use base config
        context, resources = parse_service_file(service_file, environment="nonexistent")

        assert context.tier == "critical"  # Base value
        assert context.environment == "nonexistent"  # Environment name is still set


def test_environment_variable_substitution():
    """Test that ${env} variable works in templates."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        service_file = tmpdir / "payment-api.yaml"
        service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability-${env}
    spec:
      objective: 99.9
      description: "Availability for ${env} environment"
        """)

        # Create staging environment
        env_dir = tmpdir / "environments"
        env_dir.mkdir()

        (env_dir / "staging.yaml").write_text("""
environment: staging
service:
  tier: standard
        """)

        # Parse with environment
        context, resources = parse_service_file(service_file, environment="staging")

        # Check that ${env} was substituted
        assert context.environment == "staging"
        assert resources[0].name == "availability-staging"
        assert resources[0].spec["description"] == "Availability for staging environment"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
