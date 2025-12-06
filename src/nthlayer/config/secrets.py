"""
Backwards-compatible re-export of secrets module.

The secrets functionality has been refactored into:
- nthlayer.config.secrets/ (package) - Core classes and resolver
- nthlayer.config.secrets/backends.py - Cloud backends (lazy loaded)

This module re-exports everything for backwards compatibility.
"""

# Re-export all public APIs
from nthlayer.config.secrets import (
    SECRET_REF_PATTERN,
    BaseSecretBackend,
    EnvSecretBackend,
    FileSecretBackend,
    SecretBackend,
    SecretConfig,
    SecretResolver,
    get_secret_resolver,
    resolve_secret,
)


# Lazy imports for cloud backends (only loaded when accessed)
def __getattr__(name: str):
    """Lazy load cloud backends to avoid import errors when deps not installed."""
    cloud_backends = {
        "VaultSecretBackend",
        "AWSSecretBackend",
        "AzureSecretBackend",
        "GCPSecretBackend",
        "DopplerSecretBackend",
    }
    if name in cloud_backends:
        from nthlayer.config.secrets import backends

        return getattr(backends, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core
    "SecretBackend",
    "SecretConfig",
    "BaseSecretBackend",
    "EnvSecretBackend",
    "FileSecretBackend",
    "SecretResolver",
    "get_secret_resolver",
    "resolve_secret",
    "SECRET_REF_PATTERN",
]
# Cloud backends available via __getattr__: VaultSecretBackend, AWSSecretBackend,
# AzureSecretBackend, GCPSecretBackend, DopplerSecretBackend
