"""
Re-export shim — canonical source is nthlayer_common.identity.ownership_providers.pagerduty.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.identity.ownership_providers.pagerduty import (  # noqa: F401
    PagerDutyOwnershipProvider,
)

__all__ = ["PagerDutyOwnershipProvider"]
