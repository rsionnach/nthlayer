"""
Configuration file loading and merging.

Search order:
1. Explicit path (--config flag)
2. .nthlayer/config.yaml (project root)
3. ~/.nthlayer/config.yaml (user home)
4. Default configuration
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog
import yaml

from nthlayer.config.integrations import IntegrationConfig
from nthlayer.config.secrets import SecretBackend, SecretConfig

logger = structlog.get_logger()

# Valid environment name pattern: alphanumeric, dash, underscore
VALID_ENV_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""

    pass


class PathTraversalError(ValueError):
    """Raised when a path contains traversal sequences."""

    pass


def validate_url(url: str, field_name: str = "url") -> str:
    """Validate that a string is a valid HTTP/HTTPS URL.

    Args:
        url: URL string to validate
        field_name: Name of the field for error messages

    Returns:
        The validated URL

    Raises:
        ConfigValidationError: If URL is invalid
    """
    if not url:
        raise ConfigValidationError(f"{field_name} cannot be empty")

    try:
        result = urlparse(url)
        if result.scheme not in ("http", "https"):
            raise ConfigValidationError(
                f"{field_name} must use http or https scheme, got: {result.scheme!r}"
            )
        if not result.netloc:
            raise ConfigValidationError(f"{field_name} must have a host: {url!r}")
        return url
    except Exception as e:
        if isinstance(e, ConfigValidationError):
            raise
        raise ConfigValidationError(f"{field_name} is not a valid URL: {url!r}") from e


def validate_environment_name(env: str, field_name: str = "environment") -> str:
    """Validate that an environment name is valid.

    Valid names: start with letter, contain only alphanumeric, dash, underscore.

    Args:
        env: Environment name to validate
        field_name: Name of the field for error messages

    Returns:
        The validated environment name

    Raises:
        ConfigValidationError: If environment name is invalid
    """
    if not env:
        raise ConfigValidationError(f"{field_name} cannot be empty")

    if not VALID_ENV_NAME_PATTERN.match(env):
        raise ConfigValidationError(
            f"{field_name} must start with a letter and contain only "
            f"alphanumeric characters, dashes, or underscores: {env!r}"
        )

    # Check max length
    if len(env) > 64:
        raise ConfigValidationError(f"{field_name} must be 64 characters or less")

    return env


def _validate_path_safe(path: Path, allowed_roots: list[Path] | None = None) -> Path:
    """
    Validate a path is safe and doesn't contain traversal attacks.

    Args:
        path: Path to validate
        allowed_roots: Optional list of allowed root directories. If None,
                      only checks for traversal sequences.

    Returns:
        Resolved absolute path

    Raises:
        PathTraversalError: If path contains unsafe sequences or escapes allowed roots
    """
    # Check for explicit traversal sequences in the original path string
    path_str = str(path)
    if ".." in path_str:
        raise PathTraversalError(f"Path contains traversal sequence: {path_str}")

    # Resolve to absolute path
    resolved = path.resolve()

    # If allowed_roots specified, ensure path is within one of them
    if allowed_roots:
        for root in allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                return resolved
            except ValueError:
                continue
        raise PathTraversalError("Path escapes allowed directories")

    return resolved


def get_config_path(explicit_path: str | Path | None = None) -> Path | None:
    """
    Find the configuration file to use.

    Search order:
    1. Explicit path if provided
    2. .nthlayer/config.yaml in current directory
    3. ~/.nthlayer/config.yaml in home directory

    Returns:
        Path to config file or None if not found

    Raises:
        PathTraversalError: If explicit path contains traversal sequences
    """
    if explicit_path:
        path = Path(explicit_path)
        # Validate path doesn't contain traversal sequences
        _validate_path_safe(path)
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

        # Validate credentials_file path if provided
        credentials_file_str = data.get("credentials_file")
        if credentials_file_str:
            credentials_file = Path(credentials_file_str)
            # Validate path - only allow within home directory
            _validate_path_safe(credentials_file, allowed_roots=[Path.home()])
        else:
            credentials_file = self.credentials_path

        return SecretConfig(
            backend=backend,
            fallback=fallback,
            strict=data.get("strict", False),
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
            credentials_file=credentials_file,
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
