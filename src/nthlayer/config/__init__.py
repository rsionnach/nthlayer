"""
NthLayer Configuration System.

Provides unified configuration management with:
- Pydantic-based settings (environment variables, .env files)
- Multi-backend secrets resolution (env, file, Vault, AWS, etc.)
- Integration profiles for different environments
- Per-project and user-level config files
"""

# Re-export Settings for backward compatibility
from nthlayer.config.settings import Settings, get_settings, settings

from nthlayer.config.secrets import (
    SecretResolver,
    SecretBackend,
    resolve_secret,
    get_secret_resolver,
)
from nthlayer.config.integrations import (
    IntegrationConfig,
    PrometheusConfig,
    GrafanaConfig,
    PagerDutyConfig,
    SlackConfig,
    get_integration_config,
)
from nthlayer.config.loader import (
    ConfigLoader,
    load_config,
    get_config_path,
)

__all__ = [
    # Settings (backward compat)
    "Settings",
    "get_settings",
    "settings",
    # Secrets
    "SecretResolver",
    "SecretBackend",
    "resolve_secret",
    "get_secret_resolver",
    # Integrations
    "IntegrationConfig",
    "PrometheusConfig",
    "GrafanaConfig",
    "PagerDutyConfig",
    "SlackConfig",
    "get_integration_config",
    # Loader
    "ConfigLoader",
    "load_config",
    "get_config_path",
]
