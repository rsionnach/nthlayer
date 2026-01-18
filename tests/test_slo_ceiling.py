"""Tests for SLO ceiling validation based on dependency SLAs."""

from nthlayer.slos.ceiling import (
    CeilingValidationResult,
    DependencySLA,
    calculate_slo_ceiling,
    extract_dependencies_from_spec,
    extract_dependencies_with_slas,
    validate_slo_ceiling,
)


class TestDependencySLA:
    """Tests for DependencySLA dataclass."""

    def test_create_with_sla(self):
        """Create dependency with SLA."""
        dep = DependencySLA(name="postgres-main", sla=99.95)
        assert dep.name == "postgres-main"
        assert dep.sla == 99.95

    def test_create_without_sla(self):
        """Create dependency without SLA."""
        dep = DependencySLA(name="redis-cache", sla=None)
        assert dep.name == "redis-cache"
        assert dep.sla is None


class TestExtractDependenciesWithSLAs:
    """Tests for extract_dependencies_with_slas function."""

    def test_empty_spec(self):
        """Empty spec returns empty lists and not opted in."""
        deps, missing, opted_in = extract_dependencies_with_slas({})
        assert deps == []
        assert missing == []
        assert opted_in is False

    def test_no_sla_fields_not_opted_in(self):
        """Dependencies without SLA fields means not opted in."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main"},
                            {"name": "redis-cache"},
                        ]
                    },
                }
            ]
        }
        deps, missing, opted_in = extract_dependencies_with_slas(spec)
        assert deps == []
        assert missing == ["postgres-main", "redis-cache"]
        assert opted_in is False

    def test_one_sla_field_opts_in(self):
        """At least one SLA field opts in to validation."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache"},  # No SLA
                        ]
                    },
                }
            ]
        }
        deps, missing, opted_in = extract_dependencies_with_slas(spec)
        assert len(deps) == 1
        assert deps[0].name == "postgres-main"
        assert deps[0].sla == 99.95
        assert missing == ["redis-cache"]
        assert opted_in is True

    def test_all_sla_fields(self):
        """All dependencies have SLA fields."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache", "sla": 99.99},
                        ]
                    },
                }
            ]
        }
        deps, missing, opted_in = extract_dependencies_with_slas(spec)
        assert len(deps) == 2
        assert missing == []
        assert opted_in is True

    def test_external_apis(self):
        """Extracts external APIs with SLA."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "external_apis": [
                            {"name": "stripe", "sla": 99.9},
                        ]
                    },
                }
            ]
        }
        deps, missing, opted_in = extract_dependencies_with_slas(spec)
        assert len(deps) == 1
        assert deps[0].name == "stripe"
        assert deps[0].sla == 99.9
        assert opted_in is True

    def test_deduplicates_dependencies(self):
        """Duplicate dependencies are removed."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "postgres-main", "sla": 99.95},  # Duplicate
                        ]
                    },
                }
            ]
        }
        deps, _, _ = extract_dependencies_with_slas(spec)
        assert len(deps) == 1


class TestCalculateSLOCeiling:
    """Tests for calculate_slo_ceiling function."""

    def test_no_dependencies(self):
        """No dependencies = 100% ceiling."""
        ceiling = calculate_slo_ceiling([])
        assert ceiling == 100.0

    def test_single_dependency(self):
        """Single dependency = that dependency's SLA."""
        deps = [DependencySLA("db", 99.95)]
        ceiling = calculate_slo_ceiling(deps)
        assert ceiling == 99.95

    def test_multiple_dependencies(self):
        """Multiple dependencies multiply."""
        # 99.95% × 99.99% = 99.94%
        deps = [
            DependencySLA("db", 99.95),
            DependencySLA("cache", 99.99),
        ]
        ceiling = calculate_slo_ceiling(deps)
        assert 99.93 <= ceiling <= 99.95  # Allow rounding

    def test_skips_none_slas(self):
        """Dependencies with None SLA are skipped."""
        deps = [
            DependencySLA("db", 99.95),
            DependencySLA("unknown", None),
        ]
        ceiling = calculate_slo_ceiling(deps)
        assert ceiling == 99.95  # Only db counted


class TestValidateSLOCeiling:
    """Tests for validate_slo_ceiling function."""

    def test_not_opted_in_skips_validation(self):
        """No SLA fields = validation skipped."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main"},
                            {"name": "redis-cache"},
                        ]
                    },
                }
            ]
        }
        result = validate_slo_ceiling(99.99, spec)
        assert result.is_valid is True
        assert result.opted_in is False
        assert "skipped" in result.message.lower()

    def test_valid_slo_with_explicit_slas(self):
        """SLO below ceiling passes validation."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache", "sla": 99.99},
                        ]
                    },
                }
            ]
        }
        result = validate_slo_ceiling(99.9, spec)
        assert result.is_valid is True
        assert result.opted_in is True

    def test_invalid_slo_exceeds_ceiling(self):
        """SLO above ceiling fails validation."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache", "sla": 99.99},
                        ]
                    },
                }
            ]
        }
        # Ceiling is ~99.94%, so 99.99% exceeds it
        result = validate_slo_ceiling(99.99, spec)
        assert result.is_valid is False
        assert result.opted_in is True
        assert "exceeds" in result.message.lower()

    def test_partial_slas_informs_missing(self):
        """Partial SLAs reports missing ones."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache"},  # No SLA
                        ]
                    },
                }
            ]
        }
        result = validate_slo_ceiling(99.9, spec)
        assert result.is_valid is True  # Doesn't fail
        assert result.opted_in is True
        assert result.dependencies_missing_sla == ["redis-cache"]
        assert "partial" in result.message.lower() or "missing" in result.message.lower()

    def test_no_dependencies_always_valid(self):
        """No dependencies = any SLO is valid (not opted in)."""
        spec = {"resources": []}
        result = validate_slo_ceiling(99.999, spec)
        assert result.is_valid is True
        assert result.opted_in is False
        assert result.ceiling_slo == 100.0

    def test_result_contains_ceiling(self):
        """Result contains calculated ceiling."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {"databases": [{"name": "db", "sla": 99.95}]},
                }
            ]
        }
        result = validate_slo_ceiling(99.9, spec)
        assert result.ceiling_slo == 99.95

    def test_tight_margin_message(self):
        """Tight margin (< 0.1%) is noted in message."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {"databases": [{"name": "db", "sla": 99.95}]},
                }
            ]
        }
        # Target very close to ceiling (99.95 - 99.9 = 0.05 < 0.1)
        result = validate_slo_ceiling(99.9, spec)
        assert result.is_valid is True
        assert "close" in result.message.lower() or "margin" in result.message.lower()


class TestCeilingValidationResult:
    """Tests for CeilingValidationResult dataclass."""

    def test_to_dict(self):
        """Result can be serialized to dict."""
        deps = [DependencySLA("db", 99.95)]
        result = CeilingValidationResult(
            is_valid=True,
            target_slo=99.9,
            ceiling_slo=99.95,
            dependencies_with_sla=deps,
            opted_in=True,
            message="OK",
        )
        d = result.to_dict()
        assert d["is_valid"] is True
        assert d["target_slo"] == 99.9
        assert d["ceiling_slo"] == 99.95
        assert d["opted_in"] is True
        assert len(d["dependencies_with_sla"]) == 1

    def test_dependency_slas_property(self):
        """dependency_slas property returns dict of SLAs."""
        deps = [
            DependencySLA("db", 99.95),
            DependencySLA("cache", 99.99),
        ]
        result = CeilingValidationResult(
            is_valid=True,
            target_slo=99.9,
            ceiling_slo=99.94,
            dependencies_with_sla=deps,
            opted_in=True,
            message="OK",
        )
        assert result.dependency_slas == {"db": 99.95, "cache": 99.99}


class TestValidatorIntegration:
    """Integration tests for validator with ceiling validation."""

    def test_native_validator_skips_when_not_opted_in(self, tmp_path):
        """Native validator skips ceiling validation when no SLA fields."""
        from nthlayer.validation.conftest import ConftestValidator

        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
        - name: redis-cache
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
      window: 30d
""")

        validator = ConftestValidator()
        result = validator.validate_file(service_file)

        # Should NOT have any ceiling issues (not opted in)
        ceiling_issues = [i for i in result.issues if "ceiling" in i.rule_name]
        assert len(ceiling_issues) == 0

    def test_native_validator_warns_on_ceiling_exceeded(self, tmp_path):
        """Native validator warns when SLO exceeds ceiling."""
        from nthlayer.validation.conftest import ConftestValidator

        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          sla: 99.95
        - name: redis-cache
          sla: 99.99
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
      window: 30d
""")

        validator = ConftestValidator()
        result = validator.validate_file(service_file)

        # Should have a ceiling exceeded warning
        ceiling_issues = [i for i in result.issues if "ceiling.exceeded" in i.rule_name]
        assert len(ceiling_issues) > 0
        assert any("exceeds" in i.message.lower() for i in ceiling_issues)

    def test_native_validator_passes_achievable_slo(self, tmp_path):
        """Native validator passes when SLO is achievable."""
        from nthlayer.validation.conftest import ConftestValidator

        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          sla: 99.95
  - kind: SLO
    name: availability
    spec:
      objective: 99.5
      window: 30d
""")

        validator = ConftestValidator()
        result = validator.validate_file(service_file)

        # Should NOT have ceiling exceeded warning
        ceiling_exceeded = [i for i in result.issues if "ceiling.exceeded" in i.rule_name]
        assert len(ceiling_exceeded) == 0


class TestRealWorldScenarios:
    """Tests for realistic scenarios."""

    def test_payment_api_with_stripe_dependency(self):
        """Payment API depending on Stripe with explicit SLA."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "external_apis": [
                            {"name": "stripe", "sla": 99.9},
                        ],
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                        ],
                    },
                }
            ]
        }
        # stripe (99.9%) × postgres (99.95%) ≈ 99.85%
        result = validate_slo_ceiling(99.95, spec)
        assert result.is_valid is False
        assert result.ceiling_slo < 99.9

    def test_startup_mode_no_slas(self):
        """Startup with no SLAs defined - validation skipped."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main"},
                            {"name": "redis-cache"},
                        ],
                        "services": [
                            {"name": "auth-service"},
                        ],
                    },
                }
            ]
        }
        # Even with aggressive SLO, validation skipped
        result = validate_slo_ceiling(99.999, spec)
        assert result.is_valid is True
        assert result.opted_in is False


class TestExtractDependenciesFromSpec:
    """Tests for backwards-compatible extract_dependencies_from_spec."""

    def test_returns_all_dependency_names(self):
        """Returns list of all dependency names."""
        spec = {
            "resources": [
                {
                    "kind": "Dependencies",
                    "name": "upstream",
                    "spec": {
                        "databases": [
                            {"name": "postgres-main", "sla": 99.95},
                            {"name": "redis-cache"},
                        ]
                    },
                }
            ]
        }
        names = extract_dependencies_from_spec(spec)
        assert "postgres-main" in names
        assert "redis-cache" in names
