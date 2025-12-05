"""
Loki Alert Models

Data models for LogQL alert rules compatible with Grafana Loki Ruler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogQLAlert:
    """A LogQL alert rule for Grafana Loki Ruler."""

    name: str
    expr: str
    severity: str = "warning"
    for_duration: str = "5m"
    summary: str = ""
    description: str = ""
    technology: str = ""
    category: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.summary:
            self.summary = f"{self.name} triggered"
        if not self.description:
            self.description = self.summary

    def to_ruler_format(self) -> dict[str, Any]:
        """Convert to Grafana Loki Ruler format.

        Returns YAML-serializable dict matching Loki ruler format:
        https://grafana.com/docs/loki/latest/alert/
        """
        rule = {
            "alert": self.name,
            "expr": self.expr,
            "for": self.for_duration,
            "labels": {
                "severity": self.severity,
                **self.labels,
            },
            "annotations": {
                "summary": self.summary,
                "description": self.description,
                **self.annotations,
            },
        }
        if self.technology:
            rule["labels"]["technology"] = self.technology
        return rule

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        technology: str = "",
        category: str = "",
    ) -> LogQLAlert:
        """Create LogQLAlert from dictionary."""
        labels = data.get("labels", {})
        annotations = data.get("annotations", {})

        return cls(
            name=data.get("alert", data.get("name", "UnnamedAlert")),
            expr=data.get("expr", ""),
            severity=labels.get("severity", "warning"),
            for_duration=data.get("for", "5m"),
            summary=annotations.get("summary", ""),
            description=annotations.get("description", ""),
            technology=technology,
            category=category,
            labels={k: v for k, v in labels.items() if k != "severity"},
            annotations={
                k: v for k, v in annotations.items() if k not in ("summary", "description")
            },
        )
