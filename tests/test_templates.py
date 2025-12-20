"""Tests for service template system."""

import pytest
from nthlayer.specs.parser import parse_service_file
from nthlayer.specs.template import substitute_variables
from nthlayer.specs.template_loader import TemplateLoader
from nthlayer.specs.templates import ServiceTemplate, TemplateRegistry


class TestTemplateLoader:
    """Tests for TemplateLoader class."""

    def test_load_builtin_templates(self):
        """Should load all built-in templates."""
        registry = TemplateLoader.load_builtin()

        assert isinstance(registry, TemplateRegistry)
        assert "critical-api" in registry.templates
        assert "standard-api" in registry.templates
        assert "low-api" in registry.templates
        assert "background-job" in registry.templates
        assert "pipeline" in registry.templates

        # At least 5 templates
        assert len(registry.templates) >= 5

    def test_template_registry_get(self):
        """Should get template by name."""
        registry = TemplateLoader.load_builtin()

        template = registry.get("critical-api")
        assert template is not None
        assert isinstance(template, ServiceTemplate)
        assert template.name == "critical-api"

        # Non-existent template
        assert registry.get("nonexistent") is None

    def test_template_registry_list(self):
        """Should list all templates sorted."""
        registry = TemplateLoader.load_builtin()

        templates = registry.list()
        assert len(templates) >= 5

        # Should be sorted
        names = [t.name for t in templates]
        assert names == sorted(names)

    def test_template_registry_exists(self):
        """Should check template existence."""
        registry = TemplateLoader.load_builtin()

        assert registry.exists("critical-api")
        assert registry.exists("standard-api")
        assert not registry.exists("nonexistent")


class TestBuiltinTemplates:
    """Tests for built-in template content."""

    def test_critical_api_template(self):
        """Critical API template should have correct configuration."""
        registry = TemplateLoader.load_builtin()
        template = registry.get("critical-api")

        assert template.tier == "critical"
        assert template.type == "api"
        assert "99.9" in template.description

        # Should have 3 resources: 2 SLOs + PagerDuty
        assert len(template.resources) == 3

        # Check SLOs
        slos = [r for r in template.resources if r.kind == "SLO"]
        assert len(slos) == 2
        assert any(r.name == "availability" for r in slos)
        assert any(r.name == "latency-p95" for r in slos)

        # Check PagerDuty
        pd = [r for r in template.resources if r.kind == "PagerDuty"]
        assert len(pd) == 1
        assert pd[0].spec["urgency"] == "high"

    def test_standard_api_template(self):
        """Standard API template should have correct configuration."""
        registry = TemplateLoader.load_builtin()
        template = registry.get("standard-api")

        assert template.tier == "standard"
        assert template.type == "api"

        # Should have 3 resources
        assert len(template.resources) == 3

        # PagerDuty should be low urgency
        pd = [r for r in template.resources if r.kind == "PagerDuty"]
        assert len(pd) == 1
        assert pd[0].spec["urgency"] == "low"

    def test_low_api_template(self):
        """Low API template should have correct configuration."""
        registry = TemplateLoader.load_builtin()
        template = registry.get("low-api")

        assert template.tier == "low"
        assert template.type == "api"

        # Should have 2 SLOs (no PagerDuty for low tier)
        assert len(template.resources) == 2
        slos = [r for r in template.resources if r.kind == "SLO"]
        assert len(slos) == 2

    def test_background_job_template(self):
        """Background job template should have success rate SLO."""
        registry = TemplateLoader.load_builtin()
        template = registry.get("background-job")

        assert template.tier == "standard"
        assert template.type == "background-job"

        # Should have success-rate SLO
        slos = [r for r in template.resources if r.kind == "SLO"]
        assert any(r.name == "success-rate" for r in slos)

    def test_pipeline_template(self):
        """Pipeline template should have appropriate SLOs."""
        registry = TemplateLoader.load_builtin()
        template = registry.get("pipeline")

        assert template.tier == "standard"
        assert template.type == "pipeline"

        # Should have success rate and freshness SLOs
        slos = [r for r in template.resources if r.kind == "SLO"]
        assert any(r.name == "success-rate" for r in slos)
        assert any(r.name == "freshness-p95" for r in slos)


class TestServiceWithTemplate:
    """Tests for parsing services that use templates."""

    def test_service_with_template_basic(self, tmp_path):
        """Should apply template resources to service."""
        service_yaml = tmp_path / "test-api.yaml"
        service_yaml.write_text("""
service:
  name: test-api
  team: test-team
  tier: critical
  type: api
  template: critical-api
""")

        context, resources = parse_service_file(service_yaml)

        # Should have service context
        assert context.name == "test-api"
        assert context.team == "test-team"
        assert context.template == "critical-api"

        # Should have template resources
        assert len(resources) == 3  # 2 SLOs + PagerDuty

        # All resources should have context
        for resource in resources:
            assert resource.context is not None
            assert resource.context.name == "test-api"

    def test_service_with_template_override(self, tmp_path):
        """Should allow overriding template resources."""
        service_yaml = tmp_path / "test-api.yaml"
        service_yaml.write_text("""
service:
  name: test-api
  team: test-team
  tier: critical
  type: api
  template: critical-api

resources:
  # Override latency threshold
  - kind: SLO
    name: latency-p95
    spec:
      threshold_ms: 300
""")

        context, resources = parse_service_file(service_yaml)

        # Should still have 3 resources (override, not add)
        assert len(resources) == 3

        # Latency SLO should use overridden value
        latency = next(r for r in resources if r.name == "latency-p95")
        assert latency.spec["threshold_ms"] == 300

        # Availability should come from template (unchanged)
        availability = next(r for r in resources if r.name == "availability")
        assert "objective" in availability.spec

    def test_service_with_template_add_resource(self, tmp_path):
        """Should allow adding new resources to template."""
        service_yaml = tmp_path / "test-api.yaml"
        service_yaml.write_text("""
service:
  name: test-api
  team: test-team
  tier: critical
  type: api
  template: critical-api

resources:
  # Add dependencies (not in template)
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

        # Should have Dependencies
        deps = [r for r in resources if r.kind == "Dependencies"]
        assert len(deps) == 1
        assert deps[0].name == "upstream"

    def test_unknown_template_error(self, tmp_path):
        """Should error on unknown template."""
        service_yaml = tmp_path / "test-api.yaml"
        service_yaml.write_text("""
service:
  name: test-api
  team: test-team
  tier: critical
  type: api
  template: nonexistent-template
""")

        from nthlayer.specs.parser import ServiceParseError

        with pytest.raises(ServiceParseError) as exc:
            parse_service_file(service_yaml)

        assert "Unknown template" in str(exc.value)
        assert "nonexistent-template" in str(exc.value)
        assert "Available templates" in str(exc.value)

    def test_service_without_template(self, tmp_path):
        """Should work without template (manual resources)."""
        service_yaml = tmp_path / "test-api.yaml"
        service_yaml.write_text("""
service:
  name: test-api
  team: test-team
  tier: critical
  type: api

resources:
  - kind: SLO
    name: custom-slo
    spec:
      objective: 99.99
""")

        context, resources = parse_service_file(service_yaml)

        assert context.template is None
        assert len(resources) == 1
        assert resources[0].name == "custom-slo"


class TestTemplateVariableSubstitution:
    """Tests for variable substitution in template resources."""

    def test_variables_in_template(self, tmp_path):
        """Template variables should work in template resources."""
        service_yaml = tmp_path / "my-api.yaml"
        service_yaml.write_text("""
service:
  name: my-api
  team: my-team
  tier: critical
  type: api
  template: critical-api
""")

        context, resources = parse_service_file(service_yaml)

        # Check that template variables are present (not yet substituted)
        slo = next(r for r in resources if r.kind == "SLO")
        query = slo.spec["indicator"]["query"]
        assert "${service}" in query

        # Substitute variables
        rendered_query = substitute_variables(query, context.to_dict())
        assert "my-api" in rendered_query
        assert "${service}" not in rendered_query

    def test_variables_in_override(self, tmp_path):
        """Variables should work in user overrides too."""
        service_yaml = tmp_path / "my-api.yaml"
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
        query = custom.spec["query"]

        # Substitute
        rendered = substitute_variables(query, context.to_dict())
        assert rendered == "service=payment-api,team=payments"
