"""Auto-detection of environment from CI/CD context.

Detects the current environment based on environment variables,
git branches, or other context clues.
"""

import os
from typing import Optional


def _extract_env_from_namespace(namespace: str) -> Optional[str]:
    """Extract environment from Kubernetes namespace.
    
    Examples:
        payments-dev -> dev
        search-prod -> prod
        staging-payments -> staging
    """
    if not namespace:
        return None
    
    for env in ["dev", "development", "staging", "stage", "prod", "production"]:
        if env in namespace.lower():
            if "dev" in env.lower():
                return "dev"
            elif "stag" in env.lower():
                return "staging"
            elif "prod" in env.lower():
                return "prod"
    
    return None


def _extract_env_from_cluster(cluster: str) -> Optional[str]:
    """Extract environment from cluster name.
    
    Examples:
        my-app-dev-cluster -> dev
        production-cluster -> prod
    """
    if not cluster:
        return None
    
    cluster_lower = cluster.lower()
    
    if "dev" in cluster_lower:
        return "dev"
    elif "stag" in cluster_lower:
        return "staging"
    elif "prod" in cluster_lower:
        return "prod"
    
    return None


def _extract_env_from_branch(branch: str) -> Optional[str]:
    """Extract environment from git branch name.
    
    Examples:
        develop -> dev
        main -> prod
        master -> prod
        staging -> staging
        release/staging -> staging
    """
    if not branch:
        return None
    
    branch_lower = branch.lower()
    
    # Remove common prefixes
    for prefix in ["refs/heads/", "origin/"]:
        if branch_lower.startswith(prefix):
            branch_lower = branch_lower[len(prefix):]
    
    # Direct mappings
    if branch_lower in ["develop", "dev", "development"]:
        return "dev"
    elif branch_lower in ["main", "master"]:
        return "prod"
    elif branch_lower in ["staging", "stage"]:
        return "staging"
    
    # Check for keywords in branch name
    if "dev" in branch_lower:
        return "dev"
    elif "stag" in branch_lower:
        return "staging"
    elif "prod" in branch_lower:
        return "prod"
    
    return None


# Common environment variable names used by CI/CD systems
ENV_VAR_MAPPINGS = {
    # Direct environment specification
    "NTHLAYER_ENV": lambda v: v,
    "NTHLAYER_ENVIRONMENT": lambda v: v,
    "ENVIRONMENT": lambda v: v,
    "ENV": lambda v: v,
    "DEPLOY_ENV": lambda v: v,
    
    # Kubernetes
    "K8S_NAMESPACE": _extract_env_from_namespace,
    "NAMESPACE": _extract_env_from_namespace,
    
    # AWS
    "AWS_ENV": lambda v: v,
    "ECS_CLUSTER": _extract_env_from_cluster,
    
    # CI/CD specific
    "GITHUB_REF_NAME": _extract_env_from_branch,
    "CI_COMMIT_BRANCH": _extract_env_from_branch,  # GitLab
    "CIRCLE_BRANCH": _extract_env_from_branch,     # CircleCI
    "BRANCH_NAME": _extract_env_from_branch,       # Jenkins
    
    # Deployment tools
    "ARGOCD_ENV_ENV": lambda v: v,
    "FLUX_ENV": lambda v: v,
}


def detect_environment() -> Optional[str]:
    """Auto-detect current environment from context.
    
    Checks environment variables, git context, and other signals
    to determine the current deployment environment.
    
    Returns:
        Detected environment name (dev, staging, prod) or None
        
    Example:
        >>> os.environ["NTHLAYER_ENV"] = "dev"
        >>> detect_environment()
        'dev'
        
        >>> os.environ["K8S_NAMESPACE"] = "payments-prod"
        >>> detect_environment()
        'prod'
    """
    # Check each environment variable in priority order
    for var_name, extractor in ENV_VAR_MAPPINGS.items():
        value = os.environ.get(var_name)
        if value:
            try:
                env = extractor(value)
                if env:
                    return env
            except Exception:
                # Skip invalid extractors
                continue
    
    return None


def get_environment(
    explicit_env: Optional[str] = None,
    auto_detect: bool = True
) -> Optional[str]:
    """Get environment with optional auto-detection.
    
    Priority:
    1. Explicit environment parameter (--env flag)
    2. Auto-detected from context (if enabled)
    3. None (use base configuration)
    
    Args:
        explicit_env: Explicitly specified environment
        auto_detect: Whether to auto-detect if not explicit
        
    Returns:
        Environment name or None
        
    Example:
        >>> get_environment(explicit_env="prod")
        'prod'
        
        >>> os.environ["NTHLAYER_ENV"] = "staging"
        >>> get_environment(auto_detect=True)
        'staging'
    """
    # Explicit takes precedence
    if explicit_env:
        return explicit_env
    
    # Auto-detect if enabled
    if auto_detect:
        return detect_environment()
    
    return None


def print_environment_detection_info(environment: Optional[str], source: str = "unknown"):
    """Print information about detected environment.
    
    Args:
        environment: Detected environment name
        source: Source of detection (flag, auto, etc.)
    """
    if environment:
        print(f"🌍 Environment: {environment} (source: {source})")
    else:
        print("📋 Environment: none (using base configuration)")
