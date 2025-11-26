"""
Data models for service specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    language: str | None = None
    framework: str | None = None
    template: str | None = None
    environment: str | None = None  # NEW: runtime environment (dev, staging, prod)
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
}

# Valid service tiers
VALID_TIERS = {
    "critical",
    "standard",
    "low",
}

# Valid service types
VALID_SERVICE_TYPES = {
    "api",
    "web",
    "background-job",
    "pipeline",
    "database",
}
