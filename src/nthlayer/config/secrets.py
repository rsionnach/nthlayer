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
            logger.warning(
                "failed_to_load_credentials", file=str(self.credentials_file), error=str(e)
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


class VaultSecretBackend(BaseSecretBackend):
    """
    HashiCorp Vault secret backend.
    
    Supports multiple authentication methods:
    - token: Uses VAULT_TOKEN environment variable
    - kubernetes: Uses service account JWT for in-cluster auth
    - aws_iam: Uses AWS IAM credentials for auth
    - approle: Uses AppRole for machine-to-machine auth
    - github: Uses GitHub personal access token
    
    Config in .nthlayer/config.yaml:
        secrets:
          backend: vault
          vault:
            address: https://vault.example.com
            auth_method: kubernetes  # or token, aws_iam, approle
            role: nthlayer-app
            namespace: admin  # Enterprise only
    """
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        try:
            import hvac
        except ImportError as err:
            raise ImportError("hvac package required for Vault backend: pip install hvac") from err
        
        self._client = hvac.Client(
            url=self.config.vault_address,
            namespace=self.config.vault_namespace,
        )
        
        auth_method = self.config.vault_auth_method
        
        if auth_method == "token":
            token = os.environ.get("VAULT_TOKEN")
            if token:
                self._client.token = token
            else:
                logger.warning("vault_token_not_set", hint="Set VAULT_TOKEN env var")
        
        elif auth_method == "kubernetes":
            jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            if os.path.exists(jwt_path):
                with open(jwt_path) as f:
                    jwt = f.read()
                self._client.auth.kubernetes.login(
                    role=self.config.vault_role,
                    jwt=jwt,
                )
            else:
                logger.warning("kubernetes_jwt_not_found", path=jwt_path)
        
        elif auth_method == "aws_iam":
            try:
                import boto3
                session = boto3.Session()
                credentials = session.get_credentials()
                self._client.auth.aws.iam_login(
                    role=self.config.vault_role,
                    access_key=credentials.access_key,
                    secret_key=credentials.secret_key,
                    session_token=credentials.token,
                    region=self.config.aws_region,
                )
            except ImportError as err:
                raise ImportError("boto3 required for AWS IAM auth: pip install boto3") from err
            except Exception as e:
                logger.error("vault_aws_iam_auth_failed", error=str(e))
        
        elif auth_method == "approle":
            role_id = os.environ.get("VAULT_ROLE_ID")
            secret_id = os.environ.get("VAULT_SECRET_ID")
            if role_id and secret_id:
                self._client.auth.approle.login(
                    role_id=role_id,
                    secret_id=secret_id,
                )
            else:
                logger.warning(
                    "vault_approle_creds_missing",
                    hint="Set VAULT_ROLE_ID and VAULT_SECRET_ID env vars"
                )
        
        elif auth_method == "github":
            github_token = os.environ.get("VAULT_GITHUB_TOKEN")
            if github_token:
                self._client.auth.github.login(token=github_token)
            else:
                logger.warning("vault_github_token_missing")
        
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
    """
    AWS Secrets Manager backend.
    
    Uses the default AWS credential chain:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - Shared credentials file (~/.aws/credentials)
    - IAM role (when running on EC2/ECS/Lambda)
    
    Secret path format:
    - "grafana/api_key" -> AWS secret "nthlayer/grafana" with key "api_key"
    - "database/password" -> AWS secret "nthlayer/database" with key "password"
    """
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        try:
            import boto3
        except ImportError as err:
            raise ImportError("boto3 package required for AWS backend: pip install boto3") from err
        
        self._client = boto3.client("secretsmanager", region_name=self.config.aws_region)
        return self._client
    
    def get_secret(self, path: str) -> str | None:
        try:
            import json
            client = self._get_client()
            
            if "/" in path:
                parts = path.rsplit("/", 1)
                secret_id = f"{self.config.aws_secret_prefix}{parts[0]}"
                key = parts[1]
            else:
                secret_id = f"{self.config.aws_secret_prefix}{path}"
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
        """Create or update a secret in AWS Secrets Manager."""
        try:
            import json
            client = self._get_client()
            
            if "/" in path:
                parts = path.rsplit("/", 1)
                secret_id = f"{self.config.aws_secret_prefix}{parts[0]}"
                key = parts[1]
            else:
                secret_id = f"{self.config.aws_secret_prefix}{path}"
                key = "value"
            
            try:
                existing = client.get_secret_value(SecretId=secret_id)
                secret_data = json.loads(existing.get("SecretString", "{}"))
            except client.exceptions.ResourceNotFoundException:
                secret_data = {}
            
            secret_data[key] = value
            
            try:
                client.put_secret_value(
                    SecretId=secret_id,
                    SecretString=json.dumps(secret_data)
                )
            except client.exceptions.ResourceNotFoundException:
                client.create_secret(
                    Name=secret_id,
                    SecretString=json.dumps(secret_data)
                )
            
            return True
        except Exception as e:
            logger.error("aws_set_secret_failed", path=path, error=str(e))
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
    
    def supports_write(self) -> bool:
        return True


class AzureSecretBackend(BaseSecretBackend):
    """
    Azure Key Vault backend.
    
    Uses DefaultAzureCredential for authentication:
    - Environment variables (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)
    - Managed Identity (when running on Azure)
    - Azure CLI credentials
    - Visual Studio Code credentials
    
    Secret path format:
    - "grafana/api-key" -> Key Vault secret "nthlayer-grafana-api-key"
    - "database/password" -> Key Vault secret "nthlayer-database-password"
    
    Note: Azure Key Vault secret names can only contain alphanumeric and hyphens.
    """
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if not self.config.azure_vault_url:
            raise ValueError("Azure vault_url not configured")
        
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError as err:
            raise ImportError(
                "Azure SDK required: pip install azure-identity azure-keyvault-secrets"
            ) from err
        
        credential = DefaultAzureCredential()
        self._client = SecretClient(
            vault_url=self.config.azure_vault_url,
            credential=credential
        )
        return self._client
    
    def _path_to_secret_name(self, path: str) -> str:
        """Convert path to Azure-compatible secret name."""
        return f"nthlayer-{path.replace('/', '-').replace('_', '-')}"
    
    def _secret_name_to_path(self, name: str) -> str:
        """Convert Azure secret name back to path."""
        if name.startswith("nthlayer-"):
            return name[9:].replace("-", "/")
        return name
    
    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            secret = client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            logger.debug("azure_secret_not_found", path=path, error=str(e))
            return None
    
    def set_secret(self, path: str, value: str) -> bool:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            client.set_secret(secret_name, value)
            return True
        except Exception as e:
            logger.error("azure_set_secret_failed", path=path, error=str(e))
            return False
    
    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            secrets = []
            for secret_properties in client.list_properties_of_secrets():
                name = secret_properties.name
                if name.startswith("nthlayer-"):
                    secrets.append(self._secret_name_to_path(name))
            return secrets
        except Exception:
            return []
    
    def supports_write(self) -> bool:
        return True


class GCPSecretBackend(BaseSecretBackend):
    """
    Google Cloud Secret Manager backend.
    
    Uses Application Default Credentials:
    - GOOGLE_APPLICATION_CREDENTIALS environment variable
    - Workload Identity (GKE)
    - Compute Engine default service account
    - gcloud CLI credentials
    
    Secret path format:
    - "grafana/api_key" -> GCP secret "nthlayer-grafana-api-key"
    - "database/password" -> GCP secret "nthlayer-database-password"
    """
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if not self.config.gcp_project_id:
            raise ValueError("GCP project_id not configured")
        
        try:
            from google.cloud import secretmanager
        except ImportError as err:
            raise ImportError(
                "Google Cloud SDK required: pip install google-cloud-secret-manager"
            ) from err
        
        self._client = secretmanager.SecretManagerServiceClient()
        return self._client
    
    def _path_to_secret_name(self, path: str) -> str:
        """Convert path to GCP-compatible secret name."""
        return f"{self.config.gcp_secret_prefix}{path.replace('/', '-').replace('_', '-')}"
    
    def _get_secret_path(self, secret_name: str, version: str = "latest") -> str:
        """Get full GCP secret path."""
        return f"projects/{self.config.gcp_project_id}/secrets/{secret_name}/versions/{version}"
    
    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            secret_path = self._get_secret_path(secret_name)
            
            response = client.access_secret_version(request={"name": secret_path})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logger.debug("gcp_secret_not_found", path=path, error=str(e))
            return None
    
    def set_secret(self, path: str, value: str) -> bool:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            parent = f"projects/{self.config.gcp_project_id}"
            secret_path = f"{parent}/secrets/{secret_name}"
            
            try:
                client.get_secret(request={"name": secret_path})
            except Exception:
                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
            
            client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": value.encode("UTF-8")},
                }
            )
            return True
        except Exception as e:
            logger.error("gcp_set_secret_failed", path=path, error=str(e))
            return False
    
    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            parent = f"projects/{self.config.gcp_project_id}"
            secrets = []
            
            for secret in client.list_secrets(request={"parent": parent}):
                name = secret.name.split("/")[-1]
                if name.startswith(self.config.gcp_secret_prefix):
                    path = name[len(self.config.gcp_secret_prefix):].replace("-", "/")
                    secrets.append(path)
            
            return secrets
        except Exception:
            return []
    
    def supports_write(self) -> bool:
        return True


class DopplerSecretBackend(BaseSecretBackend):
    """
    Doppler secrets backend.
    
    Requires DOPPLER_TOKEN environment variable or token in config.
    
    Secret path format:
    - "GRAFANA_API_KEY" -> Doppler secret "GRAFANA_API_KEY"
    - "grafana/api_key" -> Doppler secret "GRAFANA_API_KEY" (converted)
    """
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._secrets_cache: dict[str, str] | None = None
    
    def _get_token(self) -> str | None:
        return os.environ.get("DOPPLER_TOKEN")
    
    def _path_to_key(self, path: str) -> str:
        """Convert path to Doppler key format (uppercase with underscores)."""
        return path.replace("/", "_").replace("-", "_").upper()
    
    def _fetch_secrets(self) -> dict[str, str]:
        """Fetch all secrets from Doppler."""
        if self._secrets_cache is not None:
            return self._secrets_cache
        
        token = self._get_token()
        if not token:
            logger.warning("doppler_token_not_set")
            return {}
        
        try:
            import httpx
        except ImportError as err:
            raise ImportError("httpx required for Doppler backend") from err
        
        project = self.config.doppler_project or "nthlayer"
        config = self.config.doppler_config or "prd"
        
        try:
            response = httpx.get(
                "https://api.doppler.com/v3/configs/config/secrets/download",
                params={"project": project, "config": config, "format": "json"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
            response.raise_for_status()
            self._secrets_cache = response.json()
            return self._secrets_cache
        except Exception as e:
            logger.error("doppler_fetch_failed", error=str(e))
            return {}
    
    def get_secret(self, path: str) -> str | None:
        secrets = self._fetch_secrets()
        key = self._path_to_key(path)
        return secrets.get(key)
    
    def set_secret(self, path: str, value: str) -> bool:
        token = self._get_token()
        if not token:
            return False
        
        try:
            import httpx
        except ImportError:
            return False
        
        project = self.config.doppler_project or "nthlayer"
        config = self.config.doppler_config or "prd"
        key = self._path_to_key(path)
        
        try:
            response = httpx.post(
                "https://api.doppler.com/v3/configs/config/secrets",
                json={
                    "project": project,
                    "config": config,
                    "secrets": {key: value}
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
            response.raise_for_status()
            self._secrets_cache = None
            return True
        except Exception as e:
            logger.error("doppler_set_failed", error=str(e))
            return False
    
    def list_secrets(self) -> list[str]:
        secrets = self._fetch_secrets()
        return list(secrets.keys())
    
    def supports_write(self) -> bool:
        return True


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
            try:
                self._backends[SecretBackend.VAULT] = VaultSecretBackend(self.config)
            except ImportError:
                logger.debug("vault_backend_unavailable", reason="hvac not installed")
        
        if self.config.aws_region:
            try:
                self._backends[SecretBackend.AWS] = AWSSecretBackend(self.config)
            except ImportError:
                logger.debug("aws_backend_unavailable", reason="boto3 not installed")
        
        if self.config.azure_vault_url:
            try:
                self._backends[SecretBackend.AZURE] = AzureSecretBackend(self.config)
            except ImportError:
                logger.debug("azure_backend_unavailable", reason="azure-identity not installed")
        
        if self.config.gcp_project_id:
            try:
                self._backends[SecretBackend.GCP] = GCPSecretBackend(self.config)
            except ImportError:
                logger.debug(
                    "gcp_backend_unavailable", reason="google-cloud-secret-manager not installed"
                )
        
        if os.environ.get("DOPPLER_TOKEN") or self.config.doppler_project:
            try:
                self._backends[SecretBackend.DOPPLER] = DopplerSecretBackend(self.config)
            except ImportError:
                logger.debug("doppler_backend_unavailable", reason="httpx not installed")
    
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
