"""Tests for contract & dependency validation (OpenSRM Phase 4).

Tests for ContractRegistry, dependency expectation validation,
transitive feasibility checks, and template resolution.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml
from nthlayer.specs.contracts import (
    ContractRegistry,
    validate_dependency_expectations,
    validate_transitive_feasibility,
)
from nthlayer.specs.manifest import (
    Contract,
    Dependency,
    DependencySLO,
    ReliabilityManifest,
    SLODefinition,
)
from nthlayer.specs.opensrm_parser import (
    _deep_merge_spec,
    resolve_opensrm_template,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_manifest(
    name: str = "test-service",
    team: str = "platform",
    tier: str = "standard",
    service_type: str = "api",
    slos: list[SLODefinition] | None = None,
    dependencies: list[Dependency] | None = None,
    contract: Contract | None = None,
) -> ReliabilityManifest:
    return ReliabilityManifest(
        name=name,
        team=team,
        tier=tier,
        type=service_type,
        slos=slos or [],
        dependencies=dependencies or [],
        contract=contract,
    )


# =============================================================================
# TestContractRegistry
# =============================================================================


class TestContractRegistry:
    def test_register_and_get(self) -> None:
        registry = ContractRegistry()
        manifest = _make_manifest(
            name="payment-api",
            contract=Contract(availability=0.999),
        )
        registry.register(manifest)

        contract = registry.get_contract("payment-api")
        assert contract is not None
        assert contract.availability == 0.999

    def test_missing_returns_none(self) -> None:
        registry = ContractRegistry()
        assert registry.get_contract("nonexistent") is None

    def test_has_contract(self) -> None:
        registry = ContractRegistry()
        manifest = _make_manifest(
            name="svc-a",
            contract=Contract(availability=0.99),
        )
        registry.register(manifest)

        assert registry.has_contract("svc-a") is True
        assert registry.has_contract("svc-b") is False

    def test_from_manifests(self) -> None:
        manifests = [
            _make_manifest(name="svc-a", contract=Contract(availability=0.999)),
            _make_manifest(name="svc-b", contract=Contract(availability=0.99)),
            _make_manifest(name="svc-c"),  # no contract
        ]
        registry = ContractRegistry.from_manifests(manifests)

        assert registry.has_contract("svc-a")
        assert registry.has_contract("svc-b")
        assert not registry.has_contract("svc-c")

    def test_services_list(self) -> None:
        manifests = [
            _make_manifest(name="svc-b", contract=Contract(availability=0.99)),
            _make_manifest(name="svc-a", contract=Contract(availability=0.999)),
        ]
        registry = ContractRegistry.from_manifests(manifests)

        assert registry.services == ["svc-a", "svc-b"]

    def test_manifest_without_contract_skipped(self) -> None:
        registry = ContractRegistry()
        manifest = _make_manifest(name="no-contract")
        registry.register(manifest)

        assert not registry.has_contract("no-contract")
        assert registry.services == []

    def test_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a valid OpenSRM manifest with contract
            manifest_path = Path(tmpdir) / "svc-a.reliability.yaml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "svc-a",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {
                            "type": "api",
                            "contract": {"availability": 0.999},
                        },
                    }
                )
            )

            # Write a manifest without contract
            no_contract = Path(tmpdir) / "svc-b.reliability.yaml"
            no_contract.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "svc-b",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {"type": "api"},
                    }
                )
            )

            # Write a non-manifest file
            (Path(tmpdir) / "readme.yaml").write_text("just: some yaml")

            registry = ContractRegistry.from_directory(tmpdir)

            assert registry.has_contract("svc-a")
            assert not registry.has_contract("svc-b")
            assert registry.services == ["svc-a"]

    def test_from_directory_yml_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "svc-y.reliability.yml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "svc-y",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {
                            "type": "api",
                            "contract": {"availability": 0.99},
                        },
                    }
                )
            )

            registry = ContractRegistry.from_directory(tmpdir)
            assert registry.has_contract("svc-y")

    def test_from_directory_skips_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a file that looks like a manifest but is invalid
            bad_path = Path(tmpdir) / "bad.reliability.yaml"
            bad_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {"name": "bad"},
                        # Missing required fields → ManifestLoadError
                    }
                )
            )

            registry = ContractRegistry.from_directory(tmpdir)
            assert registry.services == []

    def test_from_directory_nonexistent(self) -> None:
        registry = ContractRegistry.from_directory("/nonexistent/path")
        assert registry.services == []


# =============================================================================
# TestDependencyExpectationValidation
# =============================================================================


class TestDependencyExpectationValidation:
    def test_within_contract_no_warning(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(
                    name="db",
                    type="database",
                    critical=True,
                    slo=DependencySLO(availability=99.9),
                ),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [_make_manifest(name="db", contract=Contract(availability=0.9999))]
        )

        warnings = validate_dependency_expectations(manifest, registry)
        assert len(warnings) == 0

    def test_exceeds_contract_warns(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(
                    name="db",
                    type="database",
                    critical=True,
                    slo=DependencySLO(availability=99.999),
                ),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [_make_manifest(name="db", contract=Contract(availability=0.999))]
        )

        warnings = validate_dependency_expectations(manifest, registry)
        assert len(warnings) >= 1
        assert "exceeds provider contract" in warnings[0]

    def test_missing_critical_dep_contract_warns(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="unknown-svc", type="api", critical=True),
            ],
        )
        registry = ContractRegistry()

        warnings = validate_dependency_expectations(manifest, registry)
        assert any("no contract in registry" in w for w in warnings)

    def test_non_critical_no_contract_no_warning(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="cache", type="cache", critical=False),
            ],
        )
        registry = ContractRegistry()

        warnings = validate_dependency_expectations(manifest, registry)
        assert len(warnings) == 0

    def test_no_slo_expectations_no_warning(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="db", type="database", critical=True),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [_make_manifest(name="db", contract=Contract(availability=0.999))]
        )

        warnings = validate_dependency_expectations(manifest, registry)
        # Only the "no contract" warning should NOT appear since it's in the registry.
        # The "exceeds" warning should not appear since there's no SLO expectation.
        assert not any("exceeds" in w for w in warnings)

    def test_multiple_deps_mixed(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(
                    name="db",
                    type="database",
                    critical=True,
                    slo=DependencySLO(availability=99.999),
                ),
                Dependency(
                    name="cache",
                    type="cache",
                    critical=False,
                ),
                Dependency(
                    name="api-svc",
                    type="api",
                    critical=True,
                    slo=DependencySLO(availability=99.9),
                ),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [
                _make_manifest(name="db", contract=Contract(availability=0.999)),
                _make_manifest(name="api-svc", contract=Contract(availability=0.999)),
            ]
        )

        warnings = validate_dependency_expectations(manifest, registry)
        # db: 99.999 > 99.9 → warn
        # cache: non-critical, no warning
        # api-svc: 99.9 <= 99.9 → no warn, but it IS in registry
        assert any("db" in w and "exceeds" in w for w in warnings)
        assert not any("api-svc" in w and "exceeds" in w for w in warnings)


# =============================================================================
# TestTransitiveFeasibility
# =============================================================================


class TestTransitiveFeasibility:
    def test_feasible_no_warning(self) -> None:
        manifest = _make_manifest(
            contract=Contract(availability=0.99),
            dependencies=[
                Dependency(name="db", type="database", critical=True),
                Dependency(name="cache", type="cache", critical=True),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [
                _make_manifest(name="db", contract=Contract(availability=0.999)),
                _make_manifest(name="cache", contract=Contract(availability=0.999)),
            ]
        )

        warnings = validate_transitive_feasibility(manifest, registry)
        # 0.999 * 0.999 = 0.998001 > 0.99 → feasible
        assert not any("infeasible" in w for w in warnings)

    def test_infeasible_warns(self) -> None:
        manifest = _make_manifest(
            contract=Contract(availability=0.9999),
            dependencies=[
                Dependency(name="db", type="database", critical=True),
                Dependency(name="queue", type="queue", critical=True),
            ],
        )
        registry = ContractRegistry.from_manifests(
            [
                _make_manifest(name="db", contract=Contract(availability=0.999)),
                _make_manifest(name="queue", contract=Contract(availability=0.999)),
            ]
        )

        warnings = validate_transitive_feasibility(manifest, registry)
        # 0.999 * 0.999 = 0.998001 < 0.9999 → infeasible
        assert any("infeasible" in w for w in warnings)

    def test_no_contract_skips(self) -> None:
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="db", type="database", critical=True),
            ],
        )
        registry = ContractRegistry()

        warnings = validate_transitive_feasibility(manifest, registry)
        assert len(warnings) == 0

    def test_no_critical_deps_skips(self) -> None:
        manifest = _make_manifest(
            contract=Contract(availability=0.999),
            dependencies=[
                Dependency(name="cache", type="cache", critical=False),
            ],
        )
        registry = ContractRegistry()

        warnings = validate_transitive_feasibility(manifest, registry)
        assert len(warnings) == 0

    def test_unknown_deps_warn(self) -> None:
        manifest = _make_manifest(
            contract=Contract(availability=0.999),
            dependencies=[
                Dependency(name="mystery-svc", type="api", critical=True),
            ],
        )
        registry = ContractRegistry()

        warnings = validate_transitive_feasibility(manifest, registry)
        assert any("unknown availability" in w for w in warnings)

    def test_fallback_to_expected_slo(self) -> None:
        manifest = _make_manifest(
            contract=Contract(availability=0.99),
            dependencies=[
                Dependency(
                    name="db",
                    type="database",
                    critical=True,
                    slo=DependencySLO(availability=99.99),
                ),
            ],
        )
        # db not in registry, but has SLO expectation
        registry = ContractRegistry()

        warnings = validate_transitive_feasibility(manifest, registry)
        # 99.99% → 0.9999 > 0.99 → feasible
        assert not any("infeasible" in w for w in warnings)


# =============================================================================
# TestTemplateResolution
# =============================================================================


class TestTemplateResolution:
    def test_merges_slos(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)
            template_file = template_dir / "critical-api.yaml"
            template_file.write_text(
                yaml.dump(
                    {
                        "spec": {
                            "slos": {
                                "availability": {"target": 99.9, "window": "30d"},
                                "latency": {"target": 200, "unit": "ms"},
                            },
                        },
                    }
                )
            )

            manifest_data = {
                "apiVersion": "srm/v1",
                "kind": "ServiceReliabilityManifest",
                "metadata": {
                    "name": "my-api",
                    "team": "platform",
                    "tier": "standard",
                    "template": "critical-api",
                },
                "spec": {
                    "type": "api",
                },
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, template_dir)

            assert len(warnings) == 0
            assert "availability" in resolved["spec"]["slos"]
            assert "latency" in resolved["spec"]["slos"]
            assert resolved["spec"]["slos"]["availability"]["target"] == 99.9

    def test_service_overrides_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)
            template_file = template_dir / "base.yaml"
            template_file.write_text(
                yaml.dump(
                    {
                        "spec": {
                            "slos": {
                                "availability": {"target": 99.9, "window": "30d"},
                            },
                        },
                    }
                )
            )

            manifest_data = {
                "apiVersion": "srm/v1",
                "kind": "ServiceReliabilityManifest",
                "metadata": {
                    "name": "my-api",
                    "team": "platform",
                    "tier": "standard",
                    "template": "base",
                },
                "spec": {
                    "type": "api",
                    "slos": {
                        "availability": {"target": 99.95, "window": "7d"},
                    },
                },
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, template_dir)

            assert len(warnings) == 0
            # Service override wins
            assert resolved["spec"]["slos"]["availability"]["target"] == 99.95
            assert resolved["spec"]["slos"]["availability"]["window"] == "7d"

    def test_template_not_found_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_data = {
                "metadata": {"template": "nonexistent"},
                "spec": {"type": "api"},
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, tmpdir)

            assert len(warnings) == 1
            assert "not found" in warnings[0]
            # Data should be unchanged
            assert resolved["spec"]["type"] == "api"

    def test_template_chaining_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)
            template_file = template_dir / "chained.yaml"
            template_file.write_text(
                yaml.dump(
                    {
                        "metadata": {"template": "another-template"},
                        "spec": {
                            "slos": {"availability": {"target": 99.9}},
                        },
                    }
                )
            )

            manifest_data = {
                "metadata": {"template": "chained"},
                "spec": {"type": "api"},
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, template_dir)

            assert len(warnings) == 1
            assert "chaining not allowed" in warnings[0]
            # Data should be unchanged (no merge)
            assert "slos" not in resolved.get("spec", {})

    def test_no_template_passthrough(self) -> None:
        manifest_data = {
            "metadata": {"name": "svc"},
            "spec": {"type": "api"},
        }

        resolved, warnings = resolve_opensrm_template(manifest_data, None)

        assert len(warnings) == 0
        assert resolved is manifest_data

    def test_no_template_dir_warns(self) -> None:
        manifest_data = {
            "metadata": {"template": "some-template"},
            "spec": {"type": "api"},
        }

        resolved, warnings = resolve_opensrm_template(manifest_data, None)

        assert len(warnings) == 1
        assert "no template directory" in warnings[0]

    def test_template_invalid_yaml_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)
            template_file = template_dir / "broken.yaml"
            template_file.write_text(": : : invalid yaml {{{}}")

            manifest_data = {
                "metadata": {"template": "broken"},
                "spec": {"type": "api"},
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, template_dir)

            assert len(warnings) == 1
            assert "Failed to load template" in warnings[0]

    def test_template_not_a_dict_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)
            template_file = template_dir / "scalar.yaml"
            template_file.write_text("just a string")

            manifest_data = {
                "metadata": {"template": "scalar"},
                "spec": {"type": "api"},
            }

            resolved, warnings = resolve_opensrm_template(manifest_data, template_dir)

            assert len(warnings) == 1
            assert "not a valid YAML object" in warnings[0]


class TestDeepMergeSpec:
    def test_override_wins(self) -> None:
        base = {"type": "api", "window": "30d"}
        override = {"window": "7d"}

        result = _deep_merge_spec(base, override)
        assert result["type"] == "api"
        assert result["window"] == "7d"

    def test_nested_merge(self) -> None:
        base = {"ownership": {"team": "platform", "slack": "#old"}}
        override = {"ownership": {"slack": "#new"}}

        result = _deep_merge_spec(base, override)
        assert result["ownership"]["team"] == "platform"
        assert result["ownership"]["slack"] == "#new"

    def test_slo_leaf_replacement(self) -> None:
        base = {
            "slos": {
                "availability": {"target": 99.9, "window": "30d"},
                "latency": {"target": 200, "unit": "ms"},
            }
        }
        override = {
            "slos": {
                "availability": {"target": 99.95},
            }
        }

        result = _deep_merge_spec(base, override)
        # availability replaced entirely (leaf-level)
        assert result["slos"]["availability"] == {"target": 99.95}
        # latency preserved from base
        assert result["slos"]["latency"]["target"] == 200


# =============================================================================
# TestValidateServiceFileContracts
# =============================================================================


class TestValidateServiceFileContracts:
    def test_contract_warnings_in_result(self) -> None:
        """validate_service_file includes contract warnings for OpenSRM files."""
        from nthlayer.specs.validator import validate_service_file

        with tempfile.TemporaryDirectory() as tmpdir:
            # SLO target (99.9%) is looser than contract (99.95%)
            manifest_path = Path(tmpdir) / "svc.reliability.yaml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "svc",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {
                            "type": "api",
                            "slos": {
                                "availability": {"target": 99.9, "window": "30d"},
                            },
                            "contract": {"availability": 0.9995},
                        },
                    }
                )
            )

            result = validate_service_file(str(manifest_path))

            assert result.valid  # contract issues are warnings, not errors
            assert any("looser than contract" in w for w in result.warnings)

    def test_dep_warnings_with_registry(self) -> None:
        """validate_service_file includes dependency warnings when registry is provided."""
        from nthlayer.specs.validator import validate_service_file

        with tempfile.TemporaryDirectory() as tmpdir:
            # Main service expects db at 99.999%
            main_path = Path(tmpdir) / "main.reliability.yaml"
            main_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "main",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {
                            "type": "api",
                            "dependencies": [
                                {
                                    "name": "db-svc",
                                    "type": "database",
                                    "critical": True,
                                    "slo": {"availability": 99.999},
                                },
                            ],
                        },
                    }
                )
            )

            # db-svc contracts at 99.9%
            db_path = Path(tmpdir) / "db-svc.reliability.yaml"
            db_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "db-svc",
                            "team": "data",
                            "tier": "critical",
                        },
                        "spec": {
                            "type": "database",
                            "contract": {"availability": 0.999},
                        },
                    }
                )
            )

            registry = ContractRegistry.from_directory(tmpdir)

            result = validate_service_file(str(main_path), contract_registry=registry)

            assert result.valid
            assert any("exceeds provider contract" in w for w in result.warnings)

    def test_no_registry_skips_dep_validation(self) -> None:
        """Without a registry, no dependency warnings are produced."""
        from nthlayer.specs.validator import validate_service_file

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "svc.reliability.yaml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "apiVersion": "srm/v1",
                        "kind": "ServiceReliabilityManifest",
                        "metadata": {
                            "name": "svc",
                            "team": "platform",
                            "tier": "standard",
                        },
                        "spec": {
                            "type": "api",
                            "dependencies": [
                                {
                                    "name": "unknown",
                                    "type": "api",
                                    "critical": True,
                                },
                            ],
                        },
                    }
                )
            )

            result = validate_service_file(str(manifest_path))

            # No registry → no dependency warnings
            assert not any("no contract in registry" in w for w in result.warnings)
