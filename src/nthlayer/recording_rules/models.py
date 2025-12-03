"""Data models for Prometheus recording rules."""

from dataclasses import dataclass, field
from typing import Dict, List

import yaml


@dataclass
class RecordingRule:
    """A Prometheus recording rule.
    
    Recording rules precompute frequently needed or expensive expressions
    and save their result as a new time series.
    """
    
    record: str
    """The name of the time series to output to."""
    
    expr: str
    """The PromQL expression to evaluate."""
    
    labels: Dict[str, str] = field(default_factory=dict)
    """Labels to add or overwrite before storing the result."""
    
    def to_dict(self) -> dict:
        """Convert to Prometheus rule format.
        
        Returns:
            Dictionary in Prometheus recording rule format
        """
        rule = {
            "record": self.record,
            "expr": self.expr,
        }
        
        if self.labels:
            rule["labels"] = self.labels
        
        return rule


@dataclass
class RecordingRuleGroup:
    """A group of recording rules.
    
    Prometheus organizes rules into groups that are evaluated at a regular interval.
    """
    
    name: str
    """The name of the rule group."""
    
    interval: str = "30s"
    """How often rules in the group are evaluated (default: 30s)."""
    
    rules: List[RecordingRule] = field(default_factory=list)
    """List of recording rules in this group."""
    
    def add_rule(self, rule: RecordingRule):
        """Add a recording rule to this group.
        
        Args:
            rule: RecordingRule to add
        """
        self.rules.append(rule)
    
    def to_dict(self) -> dict:
        """Convert to Prometheus rule group format.
        
        Returns:
            Dictionary in Prometheus rule group format
        """
        return {
            "name": self.name,
            "interval": self.interval,
            "rules": [rule.to_dict() for rule in self.rules]
        }
    
    def to_yaml(self) -> str:
        """Convert to YAML format for Prometheus.
        
        Returns:
            YAML string in Prometheus format
        """
        # Wrap in groups array as required by Prometheus
        data = {"groups": [self.to_dict()]}
        return yaml.dump(data, default_flow_style=False, sort_keys=False)


def create_rule_groups(groups: List[RecordingRuleGroup]) -> str:
    """Create YAML output for multiple rule groups.
    
    Args:
        groups: List of RecordingRuleGroup objects
        
    Returns:
        YAML string with all groups
    """
    data = {"groups": [group.to_dict() for group in groups]}
    return yaml.dump(data, default_flow_style=False, sort_keys=False)
