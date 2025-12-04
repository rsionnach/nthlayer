"""
Tier-based defaults for PagerDuty escalation policies and schedules.

Provides sensible defaults based on service tier and support model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Tier(StrEnum):
    """Service criticality tier."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SupportModel(StrEnum):
    """Who responds to alerts and when."""

    SELF = "self"  # Team handles everything 24/7
    SHARED = "shared"  # Team (business hours) + SRE (off-hours)
    SRE = "sre"  # SRE handles everything
    BUSINESS_HOURS = "business_hours"  # No off-hours support


@dataclass
class EscalationRule:
    """Single escalation rule configuration."""

    target_type: str  # "schedule" or "user"
    target_name: str  # Schedule name suffix (e.g., "primary") or user email
    delay_minutes: int


@dataclass
class EscalationConfig:
    """Full escalation policy configuration."""

    rules: list[EscalationRule]
    num_loops: int
    urgency: str  # "high" or "low"


@dataclass
class ScheduleConfig:
    """Schedule configuration."""

    name_suffix: str  # e.g., "primary", "secondary", "manager"
    rotation_type: str  # "weekly", "daily", "custom"
    rotation_length_seconds: int
    handoff_hour: int  # 0-23
    handoff_minute: int  # 0-59
    coverage_type: str  # "24x7", "business_hours", "extended_hours"
    start_hour: int | None = None  # For non-24x7 coverage
    end_hour: int | None = None


# Tier-based escalation timing
TIER_ESCALATION_DEFAULTS: dict[str, dict[str, Any]] = {
    Tier.CRITICAL: {
        "primary_delay": 5,
        "secondary_delay": 15,
        "manager_delay": 30,
        "num_loops": 3,
        "urgency": "high",
        "include_manager": True,
    },
    Tier.HIGH: {
        "primary_delay": 15,
        "secondary_delay": 30,
        "manager_delay": 60,
        "num_loops": 2,
        "urgency": "high",
        "include_manager": True,
    },
    Tier.MEDIUM: {
        "primary_delay": 30,
        "secondary_delay": 60,
        "manager_delay": None,
        "num_loops": 1,
        "urgency": "low",
        "include_manager": False,
    },
    Tier.LOW: {
        "primary_delay": 60,
        "secondary_delay": None,
        "manager_delay": None,
        "num_loops": 0,
        "urgency": "low",
        "include_manager": False,
    },
}


# Schedule coverage by tier + support model
TIER_SCHEDULE_DEFAULTS: dict[str, dict[str, Any]] = {
    Tier.CRITICAL: {
        "rotation_type": "weekly",
        "rotation_length_seconds": 604800,  # 1 week
        "handoff_hour": 9,
        "handoff_minute": 0,
    },
    Tier.HIGH: {
        "rotation_type": "weekly",
        "rotation_length_seconds": 604800,
        "handoff_hour": 9,
        "handoff_minute": 0,
    },
    Tier.MEDIUM: {
        "rotation_type": "weekly",
        "rotation_length_seconds": 604800,
        "handoff_hour": 9,
        "handoff_minute": 0,
    },
    Tier.LOW: {
        "rotation_type": "weekly",
        "rotation_length_seconds": 604800,
        "handoff_hour": 9,
        "handoff_minute": 0,
    },
}


# Support model coverage patterns
SUPPORT_MODEL_DEFAULTS: dict[str, dict[str, Any]] = {
    SupportModel.SELF: {
        "coverage_type": "24x7",
        "sre_backup": False,
        "off_hours_behavior": "page_team",
    },
    SupportModel.SHARED: {
        "coverage_type": "business_hours",
        "sre_backup": True,
        "off_hours_behavior": "page_sre",
        "business_hours_start": 9,
        "business_hours_end": 18,
    },
    SupportModel.SRE: {
        "coverage_type": "24x7",
        "sre_backup": False,
        "off_hours_behavior": "page_sre",
        "team_notified": True,
    },
    SupportModel.BUSINESS_HOURS: {
        "coverage_type": "business_hours",
        "sre_backup": False,
        "off_hours_behavior": "suppress",
        "business_hours_start": 9,
        "business_hours_end": 18,
    },
}


def get_escalation_config(
    tier: str,
    support_model: str = "self",
    team: str = "",
) -> EscalationConfig:
    """
    Get escalation configuration based on tier and support model.

    Args:
        tier: Service tier (critical, high, medium, low)
        support_model: Support model (self, shared, sre, business_hours)
        team: Team name for schedule references

    Returns:
        EscalationConfig with rules and settings
    """
    tier_config = TIER_ESCALATION_DEFAULTS.get(tier, TIER_ESCALATION_DEFAULTS[Tier.MEDIUM])

    rules = []

    # Primary on-call
    rules.append(
        EscalationRule(
            target_type="schedule",
            target_name="primary",
            delay_minutes=tier_config["primary_delay"],
        )
    )

    # Secondary on-call (if configured)
    if tier_config.get("secondary_delay"):
        rules.append(
            EscalationRule(
                target_type="schedule",
                target_name="secondary",
                delay_minutes=tier_config["secondary_delay"],
            )
        )

    # Manager escalation (if configured)
    if tier_config.get("include_manager") and tier_config.get("manager_delay"):
        rules.append(
            EscalationRule(
                target_type="schedule",
                target_name="manager",
                delay_minutes=tier_config["manager_delay"],
            )
        )

    return EscalationConfig(
        rules=rules,
        num_loops=tier_config["num_loops"],
        urgency=tier_config["urgency"],
    )


def get_schedule_config(
    tier: str,
    support_model: str = "self",
    schedule_type: str = "primary",
    timezone: str = "America/New_York",
) -> ScheduleConfig:
    """
    Get schedule configuration based on tier and support model.

    Args:
        tier: Service tier
        support_model: Support model
        schedule_type: Type of schedule (primary, secondary, manager)
        timezone: Timezone for the schedule

    Returns:
        ScheduleConfig with rotation and coverage settings
    """
    tier_config = TIER_SCHEDULE_DEFAULTS.get(tier, TIER_SCHEDULE_DEFAULTS[Tier.MEDIUM])
    support_config = SUPPORT_MODEL_DEFAULTS.get(
        support_model, SUPPORT_MODEL_DEFAULTS[SupportModel.SELF]
    )

    coverage_type = support_config["coverage_type"]
    start_hour = None
    end_hour = None

    if coverage_type == "business_hours":
        start_hour = support_config.get("business_hours_start", 9)
        end_hour = support_config.get("business_hours_end", 18)

    return ScheduleConfig(
        name_suffix=schedule_type,
        rotation_type=tier_config["rotation_type"],
        rotation_length_seconds=tier_config["rotation_length_seconds"],
        handoff_hour=tier_config["handoff_hour"],
        handoff_minute=tier_config["handoff_minute"],
        coverage_type=coverage_type,
        start_hour=start_hour,
        end_hour=end_hour,
    )


def get_schedules_for_tier(tier: str) -> list[str]:
    """
    Get list of schedule types needed for a tier.

    Args:
        tier: Service tier

    Returns:
        List of schedule type suffixes (primary, secondary, manager)
    """
    tier_config = TIER_ESCALATION_DEFAULTS.get(tier, TIER_ESCALATION_DEFAULTS[Tier.MEDIUM])

    schedules = ["primary"]

    if tier_config.get("secondary_delay"):
        schedules.append("secondary")

    if tier_config.get("include_manager"):
        schedules.append("manager")

    return schedules
