"""Policy rule evaluators for build-time spec validation.

Each evaluator takes a ReliabilityManifest and a PolicyRule, returning
a list of PolicyViolation instances for any rules that are not met.
"""

from __future__ import annotations

from typing import Any

from nthlayer.policies.models import PolicyRule, PolicyViolation, RuleType
from nthlayer.specs.manifest import ReliabilityManifest


def evaluate_required_fields(
    manifest: ReliabilityManifest, rule: PolicyRule
) -> list[PolicyViolation]:
    """Check that required fields are present and non-empty.

    params.fields: list of dot-path field names, e.g.:
      - "ownership.runbook"
      - "description"
    """
    violations = []
    for field_path in rule.params.get("fields", []):
        value = _resolve_field(manifest, field_path)
        if value is None or value == "" or value == []:
            violations.append(
                PolicyViolation(
                    rule_name=rule.name,
                    rule_type=RuleType.required_fields,
                    severity=rule.severity,
                    message=f"Required field '{field_path}' is missing or empty",
                    field_path=field_path,
                )
            )
    return violations


def evaluate_tier_constraint(
    manifest: ReliabilityManifest, rule: PolicyRule
) -> list[PolicyViolation]:
    """Enforce tier-specific requirements.

    params.tier: which tier this rule applies to (or "all")
    params.min_slos: minimum number of SLOs required
    params.require_deployment_gates: bool
    params.require_ownership: bool
    """
    violations = []
    tier = rule.params.get("tier", "all")
    if tier != "all" and manifest.tier != tier:
        return []

    min_slos = rule.params.get("min_slos")
    if min_slos is not None and len(manifest.slos) < min_slos:
        violations.append(
            PolicyViolation(
                rule_name=rule.name,
                rule_type=RuleType.tier_constraint,
                severity=rule.severity,
                message=f"Tier '{manifest.tier}' requires at least {min_slos} SLOs, found {len(manifest.slos)}",
            )
        )

    if rule.params.get("require_deployment_gates") and not manifest.deployment:
        violations.append(
            PolicyViolation(
                rule_name=rule.name,
                rule_type=RuleType.tier_constraint,
                severity=rule.severity,
                message=f"Tier '{manifest.tier}' requires deployment gates",
            )
        )

    if rule.params.get("require_ownership") and not manifest.ownership:
        violations.append(
            PolicyViolation(
                rule_name=rule.name,
                rule_type=RuleType.tier_constraint,
                severity=rule.severity,
                message=f"Tier '{manifest.tier}' requires ownership configuration",
            )
        )

    return violations


def evaluate_dependency_rule(
    manifest: ReliabilityManifest, rule: PolicyRule
) -> list[PolicyViolation]:
    """Enforce dependency constraints.

    params.require_critical_deps_have_slo: bool
    params.max_critical_deps: int
    """
    violations = []
    critical_deps = [d for d in manifest.dependencies if d.critical]

    if rule.params.get("require_critical_deps_have_slo"):
        for dep in critical_deps:
            if not dep.slo:
                violations.append(
                    PolicyViolation(
                        rule_name=rule.name,
                        rule_type=RuleType.dependency_rule,
                        severity=rule.severity,
                        message=f"Critical dependency '{dep.name}' has no SLO expectations declared",
                        field_path=f"dependencies.{dep.name}.slo",
                    )
                )

    max_critical = rule.params.get("max_critical_deps")
    if max_critical is not None and len(critical_deps) > max_critical:
        violations.append(
            PolicyViolation(
                rule_name=rule.name,
                rule_type=RuleType.dependency_rule,
                severity=rule.severity,
                message=f"Service has {len(critical_deps)} critical dependencies, max allowed is {max_critical}",
            )
        )

    return violations


RULE_EVALUATORS = {
    RuleType.required_fields: evaluate_required_fields,
    RuleType.tier_constraint: evaluate_tier_constraint,
    RuleType.dependency_rule: evaluate_dependency_rule,
}


def _resolve_field(manifest: ReliabilityManifest, field_path: str) -> Any:
    """Resolve a dot-path field on a manifest. Returns None if missing."""
    obj: Any = manifest
    for part in field_path.split("."):
        if obj is None:
            return None
        if hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            return None
    return obj
