"""
Secret resolution system with pluggable backend support.

Core backends (always available):
- Environment variables (default)
- Credentials file (~/.nthlayer/credentials.yaml)

Optional backends (loaded on demand):
- HashiCorp Vault (requires hvac)
- AWS Secrets Manager (requires boto3)
- Azure Key Vault (requires azure-identity)
- GCP Secret Manager (requires google-cloud-secret-manager)
- Doppler (requires httpx)
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()

SECRET_REF_PATTERN = re.compile(r"\$\{(\w+):([^}|]+)(?:\|(\w+):([^}]+))?\}")


class SecretBackend(StrEnum):
    """Supported secret backends."""

    ENV = "env"
    FILE = "file"
    VAULT = "vault"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    GITHUB = "github"
    DOPPLER = "doppler"


@dataclass
class SecretConfig:
    """Configuration for secrets resolution."""

    backend: SecretBackend = SecretBackend.ENV
    fallback: list[SecretBackend] = field(
        default_factory=lambda: [SecretBackend.ENV, SecretBackend.FILE]
    )

    # Vault config
    vault_address: str | None = None
    vault_namespace: str | None = None
    vault_auth_method: str = "token"
    vault_role: str | None = None
    vault_path_prefix: str = "secret/data/nthlayer"

    # AWS config
    aws_region: str = "us-east-1"
    aws_secret_prefix: str = "nthlayer/"

    # Azure config
    azure_vault_url: str | None = None

    # GCP config
    gcp_project_id: str | None = None
    gcp_secret_prefix: str = "nthlayer-"

    # Doppler config
    doppler_project: str | None = None
    doppler_config: str | None = None

    # File config
    credentials_file: Path = field(
        default_factory=lambda: Path.home() / ".nthlayer" / "credentials.yaml"
    )


class BaseSecretBackend(ABC):
    """Base class for secret backends."""

    @abstractmethod
    def get_secret(self, path: str) -> str | None:
        """Get a secret by path."""
        pass

    @abstractmethod
    def set_secret(self, path: str, value: str) -> bool:
        """Set a secret (if supported)."""
        pass

    @abstractmethod
    def list_secrets(self) -> list[str]:
        """List available secrets."""
        pass

    def supports_write(self) -> bool:
        """Whether this backend supports writing secrets."""
        return False


class EnvSecretBackend(BaseSecretBackend):
    """Environment variable secret backend."""

    def __init__(self, prefix: str = "NTHLAYER_"):
        self.prefix = prefix

    def get_secret(self, path: str) -> str | None:
        env_key = self._path_to_env(path)
        return os.environ.get(env_key)

    def set_secret(self, path: str, value: str) -> bool:
        return False

    def list_secrets(self) -> list[str]:
        secrets = []
        for key in os.environ:
            if key.startswith(self.prefix):
                path = self._env_to_path(key)
                secrets.append(path)
        return secrets

    def _path_to_env(self, path: str) -> str:
        """Convert secret path to environment variable name."""
        normalized = path.replace("/", "_").replace("-", "_").upper()
        return f"{self.prefix}{normalized}"

    def _env_to_path(self, env_key: str) -> str:
        """Convert environment variable name to secret path."""
        without_prefix = env_key[len(self.prefix) :]
        return without_prefix.lower().replace("_", "/")


class FileSecretBackend(BaseSecretBackend):
    """File-based secret backend using credentials.yaml."""

    def __init__(self, credentials_file: Path):
        self.credentials_file = credentials_file
        self._cache: dict[str, Any] | None = None

    def _load_credentials(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache

        if not self.credentials_file.exists():
            self._cache = {}
            return self._cache

        try:
            with open(self.credentials_file) as f:
                self._cache = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(
                "failed_to_load_credentials",
                file=str(self.credentials_file),
                error=str(e),
            )
            self._cache = {}

        return self._cache

    def get_secret(self, path: str) -> str | None:
        data = self._load_credentials()
        parts = path.split("/")

        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return str(current) if current is not None else None

    def set_secret(self, path: str, value: str) -> bool:
        data = self._load_credentials()
        parts = path.split("/")

        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.credentials_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        os.chmod(self.credentials_file, 0o600)
        self._cache = data
        return True

    def list_secrets(self) -> list[str]:
        data = self._load_credentials()
        return self._flatten_keys(data)

    def _flatten_keys(self, data: dict, prefix: str = "") -> list[str]:
        keys = []
        for k, v in data.items():
            path = f"{prefix}/{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(self._flatten_keys(v, path))
            else:
                keys.append(path)
        return keys

    def supports_write(self) -> bool:
        return True


def _load_cloud_backend(
    backend_type: SecretBackend, config: SecretConfig
) -> BaseSecretBackend | None:
    """Lazy-load a cloud backend. Returns None if dependencies not available."""
    try:
        if backend_type == SecretBackend.VAULT:
            from nthlayer.config.secrets.backends import VaultSecretBackend

            return VaultSecretBackend(config)
        elif backend_type == SecretBackend.AWS:
            from nthlayer.config.secrets.backends import AWSSecretBackend

            return AWSSecretBackend(config)
        elif backend_type == SecretBackend.AZURE:
            from nthlayer.config.secrets.backends import AzureSecretBackend

            return AzureSecretBackend(config)
        elif backend_type == SecretBackend.GCP:
            from nthlayer.config.secrets.backends import GCPSecretBackend

            return GCPSecretBackend(config)
        elif backend_type == SecretBackend.DOPPLER:
            from nthlayer.config.secrets.backends import DopplerSecretBackend

            return DopplerSecretBackend(config)
    except ImportError as e:
        logger.debug(f"{backend_type}_backend_unavailable", reason=str(e))
    return None


class SecretResolver:
    """Resolves secrets from multiple backends with fallback support."""

    def __init__(self, config: SecretConfig | None = None):
        self.config = config or SecretConfig()
        self._backends: dict[SecretBackend, BaseSecretBackend] = {}
        self._init_backends()

    def _init_backends(self):
        """Initialize configured backends."""
        # Core backends - always available
        self._backends[SecretBackend.ENV] = EnvSecretBackend()
        self._backends[SecretBackend.FILE] = FileSecretBackend(self.config.credentials_file)

        # Cloud backends - lazy loaded on demand
        if self.config.vault_address:
            backend = _load_cloud_backend(SecretBackend.VAULT, self.config)
            if backend:
                self._backends[SecretBackend.VAULT] = backend

        if self.config.aws_region and self.config.aws_secret_prefix:
            backend = _load_cloud_backend(SecretBackend.AWS, self.config)
            if backend:
                self._backends[SecretBackend.AWS] = backend

        if self.config.azure_vault_url:
            backend = _load_cloud_backend(SecretBackend.AZURE, self.config)
            if backend:
                self._backends[SecretBackend.AZURE] = backend

        if self.config.gcp_project_id:
            backend = _load_cloud_backend(SecretBackend.GCP, self.config)
            if backend:
                self._backends[SecretBackend.GCP] = backend

        if os.environ.get("DOPPLER_TOKEN") or self.config.doppler_project:
            backend = _load_cloud_backend(SecretBackend.DOPPLER, self.config)
            if backend:
                self._backends[SecretBackend.DOPPLER] = backend

    def resolve(self, path: str, backend: SecretBackend | None = None) -> str | None:
        """Resolve a secret by path."""
        if backend:
            if backend in self._backends:
                return self._backends[backend].get_secret(path)
            return None

        # Try primary backend
        if self.config.backend in self._backends:
            value = self._backends[self.config.backend].get_secret(path)
            if value is not None:
                return value

        # Try fallbacks
        for fallback in self.config.fallback:
            if fallback in self._backends and fallback != self.config.backend:
                value = self._backends[fallback].get_secret(path)
                if value is not None:
                    logger.debug("secret_resolved_from_fallback", path=path, backend=fallback)
                    return value

        return None

    def resolve_string(self, text: str) -> str:
        """Resolve all secret references in a string."""

        def replace_match(match):
            backend_name = match.group(1)
            path = match.group(2)
            fallback_type = match.group(3)
            fallback_value = match.group(4)

            if backend_name == "secret":
                value = self.resolve(path)
            else:
                try:
                    backend = SecretBackend(backend_name)
                    value = self.resolve(path, backend)
                except ValueError:
                    return match.group(0)

            if value is None and fallback_type:
                if fallback_type == "default":
                    value = fallback_value
                elif fallback_type == "env":
                    value = os.environ.get(fallback_value)

            return value if value is not None else match.group(0)

        return SECRET_REF_PATTERN.sub(replace_match, text)

    def set_secret(self, path: str, value: str, backend: SecretBackend | None = None) -> bool:
        """Set a secret in the specified or default backend."""
        target = backend or self.config.backend

        if target in self._backends:
            b = self._backends[target]
            if b.supports_write():
                return b.set_secret(path, value)

        # Fallback to file backend for writes
        if SecretBackend.FILE in self._backends:
            return self._backends[SecretBackend.FILE].set_secret(path, value)

        return False

    def list_secrets(self) -> dict[str, list[str]]:
        """List all available secrets by backend."""
        result = {}
        for name, backend in self._backends.items():
            secrets = backend.list_secrets()
            if secrets:
                result[name] = secrets
        return result

    def verify_secrets(self, paths: list[str]) -> dict[str, tuple[bool, str | None]]:
        """Verify that secrets exist and return their resolution status.

        Returns:
            Dict mapping path to (found, backend_name) tuple
        """
        results = {}
        for path in paths:
            found = False
            backend_name = None

            # Try primary backend first
            if self.config.backend in self._backends:
                value = self._backends[self.config.backend].get_secret(path)
                if value is not None:
                    found = True
                    backend_name = self.config.backend.value

            # Try fallbacks if not found
            if not found:
                for fallback in self.config.fallback:
                    if fallback in self._backends:
                        value = self._backends[fallback].get_secret(path)
                        if value is not None:
                            found = True
                            backend_name = fallback.value
                            break

            results[path] = (found, backend_name)

        return results


_resolver: SecretResolver | None = None


def get_secret_resolver(config: SecretConfig | None = None) -> SecretResolver:
    """Get or create the global secret resolver."""
    global _resolver
    if _resolver is None or config is not None:
        _resolver = SecretResolver(config)
    return _resolver


def resolve_secret(path: str, backend: SecretBackend | None = None) -> str | None:
    """Convenience function to resolve a single secret."""
    return get_secret_resolver().resolve(path, backend)


__all__ = [
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
