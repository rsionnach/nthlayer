"""
OpenSRM format parser.

Parses Service Reliability Manifest files in the OpenSRM format:

    apiVersion: srm/v1
    kind: ServiceReliabilityManifest
    metadata:
      name: payment-api
      team: payments
      tier: critical
    spec:
      type: api
      slos:
        availability:
          target: 99.95
          window: 30d

Produces a ReliabilityManifest for downstream generators.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

from nthlayer.specs.manifest import (
    Contract,
    Dependency,
    DependencyCriticality,
    DependencySLO,
    DeploymentConfig,
    DeploymentGates,
    ErrorBudgetGate,
    Instrumentation,
    Observability,
    Ownership,
    PagerDutyConfig,
    RecentIncidentsGate,
    ReliabilityManifest,
    RollbackConfig,
    SLOComplianceGate,
    SLODefinition,
    SourceFormat,
    TelemetryEvent,
)


class OpenSRMParseError(Exception):
    """Error parsing OpenSRM manifest."""

    pass


def is_opensrm_format(data: dict[str, Any]) -> bool:
    """
    Check if data is in OpenSRM format.

    OpenSRM format is identified by:
    - apiVersion: srm/v1
    - kind: ServiceReliabilityManifest
    """
    return data.get("apiVersion") == "srm/v1" and data.get("kind") == "ServiceReliabilityManifest"


def parse_opensrm(
    data: dict[str, Any],
    source_file: str | None = None,
) -> ReliabilityManifest:
    """
    Parse OpenSRM format data into a ReliabilityManifest.

    Args:
        data: Parsed YAML data in OpenSRM format
        source_file: Optional source file path for error messages

    Returns:
        ReliabilityManifest instance

    Raises:
        OpenSRMParseError: If the data is invalid
    """
    # Validate structure
    if not is_opensrm_format(data):
        raise OpenSRMParseError(
            "Invalid OpenSRM format. Expected apiVersion: srm/v1 and "
            "kind: ServiceReliabilityManifest"
        )

    metadata = data.get("metadata", {})
    spec = data.get("spec", {})

    # Parse required metadata fields
    name = metadata.get("name")
    if not name:
        raise OpenSRMParseError("metadata.name is required")

    team = metadata.get("team")
    if not team:
        raise OpenSRMParseError("metadata.team is required")

    tier = metadata.get("tier")
    if not tier:
        raise OpenSRMParseError("metadata.tier is required")

    # Parse required spec fields
    service_type = spec.get("type")
    if not service_type:
        raise OpenSRMParseError("spec.type is required")

    # Parse SLOs
    slos = _parse_slos(spec.get("slos", {}))

    # Parse dependencies
    dependencies = _parse_dependencies(spec.get("dependencies", []))

    # Parse ownership
    ownership = _parse_ownership(spec.get("ownership"))

    # Parse observability
    observability = _parse_observability(spec.get("observability"))

    # Parse deployment
    deployment = _parse_deployment(spec.get("deployment"))

    # Parse contract
    contract = _parse_contract(spec.get("contract"))

    # Parse instrumentation (for ai-gate)
    instrumentation = _parse_instrumentation(spec.get("instrumentation"))

    return ReliabilityManifest(
        # Metadata
        name=name,
        team=team,
        tier=tier,
        description=metadata.get("description"),
        labels=metadata.get("labels", {}),
        annotations=metadata.get("annotations", {}),
        # Spec
        type=service_type,
        slos=slos,
        dependencies=dependencies,
        ownership=ownership,
        observability=observability,
        deployment=deployment,
        contract=contract,
        # AI Gate
        instrumentation=instrumentation,
        # Source tracking
        source_format=SourceFormat.OPENSRM,
        source_file=source_file,
        raw_data=data,
    )


def parse_opensrm_file(file_path: str | Path) -> ReliabilityManifest:
    """
    Parse an OpenSRM manifest file.

    Args:
        file_path: Path to the YAML file

    Returns:
        ReliabilityManifest instance

    Raises:
        OpenSRMParseError: If the file is invalid
        FileNotFoundError: If the file doesn't exist
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {file_path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise OpenSRMParseError(f"Invalid YAML in {file_path}: {e}") from e

    if not isinstance(data, dict):
        raise OpenSRMParseError(f"Expected YAML object in {file_path}")

    return parse_opensrm(data, source_file=str(path))


# =============================================================================
# Internal Parsing Functions
# =============================================================================


def _parse_slos(slos_data: dict[str, Any]) -> list[SLODefinition]:
    """Parse SLOs from OpenSRM spec.slos section."""
    slos = []

    for name, config in slos_data.items():
        if not isinstance(config, dict):
            # Simple target value
            slos.append(SLODefinition(name=name, target=float(config)))
            continue

        # Full SLO definition
        target = config.get("target")
        if target is None:
            # Check for 'minimum' (throughput SLOs)
            target = config.get("minimum")
        if target is None:
            raise OpenSRMParseError(f"SLO '{name}' requires a target or minimum value")

        slo = SLODefinition(
            name=name,
            target=float(target),
            window=config.get("window", "30d"),
            slo_type=config.get("type"),
            unit=config.get("unit"),
            percentile=config.get("percentile"),
            indicator_query=config.get("query"),
            description=config.get("description"),
            labels=config.get("labels", {}),
        )
        slos.append(slo)

    return slos


def _parse_dependencies(deps_data: list[dict[str, Any]]) -> list[Dependency]:
    """Parse dependencies from OpenSRM spec.dependencies section."""
    dependencies = []

    for dep_data in deps_data:
        if not isinstance(dep_data, dict):
            continue

        name = dep_data.get("name")
        if not name:
            continue

        # Parse dependency SLO expectations
        slo = None
        if "slo" in dep_data:
            slo_data = dep_data["slo"]
            slo = DependencySLO(
                availability=slo_data.get("availability"),
                latency_p99=slo_data.get("latency_p99") or slo_data.get("latency", {}).get("p99"),
            )

        # Parse criticality
        criticality = None
        if "criticality" in dep_data:
            try:
                criticality = DependencyCriticality(dep_data["criticality"])
            except ValueError:
                logger.warning(
                    "Invalid dependency criticality '%s' for '%s', ignoring",
                    dep_data["criticality"],
                    name,
                )

        dep = Dependency(
            name=name,
            type=dep_data.get("type", "unknown"),
            critical=dep_data.get("critical", False),
            criticality=criticality,
            slo=slo,
            manifest=dep_data.get("manifest"),
            database_type=dep_data.get("database_type"),
        )
        dependencies.append(dep)

    return dependencies


def _parse_ownership(ownership_data: dict[str, Any] | None) -> Ownership | None:
    """Parse ownership from OpenSRM spec.ownership section."""
    if not ownership_data:
        return None

    team = ownership_data.get("team")
    if not team:
        return None

    # Parse PagerDuty config
    pagerduty = None
    if "pagerduty" in ownership_data:
        pd_data = ownership_data["pagerduty"]
        pagerduty = PagerDutyConfig(
            service_id=pd_data.get("service_id"),
            escalation_policy_id=pd_data.get("escalation_policy_id"),
        )

    return Ownership(
        team=team,
        slack=ownership_data.get("slack"),
        email=ownership_data.get("email"),
        escalation=ownership_data.get("escalation"),
        pagerduty=pagerduty,
        runbook=ownership_data.get("runbook"),
        documentation=ownership_data.get("documentation"),
    )


def _parse_observability(obs_data: dict[str, Any] | None) -> Observability | None:
    """Parse observability from OpenSRM spec.observability section."""
    if not obs_data:
        return None

    return Observability(
        metrics_prefix=obs_data.get("metrics_prefix"),
        logs_label=obs_data.get("logs_label"),
        traces_service=obs_data.get("traces_service"),
        prometheus_job=obs_data.get("prometheus_job"),
        labels=obs_data.get("labels", {}),
    )


def _parse_deployment(deploy_data: dict[str, Any] | None) -> DeploymentConfig | None:
    """Parse deployment from OpenSRM spec.deployment section."""
    if not deploy_data:
        return None

    # Parse gates
    gates = None
    if "gates" in deploy_data:
        gates_data = deploy_data["gates"]
        gates = DeploymentGates(
            error_budget=_parse_error_budget_gate(gates_data.get("error_budget")),
            slo_compliance=_parse_slo_compliance_gate(gates_data.get("slo_compliance")),
            recent_incidents=_parse_recent_incidents_gate(gates_data.get("recent_incidents")),
        )

    # Parse rollback
    rollback = None
    if "rollback" in deploy_data:
        rb_data = deploy_data["rollback"]
        rollback = RollbackConfig(
            automatic=rb_data.get("automatic", False),
            error_rate_increase=rb_data.get("criteria", {}).get("error_rate_increase"),
            latency_increase=rb_data.get("criteria", {}).get("latency_increase"),
        )

    return DeploymentConfig(
        environments=deploy_data.get("environments", []),
        gates=gates,
        rollback=rollback,
    )


def _parse_error_budget_gate(gate_data: dict[str, Any] | None) -> ErrorBudgetGate | None:
    """Parse error budget gate configuration."""
    if not gate_data:
        return None

    return ErrorBudgetGate(
        enabled=gate_data.get("enabled", True),
        threshold=gate_data.get("threshold"),
    )


def _parse_slo_compliance_gate(gate_data: dict[str, Any] | None) -> SLOComplianceGate | None:
    """Parse SLO compliance gate configuration."""
    if not gate_data:
        return None

    return SLOComplianceGate(
        threshold=gate_data.get("threshold", 0.99),
    )


def _parse_recent_incidents_gate(gate_data: dict[str, Any] | None) -> RecentIncidentsGate | None:
    """Parse recent incidents gate configuration."""
    if not gate_data:
        return None

    return RecentIncidentsGate(
        p1_max=gate_data.get("p1_max", 0),
        p2_max=gate_data.get("p2_max", 2),
        lookback=gate_data.get("lookback", "7d"),
    )


def _parse_contract(contract_data: dict[str, Any] | None) -> Contract | None:
    """Parse contract from OpenSRM spec.contract section."""
    if not contract_data:
        return None

    return Contract(
        availability=contract_data.get("availability"),
        latency=contract_data.get("latency"),
        judgment=contract_data.get("judgment"),
    )


def _parse_instrumentation(instr_data: dict[str, Any] | None) -> Instrumentation | None:
    """Parse instrumentation from OpenSRM spec.instrumentation section (ai-gate)."""
    if not instr_data:
        return None

    # Parse telemetry events
    events = []
    for event_data in instr_data.get("telemetry_events", []):
        if isinstance(event_data, dict):
            events.append(
                TelemetryEvent(
                    name=event_data.get("name", ""),
                    fields=event_data.get("fields", []),
                )
            )

    return Instrumentation(
        telemetry_events=events,
        feedback_loop=instr_data.get("feedback_loop"),
        ground_truth_source=instr_data.get("ground_truth_source"),
    )
