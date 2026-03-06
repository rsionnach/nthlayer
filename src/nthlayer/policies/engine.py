"""PolicyEngine: loads and evaluates policy rules against service manifests.

Central policies are loaded from a YAML file. Per-service overrides are
loaded from PolicyRules resources in the service YAML. Both are merged
and evaluated together.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nthlayer.policies.models import PolicyReport, PolicyRule, PolicySeverity, RuleType
from nthlayer.policies.rules import RULE_EVALUATORS
from nthlayer.specs.manifest import ReliabilityManifest


class PolicyEngine:
    """Loads and evaluates policy rules against a service manifest."""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules: list[PolicyRule] = rules or []

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        """Load policy rules from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        rules = _parse_rules(data.get("rules", []))
        return cls(rules=rules)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyEngine:
        """Load policy rules from a dict (for per-service PolicyRules resources)."""
        rules = _parse_rules(data.get("rules", []))
        return cls(rules=rules)

    def add_rules(self, rules: list[PolicyRule]) -> None:
        """Merge additional rules (e.g., per-service overrides)."""
        self._rules.extend(rules)

    def evaluate(self, manifest: ReliabilityManifest) -> PolicyReport:
        """Evaluate all rules against the manifest."""
        report = PolicyReport(service=manifest.name)
        for rule in self._rules:
            evaluator = RULE_EVALUATORS.get(rule.type)
            if evaluator is None:
                continue
            violations = evaluator(manifest, rule)
            report.violations.extend(violations)
            report.rules_evaluated += 1
        return report


def _parse_rules(raw_rules: list[dict[str, Any]]) -> list[PolicyRule]:
    """Parse raw YAML rule dicts into PolicyRule objects."""
    rules = []
    for raw in raw_rules:
        rules.append(
            PolicyRule(
                name=raw["name"],
                type=RuleType(raw["type"]),
                severity=PolicySeverity(raw.get("severity", "error")),
                params=raw.get("params", {}),
                description=raw.get("description"),
            )
        )
    return rules
