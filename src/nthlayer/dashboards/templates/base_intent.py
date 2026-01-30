"""
Intent-Based Template System for NthLayer Dashboard Generation.

This module provides the base class for intent-based templates that use
the metric resolution system instead of hardcoded metric names.
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.resolver import MetricResolver, ResolutionResult, ResolutionStatus
from nthlayer.dashboards.templates.base import TechnologyTemplate

logger = logging.getLogger(__name__)


class IntentBasedTemplate(TechnologyTemplate):
    """
    Base class for intent-based dashboard templates.

    Intent-based templates define panels using abstract "intents" instead of
    hardcoded metric names. The MetricResolver translates these intents to
    actual metrics at generation time, enabling:

    1. Exporter-agnostic dashboards
    2. Automatic fallback handling
    3. Guidance panels when metrics unavailable
    4. Custom metric overrides
    """

    def __init__(self, resolver: Optional[MetricResolver] = None):
        """
        Initialize template with optional resolver.

        Args:
            resolver: MetricResolver for translating intents to metrics
        """
        self.resolver = resolver
        self._resolution_results: Dict[str, ResolutionResult] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Technology name."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name for UI."""
        pass

    @abstractmethod
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """
        Get panel specifications using intents.

        Subclasses implement this to define panels with intents
        instead of hardcoded metrics.

        Args:
            service_name: Service name or template variable

        Returns:
            List of PanelSpec objects
        """
        pass

    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """
        Get resolved panels for the dashboard.

        This method:
        1. Gets panel specs with intents
        2. Resolves intents to actual metrics
        3. Builds Panel objects with resolved queries
        4. Creates guidance panels for unresolved intents

        Args:
            service_name: Service name or template variable

        Returns:
            List of Panel objects with resolved queries
        """
        specs = self.get_panel_specs(service_name)
        panels = []

        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)

        return panels

    def _build_panel_from_spec(self, spec: PanelSpec, service_name: str) -> Optional[Panel]:
        """
        Build a Panel from a PanelSpec, resolving intents.

        Args:
            spec: Panel specification with intents
            service_name: Service name for query building

        Returns:
            Panel object if resolvable, None if should be skipped
        """
        targets = []
        all_resolved = True
        unresolved_intents = []

        for query_spec in spec.queries:
            result = self._resolve_intent(query_spec.intent)

            if result.resolved and result.metric_name:
                # Build target with resolved metric
                expr = query_spec.build_query(result.metric_name, service_name)
                metric_prefix = result.metric_name.split("_")[0]
                targets.append(
                    Target(
                        expr=expr,
                        legend_format=query_spec.legend or "{{" + metric_prefix + "}}",
                        ref_id=query_spec.ref_id,
                    )
                )

                if result.status == ResolutionStatus.FALLBACK:
                    logger.info(f"Panel '{spec.title}': Using fallback for {query_spec.intent}")
            else:
                all_resolved = False
                unresolved_intents.append(query_spec.intent)

        # Handle unresolved intents
        if not all_resolved:
            if spec.skip_if_unavailable:
                logger.info(f"Skipping panel '{spec.title}': {unresolved_intents} unresolved")
                return None
            else:
                # Create guidance panel
                return self._build_guidance_panel(spec, unresolved_intents)

        # Build the actual panel
        panel = Panel(
            title=spec.title,
            panel_type=self._panel_type_to_string(spec.panel_type),
            targets=targets,
            description=spec.description,
            unit=spec.unit,
            grid_pos={"h": spec.height, "w": spec.width, "x": 0, "y": 0},
        )

        # Gauge panels need min/max for correct rendering
        if spec.panel_type == PanelType.GAUGE:
            panel.min = 0
            if spec.unit == "percent":
                panel.max = 100
            elif spec.unit == "percentunit":
                panel.max = 1
            # Other units: omit max so Grafana auto-scales

        return panel

    def _resolve_intent(self, intent: str) -> ResolutionResult:
        """
        Resolve an intent to a metric, with caching.

        Args:
            intent: Intent name to resolve

        Returns:
            ResolutionResult with status and metric
        """
        if intent in self._resolution_results:
            return self._resolution_results[intent]

        if self.resolver:
            result = self.resolver.resolve(intent)
        else:
            # No resolver - use first candidate from intent definition as
            # a reasonable default so panels render with standard metric
            # names instead of being empty guidance shells.
            from nthlayer.dashboards.intents import get_intent

            intent_def = get_intent(intent)
            if intent_def and intent_def.candidates:
                result = ResolutionResult(
                    intent=intent,
                    status=ResolutionStatus.FALLBACK,
                    metric_name=intent_def.candidates[0],
                    message=f"No resolver; using default candidate: {intent_def.candidates[0]}",
                )
            else:
                result = ResolutionResult(
                    intent=intent,
                    status=ResolutionStatus.UNRESOLVED,
                    message="No resolver configured and no candidates defined",
                )

        self._resolution_results[intent] = result
        return result

    def _build_guidance_panel(self, spec: PanelSpec, unresolved_intents: List[str]) -> Panel:
        """
        Build a guidance panel for unresolved intents.

        Creates a panel that displays helpful guidance in Grafana's "No data"
        message area, making it clear what instrumentation is needed.

        Args:
            spec: Original panel specification
            unresolved_intents: List of intents that couldn't be resolved

        Returns:
            Panel with guidance for missing instrumentation
        """
        technology = unresolved_intents[0].split(".")[0] if unresolved_intents else self.name

        # Get exporter recommendation
        exporter_rec = None
        if self.resolver:
            exporter_rec = self.resolver.get_exporter_recommendation(technology)

        # Build short guidance for noValue display
        if exporter_rec:
            install_cmd = exporter_rec.helm or exporter_rec.docker or ""
            short_guidance = f"Install {exporter_rec.name}: {install_cmd}"
        else:
            short_guidance = f"Add metrics: {', '.join(unresolved_intents[:2])}"
            if len(unresolved_intents) > 2:
                short_guidance += f" (+{len(unresolved_intents) - 2} more)"

        # Build detailed content for description/tooltip
        lines = [
            f"### {spec.title} - Needs Instrumentation",
            "",
            "This panel requires metrics that aren't currently being collected.",
            "",
            "**Missing metrics:**",
        ]

        for intent in unresolved_intents:
            result = self._resolution_results.get(intent)
            if result:
                lines.append(f"- `{intent}`: {result.message}")
            else:
                lines.append(f"- `{intent}`")

        if exporter_rec:
            lines.extend(
                [
                    "",
                    "**To enable, install exporter:**",
                    "```",
                    exporter_rec.helm or exporter_rec.docker or "",
                    "```",
                    "",
                    f"[Documentation]({exporter_rec.docs_url})" if exporter_rec.docs_url else "",
                ]
            )

        lines.extend(
            [
                "",
                "**Or add custom metric in service YAML:**",
                "```yaml",
                "metrics:",
            ]
        )
        for intent in unresolved_intents:
            lines.append(f"  {intent}: your_custom_metric")
        lines.append("```")

        content = "\n".join(lines)

        # Create panel with guidance metadata for noValue configuration
        panel = Panel(
            title=f"{spec.title}",
            panel_type="stat",  # Use stat panel - it shows noValue message clearly
            targets=[],  # No targets = triggers noValue display
            description=content,
            unit=spec.unit,
            grid_pos={"h": spec.height, "w": spec.width, "x": 0, "y": 0},
        )

        # Add custom attribute for noValue message (used during SDK conversion)
        panel.no_value_message = short_guidance  # type: ignore[attr-defined]
        panel.is_guidance_panel = True  # type: ignore[attr-defined]

        return panel

    def _panel_type_to_string(self, panel_type: PanelType) -> str:
        """Convert PanelType enum to string for Panel model."""
        mapping = {
            PanelType.TIMESERIES: "timeseries",
            PanelType.GAUGE: "gauge",
            PanelType.STAT: "stat",
            PanelType.TABLE: "table",
            PanelType.HEATMAP: "heatmap",
            PanelType.TEXT: "text",
        }
        return mapping.get(panel_type, "timeseries")

    def get_resolution_summary(self) -> Dict[str, Any]:
        """
        Get summary of intent resolution for this template.

        Returns:
            Dict with resolution statistics
        """
        summary: Dict[str, Any] = {
            "total_intents": len(self._resolution_results),
            "resolved": 0,
            "fallback": 0,
            "unresolved": 0,
            "details": {},
        }

        for intent, result in self._resolution_results.items():
            if result.status == ResolutionStatus.RESOLVED:
                summary["resolved"] += 1
            elif result.status == ResolutionStatus.FALLBACK:
                summary["fallback"] += 1
            elif result.status == ResolutionStatus.UNRESOLVED:
                summary["unresolved"] += 1

            summary["details"][intent] = {
                "status": result.status.value,
                "metric": result.metric_name,
                "message": result.message,
            }

        return summary
