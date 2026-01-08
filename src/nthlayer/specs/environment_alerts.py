"""Environment-aware alert filtering.

Different environments get different alert coverage based on their needs.
"""

from typing import List, Optional

from nthlayer.alerts.models import AlertRule

# Alert severity levels to include per environment
ENVIRONMENT_ALERT_SEVERITIES = {
    "dev": ["critical"],  # Only critical alerts in dev
    "staging": ["critical", "warning"],  # Critical + warning in staging
    "prod": ["critical", "warning", "info"],  # All alerts in production
}

# Typical alert distribution by technology (approximate baseline counts)
# Used for estimating alert counts when actual alert generation is not performed
TYPICAL_ALERT_COUNTS = {
    "postgres": {"critical": 8, "warning": 10, "info": 5},
    "postgresql": {"critical": 8, "warning": 10, "info": 5},  # Alias
    "redis": {"critical": 5, "warning": 8, "info": 4},
    "mysql": {"critical": 7, "warning": 9, "info": 4},
    "mongodb": {"critical": 6, "warning": 8, "info": 5},
    "kafka": {"critical": 10, "warning": 12, "info": 6},
    "rabbitmq": {"critical": 6, "warning": 8, "info": 4},
    "elasticsearch": {"critical": 8, "warning": 11, "info": 6},
    "kubernetes": {"critical": 15, "warning": 20, "info": 10},
}
DEFAULT_ALERT_COUNTS = {"critical": 5, "warning": 7, "info": 3}


def filter_alerts_by_environment(
    alerts: List[AlertRule], environment: Optional[str] = None, tier: Optional[str] = None
) -> List[AlertRule]:
    """Filter alerts based on environment and service tier.

    Combines environment-based filtering with tier-based filtering to determine
    which alerts are appropriate for a given deployment context.

    Args:
        alerts: List of alert rules
        environment: Environment name (dev, staging, prod)
        tier: Service tier (critical, standard, low)

    Returns:
        Filtered list of alert rules

    Example:
        >>> alerts = [
        ...     AlertRule(name="db_down", severity="critical"),
        ...     AlertRule(name="db_slow", severity="warning"),
        ...     AlertRule(name="db_cache_miss", severity="info"),
        ... ]
        >>> filtered = filter_alerts_by_environment(alerts, environment="dev")
        >>> len(filtered)  # Only critical alert
        1
        >>> filtered = filter_alerts_by_environment(alerts, environment="prod")
        >>> len(filtered)  # All alerts
        3
    """
    if not alerts:
        return []

    # Default to production (most comprehensive) if not specified
    if not environment:
        environment = "prod"

    env_lower = environment.lower()

    # Normalize environment names
    if env_lower in ["development"]:
        env_lower = "dev"
    elif env_lower in ["stage"]:
        env_lower = "staging"
    elif env_lower in ["production"]:
        env_lower = "prod"

    # Get allowed severities for environment
    allowed_severities = ENVIRONMENT_ALERT_SEVERITIES.get(
        env_lower,
        ENVIRONMENT_ALERT_SEVERITIES["prod"],  # Default to prod (safest)
    )

    # Filter by environment
    filtered = [alert for alert in alerts if alert.severity.lower() in allowed_severities]

    # Further filter by tier if specified
    if tier:
        tier_lower = tier.lower()

        if tier_lower == "critical":
            # Critical services get all alerts (no additional filtering)
            pass
        elif tier_lower == "standard":
            # Standard services get critical + warning only
            filtered = [a for a in filtered if a.severity.lower() in ["critical", "warning"]]
        elif tier_lower == "low":
            # Low tier services get only critical alerts
            filtered = [a for a in filtered if a.severity.lower() == "critical"]

    return filtered


def explain_alert_filtering(environment: Optional[str] = None, tier: Optional[str] = None) -> None:
    """Print explanation of alert filtering rules.

    Args:
        environment: Environment name
        tier: Service tier
    """
    env = environment or "prod"
    env_lower = env.lower()

    if env_lower in ["development"]:
        env_lower = "dev"
    elif env_lower in ["stage"]:
        env_lower = "staging"
    elif env_lower in ["production"]:
        env_lower = "prod"

    allowed_severities = ENVIRONMENT_ALERT_SEVERITIES.get(
        env_lower, ENVIRONMENT_ALERT_SEVERITIES["prod"]
    )

    print("🔍 Alert Filtering Strategy:")
    print(f"   Environment: {env}")
    if tier:
        print(f"   Tier: {tier}")
    print()

    print(f"   Severities included: {', '.join(allowed_severities)}")

    if env_lower == "dev":
        print("   Rationale: Development gets only critical alerts to reduce noise")
    elif env_lower == "staging":
        print("   Rationale: Staging gets critical + warning for pre-prod validation")
    elif env_lower == "prod":
        print("   Rationale: Production gets all alerts for comprehensive coverage")

    if tier:
        tier_lower = tier.lower()
        print()
        print("   Additional tier filtering:")
        if tier_lower == "critical":
            print("   • Critical tier: No additional filtering")
        elif tier_lower == "standard":
            print("   • Standard tier: Only critical + warning")
        elif tier_lower == "low":
            print("   • Low tier: Only critical alerts")

    print()


def get_alert_count_estimate(
    technology: str, environment: Optional[str] = None, tier: Optional[str] = None
) -> dict[str, int]:
    """Estimate alert counts for a technology with filtering applied.

    Args:
        technology: Technology name (postgres, redis, etc.)
        environment: Environment name
        tier: Service tier

    Returns:
        Dictionary with counts: {total, critical, warning, info, filtered}
    """
    # Use module-level constants for alert count estimates
    counts = TYPICAL_ALERT_COUNTS.get(technology, DEFAULT_ALERT_COUNTS)

    total = sum(counts.values())

    # Apply environment filtering
    env_lower = (environment or "prod").lower()
    if env_lower in ["development"]:
        env_lower = "dev"
    elif env_lower in ["stage"]:
        env_lower = "staging"

    allowed = ENVIRONMENT_ALERT_SEVERITIES.get(env_lower, ["critical", "warning", "info"])

    filtered = sum(counts[severity] for severity in allowed if severity in counts)

    # Apply tier filtering
    if tier:
        tier_lower = tier.lower()
        if tier_lower == "standard":
            filtered = counts.get("critical", 0) + counts.get("warning", 0)
        elif tier_lower == "low":
            filtered = counts.get("critical", 0)

    return {
        "total": total,
        "critical": counts.get("critical", 0),
        "warning": counts.get("warning", 0),
        "info": counts.get("info", 0),
        "filtered": filtered,
    }
