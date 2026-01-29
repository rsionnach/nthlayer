"""Dashboard builder for ReliabilityManifest.

Adapts ReliabilityManifest to the existing DashboardBuilderSDK by converting
manifest data to ServiceContext + Resources, then delegating.

Supports both OpenSRM and legacy formats through the unified manifest model.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
from nthlayer.specs.manifest import ReliabilityManifest
from nthlayer.specs.models import Resource, ServiceContext

logger = logging.getLogger(__name__)


class ManifestDashboardBuilder:
    """Builds Grafana dashboards from ReliabilityManifest using Foundation SDK.

    Uses adapter pattern: converts manifest to ServiceContext + Resources,
    then delegates to DashboardBuilderSDK for actual panel generation.
    """

    def __init__(
        self,
        manifest: ReliabilityManifest,
        full_panels: bool = False,
        discovery_client: Any = None,
        enable_validation: bool = False,
        prometheus_url: Optional[str] = None,
        custom_metric_overrides: Optional[Dict[str, str]] = None,
        use_intent_templates: bool = True,
    ):
        """Initialize builder with manifest.

        Args:
            manifest: ReliabilityManifest instance
            full_panels: If True, use all template panels
            discovery_client: Optional for validation
            enable_validation: Whether to validate against discovered metrics
            prometheus_url: URL for metric discovery
            custom_metric_overrides: Dict of intent -> custom metric mappings
            use_intent_templates: Whether to use intent-based templates
        """
        self.manifest = manifest

        # Convert manifest to legacy types for delegation
        context = self._manifest_to_context()
        resources = self._manifest_to_resources(context)

        # Delegate to existing builder
        self._builder = DashboardBuilderSDK(
            service_context=context,
            resources=resources,
            full_panels=full_panels,
            discovery_client=discovery_client,
            enable_validation=enable_validation,
            prometheus_url=prometheus_url,
            custom_metric_overrides=custom_metric_overrides,
            use_intent_templates=use_intent_templates,
        )

    def build(self) -> Dict[str, Any]:
        """Build dashboard JSON.

        Returns:
            Dashboard JSON dictionary ready for Grafana API.
        """
        return self._builder.build()

    def _manifest_to_context(self):
        """Convert manifest to ServiceContext."""
        return self.manifest.as_service_context()

    def _manifest_to_resources(self, context: ServiceContext) -> List[Resource]:
        """Convert manifest SLOs and dependencies to Resources."""
        resources: List[Resource] = []

        # Convert SLOs
        for slo in self.manifest.slos:
            indicator: Dict[str, Any] = {}
            if slo.slo_type:
                indicator["type"] = slo.slo_type
            if slo.indicator_query:
                indicator["query"] = slo.indicator_query

            spec: Dict[str, Any] = {
                "objective": slo.target,
                "window": slo.window,
            }
            if indicator:
                spec["indicator"] = indicator

            resources.append(
                Resource(
                    kind="SLO",
                    name=slo.name,
                    spec=spec,
                    context=context,
                )
            )

        # Convert dependencies
        if self.manifest.dependencies:
            dep_spec: Dict[str, Any] = {
                "databases": [],
                "caches": [],
                "services": [],
                "queues": [],
            }
            for dep in self.manifest.dependencies:
                if dep.type == "database":
                    dep_spec["databases"].append(
                        {
                            "name": dep.name,
                            "type": dep.database_type or "unknown",
                        }
                    )
                elif dep.type == "cache":
                    cache_type = "redis"
                    name_lower = dep.name.lower()
                    if "memcache" in name_lower or "memcached" in name_lower:
                        cache_type = "memcached"
                    dep_spec["caches"].append(
                        {
                            "name": dep.name,
                            "type": cache_type,
                        }
                    )
                elif dep.type == "queue":
                    dep_spec["queues"].append(
                        {
                            "name": dep.name,
                            "type": dep.name.split("-")[0].lower(),
                        }
                    )
                elif dep.type == "api":
                    dep_spec["services"].append(
                        {
                            "name": dep.name,
                            "type": dep.type,
                        }
                    )
                else:
                    logger.warning(
                        "Unknown dependency type '%s' for '%s', skipping",
                        dep.type,
                        dep.name,
                    )

            resources.append(
                Resource(
                    kind="Dependencies",
                    name="dependencies",
                    spec=dep_spec,
                    context=context,
                )
            )

        return resources


def build_dashboard_from_manifest(
    manifest: ReliabilityManifest,
    full_panels: bool = False,
    prometheus_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Grafana dashboard from ReliabilityManifest.

    Convenience function matching the pattern of build_dashboard().

    Args:
        manifest: ReliabilityManifest instance
        full_panels: Include all template panels
        prometheus_url: Optional Prometheus URL for metric discovery

    Returns:
        Dashboard JSON dictionary
    """
    builder = ManifestDashboardBuilder(
        manifest=manifest,
        full_panels=full_panels,
        prometheus_url=prometheus_url,
    )
    return builder.build()
