"""
SLO data models.

Based on OpenSLO specification: https://github.com/OpenSLO/OpenSLO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class SLOStatus(str, Enum):
    """SLO compliance status."""
    
    HEALTHY = "healthy"      # < 50% budget burned
    WARNING = "warning"      # 50-80% budget burned
    CRITICAL = "critical"    # 80-95% budget burned
    EXHAUSTED = "exhausted"  # > 95% budget burned


class TimeWindowType(str, Enum):
    """Type of time window for SLO evaluation."""
    
    ROLLING = "rolling"      # Rolling window (e.g., last 30 days)
    CALENDAR = "calendar"    # Calendar window (e.g., current month)


@dataclass
class TimeWindow:
    """Time window for SLO evaluation."""
    
    duration: str  # Duration string (e.g., "30d", "7d", "1h")
    type: TimeWindowType = TimeWindowType.ROLLING
    
    def to_timedelta(self) -> timedelta:
        """Convert duration string to timedelta."""
        # Parse duration string (e.g., "30d" -> 30 days)
        unit = self.duration[-1]
        value = int(self.duration[:-1])
        
        if unit == "d":
            return timedelta(days=value)
        elif unit == "h":
            return timedelta(hours=value)
        elif unit == "m":
            return timedelta(minutes=value)
        elif unit == "w":
            return timedelta(weeks=value)
        else:
            raise ValueError(f"Unsupported duration unit: {unit}")
    
    def get_start_time(self, now: datetime | None = None) -> datetime:
        """Get the start time for this window."""
        if now is None:
            now = datetime.utcnow()
        
        if self.type == TimeWindowType.ROLLING:
            return now - self.to_timedelta()
        else:
            # Calendar-based window (simplified - just use rolling for now)
            return now - self.to_timedelta()


@dataclass
class SLO:
    """
    Service Level Objective.
    
    Represents a target reliability goal for a service.
    Based on OpenSLO specification.
    """
    
    id: str
    service: str
    name: str
    description: str
    target: float  # Target percentage (e.g., 0.9995 for 99.95%)
    time_window: TimeWindow
    
    # Prometheus query for the SLI (Service Level Indicator)
    query: str
    
    # Metadata
    owner: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SLO:
        """Create SLO from dictionary (OpenSLO YAML)."""
        # Parse time window
        window_data = data.get("timeWindow", [{}])[0]
        time_window = TimeWindow(
            duration=window_data.get("duration", "30d"),
            type=TimeWindowType(window_data.get("type", "rolling"))
        )
        
        # Get target value
        objectives = data.get("objectives", [{}])
        target = objectives[0].get("target", 0.999) if objectives else 0.999
        
        return cls(
            id=data.get("metadata", {}).get("name", ""),
            service=data.get("service", ""),
            name=data.get("metadata", {}).get("displayName", ""),
            description=data.get("description", ""),
            target=target,
            time_window=time_window,
            query=objectives[0].get("indicator", {}).get("spec", {}).get("query", "") if objectives else "",
            owner=data.get("metadata", {}).get("labels", {}).get("owner"),
            labels=data.get("metadata", {}).get("labels", {}),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenSLO format."""
        return {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {
                "name": self.id,
                "displayName": self.name,
                "labels": self.labels,
            },
            "spec": {
                "service": self.service,
                "description": self.description,
                "objectives": [
                    {
                        "target": self.target,
                        "indicator": {
                            "spec": {
                                "query": self.query,
                            }
                        }
                    }
                ],
                "timeWindow": [
                    {
                        "duration": self.time_window.duration,
                        "type": self.time_window.type.value,
                    }
                ]
            }
        }
    
    def error_budget_percent(self) -> float:
        """Calculate allowed error budget percentage."""
        return 1.0 - self.target
    
    def error_budget_minutes(self) -> float:
        """Calculate total error budget in minutes for the time window."""
        total_minutes = self.time_window.to_timedelta().total_seconds() / 60
        return total_minutes * self.error_budget_percent()


@dataclass
class ErrorBudget:
    """
    Error budget tracking for an SLO.
    
    Tracks how much error budget has been consumed and what caused it.
    """
    
    slo_id: str
    service: str
    
    # Time period
    period_start: datetime
    period_end: datetime
    
    # Budget amounts (in minutes)
    total_budget_minutes: float
    burned_minutes: float
    remaining_minutes: float
    
    # Burn sources
    incident_burn_minutes: float = 0.0
    deployment_burn_minutes: float = 0.0
    slo_breach_burn_minutes: float = 0.0
    
    # Status
    status: SLOStatus = SLOStatus.HEALTHY
    burn_rate: float = 0.0  # Current burn rate (multiplier of baseline)
    
    # Metadata
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def percent_consumed(self) -> float:
        """Percentage of error budget consumed."""
        if self.total_budget_minutes == 0:
            return 0.0
        return (self.burned_minutes / self.total_budget_minutes) * 100
    
    @property
    def percent_remaining(self) -> float:
        """Percentage of error budget remaining."""
        return 100 - self.percent_consumed
    
    def calculate_status(self) -> SLOStatus:
        """Determine status based on budget consumption."""
        consumed = self.percent_consumed
        
        if consumed >= 95:
            return SLOStatus.EXHAUSTED
        elif consumed >= 80:
            return SLOStatus.CRITICAL
        elif consumed >= 50:
            return SLOStatus.WARNING
        else:
            return SLOStatus.HEALTHY
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API/CLI output."""
        return {
            "slo_id": self.slo_id,
            "service": self.service,
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "budget": {
                "total_minutes": self.total_budget_minutes,
                "burned_minutes": self.burned_minutes,
                "remaining_minutes": self.remaining_minutes,
                "percent_consumed": round(self.percent_consumed, 2),
                "percent_remaining": round(self.percent_remaining, 2),
            },
            "burn_sources": {
                "incidents": self.incident_burn_minutes,
                "deployments": self.deployment_burn_minutes,
                "slo_breaches": self.slo_breach_burn_minutes,
            },
            "status": self.status.value,
            "burn_rate": self.burn_rate,
            "updated_at": self.updated_at.isoformat(),
        }
