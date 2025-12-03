"""
Alert Rule Models

Data models for representing alerting rules.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AlertRule:
    """
    Prometheus alerting rule.
    
    Based on awesome-prometheus-alerts format with extensions
    for NthLayer-specific metadata.
    """
    
    name: str
    expr: str  # PromQL expression
    duration: str = "5m"  # How long condition must be true
    severity: str = "warning"  # critical, warning, info
    summary: str = ""
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    
    # NthLayer-specific metadata
    technology: str = ""  # postgres, redis, nginx, etc.
    category: str = ""  # database, proxy, orchestrator, etc.
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], technology: str = "", category: str = "") -> "AlertRule":
        """
        Parse alert rule from YAML dict (awesome-prometheus-alerts format).
        
        Example input:
            {
                "alert": "PostgresqlDown",
                "expr": "pg_up == 0",
                "for": "0m",
                "labels": {"severity": "critical"},
                "annotations": {
                    "summary": "Postgresql down (instance {{ $labels.instance }})",
                    "description": "Postgresql instance is down"
                }
            }
        """
        return cls(
            name=data["alert"],
            expr=data["expr"],
            duration=data.get("for", "5m"),
            severity=data.get("labels", {}).get("severity", "warning"),
            summary=data.get("annotations", {}).get("summary", ""),
            description=data.get("annotations", {}).get("description", ""),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            technology=technology,
            category=category,
        )
    
    def to_prometheus(self) -> Dict[str, Any]:
        """
        Convert to Prometheus YAML format.
        
        Output format matches Prometheus alerting rule syntax.
        """
        return {
            "alert": self.name,
            "expr": self.expr,
            "for": self.duration,
            "labels": self.labels,
            "annotations": self.annotations,
        }
    
    def customize_for_service(
        self,
        service_name: str,
        team: str,
        tier: int,
        notification_channel: str = "",
        runbook_url: str = ""
    ) -> "AlertRule":
        """
        Customize alert for a specific service.
        
        Adds service context labels and annotations:
        - service: Service name
        - team: Owning team
        - tier: Service tier
        - notification_channel: Where to send alerts
        - runbook_url: Link to troubleshooting docs
        """
        # Create a copy
        customized = AlertRule(
            name=self.name,
            expr=self.expr,
            duration=self.duration,
            severity=self.severity,
            summary=self.summary,
            description=self.description,
            labels=self.labels.copy(),
            annotations=self.annotations.copy(),
            technology=self.technology,
            category=self.category,
        )
        
        # Add service context to labels
        customized.labels["service"] = service_name
        customized.labels["team"] = team
        customized.labels["tier"] = str(tier)
        
        # Add notification and runbook to annotations
        if notification_channel:
            customized.annotations["channel"] = notification_channel
        
        if runbook_url:
            customized.annotations["runbook"] = (
                f"{runbook_url}/{service_name}/{self.name}"
            )
        
        return customized
    
    def is_critical(self) -> bool:
        """Check if alert is critical severity"""
        return self.severity == "critical"
    
    def is_down_alert(self) -> bool:
        """Check if alert is a 'down' or 'unavailable' alert"""
        down_keywords = ["down", "unavailable", "unreachable", "offline"]
        name_lower = self.name.lower()
        return any(keyword in name_lower for keyword in down_keywords)
    
    def __repr__(self) -> str:
        return f"AlertRule(name='{self.name}', severity='{self.severity}', tech='{self.technology}')"
