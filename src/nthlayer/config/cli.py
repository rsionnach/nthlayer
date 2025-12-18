"""
CLI commands for configuration and secrets management.

Commands:
    nthlayer config show          - Show current configuration
    nthlayer config set KEY VALUE - Set a configuration value
    nthlayer config init          - Interactive setup wizard
    nthlayer secrets list         - List available secrets
    nthlayer secrets verify       - Verify required secrets exist
    nthlayer secrets set PATH     - Set a secret
"""

from __future__ import annotations

import getpass
from pathlib import Path

from nthlayer.config.integrations import (
    GrafanaProfile,
    GrafanaType,
    IntegrationConfig,
    PrometheusProfile,
    PrometheusType,
)
from nthlayer.config.loader import (
    get_config_path,
    load_config,
    save_config,
)
from nthlayer.config.secrets import (
    SecretBackend,
    get_secret_resolver,
)

REQUIRED_SECRETS = [
    "grafana/api_key",
    "prometheus/password",
    "pagerduty/api_key",
    "slack/webhook_url",
]


def config_show_command(reveal_secrets: bool = False) -> int:
    """Show current configuration."""
    config_path = get_config_path()
    
    print("=" * 60)
    print("  NthLayer Configuration")
    print("=" * 60)
    print()
    
    if config_path:
        print(f"Config file: {config_path}")
    else:
        print("Config file: (using defaults)")
    print()
    
    config = load_config()
    
    print("Prometheus:")
    print(f"  Default profile: {config.prometheus.default}")
    for name, profile in config.prometheus.profiles.items():
        marker = " *" if name == config.prometheus.default else ""
        print(f"  [{name}]{marker}")
        print(f"    Type: {profile.type}")
        print(f"    URL: {profile.url}")
        if profile.username:
            print(f"    Username: {profile.username}")
        if profile.password_secret:
            if reveal_secrets:
                password = profile.get_password()
                masked = f"{password[:4]}...{password[-4:]}" if password else "(not set)"
                print(f"    Password: {masked}")
            else:
                print("    Password: ****")
    print()
    
    print("Grafana:")
    print(f"  Default profile: {config.grafana.default}")
    for name, grafana_profile in config.grafana.profiles.items():
        marker = " *" if name == config.grafana.default else ""
        print(f"  [{name}]{marker}")
        print(f"    Type: {grafana_profile.type}")
        print(f"    URL: {grafana_profile.url}")
        print(f"    Org ID: {grafana_profile.org_id}")
        if grafana_profile.api_key_secret:
            if reveal_secrets:
                key = grafana_profile.get_api_key()
                if key:
                    print(f"    API Key: {key[:8]}...{key[-4:]}")
                else:
                    print("    API Key: (not set)")
            else:
                print("    API Key: ****")
    print()
    
    print("Alerting:")
    print(f"  PagerDuty: {'enabled' if config.alerting.pagerduty.enabled else 'disabled'}")
    if config.alerting.pagerduty.enabled:
        policy = config.alerting.pagerduty.default_escalation_policy or "(not set)"
        print(f"    Escalation Policy: {policy}")
    print(f"  Slack: {'enabled' if config.alerting.slack.enabled else 'disabled'}")
    if config.alerting.slack.enabled:
        print(f"    Default Channel: {config.alerting.slack.default_channel}")
    print(f"  Datadog: {'enabled' if config.alerting.datadog.enabled else 'disabled'}")
    
    return 0


def config_set_command(key: str, value: str | None = None, secret: bool = False) -> int:
    """Set a configuration value."""
    config = load_config()
    
    parts = key.split(".")
    
    if secret and value is None:
        value = getpass.getpass(f"Enter value for {key}: ")
    
    if len(parts) < 2:
        print(f"Invalid key format: {key}")
        print("Use: section.key (e.g., grafana.url, prometheus.default)")
        return 1
    
    section = parts[0]
    subkey = ".".join(parts[1:])
    
    if section == "prometheus":
        _set_prometheus_config(config, subkey, value)
    elif section == "grafana":
        _set_grafana_config(config, subkey, value)
    elif section == "alerting":
        _set_alerting_config(config, subkey, value)
    else:
        print(f"Unknown section: {section}")
        return 1
    
    save_config(config)
    print(f"Updated {key}")
    return 0


def _set_prometheus_config(config: IntegrationConfig, key: str, value: str | None):
    if key == "default":
        config.prometheus.default = value or "local"
    elif key.startswith("profiles."):
        parts = key.split(".", 2)
        profile_name = parts[1]
        if profile_name not in config.prometheus.profiles:
            config.prometheus.profiles[profile_name] = PrometheusProfile(name=profile_name)
        profile = config.prometheus.profiles[profile_name]
        
        if len(parts) > 2:
            field = parts[2]
            if field == "url":
                profile.url = value or ""
            elif field == "type":
                profile.type = PrometheusType(value) if value else PrometheusType.PROMETHEUS
            elif field == "username":
                profile.username = value
            elif field == "password":
                profile.password_secret = value


def _set_grafana_config(config: IntegrationConfig, key: str, value: str | None):
    if key == "default":
        config.grafana.default = value or "local"
    elif key.startswith("profiles."):
        parts = key.split(".", 2)
        profile_name = parts[1]
        if profile_name not in config.grafana.profiles:
            config.grafana.profiles[profile_name] = GrafanaProfile(name=profile_name)
        profile = config.grafana.profiles[profile_name]
        
        if len(parts) > 2:
            field = parts[2]
            if field == "url":
                profile.url = value or ""
            elif field == "type":
                profile.type = GrafanaType(value) if value else GrafanaType.GRAFANA
            elif field == "api_key":
                profile.api_key_secret = value
            elif field == "org_id":
                profile.org_id = int(value) if value else 1


def _set_alerting_config(config: IntegrationConfig, key: str, value: str | None):
    if key.startswith("pagerduty."):
        field = key.split(".", 1)[1]
        if field == "enabled":
            enabled = value.lower() in ("true", "1", "yes") if value else False
            config.alerting.pagerduty.enabled = enabled
        elif field == "api_key":
            config.alerting.pagerduty.api_key_secret = value
        elif field == "escalation_policy":
            config.alerting.pagerduty.default_escalation_policy = value
    elif key.startswith("slack."):
        field = key.split(".", 1)[1]
        if field == "enabled":
            enabled = value.lower() in ("true", "1", "yes") if value else False
            config.alerting.slack.enabled = enabled
        elif field == "webhook_url":
            config.alerting.slack.webhook_url_secret = value
        elif field == "channel":
            config.alerting.slack.default_channel = value or "#alerts"


def config_init_command() -> int:
    """Interactive configuration wizard."""
    print("=" * 60)
    print("  NthLayer Configuration Wizard")
    print("=" * 60)
    print()
    
    config = IntegrationConfig.default()
    
    print("Secrets Backend Configuration")
    print("-" * 40)
    print("Available backends:")
    print("  1. env     - Environment variables (NTHLAYER_*)")
    print("  2. file    - Credentials file (~/.nthlayer/credentials.yaml)")
    print("  3. vault   - HashiCorp Vault")
    print("  4. aws     - AWS Secrets Manager")
    print("  5. azure   - Azure Key Vault")
    print("  6. gcp     - Google Cloud Secret Manager")
    print("  7. doppler - Doppler")
    print()
    
    backend_choice = input("Primary secrets backend [1-7] (1): ").strip() or "1"
    backend_map = {
        "1": "env", "env": "env",
        "2": "file", "file": "file",
        "3": "vault", "vault": "vault",
        "4": "aws", "aws": "aws",
        "5": "azure", "azure": "azure",
        "6": "gcp", "gcp": "gcp",
        "7": "doppler", "doppler": "doppler",
    }
    selected_backend = backend_map.get(backend_choice, "env")
    print(f"Using backend: {selected_backend}")
    
    if selected_backend == "vault":
        vault_addr = input("Vault address (https://vault.example.com): ").strip()
        vault_auth = input("Auth method [token/kubernetes/aws_iam/approle] (token): ").strip()
        vault_auth = vault_auth or "token"
        _vault_role = input("Vault role (optional): ").strip() or None  # noqa: F841
        print(f"Vault configured: {vault_addr} ({vault_auth} auth)")
    elif selected_backend == "aws":
        aws_region = input("AWS region (us-east-1): ").strip() or "us-east-1"
        print(f"AWS Secrets Manager configured in {aws_region}")
    elif selected_backend == "azure":
        azure_vault_url = input("Azure Key Vault URL: ").strip()
        print(f"Azure Key Vault configured: {azure_vault_url}")
    elif selected_backend == "gcp":
        gcp_project = input("GCP project ID: ").strip()
        print(f"GCP Secret Manager configured for project: {gcp_project}")
    elif selected_backend == "doppler":
        doppler_project = input("Doppler project (nthlayer): ").strip() or "nthlayer"
        doppler_config = input("Doppler config (prd): ").strip() or "prd"
        print(f"Doppler configured: {doppler_project}/{doppler_config}")
    
    print()
    
    print("Grafana Configuration")
    print("-" * 40)
    grafana_type = input("Grafana type [grafana/grafana-cloud] (grafana): ").strip()
    grafana_type = grafana_type or "grafana"
    grafana_url = input("Grafana URL (http://localhost:3000): ").strip()
    grafana_url = grafana_url or "http://localhost:3000"
    
    profile = GrafanaProfile(
        name="default",
        type=(
            GrafanaType(grafana_type)
            if grafana_type in ("grafana", "grafana-cloud")
            else GrafanaType.GRAFANA
        ),
        url=grafana_url,
    )
    
    if input("Configure API key? [y/N]: ").strip().lower() == "y":
        api_key = getpass.getpass("API Key: ")
        resolver = get_secret_resolver()
        resolver.set_secret("grafana/api_key", api_key)
        profile.api_key_secret = "grafana/api_key"
        print("API key stored")
    
    config.grafana.profiles["default"] = profile
    config.grafana.default = "default"
    print()
    
    print("Prometheus Configuration")
    print("-" * 40)
    prom_type = input("Prometheus type [prometheus/mimir/grafana-cloud] (prometheus): ").strip()
    prom_type = prom_type or "prometheus"
    prom_url = input("Prometheus URL (http://localhost:9090): ").strip()
    prom_url = prom_url or "http://localhost:9090"
    
    prom_profile = PrometheusProfile(
        name="default",
        type=(
            PrometheusType(prom_type)
            if prom_type in ("prometheus", "mimir", "grafana-cloud")
            else PrometheusType.PROMETHEUS
        ),
        url=prom_url,
    )
    
    config.prometheus.profiles["default"] = prom_profile
    config.prometheus.default = "default"
    print()
    
    print("Alerting Configuration")
    print("-" * 40)
    
    if input("Configure PagerDuty? [y/N]: ").strip().lower() == "y":
        config.alerting.pagerduty.enabled = True
        policy = input("Default escalation policy: ").strip()
        if policy:
            config.alerting.pagerduty.default_escalation_policy = policy
        
        if input("Configure API key? [y/N]: ").strip().lower() == "y":
            api_key = getpass.getpass("PagerDuty API Key: ")
            resolver = get_secret_resolver()
            resolver.set_secret("pagerduty/api_key", api_key)
            config.alerting.pagerduty.api_key_secret = "pagerduty/api_key"
    
    if input("Configure Slack? [y/N]: ").strip().lower() == "y":
        config.alerting.slack.enabled = True
        channel = input("Default channel (#alerts): ").strip() or "#alerts"
        config.alerting.slack.default_channel = channel
        
        if input("Configure webhook URL? [y/N]: ").strip().lower() == "y":
            webhook = getpass.getpass("Slack Webhook URL: ")
            resolver = get_secret_resolver()
            resolver.set_secret("slack/webhook_url", webhook)
            config.alerting.slack.webhook_url_secret = "slack/webhook_url"
    
    print()
    
    config_path = Path.home() / ".nthlayer" / "config.yaml"
    save_config(config, config_path)
    
    print("=" * 60)
    print(f"Configuration saved to: {config_path}")
    print()
    print("Next steps:")
    print("  1. Run 'nthlayer config show' to verify")
    print("  2. Run 'nthlayer secrets verify' to check secrets")
    print("  3. Run 'nthlayer apply <service>.yaml' to generate configs")
    
    return 0


def secrets_list_command() -> int:
    """List available secrets."""
    resolver = get_secret_resolver()
    secrets_by_backend = resolver.list_secrets()
    
    print("=" * 60)
    print("  Available Secrets")
    print("=" * 60)
    print()
    
    if not secrets_by_backend:
        print("No secrets found.")
        print()
        print("To add secrets:")
        print("  nthlayer secrets set grafana/api_key")
        print("  Or set environment variables: NTHLAYER_GRAFANA_API_KEY")
        return 0
    
    for backend, secrets in secrets_by_backend.items():
        print(f"[{backend}]")
        for secret in secrets:
            print(f"  {secret}")
        print()
    
    return 0


def secrets_verify_command(secrets: list[str] | None = None) -> int:
    """Verify required secrets exist."""
    required = secrets or REQUIRED_SECRETS
    resolver = get_secret_resolver()
    
    print("=" * 60)
    print("  Secret Verification")
    print("=" * 60)
    print()
    
    results = resolver.verify_secrets(required)
    
    all_found = True
    for path, (found, backend) in results.items():
        if found:
            print(f"  {path}: found ({backend})")
        else:
            print(f"  {path}: NOT FOUND")
            all_found = False
    
    print()
    
    if all_found:
        print("All required secrets are available.")
        return 0
    else:
        print("Some secrets are missing. Set them with:")
        print("  nthlayer secrets set <path>")
        print("  Or set environment variables: NTHLAYER_<PATH>")
        return 1


def secrets_set_command(path: str, value: str | None = None, backend: str | None = None) -> int:
    """Set a secret."""
    if value is None:
        value = getpass.getpass(f"Enter secret value for {path}: ")
    
    resolver = get_secret_resolver()
    
    target_backend = None
    if backend:
        try:
            target_backend = SecretBackend(backend)
        except ValueError:
            print(f"Unknown backend: {backend}")
            return 1
    
    success = resolver.set_secret(path, value, target_backend)
    
    if success:
        print(f"Secret stored: {path}")
        return 0
    else:
        print(f"Failed to store secret: {path}")
        print("Ensure the backend supports writing (file, vault)")
        return 1


def secrets_get_command(path: str, reveal: bool = False) -> int:
    """Get a secret value."""
    resolver = get_secret_resolver()
    value = resolver.resolve(path)
    
    if value is None:
        print(f"Secret not found: {path}")
        return 1
    
    if reveal:
        print(value)
    else:
        masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
        print(f"{path}: {masked}")
    
    return 0


def secrets_migrate_command(
    source: str,
    target: str,
    secrets: list[str] | None = None,
    dry_run: bool = False
) -> int:
    """
    Migrate secrets between backends.
    
    Examples:
        nthlayer secrets migrate env vault
        nthlayer secrets migrate file aws --secrets grafana/api_key pagerduty/token
        nthlayer secrets migrate env vault --dry-run
    """
    print("=" * 60)
    print("  Secrets Migration")
    print("=" * 60)
    print()
    
    try:
        source_backend = SecretBackend(source)
        target_backend = SecretBackend(target)
    except ValueError as e:
        print(f"Invalid backend: {e}")
        print(f"Valid backends: {', '.join(b.value for b in SecretBackend)}")
        return 1
    
    resolver = get_secret_resolver()
    
    if source_backend not in resolver._backends:
        print(f"Source backend not available: {source}")
        print("Check your configuration and ensure required packages are installed.")
        return 1
    
    if target_backend not in resolver._backends:
        print(f"Target backend not available: {target}")
        print("Check your configuration and ensure required packages are installed.")
        return 1
    
    target_backend_impl = resolver._backends[target_backend]
    if not target_backend_impl.supports_write():
        print(f"Target backend does not support writing: {target}")
        return 1
    
    source_backend_impl = resolver._backends[source_backend]
    
    if secrets:
        secrets_to_migrate = secrets
    else:
        secrets_to_migrate = source_backend_impl.list_secrets()
    
    if not secrets_to_migrate:
        print(f"No secrets found in {source} backend")
        return 0
    
    print(f"Source: {source}")
    print(f"Target: {target}")
    print(f"Secrets to migrate: {len(secrets_to_migrate)}")
    print()
    
    if dry_run:
        print("[DRY RUN] Would migrate:")
        for secret_path in secrets_to_migrate:
            value = source_backend_impl.get_secret(secret_path)
            status = "found" if value else "NOT FOUND"
            print(f"  {secret_path} ({status})")
        return 0
    
    migrated = 0
    failed = 0
    
    for secret_path in secrets_to_migrate:
        value = source_backend_impl.get_secret(secret_path)
        if value is None:
            print(f"  SKIP {secret_path} (not found in source)")
            continue
        
        success = target_backend_impl.set_secret(secret_path, value)
        if success:
            print(f"  OK   {secret_path}")
            migrated += 1
        else:
            print(f"  FAIL {secret_path}")
            failed += 1
    
    print()
    print(f"Migration complete: {migrated} migrated, {failed} failed")
    
    return 0 if failed == 0 else 1
