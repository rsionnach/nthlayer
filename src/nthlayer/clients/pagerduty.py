"""
Re-export shim — canonical source is nthlayer_common.clients.pagerduty.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.clients.pagerduty import PagerDutyClient  # noqa: F401

__all__ = ["PagerDutyClient"]
