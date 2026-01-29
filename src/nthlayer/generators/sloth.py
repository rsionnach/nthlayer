"""
Sloth SLO generator.

Generates Sloth specification YAML from NthLayer service definitions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition
from nthlayer.specs.models import ServiceContext
from nthlayer.specs.parser import parse_service_file, render_resource_spec

logger = logging.getLogger(__name__)


@dataclass
class SlothGenerationResult:
    """Result of Sloth spec generation."""

    success: bool
    service: str
    output_file: Path | None = None
    slo_count: int = 0
    error: str | None = None


def generate_sloth_spec(
    service_file: str | Path, output_dir: str | Path, environment: str | None = None
) -> SlothGenerationResult:
    """
    Generate Sloth specification YAML from NthLayer service definition.

    Args:
        service_file: Path to NthLayer service YAML file
        output_dir: Directory to write Sloth spec
        environment: Optional environment name (dev, staging, prod)

    Returns:
        SlothGenerationResult with generation details

    Example:
        Input (services/payment-api.yaml):
            service:
              name: payment-api
              team: payments
              tier: critical
            resources:
              - kind: SLO
                name: availability
                spec:
                  objective: 99.9
                  window: 30d
                  indicator:
                    query: "..."

        Output (generated/sloth/payment-api.yaml):
            version: "prometheus/v1"
            service: "payment-api"
            labels:
              tier: "critical"
              team: "payments"
            slos:
              - name: "availability"
                objective: 99.9
                description: "99.9% availability"
                sli:
                  events:
                    error_query: "..."
                    total_query: "..."
                alerting:
                  name: PaymentAPIAvailability
                  labels:
                    tier: "critical"
                  page_alert:
                    labels:
                      severity: critical
    """
    try:
        # Parse service file with optional environment overrides
        service_context, resources = parse_service_file(service_file, environment=environment)

        # Filter SLO resources
        slo_resources = [r for r in resources if r.kind == "SLO"]

        if not slo_resources:
            return SlothGenerationResult(
                success=False,
                service=service_context.name,
                error="No SLO resources found in service definition",
            )

        # Build Sloth spec
        slos: list[dict[str, Any]] = []
        sloth_spec: dict[str, Any] = {
            "version": "prometheus/v1",
            "service": service_context.name,
            "labels": {
                "tier": service_context.tier,
                "team": service_context.team,
                "type": service_context.type,
            },
            "slos": slos,
        }

        # Convert each SLO resource to Sloth format
        for slo_resource in slo_resources:
            # Render spec with variable substitution
            rendered_spec = render_resource_spec(slo_resource)

            # Convert to Sloth SLO format
            sloth_slo = convert_to_sloth_slo(
                slo_resource.name or "default",
                rendered_spec,
                service_context,
            )

            slos.append(sloth_slo)

        # Write output
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{service_context.name}.yaml"
        with open(output_file, "w") as f:
            yaml.dump(sloth_spec, f, sort_keys=False, default_flow_style=False)

        return SlothGenerationResult(
            success=True,
            service=service_context.name,
            output_file=output_file,
            slo_count=len(slo_resources),
        )

    except Exception as e:
        logger.error("Sloth generation failed for %s: %s", service_file, e)
        return SlothGenerationResult(
            success=False,
            service="unknown",
            error=str(e),
        )


def generate_sloth_from_manifest(
    manifest: ReliabilityManifest, output_dir: str | Path
) -> SlothGenerationResult:
    """Generate Sloth specification from ReliabilityManifest.

    Args:
        manifest: ReliabilityManifest instance
        output_dir: Directory to write Sloth spec

    Returns:
        SlothGenerationResult with generation details
    """
    try:
        if not manifest.slos:
            return SlothGenerationResult(
                success=False,
                service=manifest.name,
                error="No SLOs found in manifest",
            )

        # Build Sloth spec
        slos: list[dict[str, Any]] = []
        sloth_spec: dict[str, Any] = {
            "version": "prometheus/v1",
            "service": manifest.name,
            "labels": {
                "tier": manifest.tier,
                "team": manifest.team,
                "type": manifest.type,
            },
            "slos": slos,
        }

        # Convert each SLO definition to Sloth format
        for slo in manifest.slos:
            sloth_slo = _convert_slo_definition_to_sloth(slo, manifest)
            slos.append(sloth_slo)

        # Write output
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{manifest.name}.yaml"
        with open(output_file, "w") as f:
            yaml.dump(sloth_spec, f, sort_keys=False, default_flow_style=False)

        return SlothGenerationResult(
            success=True,
            service=manifest.name,
            output_file=output_file,
            slo_count=len(manifest.slos),
        )

    except Exception as e:
        logger.error(
            "Sloth generation from manifest failed for %s: %s",
            manifest.name,
            e,
        )
        return SlothGenerationResult(
            success=False,
            service=manifest.name,
            error=str(e),
        )


def _convert_slo_definition_to_sloth(
    slo: SLODefinition,
    manifest: ReliabilityManifest,
) -> dict[str, Any]:
    """Convert SLODefinition to Sloth SLO format.

    Handles ${service} variable substitution in indicator queries.

    Args:
        slo: SLO definition from manifest
        manifest: Parent manifest for context (service name, tier)

    Returns:
        Sloth SLO dict
    """
    # Determine indicator type
    indicator_type = slo.slo_type or slo.name
    if not slo.slo_type:
        logger.debug(
            "SLO '%s' has no explicit slo_type, using name '%s' as type",
            slo.name,
            slo.name,
        )

    query = slo.indicator_query or ""
    if not query:
        logger.warning(
            "SLO '%s' in manifest '%s' has no indicator_query. "
            "Generated Sloth spec will have empty PromQL queries.",
            slo.name,
            manifest.name,
        )

    # Substitute template variables (matching legacy render_resource_spec behavior)
    query = query.replace("${service}", manifest.name)
    query = query.replace("${team}", manifest.team)
    query = query.replace("${tier}", manifest.tier)
    query = query.replace("${type}", manifest.type)

    # Build SLI based on indicator type
    indicator: dict[str, Any] = {
        "type": indicator_type,
        "query": query,
    }
    if "latency" in indicator_type:
        # Use target as threshold for latency SLOs
        indicator["threshold_ms"] = slo.target

    sli = convert_indicator_to_sli(indicator)

    # Build alerting config
    alerting = generate_alerting_config(
        slo.name,
        manifest.name,
        manifest.tier,
    )

    return {
        "name": slo.name,
        "objective": slo.target,
        "description": slo.description or f"{slo.target}% {slo.name.replace('-', ' ')}",
        "sli": sli,
        "alerting": alerting,
    }


def convert_to_sloth_slo(
    slo_name: str,
    spec: dict[str, Any],
    service_context: ServiceContext,
) -> dict[str, Any]:
    """
    Convert NthLayer SLO spec to Sloth SLO format.

    Args:
        slo_name: Name of the SLO
        spec: Rendered SLO spec with variables substituted
        service_context: Service context for labels

    Returns:
        Sloth SLO dict
    """
    objective = spec.get("objective", 99.9)
    indicator = spec.get("indicator", {})

    # Build SLI based on indicator type
    sli = convert_indicator_to_sli(indicator)

    # Build alerting config
    alerting = generate_alerting_config(
        slo_name,
        service_context.name,
        service_context.tier,
    )

    return {
        "name": slo_name,
        "objective": objective,
        "description": f"{objective}% {slo_name.replace('-', ' ')}",
        "sli": sli,
        "alerting": alerting,
    }


def convert_indicator_to_sli(indicator: dict[str, Any]) -> dict[str, Any]:
    """
    Convert NthLayer indicator to Sloth SLI format.

    Sloth SLI uses "events" model:
        - error_query: Query for bad events
        - total_query: Query for all events

    Args:
        indicator: Indicator spec from resource

    Returns:
        Sloth SLI dict
    """
    indicator_type = indicator.get("type", "availability")
    query = indicator.get("query", "")

    if indicator_type == "availability":
        # For availability, query should return success ratio
        # We need to convert to error/total format for Sloth
        return {
            "events": {
                "error_query": _extract_error_query(query),
                "total_query": _extract_total_query(query),
            }
        }

    elif indicator_type == "latency":
        # For latency, query should return p95/p99 value
        # Sloth needs error (over threshold) and total queries
        threshold_ms = indicator.get("threshold_ms", 1000)
        _percentile = indicator.get("percentile", 95)  # Reserved for future use

        return {
            "events": {
                "error_query": f"{query} > {threshold_ms / 1000.0}",
                "total_query": query.replace("histogram_quantile", "sum(rate") + ")",
            }
        }

    else:
        # Generic - assume query is already in correct format
        return {
            "events": {
                "error_query": indicator.get("error_query", ""),
                "total_query": indicator.get("total_query", query),
            }
        }


def _extract_error_query(availability_query: str) -> str:
    """
    Extract error query from availability query.

    Input: sum(rate(http[code!~"5.."]])) / sum(rate(http))
    Output: sum(rate(http[code=~"5.."]))
    """
    if not availability_query:
        return ""

    # For availability query, error is the complement
    # This is a simplification - may need enhancement
    parts = availability_query.split("/")
    if "code!~" in availability_query:
        # Has error exclusion - convert to inclusion
        return parts[0].strip().replace("code!~", "code=~")

    # Default: assume numerator is good events, need to invert
    return parts[0].strip()


def _extract_total_query(availability_query: str) -> str:
    """
    Extract total query from availability query.

    Input: sum(rate(http[code!~"5.."])) / sum(rate(http))
    Output: sum(rate(http))
    """
    if not availability_query:
        return ""

    parts = availability_query.split("/")
    if len(parts) > 1:
        return parts[1].strip()

    return availability_query


def generate_alerting_config(
    slo_name: str,
    service_name: str,
    tier: str,
) -> dict[str, Any]:
    """
    Generate Sloth alerting configuration.

    Creates multi-window, multi-burn-rate alerts based on tier.

    Args:
        slo_name: Name of the SLO
        service_name: Service name
        tier: Service tier (critical, standard, low)

    Returns:
        Sloth alerting config
    """
    # Alert name in PascalCase
    alert_name = "".join(
        word.capitalize() for word in service_name.replace("-", " ").split()
    ) + "".join(word.capitalize() for word in slo_name.replace("-", " ").split())

    # Page alert for critical services
    page_alert = None
    if tier == "critical":
        page_alert = {
            "labels": {
                "severity": "critical",
            },
            "annotations": {
                "summary": f"High error budget burn on {service_name}",
            },
        }

    # Ticket alert for all tiers
    ticket_alert = {
        "labels": {
            "severity": "warning",
        },
        "annotations": {
            "summary": f"Error budget burn on {service_name}",
        },
    }

    config = {
        "name": alert_name,
        "labels": {
            "tier": tier,
            "service": service_name,
        },
        "annotations": {
            "summary": f"SLO {slo_name} for {service_name}",
        },
        "ticket_alert": ticket_alert,
    }

    if page_alert:
        config["page_alert"] = page_alert

    return config
