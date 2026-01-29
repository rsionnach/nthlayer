"""
Metrics Recommendation Engine.

Generates metric recommendations for services based on their type and runtime,
and validates coverage against discovered metrics from Prometheus.
"""

from __future__ import annotations

import logging

from nthlayer.metrics.models import (
    MetricDefinition,
    MetricMatch,
    MetricRecommendation,
)
from nthlayer.metrics.runtime import get_runtime_metrics
from nthlayer.metrics.standards.aliases import METRIC_ALIASES, get_aliases_for_canonical
from nthlayer.metrics.templates.registry import get_template, resolve_template_metrics
from nthlayer.specs.manifest import ReliabilityManifest
from nthlayer.specs.models import ServiceContext  # Used by recommend_metrics

logger = logging.getLogger(__name__)


def recommend_metrics_from_manifest(
    manifest: ReliabilityManifest,
    discovered_metrics: list[str] | None = None,
) -> MetricRecommendation:
    """Generate metric recommendations from ReliabilityManifest.

    Args:
        manifest: ReliabilityManifest instance
        discovered_metrics: List of metric names discovered from Prometheus

    Returns:
        MetricRecommendation with matched metrics and coverage stats
    """
    context = manifest.as_service_context()
    return recommend_metrics(context, discovered_metrics)


def recommend_metrics(
    context: ServiceContext,
    discovered_metrics: list[str] | None = None,
) -> MetricRecommendation:
    """
    Generate metric recommendations for a service.

    1. Load template for service type
    2. Resolve inherited metrics (e.g., gateway extends api)
    3. Add runtime-specific metrics if language specified
    4. Match discovered metrics against template using aliases
    5. Return recommendations with coverage stats

    Args:
        context: Service context with name, type, tier, language
        discovered_metrics: List of metric names discovered from Prometheus

    Returns:
        MetricRecommendation with matched metrics and coverage stats
    """
    # Get template for service type
    template = get_template(context.type)
    if not template:
        # Fall back to API template as default
        template = get_template("api")

    if not template:
        # No template available - cannot assess coverage
        logger.warning(
            "No metric template found for service type '%s' "
            "(service: %s). Coverage cannot be assessed.",
            context.type,
            context.name,
        )
        return MetricRecommendation(
            service=context.name,
            service_type=context.type,
            tier=context.tier,
            runtime=context.language,
            required=[],
            recommended=[],
            runtime_metrics=[],
            required_coverage=0.0,
            recommended_coverage=0.0,
            slo_ready=False,
        )

    # Resolve metrics with inheritance
    required_defs = resolve_template_metrics(template, "required")
    recommended_defs = resolve_template_metrics(template, "recommended")

    # Get runtime-specific metrics
    runtime_defs = get_runtime_metrics(context.language)

    # Match against discovered metrics
    required_matches = _match_metrics(required_defs, discovered_metrics)
    recommended_matches = _match_metrics(recommended_defs, discovered_metrics)
    runtime_matches = _match_metrics(runtime_defs, discovered_metrics)

    # Calculate coverage
    required_found = sum(1 for m in required_matches if m.status in ("found", "aliased"))
    recommended_found = sum(1 for m in recommended_matches if m.status in ("found", "aliased"))

    if required_matches:
        required_coverage = required_found / len(required_matches)
    else:
        required_coverage = 1.0

    if recommended_matches:
        recommended_coverage = recommended_found / len(recommended_matches)
    else:
        recommended_coverage = 1.0

    return MetricRecommendation(
        service=context.name,
        service_type=template.name,  # Use canonical template name
        tier=context.tier,
        runtime=context.language,
        required=required_matches,
        recommended=recommended_matches,
        runtime_metrics=runtime_matches,
        required_coverage=required_coverage,
        recommended_coverage=recommended_coverage,
        slo_ready=required_found == len(required_matches),
    )


def _match_metrics(
    definitions: list[MetricDefinition],
    discovered: list[str] | None,
) -> list[MetricMatch]:
    """
    Match discovered metrics to metric definitions.

    Uses alias mapping to match common Prometheus metric names
    to OTel canonical names.

    Args:
        definitions: List of metric definitions to match
        discovered: List of discovered metric names from Prometheus

    Returns:
        List of MetricMatch with status and confidence
    """
    if discovered is None:
        # No discovery performed - mark all as unknown
        return [MetricMatch(definition=d, status="unknown") for d in definitions]

    # Normalize discovered metrics to lowercase for matching
    discovered_set = {m.lower() for m in discovered}
    discovered_original = {m.lower(): m for m in discovered}

    results: list[MetricMatch] = []

    for defn in definitions:
        match = MetricMatch(definition=defn)
        canonical_lower = defn.name.lower()

        # 1. Direct match (OTel name found in Prometheus)
        if canonical_lower in discovered_set:
            match.found_as = discovered_original.get(canonical_lower, defn.name)
            match.status = "found"
            match.match_confidence = 1.0
        else:
            # 2. Check if any known aliases are present
            aliases = get_aliases_for_canonical(defn.name)
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in discovered_set:
                    match.found_as = discovered_original.get(alias_lower, alias)
                    match.status = "aliased"
                    match.match_confidence = 0.9
                    break

            # 3. Check reverse alias lookup (discovered name maps to this canonical)
            if match.status == "missing":
                for discovered_name in discovered:
                    canonical = METRIC_ALIASES.get(discovered_name)
                    if canonical and canonical.lower() == canonical_lower:
                        match.found_as = discovered_name
                        match.status = "aliased"
                        match.match_confidence = 0.9
                        break

            # 4. Fuzzy matching for similar names (partial match)
            if match.status == "missing":
                # Convert OTel dotted name to potential Prometheus format
                prometheus_style = defn.name.replace(".", "_").lower()
                for discovered_name in discovered:
                    discovered_lower = discovered_name.lower()
                    # Check if the Prometheus-style name is a substring
                    if prometheus_style in discovered_lower or discovered_lower in prometheus_style:
                        match.found_as = discovered_name
                        match.status = "aliased"
                        match.match_confidence = 0.7
                        break

        results.append(match)

    return results


def get_missing_required_metrics(recommendation: MetricRecommendation) -> list[MetricDefinition]:
    """
    Get list of missing required metrics.

    Args:
        recommendation: Metric recommendation result

    Returns:
        List of MetricDefinition for missing required metrics
    """
    return [match.definition for match in recommendation.required if match.status == "missing"]


def get_slo_blocking_metrics(recommendation: MetricRecommendation) -> list[MetricDefinition]:
    """
    Get metrics that block SLO creation.

    Returns required metrics with slo_usage that are missing.

    Args:
        recommendation: Metric recommendation result

    Returns:
        List of MetricDefinition that block SLOs
    """
    return [
        match.definition
        for match in recommendation.required
        if match.status == "missing" and match.definition.slo_usage
    ]


def filter_metrics_by_level(
    recommendation: MetricRecommendation,
    level: str,
) -> list[MetricMatch]:
    """
    Filter recommendation results by requirement level.

    Args:
        recommendation: Metric recommendation result
        level: Filter level ('required', 'recommended', 'all')

    Returns:
        Filtered list of MetricMatch
    """
    if level == "required":
        return recommendation.required
    elif level == "recommended":
        return recommendation.recommended
    else:  # 'all'
        return recommendation.required + recommendation.recommended + recommendation.runtime_metrics
