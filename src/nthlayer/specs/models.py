"""
Data models for service specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PagerDutyConfig:
    """PagerDuty-specific configuration for a service."""

    escalation_policy: str | None = None  # Use existing policy by name
    schedule: str | None = None  # Use existing schedule by name
    sre_escalation_policy: str | None = None  # SRE policy for routing overrides
    urgency: str | None = None  # Override: high | low | use_support_hours
    timezone: str = "America/New_York"


@dataclass
class ServiceContext:
    """
    Service-level context that applies to all resources.

    This is declared once at the top of the service YAML and
    all resources inherit this context implicitly.
    """

    name: str
    team: str
    tier: str
    type: str
    support_model: str = "self"  # self | shared | sre | business_hours
    language: str | None = None
    framework: str | None = None
    template: str | None = None
    environment: str | None = None  # runtime environment (dev, staging, prod)
    pagerduty: PagerDutyConfig | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dict for template variable substitution.

        Returns dict with keys for use in ${variable} templates.
        """
        result = {
            "service": self.name,
            "team": self.team,
            "tier": self.tier,
            "type": self.type,
            "support_model": self.support_model,
            "language": self.language or "",
            "framework": self.framework or "",
        }

        # Add environment if specified
        if self.environment:
            result["env"] = self.environment

        return result

    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.name:
            raise ValueError("Service name is required")
        if not self.team:
            raise ValueError("Service team is required")
        if not self.tier:
            raise ValueError("Service tier is required")
        if not self.type:
            raise ValueError("Service type is required")


@dataclass
class Resource:
    """
    A resource within a service definition.

    Resources inherit the service context implicitly, so they don't
    need to repeat the service name.
    """

    kind: str
    spec: dict[str, Any]
    name: str | None = None
    context: ServiceContext | None = None

    @property
    def full_name(self) -> str:
        """
        Generate full resource name: service-name-resource-name.

        Examples:
            service=payment-api, name=availability → payment-api-availability
            service=payment-api, name=None → payment-api
        """
        if not self.context:
            raise ValueError("Resource has no context")

        if self.name:
            return f"{self.context.name}-{self.name}"
        return self.context.name

    @property
    def service_name(self) -> str:
        """Get service name from context."""
        if not self.context:
            raise ValueError("Resource has no context")
        return self.context.name

    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.kind:
            raise ValueError("Resource kind is required")
        if not self.name:
            raise ValueError("Resource name is required")
        if self.spec is None:
            raise ValueError("Resource spec is required")


# Valid resource kinds
VALID_RESOURCE_KINDS = {
    "SLO",
    "PagerDuty",
    "Dependencies",
    "Observability",
    "DeploymentGate",
}

# Valid service tiers (OpenSRM adds 'high' between critical and standard)
VALID_TIERS = {
    "critical",
    "high",  # NEW: OpenSRM tier between critical and standard
    "standard",
    "low",
}

# Valid service types (OpenSRM defines 6 types, NthLayer adds 'web')
VALID_SERVICE_TYPES = {
    "api",  # Request/response services
    "worker",  # Background processors (OpenSRM canonical name)
    "stream",  # Event processors
    "ai-gate",  # AI decision services with judgment SLOs
    "batch",  # Scheduled jobs (OpenSRM canonical name)
    "database",  # Managed database instances
    "web",  # Web frontend (NthLayer extension)
    # Legacy aliases (deprecated, use canonical names)
    "background-job",  # → worker
    "pipeline",  # → batch
}

# Type aliases for backward compatibility
SERVICE_TYPE_ALIASES = {
    "background-job": "worker",  # NthLayer legacy → OpenSRM
    "pipeline": "batch",  # NthLayer legacy → OpenSRM
}

# Valid support models
VALID_SUPPORT_MODELS = {
    "self",  # Team handles everything 24/7
    "shared",  # Team (business hours) + SRE (off-hours)
    "sre",  # SRE handles everything
    "business_hours",  # No off-hours support
}
