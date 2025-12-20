"""
Tests for the PagerDuty integration module.
"""

from nthlayer.pagerduty.defaults import (
    SUPPORT_MODEL_DEFAULTS,
    TIER_ESCALATION_DEFAULTS,
    SupportModel,
    Tier,
    get_escalation_config,
    get_schedules_for_tier,
)
from nthlayer.pagerduty.naming import (
    get_escalation_policy_name,
    get_schedule_name,
    get_service_name,
    get_sre_escalation_policy_name,
    get_team_name,
    parse_resource_name,
    sanitize_name,
)
from nthlayer.pagerduty.resources import ResourceResult


class TestDefaults:
    """Tests for tier-based defaults."""

    def test_tier_escalation_defaults_exist(self):
        """All tiers should have escalation defaults."""
        for tier in Tier:
            assert tier in TIER_ESCALATION_DEFAULTS

    def test_critical_tier_has_fastest_escalation(self):
        """Critical tier should have shortest delays."""
        critical = TIER_ESCALATION_DEFAULTS[Tier.CRITICAL]
        high = TIER_ESCALATION_DEFAULTS[Tier.HIGH]

        assert critical["primary_delay"] < high["primary_delay"]
        assert critical["urgency"] == "high"

    def test_low_tier_has_minimal_escalation(self):
        """Low tier should have minimal escalation."""
        low = TIER_ESCALATION_DEFAULTS[Tier.LOW]

        assert low["secondary_delay"] is None
        assert low["manager_delay"] is None
        assert low["num_loops"] == 0

    def test_support_model_defaults_exist(self):
        """All support models should have defaults."""
        for model in SupportModel:
            assert model in SUPPORT_MODEL_DEFAULTS

    def test_shared_model_has_sre_backup(self):
        """Shared support model should have SRE backup."""
        shared = SUPPORT_MODEL_DEFAULTS[SupportModel.SHARED]

        assert shared["sre_backup"] is True
        assert shared["off_hours_behavior"] == "page_sre"

    def test_self_model_no_sre_backup(self):
        """Self support model should not have SRE backup."""
        self_model = SUPPORT_MODEL_DEFAULTS[SupportModel.SELF]

        assert self_model["sre_backup"] is False
        assert self_model["coverage_type"] == "24x7"


class TestGetEscalationConfig:
    """Tests for get_escalation_config function."""

    def test_critical_tier_config(self):
        """Critical tier should have 3 escalation rules."""
        config = get_escalation_config("critical")

        assert len(config.rules) == 3
        assert config.rules[0].target_name == "primary"
        assert config.rules[1].target_name == "secondary"
        assert config.rules[2].target_name == "manager"
        assert config.num_loops == 3
        assert config.urgency == "high"

    def test_low_tier_config(self):
        """Low tier should have only primary escalation."""
        config = get_escalation_config("low")

        assert len(config.rules) == 1
        assert config.rules[0].target_name == "primary"
        assert config.num_loops == 0

    def test_unknown_tier_uses_medium_defaults(self):
        """Unknown tier should fall back to medium defaults."""
        config = get_escalation_config("unknown")
        medium_config = get_escalation_config("medium")

        assert config.num_loops == medium_config.num_loops


class TestGetSchedulesForTier:
    """Tests for get_schedules_for_tier function."""

    def test_critical_tier_all_schedules(self):
        """Critical tier should have all schedule types."""
        schedules = get_schedules_for_tier("critical")

        assert "primary" in schedules
        assert "secondary" in schedules
        assert "manager" in schedules

    def test_low_tier_primary_only(self):
        """Low tier should have only primary schedule."""
        schedules = get_schedules_for_tier("low")

        assert schedules == ["primary"]


class TestNaming:
    """Tests for naming conventions."""

    def test_sanitize_name(self):
        """Names should be sanitized consistently."""
        assert sanitize_name("My Team") == "my-team"
        assert sanitize_name("my_team") == "my-team"
        assert sanitize_name("  spaces  ") == "spaces"

    def test_get_team_name(self):
        """Team name should be sanitized."""
        assert get_team_name("Payments") == "payments"
        assert get_team_name("Platform SRE") == "platform-sre"

    def test_get_escalation_policy_name(self):
        """Escalation policy should follow pattern."""
        assert get_escalation_policy_name("payments") == "payments-escalation"
        assert get_escalation_policy_name("sre", "24x7") == "sre-24x7"

    def test_get_schedule_name(self):
        """Schedule name should follow pattern."""
        assert get_schedule_name("payments", "primary") == "payments-primary"
        assert get_schedule_name("payments", "secondary") == "payments-secondary"
        assert get_schedule_name("payments", "manager") == "payments-manager"

    def test_get_service_name(self):
        """Service name should be sanitized."""
        assert get_service_name("payment-api") == "payment-api"
        assert get_service_name("Payment API") == "payment-api"

    def test_get_sre_escalation_policy_name(self):
        """SRE escalation policy name should be fixed."""
        assert get_sre_escalation_policy_name() == "sre-escalation"

    def test_parse_resource_name(self):
        """Resource names should be parseable."""
        result = parse_resource_name("payments-escalation")
        assert result["team"] == "payments"
        assert result["type"] == "escalation"

        result = parse_resource_name("payments-primary")
        assert result["team"] == "payments"
        assert result["type"] == "primary"


class TestSpecsModels:
    """Tests for updated specs models."""

    def test_service_context_has_support_model(self):
        """ServiceContext should have support_model field."""
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
            support_model="shared",
        )

        assert context.support_model == "shared"

    def test_service_context_default_support_model(self):
        """Default support_model should be 'self'."""
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
        )

        assert context.support_model == "self"

    def test_service_context_to_dict_includes_support_model(self):
        """to_dict should include support_model."""
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(
            name="payment-api",
            team="payments",
            tier="critical",
            type="api",
            support_model="shared",
        )

        result = context.to_dict()
        assert result["support_model"] == "shared"

    def test_pagerduty_config(self):
        """PagerDutyConfig should work correctly."""
        from nthlayer.specs.models import PagerDutyConfig

        config = PagerDutyConfig(
            sre_escalation_policy="sre-escalation",
            timezone="America/Los_Angeles",
        )

        assert config.sre_escalation_policy == "sre-escalation"
        assert config.timezone == "America/Los_Angeles"


class TestResourceResult:
    """Tests for ResourceResult dataclass."""

    def test_resource_result_success(self):
        """ResourceResult should track successful operations."""
        result = ResourceResult(
            success=True,
            resource_id="PABCDEF",
            resource_name="test-team",
            created=True,
        )
        assert result.success
        assert result.resource_id == "PABCDEF"
        assert result.created
        assert not result.warnings
        assert result.error is None

    def test_resource_result_failure(self):
        """ResourceResult should track failed operations."""
        result = ResourceResult(
            success=False,
            error="API rate limit exceeded",
        )
        assert not result.success
        assert result.error == "API rate limit exceeded"
        assert result.resource_id is None

    def test_resource_result_with_warnings(self):
        """ResourceResult should track warnings."""
        result = ResourceResult(
            success=True,
            resource_id="PABCDEF",
            resource_name="test-team",
            created=False,
            warnings=["Using existing team 'test-team'"],
        )
        assert result.success
        assert not result.created
        assert len(result.warnings) == 1
        assert "existing team" in result.warnings[0]
