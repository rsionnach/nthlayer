"""
Application settings using Pydantic.

Provides environment-based configuration loading with NTHLAYER_ prefix.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql+psycopg://localhost/nthlayer"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # Debug
    debug: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AWS
    aws_region: str = "us-east-1"

    # Environment
    environment: str = "development"

    # API
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = []

    # Prometheus
    prometheus_url: str = "http://localhost:9090"

    # Grafana
    grafana_base_url: str = "http://localhost:3000"
    grafana_token: str | None = None
    grafana_org_id: int = 1

    # Slack
    slack_webhook_url: str | None = None

    # PagerDuty
    pagerduty_api_key: str | None = None

    # Grafana API configuration (for auto-push dashboards)
    grafana_url: str | None = None
    grafana_api_key: str | None = None

    # Metric discovery configuration (for dashboard validation)
    metrics_url: str | None = None
    metrics_user: str | None = None
    metrics_password: str | None = None

    # Cognito (for API authentication)
    cognito_user_pool_id: str | None = None
    cognito_region: str | None = None
    cognito_audience: str | None = None
    jwt_jwks_url: str | None = None
    jwt_issuer: str | None = None

    # HTTP client settings
    http_timeout: int = 30
    http_max_retries: int = 3
    http_retry_backoff_factor: float = 0.5

    # External service URLs
    cortex_base_url: str = "https://api.cortex.io"
    pagerduty_base_url: str = "https://api.pagerduty.com"
    pagerduty_from_email: str = "nthlayer@example.com"

    # API tokens (SecretStr for security)
    cortex_token: str | None = None
    pagerduty_token: str | None = None
    slack_bot_token: str | None = None
    slack_default_channel: str | None = None

    # Queue settings
    sqs_queue_url: str | None = None
    job_queue_backend: str = "memory"  # memory, sqs, redis

    # Redis settings
    redis_max_connections: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "NTHLAYER_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
