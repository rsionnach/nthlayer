"""Integration tests for multi-environment support.

These tests verify that the --env flag works end-to-end across all CLI commands.

Note: Some tests are marked as skipped due to Python 3.9 compatibility issues
in the existing codebase (unrelated to the environment feature).
"""

import tempfile
from pathlib import Path

import pytest
import yaml


class TestEnvironmentFileDiscovery:
    """Test environment file discovery and loading."""
    
    def test_finds_shared_environment_file(self):
        """Test that shared environment files are found and loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create service file
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
            """)
            
            # Create shared environment file
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "dev.yaml").write_text("""
environment: dev
service:
  tier: low
            """)
            
            from nthlayer.specs.environments import EnvironmentLoader
            
            # Should find dev.yaml
            env_file = EnvironmentLoader.find_environment_file(service_file, "dev")
            assert env_file is not None
            assert env_file.name == "dev.yaml"
    
    def test_service_specific_overrides_shared(self):
        """Test that service-specific files take precedence over shared."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
            """)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            
            # Shared file
            (env_dir / "dev.yaml").write_text("""
environment: dev
service:
  tier: low
            """)
            
            # Service-specific file (should win)
            (env_dir / "payment-api-dev.yaml").write_text("""
environment: dev
service:
  tier: standard
            """)
            
            from nthlayer.specs.environments import EnvironmentLoader
            
            env_file = EnvironmentLoader.find_environment_file(service_file, "dev")
            assert env_file is not None
            assert env_file.name == "payment-api-dev.yaml"


class TestConfigurationMerging:
    """Test that environment configurations are properly merged."""
    
    def test_deep_merge_service_fields(self):
        """Test that service fields are deep merged, not replaced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  metadata:
    cost_center: 12345
    owner: alice@company.com
            """)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "dev.yaml").write_text("""
environment: dev
service:
  tier: low
            """)
            
            from nthlayer.specs.parser import parse_service_file
            
            context, _ = parse_service_file(service_file, environment="dev")
            
            # Overridden field
            assert context.tier == "low"
            
            # Inherited fields
            assert context.name == "payment-api"
            assert context.team == "payments"
            assert context.type == "api"
            assert context.metadata["cost_center"] == 12345
    
    def test_resource_spec_deep_merge(self):
        """Test that resource specs are deep merged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
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
          total_query: "sum(rate(requests_total[5m]))"
          error_query: "sum(rate(requests_error[5m]))"
            """)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "dev.yaml").write_text("""
environment: dev
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 95.0
            """)
            
            from nthlayer.specs.parser import parse_service_file
            
            _, resources = parse_service_file(service_file, environment="dev")
            
            slo = resources[0]
            
            # Overridden
            assert slo.spec["objective"] == 95.0
            
            # Inherited
            assert slo.spec["window"] == "30d"
            assert "indicator" in slo.spec


class TestCLIEnvironmentFlag:
    """Test that CLI commands accept and use the --env flag."""
    
    def test_generate_slo_with_env_flag(self):
        """Test generate-slo command with --env flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
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
          total_query: 'sum(rate(http_requests_total[5m]))'
          error_query: 'sum(rate(http_requests_total{status=~"5.."}[5m]))'
            """)
            
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
            
            from nthlayer.cli.generate import generate_slo_command
            
            # Generate with dev environment
            result = generate_slo_command(
                str(service_file),
                output_dir=str(output_dir),
                format="sloth",
                environment="dev",
                dry_run=False
            )
            
            assert result == 0
            
            # Check output
            output_file = output_dir / "sloth" / "test-api.yaml"
            assert output_file.exists()
            
            with open(output_file) as f:
                sloth_spec = yaml.safe_load(f)
            
            # Should use dev configuration
            assert sloth_spec["labels"]["tier"] == "low"
            assert sloth_spec["slos"][0]["objective"] == 95.0
    
    def test_validate_with_env_flag(self):
        """Test validate command with --env flag."""
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
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "dev.yaml").write_text("""
environment: dev
service:
  tier: low
            """)
            
            from nthlayer.cli.validate import validate_command
            
            # Should validate successfully with environment
            result = validate_command(
                str(service_file),
                environment="dev",
                strict=False
            )
            
            assert result == 0


class TestVariableSubstitution:
    """Test ${env} variable substitution in service definitions."""
    
    def test_env_variable_in_resource_name(self):
        """Test that ${env} is substituted in resource names."""
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
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "staging.yaml").write_text("""
environment: staging
service:
  tier: standard
            """)
            
            from nthlayer.specs.parser import parse_service_file
            
            context, resources = parse_service_file(service_file, environment="staging")
            
            # ${env} should be replaced
            assert context.environment == "staging"
            assert resources[0].name == "availability-staging"
            assert resources[0].spec["description"] == "Availability for staging environment"
    
    def test_env_variable_in_metadata(self):
        """Test that ${env} works in service metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  metadata:
    environment: ${env}
    namespace: payments-${env}
            """)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "prod.yaml").write_text("""
environment: prod
            """)
            
            from nthlayer.specs.parser import parse_service_file
            
            context, _ = parse_service_file(service_file, environment="prod")
            
            assert context.metadata["environment"] == "prod"
            assert context.metadata["namespace"] == "payments-prod"


class TestEnvironmentNotFound:
    """Test behavior when environment files don't exist."""
    
    def test_missing_environment_uses_base_config(self):
        """Test that missing environment files fallback to base config."""
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
            
            # No environments directory created
            
            from nthlayer.specs.parser import parse_service_file
            
            # Should use base config
            context, _ = parse_service_file(service_file, environment="nonexistent")
            
            assert context.tier == "critical"  # Base value
            assert context.environment == "nonexistent"  # Environment name still set


class TestMultipleEnvironments:
    """Test working with multiple environments for the same service."""
    
    def test_different_configs_per_environment(self):
        """Test that dev, staging, and prod have different configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Base service
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
            """)
            
            # Create environment files
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
            
            (env_dir / "staging.yaml").write_text("""
environment: staging
service:
  tier: standard
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.0
            """)
            
            (env_dir / "prod.yaml").write_text("""
environment: prod
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
            """)
            
            from nthlayer.specs.parser import parse_service_file
            
            # Dev
            dev_context, dev_resources = parse_service_file(service_file, environment="dev")
            assert dev_context.tier == "low"
            assert dev_resources[0].spec["objective"] == 95.0
            
            # Staging
            staging_context, staging_resources = parse_service_file(service_file, environment="staging")
            assert staging_context.tier == "standard"
            assert staging_resources[0].spec["objective"] == 99.0
            
            # Prod
            prod_context, prod_resources = parse_service_file(service_file, environment="prod")
            assert prod_context.tier == "critical"  # Inherited from base
            assert prod_resources[0].spec["objective"] == 99.99


# When Python 3.9 issues are resolved, remove the skip marker and tests will run
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
