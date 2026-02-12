"""
Backstage entity generator.

Generates JSON artifacts that Backstage can consume to display NthLayer
reliability data (SLOs, error budgets, scorecard, deployment gate) in service pages.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nthlayer.scorecard.models import ScoreBand
from nthlayer.slos.gates import DeploymentGate, GateResult
from nthlayer.slos.models import DEFAULT_SLO_OBJECTIVE
from nthlayer.specs.loader import load_manifest
from nthlayer.specs.manifest import ReliabilityManifest

logger = logging.getLogger(__name__)

# Score band to letter grade mapping
BAND_TO_GRADE: dict[ScoreBand | str, str] = {
    ScoreBand.EXCELLENT: "A",
    ScoreBand.GOOD: "B",
    ScoreBand.FAIR: "C",
    ScoreBand.POOR: "D",
    ScoreBand.CRITICAL: "F",
    "excellent": "A",
    "good": "B",
    "fair": "C",
    "poor": "D",
    "critical": "F",
}


@dataclass
class BackstageGenerationResult:
    """Result of Backstage entity generation."""

    success: bool
    service: str
    output_file: Path | None = None
    slo_count: int = 0
    error: str | None = None


def generate_backstage_entity(
    service_file: str | Path,
    output_dir: str | Path,
    prometheus_url: str | None = None,
    environment: str | None = None,
) -> BackstageGenerationResult:
    """
    Generate Backstage entity JSON from NthLayer service definition.

    Supports both OpenSRM format (apiVersion: srm/v1) and legacy NthLayer
    format (service: + resources:) with automatic detection.

    Args:
        service_file: Path to NthLayer service YAML file (OpenSRM or legacy format)
        output_dir: Directory to write Backstage entity JSON
        prometheus_url: Optional Prometheus URL for live data (not used in static mode)
        environment: Optional environment name (dev, staging, prod)

    Returns:
        BackstageGenerationResult with generation details

    Example:
        # OpenSRM format (recommended)
        result = generate_backstage_entity("payment-api.reliability.yaml", "generated/")

        # Legacy format (still supported)
        result = generate_backstage_entity("services/payment-api.yaml", "generated/")
    """
    try:
        # Load manifest with auto-format detection (OpenSRM or legacy)
        manifest = load_manifest(
            service_file,
            environment=environment,
            suppress_deprecation_warning=True,  # Don't warn during generation
        )

        # Build the Backstage entity from the unified manifest
        entity = _build_backstage_entity_from_manifest(manifest)

        # Write output
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "backstage.json"
        with open(output_file, "w") as f:
            json.dump(entity, f, indent=2)

        return BackstageGenerationResult(
            success=True,
            service=manifest.name,
            output_file=output_file,
            slo_count=len(manifest.slos),
        )

    except Exception as e:
        logger.error("Backstage generation failed for %s: %s", service_file, e)
        return BackstageGenerationResult(
            success=False,
            service="unknown",
            error=str(e),
        )


def generate_backstage_from_manifest(
    manifest: ReliabilityManifest, output_dir: str | Path
) -> BackstageGenerationResult:
    """Generate Backstage entity JSON from ReliabilityManifest.

    Args:
        manifest: ReliabilityManifest instance
        output_dir: Directory to write Backstage entity JSON

    Returns:
        BackstageGenerationResult with generation details
    """
    try:
        # Build the Backstage entity from manifest
        entity = _build_backstage_entity_from_manifest(manifest)

        # Write output
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "backstage.json"
        with open(output_file, "w") as f:
            json.dump(entity, f, indent=2)

        return BackstageGenerationResult(
            success=True,
            service=manifest.name,
            output_file=output_file,
            slo_count=len(manifest.slos),
        )

    except Exception as e:
        logger.error(
            "Backstage generation from manifest failed for %s: %s",
            manifest.name,
            e,
        )
        return BackstageGenerationResult(
            success=False,
            service=manifest.name,
            error=str(e),
        )


def _build_backstage_entity(
    service_context: Any,
    resources: list[Any],
    source_file: str | Path,
) -> dict[str, Any]:
    """Build Backstage entity dict from service context and resources."""
    now = datetime.now(timezone.utc)

    # Extract SLO resources
    slo_resources = [r for r in resources if r.kind == "SLO"]

    # Build service section
    service_section = {
        "name": service_context.name,
        "team": service_context.team,
        "tier": service_context.tier,
        "type": service_context.type,
        "description": None,
        "supportModel": getattr(service_context, "support_model", "self"),
    }

    # Build SLOs section
    slos = []
    for slo_resource in slo_resources:
        spec = slo_resource.spec
        slo_entry = {
            "name": slo_resource.name,
            "target": spec.get("objective", DEFAULT_SLO_OBJECTIVE),
            "window": spec.get("window", "30d"),
            "sloType": spec.get("indicator", {}).get("type"),
            "description": spec.get("description"),
            "currentValue": None,  # Static generation - no live data
            "status": None,
        }
        slos.append(slo_entry)

    # Build deployment gate section with default thresholds
    gate = DeploymentGate()
    thresholds = gate.get_threshold_for_tier(service_context.tier)

    deployment_gate: dict[str, Any] = {
        "status": "APPROVED",  # Default for static generation
        "message": None,
        "budgetRemainingPercent": None,  # No live data
        "warningThreshold": thresholds.get("warning"),
        "blockingThreshold": thresholds.get("blocking"),
        "recommendations": [],
    }

    # Build links section
    grafana_url = os.environ.get("NTHLAYER_GRAFANA_URL", "")
    links = {
        "grafanaDashboard": f"{grafana_url}/d/{service_context.name}" if grafana_url else None,
        "runbook": None,
        "serviceManifest": str(source_file),
        "slothSpec": f"generated/{service_context.name}/sloth/{service_context.name}.yaml",
        "alertsYaml": f"generated/{service_context.name}/alerts.yaml",
    }

    return {
        "schemaVersion": "v1",
        "generatedAt": now.isoformat(),
        "service": service_section,
        "slos": slos,
        "errorBudget": {
            "totalMinutes": None,
            "consumedMinutes": None,
            "remainingMinutes": None,
            "remainingPercent": None,
            "burnRate": None,
            "status": None,
        },
        "score": {
            "score": None,
            "grade": None,
            "band": None,
            "trend": None,
            "components": {
                "sloCompliance": None,
                "incidentScore": None,
                "deploySuccessRate": None,
                "errorBudgetRemaining": None,
            },
        },
        "deploymentGate": deployment_gate,
        "links": links,
    }


def _build_backstage_entity_from_manifest(
    manifest: ReliabilityManifest,
) -> dict[str, Any]:
    """Build Backstage entity dict from ReliabilityManifest."""
    now = datetime.now(timezone.utc)

    # Build service section
    service_section = {
        "name": manifest.name,
        "team": manifest.team,
        "tier": manifest.tier,
        "type": manifest.type,
        "description": manifest.description,
        "supportModel": manifest.support_model,
    }

    # Build SLOs section
    slos = []
    for slo in manifest.slos:
        slo_entry = {
            "name": slo.name,
            "target": slo.target,
            "window": slo.window,
            "sloType": slo.slo_type,
            "description": slo.description,
            "currentValue": None,  # Static generation - no live data
            "status": None,
        }
        slos.append(slo_entry)

    # Build deployment gate section with default thresholds
    gate = DeploymentGate()
    thresholds = gate.get_threshold_for_tier(manifest.tier)

    deployment_gate: dict[str, Any] = {
        "status": "APPROVED",  # Default for static generation
        "message": None,
        "budgetRemainingPercent": None,  # No live data
        "warningThreshold": thresholds.get("warning"),
        "blockingThreshold": thresholds.get("blocking"),
        "recommendations": [],
    }

    # Build links section
    grafana_url = os.environ.get("NTHLAYER_GRAFANA_URL", "")
    runbook_url = None
    if manifest.ownership and manifest.ownership.runbook:
        runbook_url = manifest.ownership.runbook

    links = {
        "grafanaDashboard": f"{grafana_url}/d/{manifest.name}" if grafana_url else None,
        "runbook": runbook_url,
        "serviceManifest": manifest.source_file,
        "slothSpec": f"generated/{manifest.name}/sloth/{manifest.name}.yaml",
        "alertsYaml": f"generated/{manifest.name}/alerts.yaml",
    }

    return {
        "schemaVersion": "v1",
        "generatedAt": now.isoformat(),
        "service": service_section,
        "slos": slos,
        "errorBudget": {
            "totalMinutes": None,
            "consumedMinutes": None,
            "remainingMinutes": None,
            "remainingPercent": None,
            "burnRate": None,
            "status": None,
        },
        "score": {
            "score": None,
            "grade": None,
            "band": None,
            "trend": None,
            "components": {
                "sloCompliance": None,
                "incidentScore": None,
                "deploySuccessRate": None,
                "errorBudgetRemaining": None,
            },
        },
        "deploymentGate": deployment_gate,
        "links": links,
    }


def band_to_grade(band: ScoreBand | str | None) -> str | None:
    """Convert ScoreBand to letter grade.

    Args:
        band: ScoreBand enum or string value

    Returns:
        Letter grade (A-F) or None if band is None
    """
    if band is None:
        return None
    return BAND_TO_GRADE.get(band)


def gate_result_to_status(result: GateResult) -> str:
    """Convert GateResult enum to Backstage status string.

    Args:
        result: GateResult enum value

    Returns:
        Status string: APPROVED, WARNING, or BLOCKED
    """
    mapping = {
        GateResult.APPROVED: "APPROVED",
        GateResult.WARNING: "WARNING",
        GateResult.BLOCKED: "BLOCKED",
    }
    return mapping.get(result, "APPROVED")
