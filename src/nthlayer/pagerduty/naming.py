"""
Naming conventions for PagerDuty resources.

All resources use team-prefixed naming for consistency and discoverability.
"""

from __future__ import annotations


def sanitize_name(name: str) -> str:
    """
    Sanitize a name for PagerDuty.

    PagerDuty allows most characters, but we normalize for consistency.

    Args:
        name: Raw name

    Returns:
        Sanitized name
    """
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def get_team_name(team: str) -> str:
    """
    Get PagerDuty team name.

    Args:
        team: Team identifier

    Returns:
        Team name for PagerDuty
    """
    return sanitize_name(team)


def get_escalation_policy_name(team: str, suffix: str = "escalation") -> str:
    """
    Get escalation policy name.

    Pattern: {team}-{suffix}
    Example: payments-escalation

    Args:
        team: Team identifier
        suffix: Policy suffix (default: "escalation")

    Returns:
        Escalation policy name
    """
    return f"{sanitize_name(team)}-{suffix}"


def get_schedule_name(team: str, schedule_type: str) -> str:
    """
    Get schedule name.

    Pattern: {team}-{schedule_type}
    Examples:
        - payments-primary
        - payments-secondary
        - payments-manager

    Args:
        team: Team identifier
        schedule_type: Type of schedule (primary, secondary, manager)

    Returns:
        Schedule name
    """
    return f"{sanitize_name(team)}-{schedule_type}"


def get_service_name(service: str) -> str:
    """
    Get PagerDuty service name.

    Args:
        service: Service identifier

    Returns:
        Service name for PagerDuty
    """
    return sanitize_name(service)


def get_sre_escalation_policy_name() -> str:
    """
    Get the central SRE escalation policy name.

    Returns:
        SRE escalation policy name
    """
    return "sre-escalation"


def get_sre_schedule_name(schedule_type: str) -> str:
    """
    Get SRE schedule name.

    Args:
        schedule_type: Type of schedule (primary, secondary)

    Returns:
        SRE schedule name
    """
    return f"sre-{schedule_type}"


def parse_resource_name(name: str) -> dict[str, str]:
    """
    Parse a PagerDuty resource name to extract team and type.

    Args:
        name: Resource name (e.g., "payments-escalation")

    Returns:
        Dict with team and type
    """
    parts = name.rsplit("-", 1)
    if len(parts) == 2:
        return {"team": parts[0], "type": parts[1]}
    return {"team": name, "type": ""}
