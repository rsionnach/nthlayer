"""Integration tests for end-to-end workflows."""


import pytest
from nthlayer.cli.generate import generate_slo_command
from nthlayer.cli.init import init_command
from nthlayer.cli.validate import validate_command
from nthlayer.specs.parser import parse_service_file


class TestEndToEndWorkflows:
    """Test complete user workflows from init to generation."""
    
    def test_init_validate_generate_workflow(self, tmp_path, monkeypatch):
        """Complete happy path: init → validate → generate."""
        monkeypatch.chdir(tmp_path)
        
        # 1. Init service
        result = init_command("test-api", "test-team", "critical-api", interactive=False)
        assert result == 0
        assert (tmp_path / "test-api.yaml").exists()
        
        # 2. Validate
        result = validate_command(str(tmp_path / "test-api.yaml"))
        assert result == 0
        
        # 3. Generate SLOs
        result = generate_slo_command(
            str(tmp_path / "test-api.yaml"),
            output_dir=str(tmp_path / "generated"),
            format="sloth"
        )
        assert result == 0
        assert (tmp_path / "generated" / "sloth" / "test-api.yaml").exists()
        
        # 4. Verify generated SLOs
        sloth_file = tmp_path / "generated" / "sloth" / "test-api.yaml"
        import yaml
        with open(sloth_file) as f:
            sloth_spec = yaml.safe_load(f)
        
        assert sloth_spec["service"] == "test-api"
        assert len(sloth_spec["slos"]) == 2  # From critical-api template
    
    def test_template_override_workflow(self, tmp_path, monkeypatch):
        """Test workflow with template override."""
        monkeypatch.chdir(tmp_path)
        
        # 1. Init with template
        init_command("custom-api", "team", "critical-api", interactive=False)
        
        # 2. Add override to generated file
        service_file = tmp_path / "custom-api.yaml"
        content = service_file.read_text()
        
        # Uncomment the override section and add custom threshold
        override = """
resources:
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300
"""
        content += override
        service_file.write_text(content)
        
        # 3. Validate (should still be valid)
        result = validate_command(str(service_file))
        assert result == 0
        
        # 4. Parse and verify override worked
        context, resources = parse_service_file(service_file)
        latency_slo = next(r for r in resources if r.name == "latency-p95")
        assert latency_slo.spec["threshold_ms"] == 300
    
    def test_all_templates_workflow(self, tmp_path, monkeypatch):
        """Test workflow works for all templates."""
        monkeypatch.chdir(tmp_path)
        
        templates = ["critical-api", "standard-api", "low-api", "background-job", "pipeline"]
        
        for template in templates:
            service_name = f"test-{template}"
            
            # Init
            result = init_command(service_name, "team", template, interactive=False)
            assert result == 0
            
            # Validate
            service_file = tmp_path / f"{service_name}.yaml"
            result = validate_command(str(service_file))
            assert result == 0
            
            # Generate
            result = generate_slo_command(
                str(service_file),
                output_dir=str(tmp_path / "generated"),
                format="sloth"
            )
            assert result == 0
            
            # Verify
            sloth_file = tmp_path / "generated" / "sloth" / f"{service_name}.yaml"
            assert sloth_file.exists()


class TestTemplateIntegration:
    """Test template system integration."""
    
    def test_template_merging_preserves_order(self, tmp_path):
        """Template resources should maintain order after merging."""
        service_yaml = tmp_path / "test.yaml"
        service_yaml.write_text("""
service:
  name: test
  team: team
  tier: critical
  type: api
  template: critical-api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.95  # Override
""")
        
        context, resources = parse_service_file(service_yaml)
        
        # Should have 3 resources in template order
        assert len(resources) == 3
        assert resources[0].name == "availability"  # Overridden
        assert resources[1].name == "latency-p95"   # From template
        assert resources[2].kind == "PagerDuty"     # From template
        
        # Verify override worked
        assert resources[0].spec["objective"] == 99.95
    
    def test_template_with_additional_resources(self, tmp_path):
        """Adding new resources should append after template resources."""
        service_yaml = tmp_path / "test.yaml"
        service_yaml.write_text("""
service:
  name: test
  team: team
  tier: critical
  type: api
  template: critical-api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: high
""")
        
        context, resources = parse_service_file(service_yaml)
        
        # Should have 4 resources (3 from template + 1 new)
        assert len(resources) == 4
        
        # New resource should be at the end
        assert resources[3].kind == "Dependencies"
        assert resources[3].name == "upstream"
    
    def test_template_variables_in_overrides(self, tmp_path):
        """Template variables should work in user overrides."""
        service_yaml = tmp_path / "test.yaml"
        service_yaml.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api
  template: critical-api

resources:
  - kind: SLO
    name: custom
    spec:
      query: "service=${service},team=${team}"
""")
        
        context, resources = parse_service_file(service_yaml)
        
        # Find custom SLO
        custom = next(r for r in resources if r.name == "custom")
        
        # Variables should be present (not yet substituted)
        assert "${service}" in custom.spec["query"]
        assert "${team}" in custom.spec["query"]
        
        # Substitute
        from nthlayer.specs.template import substitute_variables
        rendered = substitute_variables(custom.spec["query"], context.to_dict())
        assert rendered == "service=payment-api,team=payments"


class TestErrorHandling:
    """Test error handling in workflows."""
    
    def test_invalid_service_name_in_init(self, tmp_path, monkeypatch):
        """Init should reject invalid service names."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            "InvalidName",  # Uppercase not allowed
            "team",
            "critical-api",
            interactive=False
        )
        
        assert result == 1  # Error
    
    def test_unknown_template_in_init(self, tmp_path, monkeypatch):
        """Init should reject unknown templates."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            "test-api",
            "team",
            "nonexistent-template",
            interactive=False
        )
        
        assert result == 1  # Error
    
    def test_validation_catches_unknown_template(self, tmp_path):
        """Validation should catch unknown template references."""
        service_yaml = tmp_path / "test.yaml"
        service_yaml.write_text("""
service:
  name: test
  team: team
  tier: critical
  type: api
  template: nonexistent
""")
        
        from nthlayer.specs.parser import ServiceParseError
        
        with pytest.raises(ServiceParseError) as exc:
            parse_service_file(service_yaml)
        
        assert "Unknown template" in str(exc.value)
        assert "nonexistent" in str(exc.value)
    
    def test_validation_catches_invalid_override(self, tmp_path):
        """Validation should catch invalid resource overrides."""
        service_yaml = tmp_path / "test.yaml"
        service_yaml.write_text("""
service:
  name: test
  team: team
  tier: critical
  type: api
  template: critical-api

resources:
  - kind: SLO
    # Missing name - should error
    spec:
      objective: 99.9
""")
        
        from nthlayer.specs.parser import ServiceParseError
        
        with pytest.raises(ServiceParseError):
            parse_service_file(service_yaml)


class TestRealWorldScenarios:
    """Test realistic scenarios users might encounter."""
    
    def test_gradual_customization(self, tmp_path, monkeypatch):
        """User starts with template and gradually customizes."""
        monkeypatch.chdir(tmp_path)
        
        # Start with template
        init_command("my-api", "team", "critical-api", interactive=False)
        service_file = tmp_path / "my-api.yaml"
        
        # Stage 1: Just template
        context, resources = parse_service_file(service_file)
        assert len(resources) == 3  # Template only
        
        # Stage 2: Override one resource
        content = service_file.read_text()
        content += """
resources:
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300
"""
        service_file.write_text(content)
        
        context, resources = parse_service_file(service_file)
        assert len(resources) == 3  # Still 3 (override, not add)
        latency = next(r for r in resources if r.name == "latency-p95")
        assert latency.spec["threshold_ms"] == 300
        
        # Stage 3: Add new resource
        content = service_file.read_text()
        content += """
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: high
"""
        service_file.write_text(content)
        
        context, resources = parse_service_file(service_file)
        assert len(resources) == 4  # Now 4 (added new)
    
    def test_multiple_services_in_project(self, tmp_path, monkeypatch):
        """Multiple services can coexist in same project."""
        monkeypatch.chdir(tmp_path)
        
        services = [
            ("payment-api", "payments", "critical-api"),
            ("admin-api", "platform", "standard-api"),
            ("email-worker", "notifications", "background-job"),
        ]
        
        for name, team, template in services:
            # Init each service
            result = init_command(name, team, template, interactive=False)
            assert result == 0
            
            # Validate each
            result = validate_command(str(tmp_path / f"{name}.yaml"))
            assert result == 0
            
            # Generate each
            result = generate_slo_command(
                str(tmp_path / f"{name}.yaml"),
                output_dir=str(tmp_path / "generated")
            )
            assert result == 0
        
        # All services should have their own SLO files
        assert (tmp_path / "generated" / "sloth" / "payment-api.yaml").exists()
        assert (tmp_path / "generated" / "sloth" / "admin-api.yaml").exists()
        assert (tmp_path / "generated" / "sloth" / "email-worker.yaml").exists()
    
    def test_config_file_shared_across_services(self, tmp_path, monkeypatch):
        """Config file is created once and shared."""
        monkeypatch.chdir(tmp_path)
        
        # Init first service
        init_command("service1", "team", "critical-api", interactive=False)
        assert (tmp_path / ".nthlayer" / "config.yaml").exists()
        
        # Modify config
        config_file = tmp_path / ".nthlayer" / "config.yaml"
        config_file.write_text("custom: config")
        
        # Init second service
        init_command("service2", "team", "standard-api", interactive=False)
        
        # Config should not be overwritten
        assert config_file.read_text() == "custom: config"
