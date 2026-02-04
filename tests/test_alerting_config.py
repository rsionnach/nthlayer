"""Tests for alerting configuration parsing and tier defaults."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from nthlayer.specs.alerting import (
    TIER_DEFAULT_RULES,
    AlertChannels,
    AlertingConfig,
    SpecAlertRule,
    parse_alerting_config,
    resolve_effective_rules,
)

# -------------------------------------------------------------------------
# parse_alerting_config
# -------------------------------------------------------------------------


class TestParseAlertingConfig:
    def test_returns_none_for_none(self) -> None:
        assert parse_alerting_config(None) is None

    def test_returns_none_for_empty_dict(self) -> None:
        assert parse_alerting_config({}) is None

    def test_parses_channels(self) -> None:
        data = {
            "channels": {
                "slack_webhook": "https://hooks.slack.com/test",
                "pagerduty_key": "abc123",
            },
            "rules": [],
        }
        cfg = parse_alerting_config(data)
        assert cfg is not None
        assert cfg.channels.slack_webhook == "https://hooks.slack.com/test"
        assert cfg.channels.pagerduty_key == "abc123"

    def test_parses_rules(self) -> None:
        data = {
            "rules": [
                {
                    "name": "budget-warning",
                    "type": "budget_threshold",
                    "slo": "availability",
                    "threshold": 0.75,
                    "severity": "warning",
                },
                {
                    "name": "high-burn",
                    "type": "burn_rate",
                    "slo": "*",
                    "threshold": 3.0,
                    "severity": "critical",
                },
            ],
        }
        cfg = parse_alerting_config(data)
        assert cfg is not None
        assert len(cfg.rules) == 2
        assert cfg.rules[0].name == "budget-warning"
        assert cfg.rules[0].type == "budget_threshold"
        assert cfg.rules[0].slo == "availability"
        assert cfg.rules[0].threshold == 0.75
        assert cfg.rules[1].slo == "*"

    def test_auto_rules_defaults_to_true(self) -> None:
        cfg = parse_alerting_config({"rules": []})
        assert cfg is not None
        assert cfg.auto_rules is True

    def test_auto_rules_can_be_disabled(self) -> None:
        cfg = parse_alerting_config({"auto_rules": False, "rules": []})
        assert cfg is not None
        assert cfg.auto_rules is False


# -------------------------------------------------------------------------
# AlertChannels env var resolution
# -------------------------------------------------------------------------


class TestAlertChannelsEnv:
    def test_resolve_env_vars(self) -> None:
        with patch.dict(os.environ, {"SLACK_URL": "https://resolved.slack"}):
            channels = AlertChannels(
                slack_webhook="${SLACK_URL}",
                pagerduty_key=None,
            )
            resolved = channels.resolve_env_vars()
            assert resolved.slack_webhook == "https://resolved.slack"
            assert resolved.pagerduty_key is None

    def test_unresolved_env_var_kept(self) -> None:
        channels = AlertChannels(slack_webhook="${NONEXISTENT}")
        resolved = channels.resolve_env_vars()
        assert resolved.slack_webhook == "${NONEXISTENT}"


# -------------------------------------------------------------------------
# Tier default rules
# -------------------------------------------------------------------------


class TestTierDefaults:
    @pytest.mark.parametrize("tier", ["critical", "high", "standard", "low"])
    def test_tier_has_defaults(self, tier: str) -> None:
        assert tier in TIER_DEFAULT_RULES
        assert len(TIER_DEFAULT_RULES[tier]) >= 1

    def test_critical_has_four_rules(self) -> None:
        assert len(TIER_DEFAULT_RULES["critical"]) == 4

    def test_low_has_one_rule(self) -> None:
        assert len(TIER_DEFAULT_RULES["low"]) == 1

    def test_standard_has_no_exhaustion(self) -> None:
        types = [r[1] for r in TIER_DEFAULT_RULES["standard"]]
        assert "budget_exhaustion" not in types

    def test_critical_thresholds_tighter_than_standard(self) -> None:
        critical_warning = next(
            r for r in TIER_DEFAULT_RULES["critical"] if r[0] == "budget-warning"
        )
        standard_warning = next(
            r for r in TIER_DEFAULT_RULES["standard"] if r[0] == "budget-warning"
        )
        assert critical_warning[2] < standard_warning[2]  # 0.50 < 0.80


# -------------------------------------------------------------------------
# resolve_effective_rules
# -------------------------------------------------------------------------


class TestResolveEffectiveRules:
    def test_wildcard_expansion(self) -> None:
        cfg = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="high-burn",
                    type="burn_rate",
                    slo="*",
                    threshold=3.0,
                ),
            ],
            auto_rules=False,
        )
        result = resolve_effective_rules(cfg, "standard", ["avail", "latency"])
        assert len(result) == 2
        assert {r.slo for r in result} == {"avail", "latency"}

    def test_auto_rules_added(self) -> None:
        cfg = AlertingConfig(rules=[], auto_rules=True)
        result = resolve_effective_rules(cfg, "critical", ["availability"])
        # Should have tier-critical defaults for one SLO
        assert len(result) == len(TIER_DEFAULT_RULES["critical"])

    def test_auto_rules_not_added_when_disabled(self) -> None:
        cfg = AlertingConfig(rules=[], auto_rules=False)
        result = resolve_effective_rules(cfg, "critical", ["availability"])
        assert result == []

    def test_explicit_overrides_auto(self) -> None:
        cfg = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="budget-warning",
                    type="budget_threshold",
                    slo="availability",
                    threshold=0.60,
                ),
            ],
            auto_rules=True,
        )
        result = resolve_effective_rules(cfg, "critical", ["availability"])
        # budget-warning for availability already present, so auto-default
        # for that (name, slo) pair should NOT be duplicated
        budget_warnings = [
            r for r in result if r.name == "budget-warning" and r.slo == "availability"
        ]
        assert len(budget_warnings) == 1
        assert budget_warnings[0].threshold == 0.60

    def test_unknown_tier_no_auto_rules(self) -> None:
        cfg = AlertingConfig(rules=[], auto_rules=True)
        result = resolve_effective_rules(cfg, "nonexistent", ["availability"])
        assert result == []


# -------------------------------------------------------------------------
# get_rules_for_slo
# -------------------------------------------------------------------------


class TestGetRulesForSlo:
    def test_exact_match(self) -> None:
        cfg = AlertingConfig(
            rules=[
                SpecAlertRule(name="a", type="budget_threshold", slo="avail", threshold=0.5),
                SpecAlertRule(name="b", type="budget_threshold", slo="latency", threshold=0.5),
            ],
        )
        result = cfg.get_rules_for_slo("avail")
        assert len(result) == 1
        assert result[0].name == "a"

    def test_wildcard_matches_any(self) -> None:
        cfg = AlertingConfig(
            rules=[
                SpecAlertRule(name="a", type="burn_rate", slo="*", threshold=3.0),
            ],
        )
        result = cfg.get_rules_for_slo("whatever")
        assert len(result) == 1

    def test_disabled_rules_excluded(self) -> None:
        cfg = AlertingConfig(
            rules=[
                SpecAlertRule(
                    name="a",
                    type="budget_threshold",
                    slo="avail",
                    threshold=0.5,
                    enabled=False,
                ),
            ],
        )
        assert cfg.get_rules_for_slo("avail") == []


# -------------------------------------------------------------------------
# OpenSRM integration
# -------------------------------------------------------------------------


class TestOpenSRMParsing:
    def test_parse_opensrm_with_alerting(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "high"},
            "spec": {
                "type": "api",
                "slos": {"availability": {"target": 99.9, "window": "30d"}},
                "alerting": {
                    "channels": {"slack_webhook": "${SLACK_URL}"},
                    "rules": [
                        {
                            "name": "budget-warn",
                            "type": "budget_threshold",
                            "slo": "availability",
                            "threshold": 0.75,
                            "severity": "warning",
                        }
                    ],
                    "auto_rules": False,
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.alerting is not None
        assert len(manifest.alerting.rules) == 1
        assert manifest.alerting.channels.slack_webhook == "${SLACK_URL}"
        assert manifest.alerting.auto_rules is False

    def test_parse_opensrm_without_alerting(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "standard"},
            "spec": {"type": "api"},
        }
        manifest = parse_opensrm(data)
        assert manifest.alerting is None


# -------------------------------------------------------------------------
# Legacy format integration
# -------------------------------------------------------------------------


class TestLegacyParsing:
    def test_extract_alerting_from_legacy_resources(self) -> None:
        from nthlayer.specs.loader import _extract_alerting_from_resources

        resources = [
            {"kind": "SLO", "name": "avail", "spec": {}},
            {
                "kind": "Alerts",
                "name": "alerts",
                "spec": {
                    "channels": {"slack_webhook": "https://hooks.slack.com/x"},
                    "rules": [
                        {
                            "name": "warn",
                            "type": "budget_threshold",
                            "slo": "*",
                            "threshold": 0.80,
                        }
                    ],
                    "auto_rules": True,
                },
            },
        ]
        alerting = _extract_alerting_from_resources(resources)
        assert alerting is not None
        assert len(alerting.rules) == 1
        assert alerting.channels.slack_webhook == "https://hooks.slack.com/x"

    def test_no_alerts_resource_returns_none(self) -> None:
        from nthlayer.specs.loader import _extract_alerting_from_resources

        resources = [{"kind": "SLO", "name": "avail", "spec": {}}]
        assert _extract_alerting_from_resources(resources) is None
