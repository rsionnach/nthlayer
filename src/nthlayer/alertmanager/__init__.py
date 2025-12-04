"""
Alertmanager configuration generation.

Generates Alertmanager configuration with PagerDuty receivers,
routing rules, and inhibition rules based on service definitions.
"""

from nthlayer.alertmanager.config import (
    AlertmanagerConfig,
    InhibitRule,
    PagerDutyReceiver,
    Receiver,
    Route,
    generate_alertmanager_config,
)

__all__ = [
    "AlertmanagerConfig",
    "generate_alertmanager_config",
    "InhibitRule",
    "PagerDutyReceiver",
    "Receiver",
    "Route",
]
