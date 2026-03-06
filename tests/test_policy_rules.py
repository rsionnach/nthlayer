"""Tests for policy rule evaluators."""

from __future__ import annotations

from nthlayer.policies.models import PolicyRule, PolicySeverity, RuleType
from nthlayer.policies.rules import (
    RULE_EVALUATORS,
    _resolve_field,
    evaluate_dependency_rule,
    evaluate_required_fields,
    evaluate_tier_constraint,
)
from nthlayer.specs.manifest import (
    Dependency,
    DependencySLO,
    DeploymentConfig,
    Ownership,
    ReliabilityManifest,
    SLODefinition,
)


def _make_manifest(**overrides) -> ReliabilityManifest:
    """Create a minimal manifest with optional overrides."""
    defaults = {
        "name": "test-service",
        "team": "test-team",
        "tier": "standard",
        "type": "api",
    }
    defaults.update(overrides)
    return ReliabilityManifest(**defaults)


class TestRequiredFields:
    def test_missing_field(self):
        manifest = _make_manifest()
        rule = PolicyRule(
            name="require-description",
            type=RuleType.required_fields,
            params={"fields": ["description"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 1
        assert violations[0].field_path == "description"
        assert "missing or empty" in violations[0].message

    def test_present_field(self):
        manifest = _make_manifest(description="A service")
        rule = PolicyRule(
            name="require-description",
            type=RuleType.required_fields,
            params={"fields": ["description"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 0

    def test_nested_field_present(self):
        manifest = _make_manifest(
            ownership=Ownership(team="test-team", runbook="https://wiki/runbook"),
        )
        rule = PolicyRule(
            name="require-runbook",
            type=RuleType.required_fields,
            params={"fields": ["ownership.runbook"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 0

    def test_nested_field_missing(self):
        manifest = _make_manifest(
            ownership=Ownership(team="test-team"),
        )
        rule = PolicyRule(
            name="require-runbook",
            type=RuleType.required_fields,
            params={"fields": ["ownership.runbook"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 1
        assert violations[0].field_path == "ownership.runbook"

    def test_empty_string_is_violation(self):
        manifest = _make_manifest(description="")
        rule = PolicyRule(
            name="require-description",
            type=RuleType.required_fields,
            params={"fields": ["description"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 1

    def test_empty_list_is_violation(self):
        manifest = _make_manifest(slos=[])
        rule = PolicyRule(
            name="require-slos",
            type=RuleType.required_fields,
            params={"fields": ["slos"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 1

    def test_multiple_fields(self):
        manifest = _make_manifest()
        rule = PolicyRule(
            name="require-all",
            type=RuleType.required_fields,
            params={"fields": ["description", "ownership"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 2

    def test_no_fields_param(self):
        manifest = _make_manifest()
        rule = PolicyRule(
            name="empty",
            type=RuleType.required_fields,
            params={},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 0

    def test_ownership_none_nested_field(self):
        manifest = _make_manifest(ownership=None)
        rule = PolicyRule(
            name="require-runbook",
            type=RuleType.required_fields,
            params={"fields": ["ownership.runbook"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert len(violations) == 1

    def test_severity_propagated(self):
        manifest = _make_manifest()
        rule = PolicyRule(
            name="warn-description",
            type=RuleType.required_fields,
            severity=PolicySeverity.warning,
            params={"fields": ["description"]},
        )
        violations = evaluate_required_fields(manifest, rule)
        assert violations[0].severity == PolicySeverity.warning


class TestTierConstraint:
    def test_matching_tier_min_slos_violation(self):
        manifest = _make_manifest(tier="critical", slos=[])
        rule = PolicyRule(
            name="critical-needs-slos",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "min_slos": 2},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 1
        assert "at least 2 SLOs" in violations[0].message

    def test_matching_tier_slos_sufficient(self):
        manifest = _make_manifest(
            tier="critical",
            slos=[
                SLODefinition(name="avail", target=99.9),
                SLODefinition(name="latency", target=200),
            ],
        )
        rule = PolicyRule(
            name="critical-needs-slos",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "min_slos": 2},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 0

    def test_non_matching_tier_skipped(self):
        manifest = _make_manifest(tier="standard", slos=[])
        rule = PolicyRule(
            name="critical-needs-slos",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "min_slos": 2},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 0

    def test_tier_all_applies_to_any(self):
        manifest = _make_manifest(tier="low", slos=[])
        rule = PolicyRule(
            name="all-need-slos",
            type=RuleType.tier_constraint,
            params={"tier": "all", "min_slos": 1},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 1

    def test_require_deployment_gates(self):
        manifest = _make_manifest(tier="critical", deployment=None)
        rule = PolicyRule(
            name="critical-gates",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "require_deployment_gates": True},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 1
        assert "deployment gates" in violations[0].message

    def test_deployment_gates_present(self):
        manifest = _make_manifest(
            tier="critical",
            deployment=DeploymentConfig(environments=["prod"]),
        )
        rule = PolicyRule(
            name="critical-gates",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "require_deployment_gates": True},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 0

    def test_require_ownership(self):
        manifest = _make_manifest(tier="critical", ownership=None)
        rule = PolicyRule(
            name="critical-ownership",
            type=RuleType.tier_constraint,
            params={"tier": "critical", "require_ownership": True},
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 1
        assert "ownership" in violations[0].message

    def test_multiple_constraints(self):
        manifest = _make_manifest(tier="critical", slos=[], ownership=None, deployment=None)
        rule = PolicyRule(
            name="critical-all",
            type=RuleType.tier_constraint,
            params={
                "tier": "critical",
                "min_slos": 1,
                "require_ownership": True,
                "require_deployment_gates": True,
            },
        )
        violations = evaluate_tier_constraint(manifest, rule)
        assert len(violations) == 3


class TestDependencyRule:
    def test_critical_dep_without_slo(self):
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="postgres-main", type="database", critical=True),
            ],
        )
        rule = PolicyRule(
            name="deps-need-slos",
            type=RuleType.dependency_rule,
            params={"require_critical_deps_have_slo": True},
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 1
        assert "postgres-main" in violations[0].message
        assert violations[0].field_path == "dependencies.postgres-main.slo"

    def test_critical_dep_with_slo(self):
        manifest = _make_manifest(
            dependencies=[
                Dependency(
                    name="postgres-main",
                    type="database",
                    critical=True,
                    slo=DependencySLO(availability=0.999),
                ),
            ],
        )
        rule = PolicyRule(
            name="deps-need-slos",
            type=RuleType.dependency_rule,
            params={"require_critical_deps_have_slo": True},
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 0

    def test_non_critical_dep_ignored(self):
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="cache", type="cache", critical=False),
            ],
        )
        rule = PolicyRule(
            name="deps-need-slos",
            type=RuleType.dependency_rule,
            params={"require_critical_deps_have_slo": True},
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 0

    def test_max_critical_deps_exceeded(self):
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="db1", type="database", critical=True),
                Dependency(name="db2", type="database", critical=True),
                Dependency(name="api1", type="api", critical=True),
            ],
        )
        rule = PolicyRule(
            name="limit-critical-deps",
            type=RuleType.dependency_rule,
            params={"max_critical_deps": 2},
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 1
        assert "3 critical dependencies" in violations[0].message

    def test_max_critical_deps_within_limit(self):
        manifest = _make_manifest(
            dependencies=[
                Dependency(name="db1", type="database", critical=True),
            ],
        )
        rule = PolicyRule(
            name="limit-critical-deps",
            type=RuleType.dependency_rule,
            params={"max_critical_deps": 2},
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 0

    def test_no_dependencies(self):
        manifest = _make_manifest(dependencies=[])
        rule = PolicyRule(
            name="deps-check",
            type=RuleType.dependency_rule,
            params={
                "require_critical_deps_have_slo": True,
                "max_critical_deps": 5,
            },
        )
        violations = evaluate_dependency_rule(manifest, rule)
        assert len(violations) == 0


class TestResolveField:
    def test_top_level_field(self):
        manifest = _make_manifest(description="Hello")
        assert _resolve_field(manifest, "description") == "Hello"

    def test_nested_field(self):
        manifest = _make_manifest(
            ownership=Ownership(team="t", runbook="https://wiki"),
        )
        assert _resolve_field(manifest, "ownership.runbook") == "https://wiki"

    def test_missing_field(self):
        manifest = _make_manifest()
        assert _resolve_field(manifest, "nonexistent") is None

    def test_missing_nested_field(self):
        manifest = _make_manifest(ownership=None)
        assert _resolve_field(manifest, "ownership.runbook") is None

    def test_deeply_nested_missing(self):
        manifest = _make_manifest()
        assert _resolve_field(manifest, "ownership.pagerduty.service_id") is None


class TestRuleEvaluators:
    def test_all_types_registered(self):
        assert RuleType.required_fields in RULE_EVALUATORS
        assert RuleType.tier_constraint in RULE_EVALUATORS
        assert RuleType.dependency_rule in RULE_EVALUATORS
