"""
PagerDuty integration module.

Provides tier-based escalation policies, schedules, and event orchestration
for intelligent alert routing.
"""

from nthlayer.pagerduty.defaults import (
    SUPPORT_MODEL_DEFAULTS,
    TIER_ESCALATION_DEFAULTS,
    TIER_SCHEDULE_DEFAULTS,
    get_escalation_config,
    get_schedule_config,
)
from nthlayer.pagerduty.naming import (
    get_escalation_policy_name,
    get_schedule_name,
    get_service_name,
    get_team_name,
)
from nthlayer.pagerduty.orchestration import EventOrchestrationManager
from nthlayer.pagerduty.resources import PagerDutyResourceManager

__all__ = [
    "TIER_ESCALATION_DEFAULTS",
    "TIER_SCHEDULE_DEFAULTS",
    "SUPPORT_MODEL_DEFAULTS",
    "get_escalation_config",
    "get_schedule_config",
    "get_team_name",
    "get_escalation_policy_name",
    "get_schedule_name",
    "get_service_name",
    "PagerDutyResourceManager",
    "EventOrchestrationManager",
]
