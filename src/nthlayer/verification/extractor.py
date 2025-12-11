"""
Extract declared metrics from service.yaml to form the metric contract.
"""

from __future__ import annotations

import re
from typing import List

from nthlayer.specs.models import Resource

from .models import DeclaredMetric, MetricContract, MetricSource


def extract_metric_contract(
    service_name: str,
    resources: List[Resource],
) -> MetricContract:
    """
    Extract all declared metrics from service resources.

    Looks for metrics in:
    1. SLO indicator queries (critical)
    2. Observability.metrics declarations (optional)

    Args:
        service_name: Name of the service
        resources: List of resources from service.yaml

    Returns:
        MetricContract containing all declared metrics
    """
    contract = MetricContract(service_name=service_name)

    for resource in resources:
        if resource.kind == "SLO":
            metrics = _extract_slo_metrics(resource)
            contract.metrics.extend(metrics)
        elif resource.kind == "Observability":
            metrics = _extract_observability_metrics(resource)
            contract.metrics.extend(metrics)

    # Deduplicate by metric name (keep first occurrence)
    seen = set()
    unique_metrics = []
    for metric in contract.metrics:
        if metric.name not in seen:
            seen.add(metric.name)
            unique_metrics.append(metric)
    contract.metrics = unique_metrics

    return contract


def _extract_slo_metrics(resource: Resource) -> List[DeclaredMetric]:
    """Extract metrics from SLO indicator queries."""
    metrics = []
    spec = resource.spec or {}
    indicators = spec.get("indicators", [])

    for indicator in indicators:
        # Extract from success_ratio queries
        success_ratio = indicator.get("success_ratio", {})
        for query_key in ["total_query", "good_query", "error_query"]:
            query = success_ratio.get(query_key, "")
            if query:
                metric_names = _extract_metrics_from_query(query)
                for name in metric_names:
                    metrics.append(
                        DeclaredMetric(
                            name=name,
                            source=MetricSource.SLO_INDICATOR,
                            query=query,
                            resource_name=resource.name,
                        )
                    )

        # Extract from latency queries
        latency_query = indicator.get("latency_query", "")
        if latency_query:
            metric_names = _extract_metrics_from_query(latency_query)
            for name in metric_names:
                metrics.append(
                    DeclaredMetric(
                        name=name,
                        source=MetricSource.SLO_INDICATOR,
                        query=latency_query,
                        resource_name=resource.name,
                    )
                )

    return metrics


def _extract_observability_metrics(resource: Resource) -> List[DeclaredMetric]:
    """Extract metrics from Observability declarations."""
    metrics = []
    spec = resource.spec or {}
    declared_metrics = spec.get("metrics", [])

    for metric_name in declared_metrics:
        if isinstance(metric_name, str):
            metrics.append(
                DeclaredMetric(
                    name=metric_name,
                    source=MetricSource.OBSERVABILITY,
                    resource_name=resource.name,
                )
            )

    return metrics


def _extract_metrics_from_query(query: str) -> List[str]:
    """
    Extract metric names from a PromQL query.

    Handles common patterns:
    - rate(metric_name{labels}[5m])
    - sum(rate(metric_name{labels}[5m]))
    - histogram_quantile(0.99, rate(metric_name_bucket{labels}[5m]))

    Args:
        query: PromQL query string

    Returns:
        List of metric names found in the query
    """
    # Pattern to match metric names
    # Metric names: [a-zA-Z_:][a-zA-Z0-9_:]*
    # Must be followed by { or [ or ( or whitespace or end
    pattern = r"([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?:\{|\[|$)"

    # Find all matches
    matches = re.findall(pattern, query)

    # Filter out PromQL functions and keywords
    promql_keywords = {
        "sum",
        "rate",
        "irate",
        "increase",
        "histogram_quantile",
        "avg",
        "min",
        "max",
        "count",
        "stddev",
        "stdvar",
        "topk",
        "bottomk",
        "quantile",
        "count_values",
        "group",
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "bool",
        "and",
        "or",
        "unless",
        "offset",
        "vector",
        "scalar",
        "abs",
        "absent",
        "ceil",
        "floor",
        "round",
        "clamp",
        "clamp_max",
        "clamp_min",
        "day_of_month",
        "day_of_week",
        "days_in_month",
        "delta",
        "deriv",
        "exp",
        "hour",
        "idelta",
        "label_join",
        "label_replace",
        "ln",
        "log2",
        "log10",
        "minute",
        "month",
        "predict_linear",
        "resets",
        "sort",
        "sort_desc",
        "sqrt",
        "time",
        "timestamp",
        "year",
        "avg_over_time",
        "min_over_time",
        "max_over_time",
        "sum_over_time",
        "count_over_time",
        "quantile_over_time",
        "stddev_over_time",
        "stdvar_over_time",
        "last_over_time",
        "present_over_time",
        "changes",
        "le",  # histogram label
    }

    metrics = []
    for match in matches:
        if match.lower() not in promql_keywords and not match.startswith("__"):
            metrics.append(match)

    return metrics
