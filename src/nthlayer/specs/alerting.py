"""
Alert rule configuration for service specs.

Defines alerting configuration that can be embedded in OpenSRM or legacy
service manifests. Supports tier-based auto-defaults and env var resolution
for notification channels.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlertChannels:
    """Notification channels for alerts."""

    slack_webhook: str | None = None
    pagerduty_key: str | None = None

    def resolve_env_vars(self) -> AlertChannels:
        """Return a copy with ``${ENV_VAR}`` placeholders resolved."""
        return AlertChannels(
            slack_webhook=_resolve_env(self.slack_webhook),
            pagerduty_key=_resolve_env(self.pagerduty_key),
        )


@dataclass
class SpecAlertRule:
    """A single alert rule defined in a service spec."""

    name: str
    type: str  # budget_threshold, burn_rate, budget_exhaustion
    slo: str  # SLO name or "*" for all
    threshold: float
    severity: str = "warning"  # info, warning, critical
    enabled: bool = True


@dataclass
class AlertingConfig:
    """Top-level alerting configuration in a service spec."""

    channels: AlertChannels = field(default_factory=AlertChannels)
    rules: list[SpecAlertRule] = field(default_factory=list)
    auto_rules: bool = True

    def get_rules_for_slo(self, slo_name: str) -> list[SpecAlertRule]:
        """Return rules that apply to a specific SLO (exact match or wildcard)."""
        return [r for r in self.rules if r.enabled and (r.slo == "*" or r.slo == slo_name)]


# -------------------------------------------------------------------------
# Tier-based default rules
# -------------------------------------------------------------------------

# Each entry is (name, type, threshold, severity)
_TierRule = tuple[str, str, float, str]

TIER_DEFAULT_RULES: dict[str, list[_TierRule]] = {
    "critical": [
        ("budget-warning", "budget_threshold", 0.50, "warning"),
        ("budget-critical", "budget_threshold", 0.75, "critical"),
        ("burn-rate-warning", "burn_rate", 2.0, "warning"),
        ("budget-exhaustion", "budget_exhaustion", 12.0, "critical"),
    ],
    "high": [
        ("budget-warning", "budget_threshold", 0.65, "warning"),
        ("budget-critical", "budget_threshold", 0.85, "critical"),
        ("burn-rate-warning", "burn_rate", 3.0, "warning"),
        ("budget-exhaustion", "budget_exhaustion", 6.0, "critical"),
    ],
    "standard": [
        ("budget-warning", "budget_threshold", 0.80, "warning"),
        ("budget-critical", "budget_threshold", 0.95, "critical"),
        ("burn-rate-warning", "burn_rate", 5.0, "warning"),
    ],
    "low": [
        ("budget-critical", "budget_threshold", 0.95, "critical"),
    ],
}


def resolve_effective_rules(
    config: AlertingConfig,
    tier: str,
    slo_names: list[str],
) -> list[SpecAlertRule]:
    """
    Merge explicit rules with tier-based auto-defaults.

    Wildcard ``slo: "*"`` rules are expanded so that one concrete rule
    is produced per SLO.  Auto-generated defaults are only added when
    ``config.auto_rules`` is True and no explicit rule already covers
    the same (name, slo) pair.
    """
    # 1. Expand wildcards in explicit rules
    expanded: list[SpecAlertRule] = []
    for rule in config.rules:
        if rule.slo == "*":
            for slo_name in slo_names:
                expanded.append(
                    SpecAlertRule(
                        name=rule.name,
                        type=rule.type,
                        slo=slo_name,
                        threshold=rule.threshold,
                        severity=rule.severity,
                        enabled=rule.enabled,
                    )
                )
        else:
            expanded.append(rule)

    # 2. Generate auto-defaults if enabled
    if config.auto_rules:
        existing_keys = {(r.name, r.slo) for r in expanded}
        defaults = TIER_DEFAULT_RULES.get(tier, [])
        for name, rtype, threshold, severity in defaults:
            for slo_name in slo_names:
                if (name, slo_name) not in existing_keys:
                    expanded.append(
                        SpecAlertRule(
                            name=name,
                            type=rtype,
                            slo=slo_name,
                            threshold=threshold,
                            severity=severity,
                        )
                    )

    return expanded


# -------------------------------------------------------------------------
# Parsing helpers
# -------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env(value: str | None) -> str | None:
    """Replace ``${VAR}`` with the corresponding env var value."""
    if value is None:
        return None
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def parse_alerting_config(data: dict[str, Any] | None) -> AlertingConfig | None:
    """Parse an ``alerting`` section from spec YAML into an AlertingConfig."""
    if not data:
        return None

    channels = AlertChannels()
    channels_data = data.get("channels")
    if channels_data and isinstance(channels_data, dict):
        channels = AlertChannels(
            slack_webhook=channels_data.get("slack_webhook"),
            pagerduty_key=channels_data.get("pagerduty_key"),
        )

    rules: list[SpecAlertRule] = []
    for rule_data in data.get("rules", []):
        if not isinstance(rule_data, dict):
            continue
        rules.append(
            SpecAlertRule(
                name=rule_data.get("name", ""),
                type=rule_data.get("type", "budget_threshold"),
                slo=rule_data.get("slo", "*"),
                threshold=float(rule_data.get("threshold", 0)),
                severity=rule_data.get("severity", "warning"),
                enabled=rule_data.get("enabled", True),
            )
        )

    return AlertingConfig(
        channels=channels,
        rules=rules,
        auto_rules=data.get("auto_rules", True),
    )
