"""
Ownership providers package.

Live providers (base, kubernetes, backstage, pagerduty) are re-export shims —
canonical source is nthlayer_common.identity.ownership_providers.
Static providers (declared, codeowners) remain here in generate.
"""

from nthlayer.identity.ownership_providers.backstage import BackstageOwnershipProvider
from nthlayer.identity.ownership_providers.base import BaseOwnershipProvider, OwnershipProviderHealth
from nthlayer.identity.ownership_providers.codeowners import CODEOWNERSProvider
from nthlayer.identity.ownership_providers.declared import DeclaredOwnershipProvider
from nthlayer.identity.ownership_providers.kubernetes import KubernetesOwnershipProvider
from nthlayer.identity.ownership_providers.pagerduty import PagerDutyOwnershipProvider

__all__ = [
    "BaseOwnershipProvider",
    "OwnershipProviderHealth",
    "BackstageOwnershipProvider",
    "CODEOWNERSProvider",
    "DeclaredOwnershipProvider",
    "KubernetesOwnershipProvider",
    "PagerDutyOwnershipProvider",
]
