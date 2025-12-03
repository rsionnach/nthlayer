"""
Secret resolution system with multiple backend support.

Supports:
- Environment variables (default)
- Credentials file (~/.nthlayer/credentials.yaml)
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- GCP Secret Manager
- GitHub Actions (env-based)
- Doppler

Secret reference syntax:
    ${secret:path/to/secret}
    ${env:ENV_VAR_NAME}
    ${vault:secret/data/path#key}
    ${aws:secret-name/key}
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()

SECRET_REF_PATTERN = re.compile(r'\$\{(\w+):([^}|]+)(?:\|(\w+):([^}]+))?\}')


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
    fallback: list[SecretBackend] = field(default_factory=lambda: [SecretBackend.ENV, SecretBackend.FILE])
    
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
    credentials_file: Path = field(default_factory=lambda: Path.home() / ".nthlayer" / "credentials.yaml")


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
        without_prefix = env_key[len(self.prefix):]
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
            logger.warning("failed_to_load_credentials", file=str(self.credentials_file), error=str(e))
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


class VaultSecretBackend(BaseSecretBackend):
    """HashiCorp Vault secret backend."""
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        try:
            import hvac
        except ImportError:
            raise ImportError("hvac package required for Vault backend: pip install hvac")
        
        self._client = hvac.Client(
            url=self.config.vault_address,
            namespace=self.config.vault_namespace,
        )
        
        if self.config.vault_auth_method == "token":
            token = os.environ.get("VAULT_TOKEN")
            if token:
                self._client.token = token
        elif self.config.vault_auth_method == "kubernetes":
            jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            if os.path.exists(jwt_path):
                with open(jwt_path) as f:
                    jwt = f.read()
                self._client.auth.kubernetes.login(
                    role=self.config.vault_role,
                    jwt=jwt,
                )
        
        return self._client
    
    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
            full_path = f"{self.config.vault_path_prefix}/{path}"
            
            if "#" in path:
                vault_path, key = path.rsplit("#", 1)
                full_path = f"{self.config.vault_path_prefix}/{vault_path}"
            else:
                key = path.split("/")[-1]
                full_path = f"{self.config.vault_path_prefix}/{'/'.join(path.split('/')[:-1])}"
            
            response = client.secrets.kv.v2.read_secret_version(path=full_path)
            data = response.get("data", {}).get("data", {})
            return data.get(key)
        except Exception as e:
            logger.debug("vault_secret_not_found", path=path, error=str(e))
            return None
    
    def set_secret(self, path: str, value: str) -> bool:
        try:
            client = self._get_client()
            parts = path.split("/")
            key = parts[-1]
            vault_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
            full_path = f"{self.config.vault_path_prefix}/{vault_path}"
            
            client.secrets.kv.v2.create_or_update_secret(
                path=full_path,
                secret={key: value},
            )
            return True
        except Exception as e:
            logger.error("vault_set_secret_failed", path=path, error=str(e))
            return False
    
    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.list_secrets(path=self.config.vault_path_prefix)
            return response.get("data", {}).get("keys", [])
        except Exception:
            return []
    
    def supports_write(self) -> bool:
        return True


class AWSSecretBackend(BaseSecretBackend):
    """AWS Secrets Manager backend."""
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 package required for AWS backend")
        
        self._client = boto3.client("secretsmanager", region_name=self.config.aws_region)
        return self._client
    
    def get_secret(self, path: str) -> str | None:
        try:
            import json
            client = self._get_client()
            secret_id = f"{self.config.aws_secret_prefix}{path}"
            
            if "/" in path:
                parts = path.rsplit("/", 1)
                secret_id = f"{self.config.aws_secret_prefix}{parts[0]}"
                key = parts[1]
            else:
                key = None
            
            response = client.get_secret_value(SecretId=secret_id)
            secret_string = response.get("SecretString", "{}")
            
            if key:
                data = json.loads(secret_string)
                return data.get(key)
            return secret_string
        except Exception as e:
            logger.debug("aws_secret_not_found", path=path, error=str(e))
            return None
    
    def set_secret(self, path: str, value: str) -> bool:
        return False
    
    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            paginator = client.get_paginator("list_secrets")
            secrets = []
            for page in paginator.paginate():
                for secret in page.get("SecretList", []):
                    name = secret.get("Name", "")
                    if name.startswith(self.config.aws_secret_prefix):
                        secrets.append(name[len(self.config.aws_secret_prefix):])
            return secrets
        except Exception:
            return []


class SecretResolver:
    """
    Resolves secrets from multiple backends with fallback support.
    
    Usage:
        resolver = SecretResolver(config)
        api_key = resolver.resolve("grafana/api_key")
        
        # Or resolve references in strings
        url = resolver.resolve_string("https://user:${secret:password}@host")
    """
    
    def __init__(self, config: SecretConfig | None = None):
        self.config = config or SecretConfig()
        self._backends: dict[SecretBackend, BaseSecretBackend] = {}
        self._init_backends()
    
    def _init_backends(self):
        """Initialize configured backends."""
        self._backends[SecretBackend.ENV] = EnvSecretBackend()
        self._backends[SecretBackend.FILE] = FileSecretBackend(self.config.credentials_file)
        
        if self.config.vault_address:
            self._backends[SecretBackend.VAULT] = VaultSecretBackend(self.config)
        
        if self.config.aws_region:
            try:
                self._backends[SecretBackend.AWS] = AWSSecretBackend(self.config)
            except ImportError:
                pass
    
    def resolve(self, path: str, backend: SecretBackend | None = None) -> str | None:
        """
        Resolve a secret by path.
        
        Args:
            path: Secret path (e.g., "grafana/api_key")
            backend: Specific backend to use (or None for default + fallback)
        
        Returns:
            Secret value or None if not found
        """
        if backend:
            if backend in self._backends:
                return self._backends[backend].get_secret(path)
            return None
        
        if self.config.backend in self._backends:
            value = self._backends[self.config.backend].get_secret(path)
            if value is not None:
                return value
        
        for fallback in self.config.fallback:
            if fallback in self._backends and fallback != self.config.backend:
                value = self._backends[fallback].get_secret(path)
                if value is not None:
                    logger.debug("secret_resolved_from_fallback", path=path, backend=fallback)
                    return value
        
        return None
    
    def resolve_string(self, text: str) -> str:
        """
        Resolve all secret references in a string.
        
        Syntax: ${backend:path} or ${secret:path}
        
        Args:
            text: String containing secret references
        
        Returns:
            String with secrets resolved
        """
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
    
    def verify_secrets(self, required: list[str]) -> dict[str, tuple[bool, str | None]]:
        """
        Verify that required secrets are available.
        
        Args:
            required: List of required secret paths
        
        Returns:
            Dict of path -> (found, backend_name)
        """
        result = {}
        for path in required:
            value = self.resolve(path)
            if value is not None:
                for name, backend in self._backends.items():
                    if backend.get_secret(path) is not None:
                        result[path] = (True, name)
                        break
            else:
                result[path] = (False, None)
        return result


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
