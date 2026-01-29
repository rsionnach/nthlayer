"""
Unified Reliability Manifest model for OpenSRM and legacy formats.

This module provides the canonical internal representation that both
OpenSRM (apiVersion: srm/v1) and legacy NthLayer (service:) formats
are normalized to.

All generators (alerts, dashboards, recording rules, SLOs) consume
this unified model, ensuring format-agnostic processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nthlayer.specs.models import ServiceContext as ServiceContextType


# =============================================================================
# Constants
# =============================================================================

# Valid service tiers (OpenSRM adds 'high')
VALID_TIERS = {
    "critical",
    "high",  # NEW: OpenSRM tier between critical and standard
    "standard",
    "low",
}

# Valid service types (OpenSRM defines 6 types)
VALID_SERVICE_TYPES = {
    "api",  # Request/response services
    "worker",  # Background processors (OpenSRM canonical name)
    "stream",  # Event processors
    "ai-gate",  # AI decision services with judgment SLOs
    "batch",  # Scheduled jobs (OpenSRM canonical name)
    "database",  # Managed database instances
    "web",  # Web frontend (NthLayer extension)
}

# Type aliases for backward compatibility
SERVICE_TYPE_ALIASES = {
    "background-job": "worker",  # NthLayer legacy → OpenSRM
    "pipeline": "batch",  # NthLayer legacy → OpenSRM
}

# Judgment SLO types for ai-gate services
JUDGMENT_SLO_TYPES = {
    "reversal_rate",  # Human override tracking
    "high_confidence_failure",  # High-confidence decision failures
    "calibration",  # Confidence score accuracy (ECE)
    "feedback_latency",  # Time to ground truth
}

# Standard SLO types
STANDARD_SLO_TYPES = {
    "availability",
    "latency",
    "error_rate",
    "throughput",
}


# =============================================================================
# Enums
# =============================================================================


class SourceFormat(str, Enum):
    """Source format of the manifest file."""

    OPENSRM = "opensrm"
    LEGACY = "legacy"


class DependencyCriticality(str, Enum):
    """Criticality level for dependencies."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Ownership Models
# =============================================================================


@dataclass
class PagerDutyConfig:
    """PagerDuty integration configuration."""

    service_id: str | None = None
    escalation_policy_id: str | None = None


@dataclass
class Ownership:
    """Service ownership information (OpenSRM spec.ownership)."""

    team: str
    slack: str | None = None
    email: str | None = None
    escalation: str | None = None
    pagerduty: PagerDutyConfig | None = None
    runbook: str | None = None
    documentation: str | None = None


# =============================================================================
# SLO Models
# =============================================================================


@dataclass
class SLODefinition:
    """
    SLO definition within a reliability manifest.

    Supports both standard SLOs (availability, latency, error_rate, throughput)
    and judgment SLOs for ai-gate services.
    """

    name: str  # e.g., "availability", "latency_p99", "reversal_rate"
    target: float  # Target value (e.g., 99.95 for availability, 200 for latency ms)
    window: str = "30d"  # Time window (e.g., "30d", "7d")

    # Type-specific fields
    slo_type: str | None = None  # availability, latency, error_rate, throughput, judgment
    unit: str | None = None  # For latency: ms, s; for throughput: rps
    percentile: str | None = None  # For latency: p50, p95, p99

    # Custom indicator (for advanced use)
    indicator_query: str | None = None

    # Metadata
    description: str | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def is_judgment_slo(self) -> bool:
        """Check if this is an AI gate judgment SLO."""
        return self.name in JUDGMENT_SLO_TYPES or self.slo_type == "judgment"


@dataclass
class Contract:
    """
    External contract/promise to consumers (OpenSRM spec.contract).

    Contracts define external promises. Internal SLOs should be tighter
    than contracts to provide margin.
    """

    availability: float | None = None  # e.g., 0.999
    latency: dict[str, str] | None = None  # e.g., {"p99": "500ms"}
    judgment: dict[str, float] | None = None  # For ai-gate: {"reversal_rate": 0.05}


# =============================================================================
# Dependency Models
# =============================================================================


@dataclass
class DependencySLO:
    """Expected SLO from a dependency."""

    availability: float | None = None
    latency_p99: str | None = None


@dataclass
class Dependency:
    """Service dependency definition (OpenSRM spec.dependencies)."""

    name: str
    type: str  # database, api, queue, cache, etc.
    critical: bool = False
    criticality: DependencyCriticality | None = None
    slo: DependencySLO | None = None
    manifest: str | None = None  # URL to dependency's manifest

    # Database-specific fields
    database_type: str | None = None  # postgresql, mysql, redis, etc.


# =============================================================================
# Observability Models
# =============================================================================


@dataclass
class Observability:
    """Observability configuration (OpenSRM spec.observability)."""

    metrics_prefix: str | None = None
    logs_label: str | None = None
    traces_service: str | None = None

    # Prometheus-specific
    prometheus_job: str | None = None

    # Custom labels for generated resources
    labels: dict[str, str] = field(default_factory=dict)


# =============================================================================
# Deployment Models
# =============================================================================


@dataclass
class ErrorBudgetGate:
    """Error budget gate configuration."""

    enabled: bool = True
    threshold: float | None = None  # Minimum remaining budget (e.g., 0.10 = 10%)


@dataclass
class SLOComplianceGate:
    """SLO compliance gate configuration."""

    threshold: float = 0.99


@dataclass
class RecentIncidentsGate:
    """Recent incidents gate configuration."""

    p1_max: int = 0
    p2_max: int = 2
    lookback: str = "7d"


@dataclass
class RollbackConfig:
    """Automatic rollback configuration."""

    automatic: bool = False
    error_rate_increase: str | None = None  # e.g., "5%"
    latency_increase: str | None = None  # e.g., "50%"


@dataclass
class DeploymentGates:
    """Deployment gate configuration."""

    error_budget: ErrorBudgetGate | None = None
    slo_compliance: SLOComplianceGate | None = None
    recent_incidents: RecentIncidentsGate | None = None


@dataclass
class DeploymentConfig:
    """Deployment configuration (OpenSRM spec.deployment)."""

    environments: list[str] = field(default_factory=list)
    gates: DeploymentGates | None = None
    rollback: RollbackConfig | None = None


# =============================================================================
# AI Gate Models
# =============================================================================


@dataclass
class TelemetryEvent:
    """AI gate telemetry event configuration."""

    name: str
    fields: list[str] = field(default_factory=list)


@dataclass
class Instrumentation:
    """AI gate instrumentation configuration (OpenSRM ai-gate specific)."""

    telemetry_events: list[TelemetryEvent] = field(default_factory=list)
    feedback_loop: str | None = None  # URL or identifier for feedback collection
    ground_truth_source: str | None = None


# =============================================================================
# Main Manifest Model
# =============================================================================


@dataclass
class ReliabilityManifest:
    """
    Unified internal model for both OpenSRM and legacy NthLayer formats.

    This is the canonical representation that all generators consume.
    Both OpenSRM parser and legacy parser produce this model.

    OpenSRM Structure:
        apiVersion: srm/v1
        kind: ServiceReliabilityManifest
        metadata:
          name: payment-api
          team: payments
          tier: critical
        spec:
          type: api
          slos: {}
          dependencies: []

    Legacy NthLayer Structure:
        service:
          name: payment-api
          team: payments
          tier: critical
          type: api
        resources:
          - kind: SLO
            name: availability
            spec: {}
    """

    # ==========================================================================
    # Required Fields (must come first in dataclass)
    # ==========================================================================
    name: str
    team: str
    tier: str  # critical, high, standard, low
    type: str  # api, worker, stream, ai-gate, batch, database, web

    # ==========================================================================
    # Optional Metadata (OpenSRM: metadata section)
    # ==========================================================================
    description: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    # ==========================================================================
    # Optional Spec (OpenSRM: spec section)
    # ==========================================================================
    slos: list[SLODefinition] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    ownership: Ownership | None = None
    observability: Observability | None = None
    deployment: DeploymentConfig | None = None
    contract: Contract | None = None  # External promises to consumers

    # ==========================================================================
    # AI Gate Specific
    # ==========================================================================
    instrumentation: Instrumentation | None = None

    # ==========================================================================
    # Legacy NthLayer Fields (for backward compatibility)
    # ==========================================================================
    language: str | None = None
    framework: str | None = None
    template: str | None = None
    support_model: str = "self"  # self, shared, sre, business_hours
    environment: str | None = None

    # ==========================================================================
    # Source Tracking
    # ==========================================================================
    source_format: SourceFormat = SourceFormat.OPENSRM
    source_file: str | None = None  # Original file path

    # ==========================================================================
    # Raw Data (for debugging/migration)
    # ==========================================================================
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize the manifest."""
        # Normalize service type aliases
        if self.type in SERVICE_TYPE_ALIASES:
            self.type = SERVICE_TYPE_ALIASES[self.type]

        # Validate required fields
        if not self.name:
            raise ValueError("Service name is required")
        if not self.team:
            raise ValueError("Service team is required")
        if not self.tier:
            raise ValueError("Service tier is required")
        if not self.type:
            raise ValueError("Service type is required")

        # Validate tier
        if self.tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid tier '{self.tier}'. Must be one of: {', '.join(sorted(VALID_TIERS))}"
            )

        # Validate type (after alias normalization)
        if self.type not in VALID_SERVICE_TYPES:
            valid = ", ".join(sorted(VALID_SERVICE_TYPES))
            raise ValueError(f"Invalid type '{self.type}'. Must be one of: {valid}")

        # Validate ai-gate specific requirements
        if self.type == "ai-gate":
            judgment_slos = [s for s in self.slos if s.is_judgment_slo()]
            if not judgment_slos:
                # Warning, not error - might be added later
                pass

    def is_ai_gate(self) -> bool:
        """Check if this is an AI gate service."""
        return self.type == "ai-gate"

    def get_judgment_slos(self) -> list[SLODefinition]:
        """Get all judgment SLOs for AI gate services."""
        return [s for s in self.slos if s.is_judgment_slo()]

    def get_standard_slos(self) -> list[SLODefinition]:
        """Get all standard (non-judgment) SLOs."""
        return [s for s in self.slos if not s.is_judgment_slo()]

    def to_service_context(self) -> dict[str, Any]:
        """
        Convert to legacy ServiceContext-compatible dict.

        This enables backward compatibility with existing generators
        that expect ServiceContext.to_dict() output.
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

        if self.environment:
            result["env"] = self.environment

        return result

    def as_service_context(self) -> ServiceContextType:
        """
        Convert to a ServiceContext object.

        Centralizes manifest-to-ServiceContext conversion so that all
        generators use the same mapping. Includes PagerDuty config
        from ownership if available.
        """
        from nthlayer.specs.models import PagerDutyConfig as LegacyPagerDutyConfig
        from nthlayer.specs.models import ServiceContext

        pagerduty = None
        if self.ownership and self.ownership.pagerduty:
            pd = self.ownership.pagerduty
            pagerduty = LegacyPagerDutyConfig(
                escalation_policy=pd.escalation_policy_id,
            )

        return ServiceContext(
            name=self.name,
            team=self.team,
            tier=self.tier,
            type=self.type,
            support_model=self.support_model,
            language=self.language,
            framework=self.framework,
            environment=self.environment,
            pagerduty=pagerduty,
        )

    def validate_contracts(self) -> list[str]:
        """
        Validate that internal SLOs are tighter than external contracts.

        Returns list of validation errors.
        """
        errors: list[str] = []

        if not self.contract:
            return errors

        # Check availability contract
        if self.contract.availability:
            avail_slos = [s for s in self.slos if s.name == "availability"]
            for slo in avail_slos:
                # SLO target should be >= contract (tighter)
                if slo.target < self.contract.availability * 100:
                    errors.append(
                        f"Availability SLO ({slo.target}%) is looser than "
                        f"contract ({self.contract.availability * 100}%)"
                    )

        # Check judgment contracts for ai-gate
        if self.contract.judgment and self.is_ai_gate():
            for metric, contract_target in self.contract.judgment.items():
                matching_slos = [s for s in self.slos if s.name == metric]
                for slo in matching_slos:
                    # For error metrics, SLO target should be <= contract (tighter)
                    if slo.target > contract_target:
                        errors.append(
                            f"Judgment SLO '{metric}' ({slo.target}) is looser than "
                            f"contract ({contract_target})"
                        )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary representation.

        Returns OpenSRM-style structure regardless of source format.
        """
        result: dict[str, Any] = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {
                "name": self.name,
                "team": self.team,
                "tier": self.tier,
            },
            "spec": {
                "type": self.type,
            },
        }

        # Add optional metadata fields
        if self.description:
            result["metadata"]["description"] = self.description
        if self.labels:
            result["metadata"]["labels"] = self.labels
        if self.annotations:
            result["metadata"]["annotations"] = self.annotations

        # Add SLOs
        if self.slos:
            result["spec"]["slos"] = {}
            for slo in self.slos:
                slo_data: dict[str, Any] = {
                    "target": slo.target,
                    "window": slo.window,
                }
                if slo.unit:
                    slo_data["unit"] = slo.unit
                if slo.percentile:
                    slo_data["percentile"] = slo.percentile
                if slo.description:
                    slo_data["description"] = slo.description
                result["spec"]["slos"][slo.name] = slo_data

        # Add dependencies
        if self.dependencies:
            result["spec"]["dependencies"] = [
                {
                    "name": dep.name,
                    "type": dep.type,
                    "critical": dep.critical,
                }
                for dep in self.dependencies
            ]

        # Add ownership
        if self.ownership:
            result["spec"]["ownership"] = {
                "team": self.ownership.team,
            }
            if self.ownership.slack:
                result["spec"]["ownership"]["slack"] = self.ownership.slack
            if self.ownership.email:
                result["spec"]["ownership"]["email"] = self.ownership.email
            if self.ownership.runbook:
                result["spec"]["ownership"]["runbook"] = self.ownership.runbook

        # Add contract
        if self.contract:
            result["spec"]["contract"] = {}
            if self.contract.availability:
                result["spec"]["contract"]["availability"] = self.contract.availability
            if self.contract.latency:
                result["spec"]["contract"]["latency"] = self.contract.latency
            if self.contract.judgment:
                result["spec"]["contract"]["judgment"] = self.contract.judgment

        # Add instrumentation for ai-gate
        if self.instrumentation and self.is_ai_gate():
            result["spec"]["instrumentation"] = {}
            if self.instrumentation.telemetry_events:
                result["spec"]["instrumentation"]["telemetry_events"] = [
                    {"name": e.name, "fields": e.fields}
                    for e in self.instrumentation.telemetry_events
                ]

        return result
