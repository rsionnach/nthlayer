"""Ownership providers package."""

from nthlayer.identity.ownership_providers.backstage import BackstageOwnershipProvider
from nthlayer.identity.ownership_providers.base import BaseOwnershipProvider
from nthlayer.identity.ownership_providers.codeowners import CODEOWNERSProvider
from nthlayer.identity.ownership_providers.declared import DeclaredOwnershipProvider
from nthlayer.identity.ownership_providers.kubernetes import KubernetesOwnershipProvider
from nthlayer.identity.ownership_providers.pagerduty import PagerDutyOwnershipProvider

__all__ = [
    "BaseOwnershipProvider",
    "BackstageOwnershipProvider",
    "CODEOWNERSProvider",
    "DeclaredOwnershipProvider",
    "KubernetesOwnershipProvider",
    "PagerDutyOwnershipProvider",
]
