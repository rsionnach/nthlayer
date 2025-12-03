"""Multi-environment support for NthLayer.

Allows defining base service configurations with environment-specific overrides
for dev, staging, production, etc.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


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
        """
        base_dir = base_file.parent
        service_name = base_file.stem  # payment-api.yaml → payment-api
        
        # Search paths (service-specific files take precedence over shared)
        candidates = [
            base_dir / "environments" / f"{service_name}-{environment}.yaml",  # Most specific
            base_dir / "environments" / f"{environment}.yaml",                  # Shared
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
        base_file: Path,
        environment: Optional[str] = None
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
