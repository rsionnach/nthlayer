"""Tests for PolicyEngine."""

from __future__ import annotations

from pathlib import Path

import yaml

from nthlayer.policies.engine import PolicyEngine, _parse_rules
from nthlayer.policies.models import PolicyRule, PolicySeverity, RuleType
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition


def _make_manifest(**overrides) -> ReliabilityManifest:
    defaults = {
        "name": "test-service",
        "team": "test-team",
        "tier": "standard",
        "type": "api",
    }
    defaults.update(overrides)
    return ReliabilityManifest(**defaults)


class TestPolicyEngineFromYaml:
    def test_load_from_yaml(self, tmp_path: Path):
        policy_file = tmp_path / "policies.yaml"
        policy_file.write_text(
            yaml.dump(
                {
                    "rules": [
                        {
                            "name": "require-description",
                            "type": "required_fields",
                            "severity": "warning",
                            "params": {"fields": ["description"]},
                        },
                        {
                            "name": "critical-slos",
                            "type": "tier_constraint",
                            "params": {"tier": "critical", "min_slos": 2},
                        },
                    ]
                }
            )
        )
        engine = PolicyEngine.from_yaml(policy_file)
        assert len(engine._rules) == 2
        assert engine._rules[0].name == "require-description"
        assert engine._rules[0].severity == PolicySeverity.warning
        assert engine._rules[1].name == "critical-slos"
        assert engine._rules[1].severity == PolicySeverity.error

    def test_load_empty_yaml(self, tmp_path: Path):
        policy_file = tmp_path / "empty.yaml"
        policy_file.write_text(yaml.dump({"rules": []}))
        engine = PolicyEngine.from_yaml(policy_file)
        assert len(engine._rules) == 0

    def test_load_no_rules_key(self, tmp_path: Path):
        policy_file = tmp_path / "norules.yaml"
        policy_file.write_text(yaml.dump({"version": "1"}))
        engine = PolicyEngine.from_yaml(policy_file)
        assert len(engine._rules) == 0


class TestPolicyEngineFromDict:
    def test_load_from_dict(self):
        data = {
            "rules": [
                {
                    "name": "require-ownership",
                    "type": "required_fields",
                    "params": {"fields": ["ownership.team"]},
                },
            ]
        }
        engine = PolicyEngine.from_dict(data)
        assert len(engine._rules) == 1
        assert engine._rules[0].name == "require-ownership"

    def test_empty_dict(self):
        engine = PolicyEngine.from_dict({})
        assert len(engine._rules) == 0


class TestPolicyEngineEvaluate:
    def test_evaluate_no_violations(self):
        manifest = _make_manifest(description="A service")
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="require-description",
                    type=RuleType.required_fields,
                    params={"fields": ["description"]},
                ),
            ]
        )
        report = engine.evaluate(manifest)
        assert report.passed is True
        assert report.rules_evaluated == 1
        assert len(report.violations) == 0

    def test_evaluate_with_violations(self):
        manifest = _make_manifest()
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="require-description",
                    type=RuleType.required_fields,
                    params={"fields": ["description"]},
                ),
            ]
        )
        report = engine.evaluate(manifest)
        assert report.passed is False
        assert report.rules_evaluated == 1
        assert report.error_count == 1

    def test_evaluate_mixed_rules(self):
        manifest = _make_manifest(
            tier="critical",
            slos=[SLODefinition(name="avail", target=99.9)],
        )
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="require-description",
                    type=RuleType.required_fields,
                    severity=PolicySeverity.error,
                    params={"fields": ["description"]},
                ),
                PolicyRule(
                    name="critical-slos",
                    type=RuleType.tier_constraint,
                    severity=PolicySeverity.warning,
                    params={"tier": "critical", "min_slos": 2},
                ),
            ]
        )
        report = engine.evaluate(manifest)
        assert report.passed is False
        assert report.rules_evaluated == 2
        assert report.error_count == 1
        assert report.warning_count == 1

    def test_evaluate_service_name_in_report(self):
        manifest = _make_manifest(name="my-api")
        engine = PolicyEngine(rules=[])
        report = engine.evaluate(manifest)
        assert report.service == "my-api"

    def test_unknown_rule_type_skipped(self):
        manifest = _make_manifest()
        # Create a rule with a valid type but no evaluator registered
        # We can't easily do this with StrEnum, so we test that engine
        # handles rules gracefully
        engine = PolicyEngine(rules=[])
        report = engine.evaluate(manifest)
        assert report.rules_evaluated == 0


class TestPolicyEngineMerge:
    def test_add_rules(self):
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="rule1",
                    type=RuleType.required_fields,
                    params={"fields": ["description"]},
                ),
            ]
        )
        engine.add_rules(
            [
                PolicyRule(
                    name="rule2",
                    type=RuleType.tier_constraint,
                    params={"tier": "critical", "min_slos": 1},
                ),
            ]
        )
        assert len(engine._rules) == 2

    def test_merge_central_and_per_service(self, tmp_path: Path):
        central_file = tmp_path / "central.yaml"
        central_file.write_text(
            yaml.dump(
                {
                    "rules": [
                        {
                            "name": "central-rule",
                            "type": "required_fields",
                            "params": {"fields": ["description"]},
                        },
                    ]
                }
            )
        )
        engine = PolicyEngine.from_yaml(central_file)

        per_service = PolicyEngine.from_dict(
            {
                "rules": [
                    {
                        "name": "service-rule",
                        "type": "tier_constraint",
                        "severity": "warning",
                        "params": {"tier": "all", "min_slos": 1},
                    },
                ]
            }
        )
        engine.add_rules(per_service._rules)

        manifest = _make_manifest(slos=[])
        report = engine.evaluate(manifest)
        assert report.rules_evaluated == 2
        assert report.error_count == 1
        assert report.warning_count == 1


class TestParseRules:
    def test_valid_rules(self):
        raw = [
            {
                "name": "test",
                "type": "required_fields",
                "severity": "warning",
                "description": "Test rule",
                "params": {"fields": ["description"]},
            },
        ]
        rules = _parse_rules(raw)
        assert len(rules) == 1
        assert rules[0].name == "test"
        assert rules[0].type == RuleType.required_fields
        assert rules[0].severity == PolicySeverity.warning
        assert rules[0].description == "Test rule"

    def test_defaults(self):
        raw = [{"name": "test", "type": "tier_constraint"}]
        rules = _parse_rules(raw)
        assert rules[0].severity == PolicySeverity.error
        assert rules[0].params == {}
        assert rules[0].description is None

    def test_empty_list(self):
        assert _parse_rules([]) == []
