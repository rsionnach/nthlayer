"""Tests for environment management CLI commands.

Tests for list-environments, diff-envs, and validate-env commands.
"""

import tempfile
from pathlib import Path

import pytest


class TestListEnvironmentsCommand:
    """Tests for nthlayer list-environments command."""
    
    def test_lists_shared_environments(self):
        """Test that list-environments finds shared environment files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create environment files
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            
            (env_dir / "dev.yaml").write_text("environment: dev\n")
            (env_dir / "staging.yaml").write_text("environment: staging\n")
            (env_dir / "prod.yaml").write_text("environment: prod\n")
            
            from nthlayer.cli.environments import list_environments_command
            
            result = list_environments_command(directory=str(tmpdir))
            
            assert result == 0
    
    def test_lists_service_specific_environments(self):
        """Test that list-environments finds service-specific files."""
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
            
            (env_dir / "dev.yaml").write_text("environment: dev\n")
            (env_dir / "payment-api-dev.yaml").write_text("environment: dev\n")
            (env_dir / "payment-api-prod.yaml").write_text("environment: prod\n")
            
            from nthlayer.cli.environments import list_environments_command
            
            result = list_environments_command(service_file=str(service_file))
            
            assert result == 0
    
    def test_handles_missing_environments_directory(self):
        """Test error handling when environments directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from nthlayer.cli.environments import list_environments_command
            
            result = list_environments_command(directory=tmpdir)
            
            assert result == 1  # Error


class TestDiffEnvsCommand:
    """Tests for nthlayer diff-envs command."""
    
    def test_shows_service_tier_differences(self):
        """Test that diff-envs shows tier differences between environments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
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
            
            (env_dir / "prod.yaml").write_text("""
environment: prod
service:
  tier: critical
            """)
            
            from nthlayer.cli.environments import diff_envs_command
            
            result = diff_envs_command(
                str(service_file),
                "dev",
                "prod",
                show_all=False
            )
            
            assert result == 0
    
    def test_shows_slo_objective_differences(self):
        """Test that diff-envs shows SLO differences between environments."""
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
    name: availability
    spec:
      objective: 99.9
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
            
            (env_dir / "prod.yaml").write_text("""
environment: prod
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
            """)
            
            from nthlayer.cli.environments import diff_envs_command
            
            result = diff_envs_command(
                str(service_file),
                "dev",
                "prod",
                show_all=False
            )
            
            assert result == 0
    
    def test_show_all_flag_includes_identical_fields(self):
        """Test that --show-all displays even identical fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api
            """)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            
            (env_dir / "dev.yaml").write_text("environment: dev\n")
            (env_dir / "staging.yaml").write_text("environment: staging\n")
            
            from nthlayer.cli.environments import diff_envs_command
            
            result = diff_envs_command(
                str(service_file),
                "dev",
                "staging",
                show_all=True
            )
            
            assert result == 0


class TestValidateEnvCommand:
    """Tests for nthlayer validate-env command."""
    
    def test_validates_valid_environment_file(self):
        """Test that validate-env passes for valid files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
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
            
            from nthlayer.cli.environments import validate_env_command
            
            result = validate_env_command("dev", directory=str(tmpdir), strict=False)
            
            assert result == 0
    
    def test_detects_missing_environment_field(self):
        """Test that validate-env catches missing 'environment' field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            
            (env_dir / "dev.yaml").write_text("""
service:
  tier: low
            """)
            
            from nthlayer.cli.environments import validate_env_command
            
            result = validate_env_command("dev", directory=str(tmpdir), strict=False)
            
            assert result == 1  # Should fail
    
    def test_warns_on_environment_name_mismatch(self):
        """Test that validate-env warns when environment name doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            
            (env_dir / "dev.yaml").write_text("""
environment: development
service:
  tier: low
            """)
            
            from nthlayer.cli.environments import validate_env_command
            
            # Should pass with warning (name mismatch)
            result = validate_env_command("dev", directory=str(tmpdir), strict=False)
            
            assert result == 0  # Passes but shows warning
    
    def test_tests_merge_with_service_file(self):
        """Test that validate-env can test merge with a service file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            service_file = tmpdir / "payment-api.yaml"
            service_file.write_text("""
service:
  name: payment-api
  team: payments
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
            
            from nthlayer.cli.environments import validate_env_command
            
            result = validate_env_command(
                "dev",
                service_file=str(service_file),
                directory=None,
                strict=False
            )
            
            assert result == 0


class TestAutoEnvironmentDetection:
    """Tests for automatic environment detection from CI/CD context."""
    
    def test_detects_from_nthlayer_env_var(self, monkeypatch):
        """Test detection from NTHLAYER_ENV variable."""
        monkeypatch.setenv("NTHLAYER_ENV", "staging")
        
        from nthlayer.specs.environment_detection import detect_environment
        
        env = detect_environment()
        
        assert env == "staging"
    
    def test_detects_from_kubernetes_namespace(self, monkeypatch):
        """Test detection from K8S_NAMESPACE variable."""
        monkeypatch.setenv("K8S_NAMESPACE", "payments-prod")
        
        from nthlayer.specs.environment_detection import detect_environment
        
        env = detect_environment()
        
        assert env == "prod"
    
    def test_detects_from_git_branch(self, monkeypatch):
        """Test detection from git branch name."""
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        
        from nthlayer.specs.environment_detection import detect_environment
        
        env = detect_environment()
        
        assert env == "prod"
        
        monkeypatch.setenv("GITHUB_REF_NAME", "develop")
        env = detect_environment()
        assert env == "dev"
    
    def test_explicit_env_overrides_auto_detection(self, monkeypatch):
        """Test that explicit --env flag overrides auto-detection."""
        monkeypatch.setenv("NTHLAYER_ENV", "staging")
        
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(explicit_env="prod", auto_detect=True)
        
        assert env == "prod"  # Explicit wins


class TestEnvironmentAwareGates:
    """Tests for environment-specific deployment gate thresholds."""
    
    def test_dev_has_lenient_thresholds(self):
        """Test that development has relaxed thresholds."""
        from nthlayer.specs.environment_gates import get_deployment_gate_thresholds
        
        thresholds = get_deployment_gate_thresholds("critical", "dev")
        
        assert thresholds["block"] == 0.50  # Block at 50% in dev
        assert thresholds["warn"] == 0.70
    
    def test_prod_has_strict_thresholds(self):
        """Test that production has strict thresholds."""
        from nthlayer.specs.environment_gates import get_deployment_gate_thresholds
        
        thresholds = get_deployment_gate_thresholds("critical", "prod")
        
        assert thresholds["block"] == 0.10  # Block at 10% in prod
        assert thresholds["warn"] == 0.20
    
    def test_staging_is_between_dev_and_prod(self):
        """Test that staging thresholds are between dev and prod."""
        from nthlayer.specs.environment_gates import get_deployment_gate_thresholds
        
        dev_thresholds = get_deployment_gate_thresholds("critical", "dev")
        staging_thresholds = get_deployment_gate_thresholds("critical", "staging")
        prod_thresholds = get_deployment_gate_thresholds("critical", "prod")
        
        assert prod_thresholds["block"] < staging_thresholds["block"] < dev_thresholds["block"]
    
    def test_should_block_deployment_logic(self):
        """Test deployment blocking logic with environment thresholds."""
        from nthlayer.specs.environment_gates import should_block_deployment
        
        # Dev allows high consumption
        blocked, reason = should_block_deployment(0.30, "critical", "dev")
        assert not blocked  # 30% is under 50% dev threshold
        
        # Prod blocks at low consumption
        blocked, reason = should_block_deployment(0.15, "critical", "prod")
        assert blocked  # 15% exceeds 10% prod threshold


class TestEnvironmentAwareAlerts:
    """Tests for environment-aware alert filtering."""
    
    def test_dev_gets_only_critical_alerts(self):
        """Test that dev environment filters to critical alerts only."""
        from nthlayer.alerts.models import AlertRule
        from nthlayer.specs.environment_alerts import filter_alerts_by_environment
        
        alerts = [
            AlertRule(name="db_down", expr="pg_up == 0", severity="critical", technology="postgres"),
            AlertRule(name="db_slow", expr="pg_slow > 1", severity="warning", technology="postgres"),
            AlertRule(name="db_info", expr="pg_info > 0", severity="info", technology="postgres"),
        ]
        
        filtered = filter_alerts_by_environment(alerts, environment="dev")
        
        assert len(filtered) == 1
        assert filtered[0].severity == "critical"
    
    def test_staging_gets_critical_and_warning(self):
        """Test that staging gets critical + warning alerts."""
        from nthlayer.alerts.models import AlertRule
        from nthlayer.specs.environment_alerts import filter_alerts_by_environment
        
        alerts = [
            AlertRule(name="db_down", expr="pg_up == 0", severity="critical", technology="postgres"),
            AlertRule(name="db_slow", expr="pg_slow > 1", severity="warning", technology="postgres"),
            AlertRule(name="db_info", expr="pg_info > 0", severity="info", technology="postgres"),
        ]
        
        filtered = filter_alerts_by_environment(alerts, environment="staging")
        
        assert len(filtered) == 2
        assert filtered[0].severity == "critical"
        assert filtered[1].severity == "warning"
    
    def test_prod_gets_all_alerts(self):
        """Test that production gets all alerts."""
        from nthlayer.alerts.models import AlertRule
        from nthlayer.specs.environment_alerts import filter_alerts_by_environment
        
        alerts = [
            AlertRule(name="db_down", expr="pg_up == 0", severity="critical", technology="postgres"),
            AlertRule(name="db_slow", expr="pg_slow > 1", severity="warning", technology="postgres"),
            AlertRule(name="db_info", expr="pg_info > 0", severity="info", technology="postgres"),
        ]
        
        filtered = filter_alerts_by_environment(alerts, environment="prod")
        
        assert len(filtered) == 3
    
    def test_combines_environment_and_tier_filtering(self):
        """Test that environment and tier filters are combined."""
        from nthlayer.alerts.models import AlertRule
        from nthlayer.specs.environment_alerts import filter_alerts_by_environment
        
        alerts = [
            AlertRule(name="db_down", expr="pg_up == 0", severity="critical", technology="postgres"),
            AlertRule(name="db_slow", expr="pg_slow > 1", severity="warning", technology="postgres"),
            AlertRule(name="db_info", expr="pg_info > 0", severity="info", technology="postgres"),
        ]
        
        # Low tier in prod: only critical
        filtered = filter_alerts_by_environment(alerts, environment="prod", tier="low")
        
        assert len(filtered) == 1
        assert filtered[0].severity == "critical"
        
        # Standard tier in prod: critical + warning
        filtered = filter_alerts_by_environment(alerts, environment="prod", tier="standard")
        
        assert len(filtered) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
