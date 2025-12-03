"""Environment-aware deployment gate thresholds.

Provides different error budget thresholds based on environment.
"""

from typing import Dict, Optional

# Default thresholds by environment
DEFAULT_ENVIRONMENT_THRESHOLDS = {
    "dev": {
        "critical": {"block": 0.50, "warn": 0.70},    # Very lenient for dev
        "standard": {"block": 0.60, "warn": 0.80},
        "low": {"warn": 0.90},
    },
    "staging": {
        "critical": {"block": 0.20, "warn": 0.40},    # Production-like
        "standard": {"block": 0.30, "warn": 0.50},
        "low": {"warn": 0.60},
    },
    "prod": {
        "critical": {"block": 0.10, "warn": 0.20},    # Strictest
        "standard": {"block": 0.20, "warn": 0.40},
        "low": {"warn": 0.50},
    },
}


def get_deployment_gate_thresholds(
    tier: str,
    environment: Optional[str] = None
) -> Dict[str, float]:
    """Get deployment gate thresholds for tier and environment.
    
    Args:
        tier: Service tier (critical, standard, low)
        environment: Environment name (dev, staging, prod)
        
    Returns:
        Dictionary with 'block' and/or 'warn' thresholds
        
    Example:
        >>> get_deployment_gate_thresholds("critical", "prod")
        {'block': 0.10, 'warn': 0.20}
        
        >>> get_deployment_gate_thresholds("critical", "dev")
        {'block': 0.50, 'warn': 0.70}
    """
    # Normalize inputs
    tier_lower = tier.lower()
    
    # Default production thresholds if no environment specified
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
    
    # Get thresholds for environment
    env_thresholds = DEFAULT_ENVIRONMENT_THRESHOLDS.get(env_lower)
    
    if not env_thresholds:
        # Unknown environment, use production thresholds (safest)
        env_thresholds = DEFAULT_ENVIRONMENT_THRESHOLDS["prod"]
    
    # Get tier-specific thresholds
    tier_thresholds = env_thresholds.get(tier_lower)
    
    if not tier_thresholds:
        # Unknown tier, use critical thresholds (safest)
        tier_thresholds = env_thresholds.get("critical", {"block": 0.10, "warn": 0.20})
    
    return tier_thresholds


def explain_thresholds(tier: str, environment: Optional[str] = None) -> None:
    """Print explanation of deployment gate thresholds.
    
    Args:
        tier: Service tier
        environment: Environment name
    """
    thresholds = get_deployment_gate_thresholds(tier, environment)
    env_display = environment or "prod (default)"
    
    print("📊 Deployment Gate Thresholds:")
    print(f"   Environment: {env_display}")
    print(f"   Tier: {tier}")
    print()
    
    if "block" in thresholds:
        print(f"   🔴 Block: >{thresholds['block']*100:.0f}% budget consumed")
        print("      Deploy will be blocked")
    
    if "warn" in thresholds:
        print(f"   🟡 Warn: >{thresholds['warn']*100:.0f}% budget consumed")
        print("      Deploy allowed but with warning")
    
    print(f"   ✅ Pass: <{thresholds.get('warn', thresholds.get('block', 1.0))*100:.0f}% budget consumed")
    print()


def should_block_deployment(
    budget_consumed_pct: float,
    tier: str,
    environment: Optional[str] = None
) -> tuple[bool, str]:
    """Determine if deployment should be blocked based on error budget.
    
    Args:
        budget_consumed_pct: Percentage of error budget consumed (0.0 to 1.0)
        tier: Service tier
        environment: Environment name
        
    Returns:
        Tuple of (should_block, reason)
        
    Example:
        >>> should_block_deployment(0.15, "critical", "prod")
        (True, "15.0% budget consumed exceeds block threshold (10%)")
        
        >>> should_block_deployment(0.15, "critical", "dev")
        (False, "15.0% budget consumed is within limits")
    """
    thresholds = get_deployment_gate_thresholds(tier, environment)
    
    # Check block threshold
    if "block" in thresholds and budget_consumed_pct > thresholds["block"]:
        return (
            True,
            f"{budget_consumed_pct*100:.1f}% budget consumed exceeds "
            f"block threshold ({thresholds['block']*100:.0f}%)"
        )
    
    # Check warn threshold
    if "warn" in thresholds and budget_consumed_pct > thresholds["warn"]:
        return (
            False,
            f"{budget_consumed_pct*100:.1f}% budget consumed exceeds "
            f"warn threshold ({thresholds['warn']*100:.0f}%)"
        )
    
    return (False, f"{budget_consumed_pct*100:.1f}% budget consumed is within limits")
