"""
Configuration file loading and merging.

Search order:
1. Explicit path (--config flag)
2. .nthlayer/config.yaml (project root)
3. ~/.nthlayer/config.yaml (user home)
4. Default configuration
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from nthlayer.config.integrations import IntegrationConfig
from nthlayer.config.secrets import SecretBackend, SecretConfig

logger = structlog.get_logger()


def get_config_path(explicit_path: str | Path | None = None) -> Path | None:
    """
    Find the configuration file to use.
    
    Search order:
    1. Explicit path if provided
    2. .nthlayer/config.yaml in current directory
    3. ~/.nthlayer/config.yaml in home directory
    
    Returns:
        Path to config file or None if not found
    """
    if explicit_path:
        path = Path(explicit_path)
        if path.exists():
            return path
        return None
    
    cwd_config = Path.cwd() / ".nthlayer" / "config.yaml"
    if cwd_config.exists():
        return cwd_config
    
    home_config = Path.home() / ".nthlayer" / "config.yaml"
    if home_config.exists():
        return home_config
    
    return None


def get_credentials_path() -> Path:
    """Get the credentials file path."""
    return Path.home() / ".nthlayer" / "credentials.yaml"


class ConfigLoader:
    """
    Loads and merges configuration from multiple sources.
    """
    
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or get_config_path()
        self.credentials_path = get_credentials_path()
    
    def load(self) -> IntegrationConfig:
        """Load configuration from file or return defaults."""
        if self.config_path and self.config_path.exists():
            return self._load_from_file(self.config_path)
        return IntegrationConfig.default()
    
    def load_secrets_config(self) -> SecretConfig:
        """Load secrets configuration."""
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = yaml.safe_load(f) or {}
                return self._parse_secrets_config(data.get("secrets", {}))
            except Exception as e:
                logger.warning("failed_to_load_secrets_config", error=str(e))
        
        return SecretConfig()
    
    def _load_from_file(self, path: Path) -> IntegrationConfig:
        """Load config from YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            
            logger.debug("loaded_config", path=str(path))
            return IntegrationConfig.from_dict(data)
        except Exception as e:
            logger.warning("failed_to_load_config", path=str(path), error=str(e))
            return IntegrationConfig.default()
    
    def _parse_secrets_config(self, data: dict[str, Any]) -> SecretConfig:
        """Parse secrets section of config."""
        backend_str = data.get("backend", "env")
        try:
            backend = SecretBackend(backend_str)
        except ValueError:
            backend = SecretBackend.ENV
        
        fallback = []
        for fb in data.get("fallback", ["env", "file"]):
            try:
                fallback.append(SecretBackend(fb))
            except ValueError:
                pass
        
        return SecretConfig(
            backend=backend,
            fallback=fallback,
            vault_address=data.get("vault", {}).get("address"),
            vault_namespace=data.get("vault", {}).get("namespace"),
            vault_auth_method=data.get("vault", {}).get("auth_method", "token"),
            vault_role=data.get("vault", {}).get("role"),
            vault_path_prefix=data.get("vault", {}).get("path_prefix", "secret/data/nthlayer"),
            aws_region=data.get("aws", {}).get("region", "us-east-1"),
            aws_secret_prefix=data.get("aws", {}).get("secret_prefix", "nthlayer/"),
            azure_vault_url=data.get("azure", {}).get("vault_url"),
            gcp_project_id=data.get("gcp", {}).get("project_id"),
            gcp_secret_prefix=data.get("gcp", {}).get("secret_prefix", "nthlayer-"),
            doppler_project=data.get("doppler", {}).get("project"),
            doppler_config=data.get("doppler", {}).get("config"),
            credentials_file=Path(data.get("credentials_file", str(self.credentials_path))),
        )
    
    def save(self, config: IntegrationConfig, path: Path | None = None):
        """Save configuration to file."""
        target_path = path or self.config_path or (Path.home() / ".nthlayer" / "config.yaml")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target_path, "w") as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
        
        logger.info("saved_config", path=str(target_path))


def load_config(path: str | Path | None = None) -> IntegrationConfig:
    """
    Convenience function to load configuration.
    
    Args:
        path: Optional explicit config file path
    
    Returns:
        IntegrationConfig instance
    """
    config_path = Path(path) if path else get_config_path()
    loader = ConfigLoader(config_path)
    return loader.load()


def load_secrets_config(path: str | Path | None = None) -> SecretConfig:
    """
    Convenience function to load secrets configuration.
    
    Args:
        path: Optional explicit config file path
    
    Returns:
        SecretConfig instance
    """
    config_path = Path(path) if path else get_config_path()
    loader = ConfigLoader(config_path)
    return loader.load_secrets_config()


def save_config(config: IntegrationConfig, path: str | Path | None = None):
    """
    Convenience function to save configuration.
    
    Args:
        config: Configuration to save
        path: Optional target file path
    """
    loader = ConfigLoader()
    loader.save(config, Path(path) if path else None)
