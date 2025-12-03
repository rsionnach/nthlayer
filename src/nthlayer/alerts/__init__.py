"""
NthLayer Alerts Module

Automatic alert generation from awesome-prometheus-alerts templates.

Features:
- 580+ battle-tested alerting rules
- Automatic dependency detection
- Tier-based filtering
- Multi-platform support (Prometheus, Datadog, CloudWatch)
"""

from .loader import AlertTemplateLoader
from .models import AlertRule

__all__ = ["AlertRule", "AlertTemplateLoader"]
