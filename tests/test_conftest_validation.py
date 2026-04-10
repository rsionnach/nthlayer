"""Tests for conftest/OPA policy validation."""

import yaml

from nthlayer.validation.conftest import ConftestValidator, validate_spec


class TestConftestValidator:
    """Test ConftestValidator with native validation."""

    def test_valid_service_spec(self, tmp_path):
        """Valid spec should pass validation."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [
                {
                    "kind": "SLO",
                    "name": "availability",
                    "spec": {
                        "objective": 99.9,
                        "window": "30d",
                        "indicator": {"type": "availability"},
                    },
                }
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed
        assert result.error_count == 0

    def test_missing_service_section(self, tmp_path):
        """Missing service section should fail."""
        spec = {"resources": [{"kind": "SLO", "name": "test", "spec": {}}]}

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert not result.passed
        assert any("service section is required" in i.message for i in result.issues)

    def test_missing_required_fields(self, tmp_path):
        """Missing required service fields should fail."""
        spec = {
            "service": {
                "name": "test-api",
                # Missing: team, tier, type
            },
            "resources": [{"kind": "SLO", "name": "test", "spec": {}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert not result.passed
        assert result.error_count >= 3  # team, tier, type

    def test_invalid_tier_warns(self, tmp_path):
        """Invalid tier should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "mega-critical",  # Invalid
                "type": "api",
            },
            "resources": [{"kind": "SLO", "name": "test", "spec": {"objective": 99}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        # Should pass (warning, not error)
        assert result.passed
        assert any("not a standard tier" in i.message for i in result.issues)

    def test_invalid_type_warns(self, tmp_path):
        """Invalid type should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "microservice",  # Invalid
            },
            "resources": [{"kind": "SLO", "name": "test", "spec": {"objective": 99}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed
        assert any("not a standard type" in i.message for i in result.issues)

    def test_empty_resources_fails(self, tmp_path):
        """Empty resources should fail."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        # Empty resources is treated as missing
        assert not result.passed

    def test_resource_missing_kind_fails(self, tmp_path):
        """Resource without kind should fail."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [
                {"name": "test", "spec": {}}  # Missing kind
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert not result.passed
        assert any("kind" in i.message for i in result.issues)

    def test_critical_tier_without_slo_warns(self, tmp_path):
        """Critical tier without SLO should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "critical",
                "type": "api",
            },
            "resources": [
                {"kind": "Dependencies", "name": "deps", "spec": {}}  # No SLO
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed  # Warning, not error
        assert any("should have at least one SLO" in i.message for i in result.issues)

    def test_critical_tier_without_pagerduty_warns(self, tmp_path):
        """Critical tier without PagerDuty should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "critical",
                "type": "api",
            },
            "resources": [
                {
                    "kind": "SLO",
                    "name": "availability",
                    "spec": {"objective": 99.9, "window": "30d"},
                }
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed
        assert any("should have PagerDuty" in i.message for i in result.issues)


class TestSLOValidation:
    """Test SLO-specific validation."""

    def test_slo_missing_objective_fails(self, tmp_path):
        """SLO without objective should fail."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [
                {
                    "kind": "SLO",
                    "name": "availability",
                    "spec": {"window": "30d"},  # Missing objective
                }
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert not result.passed
        assert any("missing 'objective'" in i.message for i in result.issues)

    def test_slo_objective_out_of_range_fails(self, tmp_path):
        """SLO with objective > 100 should fail."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [{"kind": "SLO", "name": "availability", "spec": {"objective": 150}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert not result.passed
        assert any("between 0 and 100" in i.message for i in result.issues)

    def test_slo_aggressive_objective_warns(self, tmp_path):
        """SLO with > 99.99% should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [{"kind": "SLO", "name": "availability", "spec": {"objective": 99.999}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed  # Warning, not error
        assert any("aggressive" in i.message for i in result.issues)

    def test_slo_missing_window_warns(self, tmp_path):
        """SLO without window should warn."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [{"kind": "SLO", "name": "availability", "spec": {"objective": 99.9}}],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        validator = ConftestValidator()
        result = validator.validate_file(spec_file)

        assert result.passed
        assert any("should specify a window" in i.message for i in result.issues)


class TestValidateSpecFunction:
    """Test the convenience function."""

    def test_validate_spec_passes(self, tmp_path):
        """validate_spec should work for valid specs."""
        spec = {
            "service": {
                "name": "test-api",
                "team": "platform",
                "tier": "standard",
                "type": "api",
            },
            "resources": [
                {
                    "kind": "SLO",
                    "name": "availability",
                    "spec": {"objective": 99.9, "window": "30d"},
                }
            ],
        }

        spec_file = tmp_path / "test.yaml"
        with open(spec_file, "w") as f:
            yaml.dump(spec, f)

        result = validate_spec(spec_file)
        assert result.passed

    def test_validate_spec_file_not_found(self):
        """validate_spec should handle missing files."""
        result = validate_spec("/nonexistent/file.yaml")
        assert not result.passed
        assert "not found" in result.issues[0].message.lower()

    def test_validate_spec_invalid_yaml(self, tmp_path):
        """validate_spec should handle invalid YAML."""
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text("invalid: yaml: content: [")

        result = validate_spec(spec_file)
        assert not result.passed
        assert any("YAML" in i.message for i in result.issues)
