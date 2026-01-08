"""
Cloud secret backends - lazy loaded when needed.

These backends require additional dependencies:
- VaultSecretBackend: hvac
- AWSSecretBackend: boto3
- AzureSecretBackend: azure-identity, azure-keyvault-secrets
- GCPSecretBackend: google-cloud-secret-manager
- DopplerSecretBackend: httpx
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog

from nthlayer.config.secrets import BaseSecretBackend, _sanitize_path

if TYPE_CHECKING:
    from nthlayer.config.secrets import SecretConfig

logger = structlog.get_logger()


def _sanitize_error(exc: Exception) -> str:
    """Sanitize error message to avoid leaking sensitive details."""
    return type(exc).__name__


class VaultSecretBackend(BaseSecretBackend):
    """HashiCorp Vault secret backend."""

    def __init__(self, config: "SecretConfig"):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        import hvac

        self._client = hvac.Client(
            url=self.config.vault_address,
            namespace=self.config.vault_namespace,
        )

        auth_method = self.config.vault_auth_method

        if auth_method == "token":
            token = os.environ.get("VAULT_TOKEN")
            if token:
                self._client.token = token
        elif auth_method == "kubernetes":
            jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            if os.path.exists(jwt_path):
                with open(jwt_path) as f:
                    jwt = f.read()
                self._client.auth.kubernetes.login(role=self.config.vault_role, jwt=jwt)
        elif auth_method == "approle":
            role_id = os.environ.get("VAULT_ROLE_ID")
            secret_id = os.environ.get("VAULT_SECRET_ID")
            if role_id and secret_id:
                self._client.auth.approle.login(role_id=role_id, secret_id=secret_id)

        return self._client

    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
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
            logger.debug(
                "vault_secret_not_found", path=_sanitize_path(path), error=_sanitize_error(e)
            )
            return None

    def set_secret(self, path: str, value: str) -> bool:
        try:
            client = self._get_client()
            parts = path.split("/")
            key = parts[-1]
            vault_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
            full_path = f"{self.config.vault_path_prefix}/{vault_path}"
            client.secrets.kv.v2.create_or_update_secret(path=full_path, secret={key: value})
            return True
        except Exception as e:
            logger.error("vault_set_secret_failed", error=_sanitize_error(e))
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

    def __init__(self, config: "SecretConfig"):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        import boto3

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
            logger.debug(
                "aws_secret_not_found", path=_sanitize_path(path), error=_sanitize_error(e)
            )
            return None

    def set_secret(self, path: str, value: str) -> bool:
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
                client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(secret_data))
            except client.exceptions.ResourceNotFoundException:
                client.create_secret(Name=secret_id, SecretString=json.dumps(secret_data))
            return True
        except Exception as e:
            logger.error("aws_set_secret_failed", error=_sanitize_error(e))
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
                        secrets.append(name[len(self.config.aws_secret_prefix) :])
            return secrets
        except Exception:
            return []

    def supports_write(self) -> bool:
        return True


class AzureSecretBackend(BaseSecretBackend):
    """Azure Key Vault backend."""

    def __init__(self, config: "SecretConfig"):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        credential = DefaultAzureCredential()
        self._client = SecretClient(vault_url=self.config.azure_vault_url, credential=credential)
        return self._client

    def _path_to_secret_name(self, path: str) -> str:
        return f"nthlayer-{path.replace('/', '-').replace('_', '-')}"

    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            secret = client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            logger.debug(
                "azure_secret_not_found", path=_sanitize_path(path), error=_sanitize_error(e)
            )
            return None

    def set_secret(self, path: str, value: str) -> bool:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            client.set_secret(secret_name, value)
            return True
        except Exception as e:
            logger.error("azure_set_secret_failed", error=_sanitize_error(e))
            return False

    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            secrets = []
            for props in client.list_properties_of_secrets():
                name = props.name
                if name.startswith("nthlayer-"):
                    secrets.append(name[9:].replace("-", "/"))
            return secrets
        except Exception:
            return []

    def supports_write(self) -> bool:
        return True


class GCPSecretBackend(BaseSecretBackend):
    """Google Cloud Secret Manager backend."""

    def __init__(self, config: "SecretConfig"):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        from google.cloud import secretmanager

        self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def _path_to_secret_name(self, path: str) -> str:
        return f"{self.config.gcp_secret_prefix}{path.replace('/', '-').replace('_', '-')}"

    def get_secret(self, path: str) -> str | None:
        try:
            client = self._get_client()
            secret_name = self._path_to_secret_name(path)
            secret_path = (
                f"projects/{self.config.gcp_project_id}/secrets/{secret_name}/versions/latest"
            )
            response = client.access_secret_version(request={"name": secret_path})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logger.debug(
                "gcp_secret_not_found", path=_sanitize_path(path), error=_sanitize_error(e)
            )
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
            logger.error("gcp_set_secret_failed", error=_sanitize_error(e))
            return False

    def list_secrets(self) -> list[str]:
        try:
            client = self._get_client()
            parent = f"projects/{self.config.gcp_project_id}"
            secrets = []
            for secret in client.list_secrets(request={"parent": parent}):
                name = secret.name.split("/")[-1]
                if name.startswith(self.config.gcp_secret_prefix):
                    path = name[len(self.config.gcp_secret_prefix) :].replace("-", "/")
                    secrets.append(path)
            return secrets
        except Exception:
            return []

    def supports_write(self) -> bool:
        return True


class DopplerSecretBackend(BaseSecretBackend):
    """Doppler secrets backend."""

    def __init__(self, config: "SecretConfig"):
        self.config = config
        self._secrets_cache: dict[str, str] | None = None

    def _get_token(self) -> str | None:
        return os.environ.get("DOPPLER_TOKEN")

    def _path_to_key(self, path: str) -> str:
        return path.replace("/", "_").replace("-", "_").upper()

    def _fetch_secrets(self) -> dict[str, str]:
        if self._secrets_cache is not None:
            return self._secrets_cache

        token = self._get_token()
        if not token:
            return {}

        import httpx

        project = self.config.doppler_project or "nthlayer"
        config = self.config.doppler_config or "prd"

        try:
            response = httpx.get(
                "https://api.doppler.com/v3/configs/config/secrets/download",
                params={"project": project, "config": config, "format": "json"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            self._secrets_cache = response.json()
            return self._secrets_cache
        except Exception as e:
            logger.error("doppler_fetch_failed", error=_sanitize_error(e))
            return {}

    def get_secret(self, path: str) -> str | None:
        secrets = self._fetch_secrets()
        key = self._path_to_key(path)
        return secrets.get(key)

    def set_secret(self, path: str, value: str) -> bool:
        token = self._get_token()
        if not token:
            return False

        import httpx

        project = self.config.doppler_project or "nthlayer"
        config = self.config.doppler_config or "prd"
        key = self._path_to_key(path)

        try:
            response = httpx.post(
                "https://api.doppler.com/v3/configs/config/secrets",
                json={"project": project, "config": config, "secrets": {key: value}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            self._secrets_cache = None
            return True
        except Exception as e:
            logger.error("doppler_set_failed", error=_sanitize_error(e))
            return False

    def list_secrets(self) -> list[str]:
        secrets = self._fetch_secrets()
        return list(secrets.keys())

    def supports_write(self) -> bool:
        return True


__all__ = [
    "VaultSecretBackend",
    "AWSSecretBackend",
    "AzureSecretBackend",
    "GCPSecretBackend",
    "DopplerSecretBackend",
]
