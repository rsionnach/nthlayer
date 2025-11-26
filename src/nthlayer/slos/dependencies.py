"""
Dependency correlation and impact attribution.

Handles:
- Dependency criticality levels (critical/high/medium/low)
- Inherited impact calculation from upstream failures
- Optional toggle for inherited attribution (startup vs enterprise)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class DependencyCriticality:
    """Criticality level of a dependency."""
    
    CRITICAL = "critical"  # Service fails completely without it
    HIGH = "high"          # Service degrades significantly
    MEDIUM = "medium"      # Service can degrade gracefully
    LOW = "low"            # Service mostly unaffected
    
    @classmethod
    def from_string(cls, value: str) -> str:
        """Convert string to criticality level."""
        valid = {cls.CRITICAL, cls.HIGH, cls.MEDIUM, cls.LOW}
        if value not in valid:
            raise ValueError(f"Invalid criticality: {value}")
        return value


@dataclass
class Dependency:
    """A service dependency."""
    
    name: str
    criticality: str  # critical, high, medium, low
    type: str = "service"  # service, database, external_api, queue


@dataclass
class InheritedImpact:
    """Impact inherited from upstream dependency failure."""
    
    upstream_service: str
    duration_minutes: int
    criticality: str  # critical, high, medium, low
    incident_summary: str
    correlation_confidence: float  # 0.0 - 1.0
    timeframe_start: datetime
    timeframe_end: datetime
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if correlation confidence is high (>0.8)."""
        return self.correlation_confidence > 0.8


@dataclass
class ErrorBudgetAttribution:
    """Error budget attribution breakdown."""
    
    service: str
    total_consumed_minutes: int
    direct_consumed_minutes: int
    inherited_consumed_minutes: int
    
    direct_incidents: list[dict[str, Any]]
    inherited_impacts: list[InheritedImpact]
    
    attribution_enabled: bool  # Was inherited attribution active?
    
    @property
    def inherited_percentage(self) -> float:
        """Calculate percentage of budget consumed from dependencies."""
        if self.total_consumed_minutes == 0:
            return 0.0
        return (self.inherited_consumed_minutes / self.total_consumed_minutes) * 100


class DependencyCorrelator:
    """
    Correlates errors with dependency failures.
    
    Determines if downstream service errors are caused by upstream failures.
    """
    
    def __init__(
        self,
        enabled: bool = False,  # Default: OFF (startup mode)
        min_correlation_confidence: float = 0.8,
        time_window_minutes: int = 5,
    ):
        """
        Initialize dependency correlator.
        
        Args:
            enabled: Enable inherited impact attribution
            min_correlation_confidence: Minimum confidence to attribute (0.0-1.0)
            time_window_minutes: Time window for correlation
        """
        self.enabled = enabled
        self.min_correlation_confidence = min_correlation_confidence
        self.time_window_minutes = time_window_minutes
    
    def calculate_attribution(
        self,
        service: str,
        incidents: list[dict[str, Any]],
        dependencies: list[Dependency],
        upstream_incidents: dict[str, list[dict[str, Any]]],
    ) -> ErrorBudgetAttribution:
        """
        Calculate error budget attribution with optional inherited impact.
        
        Args:
            service: Service name
            incidents: Service incidents (direct)
            dependencies: Service dependencies with criticality
            upstream_incidents: Map of upstream service → incidents
        
        Returns:
            ErrorBudgetAttribution with breakdown
        """
        # Calculate direct consumption
        direct_minutes = sum(i.get("duration_minutes", 0) for i in incidents)
        
        # If attribution disabled, return simple result
        if not self.enabled:
            return ErrorBudgetAttribution(
                service=service,
                total_consumed_minutes=direct_minutes,
                direct_consumed_minutes=direct_minutes,
                inherited_consumed_minutes=0,
                direct_incidents=incidents,
                inherited_impacts=[],
                attribution_enabled=False,
            )
        
        # Calculate inherited impacts
        inherited_impacts = []
        
        for incident in incidents:
            incident_start = incident.get("start_time")
            incident_end = incident.get("end_time")
            
            if not incident_start or not incident_end:
                continue
            
            # Check each dependency for correlation
            for dep in dependencies:
                # Only correlate for critical/high dependencies
                if dep.criticality not in [
                    DependencyCriticality.CRITICAL,
                    DependencyCriticality.HIGH,
                ]:
                    continue
                
                # Find upstream incidents in same timeframe
                upstream = upstream_incidents.get(dep.name, [])
                
                for upstream_incident in upstream:
                    upstream_start = upstream_incident.get("start_time")
                    upstream_end = upstream_incident.get("end_time")
                    
                    if not upstream_start or not upstream_end:
                        continue
                    
                    # Calculate correlation
                    correlation = self._calculate_correlation(
                        incident_start,
                        incident_end,
                        upstream_start,
                        upstream_end,
                    )
                    
                    if correlation >= self.min_correlation_confidence:
                        # Calculate overlapping duration
                        overlap_minutes = self._calculate_overlap_minutes(
                            incident_start,
                            incident_end,
                            upstream_start,
                            upstream_end,
                        )
                        
                        inherited_impacts.append(InheritedImpact(
                            upstream_service=dep.name,
                            duration_minutes=overlap_minutes,
                            criticality=dep.criticality,
                            incident_summary=upstream_incident.get("summary", "Unknown incident"),
                            correlation_confidence=correlation,
                            timeframe_start=max(incident_start, upstream_start),
                            timeframe_end=min(incident_end, upstream_end),
                        ))
        
        # Calculate inherited consumption
        inherited_minutes = sum(i.duration_minutes for i in inherited_impacts)
        
        # Total = direct + inherited (but don't double-count overlaps)
        # For simplicity, we'll show both separately
        total_minutes = direct_minutes  # Direct is still counted
        
        return ErrorBudgetAttribution(
            service=service,
            total_consumed_minutes=total_minutes,
            direct_consumed_minutes=direct_minutes - inherited_minutes,  # Subtract inherited
            inherited_consumed_minutes=inherited_minutes,
            direct_incidents=incidents,
            inherited_impacts=inherited_impacts,
            attribution_enabled=True,
        )
    
    def _calculate_correlation(
        self,
        incident_start: datetime,
        incident_end: datetime,
        upstream_start: datetime,
        upstream_end: datetime,
    ) -> float:
        """
        Calculate correlation confidence between incidents.
        
        Returns value between 0.0 and 1.0.
        Higher = more likely caused by upstream.
        
        Factors:
        - Time overlap (higher = more likely related)
        - Upstream started first (indicator of causation)
        """
        # Calculate overlap
        overlap_start = max(incident_start, upstream_start)
        overlap_end = min(incident_end, upstream_end)
        
        if overlap_start >= overlap_end:
            return 0.0  # No overlap
        
        overlap_duration = (overlap_end - overlap_start).total_seconds() / 60
        incident_duration = (incident_end - incident_start).total_seconds() / 60
        
        # Overlap percentage
        overlap_pct = overlap_duration / incident_duration if incident_duration > 0 else 0
        
        # Bonus if upstream started first (suggests causation)
        causation_bonus = 0.2 if upstream_start < incident_start else 0
        
        confidence = min(overlap_pct + causation_bonus, 1.0)
        
        return confidence
    
    def _calculate_overlap_minutes(
        self,
        incident_start: datetime,
        incident_end: datetime,
        upstream_start: datetime,
        upstream_end: datetime,
    ) -> int:
        """Calculate overlapping duration in minutes."""
        overlap_start = max(incident_start, upstream_start)
        overlap_end = min(incident_end, upstream_end)
        
        if overlap_start >= overlap_end:
            return 0
        
        duration_seconds = (overlap_end - overlap_start).total_seconds()
        return int(duration_seconds / 60)


def validate_dependencies(
    service: str,
    dependencies: list[Dependency],
    all_services: set[str],
) -> tuple[list[str], list[str]]:
    """
    Validate service dependencies.
    
    Checks:
    - Dependencies exist
    - No circular dependencies
    
    Args:
        service: Service name
        dependencies: Service dependencies
        all_services: Set of all known service names
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    # Check existence
    for dep in dependencies:
        if dep.name not in all_services:
            warnings.append(
                f"Dependency '{dep.name}' not found in service registry. "
                "Ensure it's defined or will be deployed."
            )
    
    # Check for self-dependency
    for dep in dependencies:
        if dep.name == service:
            errors.append(f"Service cannot depend on itself: {service}")
    
    return errors, warnings


def detect_circular_dependencies(
    service_deps: dict[str, list[str]],
) -> list[list[str]]:
    """
    Detect circular dependency chains.
    
    Args:
        service_deps: Map of service → list of dependency names
    
    Returns:
        List of circular chains found (e.g., [["A", "B", "C", "A"]])
    """
    cycles = []
    
    def dfs(node: str, path: list[str], visited: set[str]):
        if node in path:
            # Found cycle
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return
        
        if node in visited:
            return
        
        visited.add(node)
        path.append(node)
        
        for dep in service_deps.get(node, []):
            dfs(dep, path.copy(), visited)
    
    for service in service_deps:
        dfs(service, [], set())
    
    return cycles
