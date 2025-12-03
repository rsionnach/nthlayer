"""
Integration configuration with profile support.

Supports multiple profiles per integration for different environments:
- Grafana (Cloud, OSS, Enterprise)
- Prometheus (Standalone, Mimir, Cortex, Thanos, Grafana Cloud)
- PagerDuty
- Slack
- Datadog
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nthlayer.config.secrets import SecretResolver, get_secret_resolver


class PrometheusType(StrEnum):
    """Prometheus backend types."""
    PROMETHEUS = "prometheus"
    MIMIR = "mimir"
    CORTEX = "cortex"
    THANOS = "thanos"
    GRAFANA_CLOUD = "grafana-cloud"


class GrafanaType(StrEnum):
    """Grafana backend types."""
    GRAFANA = "grafana"
    GRAFANA_CLOUD = "grafana-cloud"
    GRAFANA_ENTERPRISE = "grafana-enterprise"


@dataclass
class PrometheusProfile:
    """Configuration for a Prometheus instance."""
    name: str
    type: PrometheusType = PrometheusType.PROMETHEUS
    url: str = "http://localhost:9090"
    username: str | None = None
    password_secret: str | None = None  # Secret path for password
    tenant_id: str | None = None  # For Mimir/Cortex
    
    def get_password(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.password_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.password_secret)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "username": self.username,
            "password_secret": self.password_secret,
            "tenant_id": self.tenant_id,
        }
    
    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PrometheusProfile:
        return cls(
            name=name,
            type=PrometheusType(data.get("type", "prometheus")),
            url=data.get("url", "http://localhost:9090"),
            username=data.get("username"),
            password_secret=data.get("password_secret") or data.get("password"),
            tenant_id=data.get("tenant_id"),
        )


@dataclass
class GrafanaProfile:
    """Configuration for a Grafana instance."""
    name: str
    type: GrafanaType = GrafanaType.GRAFANA
    url: str = "http://localhost:3000"
    org_id: int = 1
    api_key_secret: str | None = None  # Secret path for API key
    
    def get_api_key(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.api_key_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.api_key_secret)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "org_id": self.org_id,
            "api_key_secret": self.api_key_secret,
        }
    
    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> GrafanaProfile:
        return cls(
            name=name,
            type=GrafanaType(data.get("type", "grafana")),
            url=data.get("url", "http://localhost:3000"),
            org_id=data.get("org_id", 1),
            api_key_secret=data.get("api_key_secret") or data.get("api_key"),
        )


@dataclass
class PrometheusConfig:
    """Prometheus configuration with multiple profiles."""
    default: str = "local"
    profiles: dict[str, PrometheusProfile] = field(default_factory=dict)
    
    def get_profile(self, name: str | None = None) -> PrometheusProfile | None:
        """Get a profile by name or the default profile."""
        profile_name = name or self.default
        return self.profiles.get(profile_name)
    
    def add_profile(self, profile: PrometheusProfile):
        """Add or update a profile."""
        self.profiles[profile.name] = profile
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "default": self.default,
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrometheusConfig:
        profiles = {}
        for name, profile_data in data.get("profiles", {}).items():
            profiles[name] = PrometheusProfile.from_dict(name, profile_data)
        
        return cls(
            default=data.get("default", "local"),
            profiles=profiles,
        )


@dataclass
class GrafanaConfig:
    """Grafana configuration with multiple profiles."""
    default: str = "local"
    profiles: dict[str, GrafanaProfile] = field(default_factory=dict)
    
    def get_profile(self, name: str | None = None) -> GrafanaProfile | None:
        """Get a profile by name or the default profile."""
        profile_name = name or self.default
        return self.profiles.get(profile_name)
    
    def add_profile(self, profile: GrafanaProfile):
        """Add or update a profile."""
        self.profiles[profile.name] = profile
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "default": self.default,
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GrafanaConfig:
        profiles = {}
        for name, profile_data in data.get("profiles", {}).items():
            profiles[name] = GrafanaProfile.from_dict(name, profile_data)
        
        return cls(
            default=data.get("default", "local"),
            profiles=profiles,
        )


@dataclass
class PagerDutyConfig:
    """PagerDuty configuration."""
    api_key_secret: str | None = None
    default_escalation_policy: str | None = None
    enabled: bool = True
    
    def get_api_key(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.api_key_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.api_key_secret)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key_secret": self.api_key_secret,
            "default_escalation_policy": self.default_escalation_policy,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PagerDutyConfig:
        return cls(
            api_key_secret=data.get("api_key_secret") or data.get("api_key"),
            default_escalation_policy=data.get("default_escalation_policy"),
            enabled=data.get("enabled", True),
        )


@dataclass
class SlackConfig:
    """Slack configuration."""
    webhook_url_secret: str | None = None
    default_channel: str = "#alerts"
    enabled: bool = True
    
    def get_webhook_url(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.webhook_url_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.webhook_url_secret)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "webhook_url_secret": self.webhook_url_secret,
            "default_channel": self.default_channel,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlackConfig:
        return cls(
            webhook_url_secret=data.get("webhook_url_secret") or data.get("webhook_url"),
            default_channel=data.get("default_channel", "#alerts"),
            enabled=data.get("enabled", True),
        )


@dataclass
class DatadogConfig:
    """Datadog configuration."""
    api_key_secret: str | None = None
    app_key_secret: str | None = None
    site: str = "datadoghq.com"
    enabled: bool = False
    
    def get_api_key(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.api_key_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.api_key_secret)
    
    def get_app_key(self, resolver: SecretResolver | None = None) -> str | None:
        if not self.app_key_secret:
            return None
        resolver = resolver or get_secret_resolver()
        return resolver.resolve(self.app_key_secret)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key_secret": self.api_key_secret,
            "app_key_secret": self.app_key_secret,
            "site": self.site,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatadogConfig:
        return cls(
            api_key_secret=data.get("api_key_secret") or data.get("api_key"),
            app_key_secret=data.get("app_key_secret") or data.get("app_key"),
            site=data.get("site", "datadoghq.com"),
            enabled=data.get("enabled", False),
        )


@dataclass 
class AlertingConfig:
    """Alerting destinations configuration."""
    pagerduty: PagerDutyConfig = field(default_factory=PagerDutyConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    datadog: DatadogConfig = field(default_factory=DatadogConfig)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "pagerduty": self.pagerduty.to_dict(),
            "slack": self.slack.to_dict(),
            "datadog": self.datadog.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertingConfig:
        return cls(
            pagerduty=PagerDutyConfig.from_dict(data.get("pagerduty", {})),
            slack=SlackConfig.from_dict(data.get("slack", {})),
            datadog=DatadogConfig.from_dict(data.get("datadog", {})),
        )


@dataclass
class IntegrationConfig:
    """
    Complete integration configuration.
    
    Combines all integration configs with profile support.
    """
    version: int = 1
    prometheus: PrometheusConfig = field(default_factory=PrometheusConfig)
    grafana: GrafanaConfig = field(default_factory=GrafanaConfig)
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    
    def get_prometheus(self, profile: str | None = None) -> PrometheusProfile | None:
        """Get Prometheus profile."""
        return self.prometheus.get_profile(profile)
    
    def get_grafana(self, profile: str | None = None) -> GrafanaProfile | None:
        """Get Grafana profile."""
        return self.grafana.get_profile(profile)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "prometheus": self.prometheus.to_dict(),
            "grafana": self.grafana.to_dict(),
            "alerting": self.alerting.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntegrationConfig:
        return cls(
            version=data.get("version", 1),
            prometheus=PrometheusConfig.from_dict(data.get("prometheus", {})),
            grafana=GrafanaConfig.from_dict(data.get("grafana", {})),
            alerting=AlertingConfig.from_dict(data.get("alerting", {})),
        )
    
    @classmethod
    def default(cls) -> IntegrationConfig:
        """Create default configuration with local profiles."""
        config = cls()
        
        config.prometheus.profiles["local"] = PrometheusProfile(
            name="local",
            type=PrometheusType.PROMETHEUS,
            url="http://localhost:9090",
        )
        
        config.grafana.profiles["local"] = GrafanaProfile(
            name="local",
            type=GrafanaType.GRAFANA,
            url="http://localhost:3000",
        )
        
        return config


_integration_config: IntegrationConfig | None = None


def get_integration_config() -> IntegrationConfig:
    """Get the global integration config (loads from file if not set)."""
    global _integration_config
    if _integration_config is None:
        from nthlayer.config.loader import load_config
        _integration_config = load_config()
    return _integration_config


def set_integration_config(config: IntegrationConfig):
    """Set the global integration config."""
    global _integration_config
    _integration_config = config
