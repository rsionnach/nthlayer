"""Tests for nthlayer.core.tiers module."""

from dataclasses import FrozenInstanceError

import pytest

from nthlayer.core.tiers import (
    TIER_CONFIGS,
    TIER_NAMES,
    VALID_TIERS,
    Tier,
    TierConfig,
    get_slo_targets,
    get_tier_config,
    get_tier_thresholds,
    is_valid_tier,
    normalize_tier,
)


class TestTierEnum:
    """Tests for Tier StrEnum."""

    def test_critical_value(self):
        assert Tier.CRITICAL == "critical"

    def test_standard_value(self):
        assert Tier.STANDARD == "standard"

    def test_low_value(self):
        assert Tier.LOW == "low"

    def test_string_coercion(self):
        assert str(Tier.CRITICAL) == "critical"
        assert f"{Tier.STANDARD}" == "standard"

    def test_membership(self):
        assert "critical" in [t.value for t in Tier]
        assert "standard" in [t.value for t in Tier]
        assert "low" in [t.value for t in Tier]

    def test_enum_count(self):
        assert len(Tier) == 3


class TestTierConfig:
    """Tests for TierConfig dataclass and TIER_CONFIGS."""

    def test_frozen_cannot_mutate(self):
        config = TIER_CONFIGS["critical"]
        with pytest.raises(FrozenInstanceError):
            config.name = "changed"

    def test_critical_config(self):
        cfg = TIER_CONFIGS["critical"]
        assert cfg.name == "critical"
        assert cfg.availability_target == 99.95
        assert cfg.latency_p99_ms == 200
        assert cfg.error_budget_blocking_pct == 10.0
        assert cfg.pagerduty_urgency == "high"

    def test_standard_config(self):
        cfg = TIER_CONFIGS["standard"]
        assert cfg.name == "standard"
        assert cfg.availability_target == 99.9
        assert cfg.latency_p99_ms == 500
        assert cfg.error_budget_blocking_pct is None
        assert cfg.pagerduty_urgency == "low"

    def test_low_config(self):
        cfg = TIER_CONFIGS["low"]
        assert cfg.name == "low"
        assert cfg.availability_target == 99.5
        assert cfg.latency_p99_ms == 1000
        assert cfg.error_budget_blocking_pct is None

    def test_all_canonical_tiers_present(self):
        for name in TIER_NAMES:
            assert name in TIER_CONFIGS

    def test_tier_names_tuple(self):
        assert TIER_NAMES == ("critical", "standard", "low")

    def test_valid_tiers_includes_aliases(self):
        assert "tier-1" in VALID_TIERS
        assert "tier-2" in VALID_TIERS
        assert "tier-3" in VALID_TIERS
        assert "critical" in VALID_TIERS


class TestNormalizeTier:
    """Tests for normalize_tier()."""

    def test_canonical_names_returned_unchanged(self):
        assert normalize_tier("critical") == "critical"
        assert normalize_tier("standard") == "standard"
        assert normalize_tier("low") == "low"

    def test_case_insensitive(self):
        assert normalize_tier("CRITICAL") == "critical"
        assert normalize_tier("Standard") == "standard"
        assert normalize_tier("LOW") == "low"

    def test_legacy_alias_tier1(self):
        assert normalize_tier("tier-1") == "critical"

    def test_legacy_alias_tier2(self):
        assert normalize_tier("tier-2") == "standard"

    def test_legacy_alias_tier3(self):
        assert normalize_tier("tier-3") == "low"

    def test_legacy_alias_case_insensitive(self):
        assert normalize_tier("Tier-1") == "critical"
        assert normalize_tier("TIER-3") == "low"

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid tier"):
            normalize_tier("platinum")

    def test_invalid_empty_like_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            normalize_tier("   ")


class TestGetTierConfig:
    """Tests for get_tier_config()."""

    def test_returns_tier_config_instance(self):
        cfg = get_tier_config("critical")
        assert isinstance(cfg, TierConfig)

    def test_accepts_aliases(self):
        cfg = get_tier_config("tier-1")
        assert cfg.name == "critical"

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            get_tier_config("nonexistent")


class TestIsValidTier:
    """Tests for is_valid_tier()."""

    def test_canonical_names_valid(self):
        assert is_valid_tier("critical") is True
        assert is_valid_tier("standard") is True
        assert is_valid_tier("low") is True

    def test_aliases_valid(self):
        assert is_valid_tier("tier-1") is True
        assert is_valid_tier("tier-2") is True
        assert is_valid_tier("tier-3") is True

    def test_case_insensitive(self):
        assert is_valid_tier("CRITICAL") is True
        assert is_valid_tier("Tier-2") is True

    def test_invalid_returns_false(self):
        assert is_valid_tier("platinum") is False
        assert is_valid_tier("tier-4") is False

    def test_empty_string_returns_false(self):
        assert is_valid_tier("") is False


class TestGetTierThresholds:
    """Tests for get_tier_thresholds()."""

    def test_critical_has_blocking(self):
        thresholds = get_tier_thresholds("critical")
        assert thresholds["warning"] == 20.0
        assert thresholds["blocking"] == 10.0

    def test_standard_no_blocking(self):
        thresholds = get_tier_thresholds("standard")
        assert thresholds["warning"] == 20.0
        assert thresholds["blocking"] is None

    def test_low_no_blocking(self):
        thresholds = get_tier_thresholds("low")
        assert thresholds["blocking"] is None


class TestGetSloTargets:
    """Tests for get_slo_targets()."""

    def test_critical_targets(self):
        targets = get_slo_targets("critical")
        assert targets["availability"] == 99.95
        assert targets["latency_ms"] == 200

    def test_low_targets(self):
        targets = get_slo_targets("low")
        assert targets["availability"] == 99.5
        assert targets["latency_ms"] == 1000

    def test_accepts_alias(self):
        targets = get_slo_targets("tier-2")
        assert targets["availability"] == 99.9
