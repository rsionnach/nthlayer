"""Multi-environment support for NthLayer.

Allows defining base service configurations with environment-specific overrides
for dev, staging, production, etc.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Valid environment names: alphanumeric with optional hyphens, no path traversal
VALID_ENVIRONMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$")


def validate_environment_name(environment: str) -> str:
    """Validate and sanitize environment name to prevent path traversal.

    Args:
        environment: Environment name to validate

    Returns:
        Normalized lowercase environment name

    Raises:
        ValueError: If environment name is invalid or contains path traversal
    """
    if not environment:
        raise ValueError("Environment name cannot be empty")

    env_lower = environment.lower().strip()

    # Check for path traversal attempts
    if ".." in env_lower or "/" in env_lower or "\\" in env_lower:
        raise ValueError(f"Invalid environment name (path traversal attempt): {environment}")

    # Validate format: alphanumeric with optional hyphens
    if not VALID_ENVIRONMENT_PATTERN.match(env_lower):
        raise ValueError(
            f"Invalid environment name format: {environment}. "
            "Must be alphanumeric with optional hyphens (e.g., 'dev', 'staging', 'prod-us')."
        )

    return env_lower


@dataclass
class EnvironmentOverride:
    """Environment-specific configuration overrides.

    Represents overrides for a specific environment (dev, staging, prod, etc.)
    that are merged with the base service configuration.
    """

    environment: str  # dev | staging | production | etc.
    service_overrides: Dict[str, Any] = field(default_factory=dict)
    resource_overrides: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """Validate environment name."""
        if not self.environment:
            raise ValueError("Environment name is required")

        # Normalize environment name
        self.environment = self.environment.lower().strip()


@dataclass
class EnvironmentConfig:
    """Complete environment configuration including base + overrides."""

    base_file: Path
    environment: Optional[str] = None
    environment_file: Optional[Path] = None
    overrides: Optional[EnvironmentOverride] = None


class EnvironmentLoader:
    """Loads environment configuration files."""

    @staticmethod
    def find_environment_file(base_file: Path, environment: str) -> Optional[Path]:
        """Find environment override file for a service.

        Search order (most specific wins):
        1. {service_dir}/environments/{service}-{env}.yaml (service-specific)
        2. {service_dir}/environments/{env}.yaml (shared)
        3. .nthlayer/environments/{service}-{env}.yaml (monorepo service-specific)

        Args:
            base_file: Path to base service YAML
            environment: Environment name (dev, staging, prod)

        Returns:
            Path to environment file if found, None otherwise

        Raises:
            ValueError: If environment name is invalid or contains path traversal
        """
        # Validate environment name to prevent path traversal attacks
        environment = validate_environment_name(environment)

        base_dir = base_file.parent
        service_name = base_file.stem  # payment-api.yaml → payment-api

        # Search paths (service-specific files take precedence over shared)
        candidates = [
            base_dir / "environments" / f"{service_name}-{environment}.yaml",  # Most specific
            base_dir / "environments" / f"{environment}.yaml",  # Shared
            base_dir / ".nthlayer" / "environments" / f"{service_name}-{environment}.yaml",
        ]

        # Find first existing file
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    @staticmethod
    def load_environment_override(env_file: Path) -> EnvironmentOverride:
        """Load environment override from YAML file.

        Args:
            env_file: Path to environment YAML file

        Returns:
            EnvironmentOverride object

        Raises:
            ValueError: If environment file is invalid
        """
        with open(env_file) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Environment file must be a YAML dictionary: {env_file}")

        if "environment" not in data:
            raise ValueError(f"Missing 'environment' field in {env_file}")

        return EnvironmentOverride(
            environment=data["environment"],
            service_overrides=data.get("service", {}),
            resource_overrides=data.get("resources", []),
        )

    @staticmethod
    def load_with_environment(
        base_file: Path, environment: Optional[str] = None
    ) -> EnvironmentConfig:
        """Load service configuration with optional environment overrides.

        Args:
            base_file: Path to base service YAML
            environment: Environment name (dev, staging, prod) or None for base only

        Returns:
            EnvironmentConfig with base and optional environment data
        """
        config = EnvironmentConfig(base_file=base_file, environment=environment)

        if environment:
            env_file = EnvironmentLoader.find_environment_file(base_file, environment)
            if env_file:
                config.environment_file = env_file
                config.overrides = EnvironmentLoader.load_environment_override(env_file)

        return config


# Standard environment names
STANDARD_ENVIRONMENTS = ["dev", "development", "staging", "stage", "prod", "production"]


def normalize_environment_name(env: str) -> str:
    """Normalize environment name to standard form.

    Args:
        env: Environment name

    Returns:
        Normalized name (dev, staging, prod)
    """
    env_lower = env.lower().strip()

    # Normalize to standard names
    if env_lower in ["dev", "development"]:
        return "dev"
    elif env_lower in ["stage", "staging"]:
        return "staging"
    elif env_lower in ["prod", "production"]:
        return "prod"
    else:
        # Keep as-is for custom environments
        return env_lower
