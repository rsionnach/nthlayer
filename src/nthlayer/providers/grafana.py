"""
Re-export shim — canonical source is nthlayer_common.providers.grafana.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.grafana import (  # noqa: F401
    GrafanaDashboardResource,
    GrafanaDatasourceResource,
    GrafanaFolderResource,
    GrafanaProvider,
    GrafanaProviderError,
)

__all__ = [
    "GrafanaProviderError",
    "GrafanaProvider",
    "GrafanaFolderResource",
    "GrafanaDashboardResource",
    "GrafanaDatasourceResource",
]
