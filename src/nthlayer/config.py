"""
Application settings and configuration.
"""

from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "postgresql+psycopg://localhost/nthlayer"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # AWS
    aws_region: str = "us-east-1"
    
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
