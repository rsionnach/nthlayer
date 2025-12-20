"""Tests for service specification parsing and validation."""

import pytest
from nthlayer.specs import (
    Resource,
    ServiceContext,
    parse_service_file,
    validate_service_file,
)
from nthlayer.specs.parser import ServiceParseError, render_resource_spec
from nthlayer.specs.template import substitute_variables, validate_template_variables


class TestServiceContext:
    """Test ServiceContext model."""

    def test_create_service_context(self):
        """Test creating service context with required fields."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        assert ctx.name == "payment-api"
        assert ctx.team == "payments"
        assert ctx.tier == "critical"
        assert ctx.type == "api"

    def test_service_context_to_dict(self):
        """Test converting service context to dict for templates."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
            language="java",
        )

        d = ctx.to_dict()

        assert d["service"] == "payment-api"
        assert d["team"] == "payments"
        assert d["tier"] == "critical"
        assert d["type"] == "api"
        assert d["language"] == "java"

    def test_service_context_requires_fields(self):
        """Test that required fields are validated."""
        with pytest.raises(ValueError, match="Service name is required"):
            ServiceContext(name="", team="team", tier="critical", type="api")


class TestResource:
    """Test Resource model."""

    def test_create_resource(self):
        """Test creating resource with context."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        resource = Resource(
            kind="SLO",
            name="availability",
            spec={"objective": 99.9},
            context=ctx,
        )

        assert resource.kind == "SLO"
        assert resource.name == "availability"
        assert resource.spec == {"objective": 99.9}
        assert resource.context == ctx

    def test_resource_full_name(self):
        """Test full resource name generation."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        resource = Resource(
            kind="SLO",
            name="availability",
            spec={},
            context=ctx,
        )

        assert resource.full_name == "payment-api-availability"

    def test_resource_full_name_without_name(self):
        """Test that resource names are now required."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        # Resource names are now required
        with pytest.raises(ValueError, match="Resource name is required"):
            Resource(
                kind="PagerDuty",
                spec={},
                context=ctx,
            )


class TestTemplateSubstitution:
    """Test template variable substitution."""

    def test_substitute_simple_variable(self):
        """Test substituting single variable."""
        result = substitute_variables(
            "${service}",
            {"service": "payment-api"},
        )

        assert result == "payment-api"

    def test_substitute_multiple_variables(self):
        """Test substituting multiple variables."""
        result = substitute_variables(
            "service=${service},team=${team}",
            {"service": "payment-api", "team": "payments"},
        )

        assert result == "service=payment-api,team=payments"

    def test_substitute_in_dict(self):
        """Test substitution in nested dict."""
        result = substitute_variables(
            {
                "name": "${service}-slo",
                "metadata": {
                    "team": "${team}",
                },
            },
            {"service": "payment-api", "team": "payments"},
        )

        assert result == {
            "name": "payment-api-slo",
            "metadata": {
                "team": "payments",
            },
        }

    def test_substitute_in_list(self):
        """Test substitution in list."""
        result = substitute_variables(
            ["${service}", "${team}"],
            {"service": "payment-api", "team": "payments"},
        )

        assert result == ["payment-api", "payments"]

    def test_preserve_primitives(self):
        """Test that primitives pass through unchanged."""
        result = substitute_variables(
            {"number": 42, "bool": True, "null": None},
            {},
        )

        assert result == {"number": 42, "bool": True, "null": None}

    def test_unknown_variable_unchanged(self):
        """Test that unknown variables are left unchanged."""
        result = substitute_variables(
            "${unknown}",
            {"service": "payment-api"},
        )

        assert result == "${unknown}"


class TestValidateTemplateVariables:
    """Test template variable validation."""

    def test_valid_variables(self):
        """Test that valid variables return empty list."""
        invalid = validate_template_variables("${service} ${team}")

        assert invalid == []

    def test_invalid_variables(self):
        """Test that invalid variables are returned."""
        invalid = validate_template_variables("${service} ${invalid}")

        assert "invalid" in invalid


class TestParseServiceFile:
    """Test service file parsing."""

    def test_parse_minimal_service(self, tmp_path):
        """Test parsing minimal service file."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: standard
  type: api
"""
        )

        ctx, resources = parse_service_file(service_file)

        assert ctx.name == "test-service"
        assert ctx.team == "test-team"
        assert ctx.tier == "standard"
        assert ctx.type == "api"
        assert len(resources) == 0

    def test_parse_service_with_resources(self, tmp_path):
        """Test parsing service with resources."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
"""
        )

        ctx, resources = parse_service_file(service_file)

        assert len(resources) == 2
        assert resources[0].kind == "SLO"
        assert resources[0].name == "availability"
        assert resources[0].spec == {"objective": 99.9}
        assert resources[0].context == ctx
        assert resources[1].kind == "PagerDuty"
        assert resources[1].name == "primary"

    def test_parse_missing_service_section(self, tmp_path):
        """Test error when service section missing."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("resources: []")

        with pytest.raises(ServiceParseError, match="Missing required 'service' section"):
            parse_service_file(service_file)

    def test_parse_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        with pytest.raises(ServiceParseError, match="Service file not found"):
            parse_service_file(tmp_path / "nonexistent.yaml")


class TestRenderResourceSpec:
    """Test rendering resource spec with template substitution."""

    def test_render_spec_with_service_placeholder(self):
        """Test rendering spec with {{ .service }} placeholder."""
        ctx = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        resource = Resource(
            kind="SLO",
            name="availability",
            spec={
                "query": "service=${service}",
            },
            context=ctx,
        )

        rendered = render_resource_spec(resource)

        assert rendered == {"query": "service=payment-api"}


class TestValidateServiceFile:
    """Test service file validation."""

    def test_validate_valid_file(self, tmp_path):
        """Test validating valid service file."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
"""
        )

        result = validate_service_file(service_file)

        assert result.valid
        assert len(result.errors) == 0
        assert result.service == "test-service"
        assert result.resource_count == 1

    def test_validate_invalid_service_name(self, tmp_path):
        """Test validation fails for invalid service name."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: Invalid_Name
  team: test-team
  tier: standard
  type: api
"""
        )

        result = validate_service_file(service_file)

        assert not result.valid
        assert any("Invalid service name" in e for e in result.errors)

    def test_validate_invalid_tier(self, tmp_path):
        """Test validation fails for invalid tier."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: invalid-tier
  type: api
"""
        )

        result = validate_service_file(service_file)

        assert not result.valid
        assert any("Invalid tier" in e for e in result.errors)

    def test_validate_duplicate_resource_names(self, tmp_path):
        """Test validation fails for duplicate resource names."""
        service_file = tmp_path / "test-service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
  - kind: SLO
    name: availability
    spec:
      objective: 99.5
"""
        )

        result = validate_service_file(service_file)

        assert not result.valid
        assert any("Duplicate resource names" in e for e in result.errors)
