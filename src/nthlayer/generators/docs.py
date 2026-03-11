"""
Service documentation generator.

Generates Markdown documentation from ReliabilityManifest metadata:
- README.md with ownership, architecture, SLOs, dependencies, deployment sections
- ADR scaffolding (template + initial architecture decision)
- API documentation stubs matched to service type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from nthlayer.specs.loader import load_manifest
from nthlayer.specs.manifest import ReliabilityManifest

logger = structlog.get_logger()


@dataclass
class DocsGenerationResult:
    """Result of documentation generation."""

    success: bool
    service: str
    files_generated: list[str] = field(default_factory=list)
    output_dir: Path | None = None
    error: str | None = None


def generate_service_docs(
    service_file: str | Path,
    output_dir: str | Path,
    environment: str | None = None,
    include_adr: bool = False,
    include_api: bool = False,
) -> DocsGenerationResult:
    """
    Generate documentation files from a service reliability manifest.

    Args:
        service_file: Path to service YAML file (OpenSRM or legacy format)
        output_dir: Directory to write generated documentation
        environment: Optional environment name (dev, staging, prod)
        include_adr: Generate ADR scaffold in adr/ subdirectory
        include_api: Generate API documentation stub

    Returns:
        DocsGenerationResult with generation details
    """
    try:
        manifest = load_manifest(
            service_file,
            environment=environment,
            suppress_deprecation_warning=True,
        )

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        files_generated: list[str] = []

        # Always generate README
        readme_content = _generate_readme(manifest)
        readme_file = output_path / "README.md"
        readme_file.write_text(readme_content)
        files_generated.append("README.md")

        # Optional ADR scaffold
        if include_adr:
            adr_files = _generate_adr_scaffold(manifest, output_path)
            files_generated.extend(adr_files)

        # Optional API docs
        if include_api:
            api_content = _generate_api_docs(manifest)
            api_file = output_path / "api.md"
            api_file.write_text(api_content)
            files_generated.append("api.md")

        logger.info(
            "docs_generated",
            service=manifest.name,
            files=files_generated,
            output_dir=str(output_path),
        )

        return DocsGenerationResult(
            success=True,
            service=manifest.name,
            files_generated=files_generated,
            output_dir=output_path,
        )

    except Exception as e:
        logger.error("docs_generation_failed", err=str(e), exc_info=True)
        return DocsGenerationResult(
            success=False,
            service="unknown",
            error=str(e),
        )


def generate_docs_from_manifest(
    manifest: ReliabilityManifest,
    output_dir: str | Path,
    include_adr: bool = False,
    include_api: bool = False,
) -> DocsGenerationResult:
    """Generate documentation from an already-loaded ReliabilityManifest.

    Args:
        manifest: ReliabilityManifest instance
        output_dir: Directory to write generated documentation
        include_adr: Generate ADR scaffold
        include_api: Generate API documentation stub

    Returns:
        DocsGenerationResult with generation details
    """
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        files_generated: list[str] = []

        readme_content = _generate_readme(manifest)
        readme_file = output_path / "README.md"
        readme_file.write_text(readme_content)
        files_generated.append("README.md")

        if include_adr:
            adr_files = _generate_adr_scaffold(manifest, output_path)
            files_generated.extend(adr_files)

        if include_api:
            api_content = _generate_api_docs(manifest)
            api_file = output_path / "api.md"
            api_file.write_text(api_content)
            files_generated.append("api.md")

        return DocsGenerationResult(
            success=True,
            service=manifest.name,
            files_generated=files_generated,
            output_dir=output_path,
        )

    except Exception as e:
        logger.error(
            "docs_generation_from_manifest_failed",
            service=manifest.name,
            err=str(e),
            exc_info=True,
        )
        return DocsGenerationResult(
            success=False,
            service=manifest.name,
            error=str(e),
        )


def _generate_readme(manifest: ReliabilityManifest) -> str:
    """Generate README.md content from manifest metadata."""
    sections: list[str] = []

    # Title
    if manifest.description:
        sections.append(f"# {manifest.name}\n\n{manifest.description}")
    else:
        sections.append(f"# {manifest.name}")

    # Ownership
    sections.append(_readme_ownership_section(manifest))

    # Architecture
    sections.append(_readme_architecture_section(manifest))

    # SLOs
    if manifest.slos:
        sections.append(_readme_slos_section(manifest))

    # Dependencies
    if manifest.dependencies:
        sections.append(_readme_dependencies_section(manifest))

    # Deployment
    sections.append(_readme_deployment_section(manifest))

    # APIs
    sections.append(_readme_apis_section(manifest))

    # Runbook
    sections.append(_readme_runbook_section(manifest))

    return "\n\n".join(sections) + "\n"


def _readme_ownership_section(manifest: ReliabilityManifest) -> str:
    """Build the Ownership section."""
    lines = ["## Ownership", ""]
    lines.append("| Field | Value |")
    lines.append("| ----- | ----- |")
    lines.append(f"| Team | {manifest.team} |")

    if manifest.ownership:
        own = manifest.ownership
        if own.slack:
            lines.append(f"| Slack | {own.slack} |")
        if own.email:
            lines.append(f"| Email | {own.email} |")
        if own.escalation:
            lines.append(f"| Escalation | {own.escalation} |")
        if own.pagerduty and own.pagerduty.escalation_policy_id:
            lines.append(f"| PagerDuty | {own.pagerduty.escalation_policy_id} |")
        if own.runbook:
            lines.append(f"| Runbook | {own.runbook} |")
    return "\n".join(lines)


def _readme_architecture_section(manifest: ReliabilityManifest) -> str:
    """Build the Architecture section."""
    lines = ["## Architecture", ""]
    lines.append("| Property | Value |")
    lines.append("| -------- | ----- |")
    lines.append(f"| Tier | {manifest.tier} |")
    lines.append(f"| Type | {manifest.type} |")
    lines.append(f"| Support Model | {manifest.support_model} |")

    if manifest.observability:
        obs = manifest.observability
        if obs.metrics_prefix:
            lines.append(f"| Metrics Prefix | {obs.metrics_prefix} |")
        if obs.prometheus_job:
            lines.append(f"| Prometheus Job | {obs.prometheus_job} |")
        if obs.grafana_url:
            lines.append(f"| Grafana | {obs.grafana_url} |")

    if manifest.dependencies:
        lines.append(f"| Dependencies | {len(manifest.dependencies)} |")

    return "\n".join(lines)


def _readme_slos_section(manifest: ReliabilityManifest) -> str:
    """Build the SLOs section."""
    lines = ["## SLOs", ""]
    lines.append("| Name | Target | Window | Type |")
    lines.append("| ---- | ------ | ------ | ---- |")
    for slo in manifest.slos:
        slo_type = slo.slo_type or "-"
        lines.append(f"| {slo.name} | {slo.target} | {slo.window} | {slo_type} |")
    return "\n".join(lines)


def _readme_dependencies_section(manifest: ReliabilityManifest) -> str:
    """Build the Dependencies section."""
    lines = ["## Dependencies", ""]
    lines.append("| Name | Type | Critical | SLO Availability |")
    lines.append("| ---- | ---- | -------- | ---------------- |")
    for dep in manifest.dependencies:
        critical = "Yes" if dep.critical else "No"
        avail = str(dep.slo.availability) if dep.slo and dep.slo.availability else "-"
        lines.append(f"| {dep.name} | {dep.type} | {critical} | {avail} |")
    return "\n".join(lines)


def _readme_deployment_section(manifest: ReliabilityManifest) -> str:
    """Build the Deployment section."""
    lines = ["## Deployment", ""]

    if manifest.deployment:
        deploy = manifest.deployment
        if deploy.environments:
            lines.append(f"**Environments:** {', '.join(deploy.environments)}")
            lines.append("")

        if deploy.gates:
            lines.append("**Gates:**")
            lines.append("")
            gates = deploy.gates
            if gates.error_budget:
                enabled = "enabled" if gates.error_budget.enabled else "disabled"
                threshold = gates.error_budget.threshold
                threshold_str = f" (threshold: {threshold})" if threshold else ""
                lines.append(f"- Error Budget: {enabled}{threshold_str}")
            if gates.slo_compliance:
                lines.append(f"- SLO Compliance: threshold {gates.slo_compliance.threshold}")
            if gates.recent_incidents:
                ri = gates.recent_incidents
                lines.append(
                    f"- Recent Incidents: P1 max {ri.p1_max}, P2 max {ri.p2_max} (lookback: {ri.lookback})"
                )

        if deploy.rollback and deploy.rollback.automatic:
            lines.append("")
            lines.append("**Rollback:** automatic")
    else:
        lines.append("No deployment configuration defined.")

    return "\n".join(lines)


def _readme_apis_section(manifest: ReliabilityManifest) -> str:
    """Build the APIs section."""
    lines = ["## APIs", ""]

    if manifest.observability and manifest.observability.grafana_url:
        lines.append(f"Dashboard: [{manifest.name}]({manifest.observability.grafana_url})")
        lines.append("")

    lines.append("<!-- TODO: Add API endpoint documentation -->")
    return "\n".join(lines)


def _readme_runbook_section(manifest: ReliabilityManifest) -> str:
    """Build the Runbook section."""
    lines = ["## Runbook", ""]

    if manifest.ownership and manifest.ownership.runbook:
        lines.append(f"[Runbook]({manifest.ownership.runbook})")
    else:
        lines.append("<!-- TODO: Add runbook link -->")

    return "\n".join(lines)


def _generate_adr_scaffold(manifest: ReliabilityManifest, output_dir: Path) -> list[str]:
    """Generate ADR directory with template and initial decision record."""
    adr_dir = output_dir / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)

    files: list[str] = []

    # ADR index
    index_content = _adr_index(manifest)
    (adr_dir / "README.md").write_text(index_content)
    files.append("adr/README.md")

    # ADR template
    template_content = _adr_template()
    (adr_dir / "template.md").write_text(template_content)
    files.append("adr/template.md")

    # Initial architecture ADR
    adr001_content = _adr_initial_architecture(manifest)
    (adr_dir / "001-initial-architecture.md").write_text(adr001_content)
    files.append("adr/001-initial-architecture.md")

    return files


def _adr_index(manifest: ReliabilityManifest) -> str:
    """Generate ADR index README."""
    return f"""# Architecture Decision Records — {manifest.name}

This directory contains architecture decision records (ADRs) for the {manifest.name} service.

## Index

| ID | Title | Status |
| -- | ----- | ------ |
| 001 | [Initial Architecture](001-initial-architecture.md) | Accepted |

## Creating a New ADR

Copy `template.md` and increment the ID number.
"""


def _adr_template() -> str:
    """Generate blank ADR template."""
    return """# ADR-NNN: Title

## Status

Proposed

## Context

What is the issue that we're seeing that is motivating this decision or change?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?
"""


def _adr_initial_architecture(manifest: ReliabilityManifest) -> str:
    """Generate initial architecture ADR from manifest data."""
    lines = [
        f"# ADR-001: Initial Architecture for {manifest.name}",
        "",
        "## Status",
        "",
        "Accepted",
        "",
        "## Context",
        "",
        f"{manifest.name} is a **{manifest.tier}**-tier **{manifest.type}** service "
        f"owned by the **{manifest.team}** team.",
    ]

    if manifest.dependencies:
        dep_names = [d.name for d in manifest.dependencies]
        lines.append(f"It depends on: {', '.join(dep_names)}.")

    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- **Tier:** {manifest.tier} — "
            f"{'requires highest reliability guarantees' if manifest.tier == 'critical' else 'standard reliability requirements'}",
        ]
    )

    if manifest.slos:
        lines.append("- **SLO targets:**")
        for slo in manifest.slos:
            lines.append(f"  - {slo.name}: {slo.target} ({slo.window} window)")

    if manifest.dependencies:
        critical_deps = [d for d in manifest.dependencies if d.critical]
        if critical_deps:
            names = ", ".join(d.name for d in critical_deps)
            lines.append(f"- **Critical dependencies:** {names}")

    lines.extend(
        [
            "",
            "## Consequences",
            "",
            "- Service must maintain SLO targets as defined above",
            "- Deployment gates enforce error budget thresholds before release",
        ]
    )

    if manifest.tier in ("critical", "high"):
        lines.append("- On-call rotation required for this tier level")

    lines.append("")
    return "\n".join(lines)


def _generate_api_docs(manifest: ReliabilityManifest) -> str:
    """Generate API documentation stub matched to service type."""
    if manifest.type in ("api", "web"):
        return _api_docs_http(manifest)
    elif manifest.type in ("worker", "batch"):
        return _api_docs_worker(manifest)
    elif manifest.type == "stream":
        return _api_docs_stream(manifest)
    elif manifest.type == "database":
        return _api_docs_database(manifest)
    elif manifest.type == "ai-gate":
        return _api_docs_ai_gate(manifest)
    else:
        return _api_docs_http(manifest)


def _api_docs_http(manifest: ReliabilityManifest) -> str:
    """HTTP endpoint documentation scaffold."""
    lines = [
        f"# API Documentation — {manifest.name}",
        "",
        "## Endpoints",
        "",
        "<!-- TODO: Document API endpoints -->",
        "",
        "### Health Check",
        "",
        "```",
        "GET /health",
        "```",
        "",
        "Returns service health status.",
        "",
        "### Example Endpoint",
        "",
        "```",
        "GET /api/v1/resource",
        "```",
        "",
        "<!-- TODO: Add request/response examples -->",
    ]

    if manifest.slos:
        lines.extend(["", "## SLO Expectations", ""])
        for slo in manifest.slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")

    lines.append("")
    return "\n".join(lines)


def _api_docs_worker(manifest: ReliabilityManifest) -> str:
    """Worker/batch job documentation scaffold."""
    lines = [
        f"# Job Documentation — {manifest.name}",
        "",
        "## Jobs",
        "",
        "<!-- TODO: Document job types and their inputs/outputs -->",
        "",
        "### Example Job",
        "",
        "| Property | Value |",
        "| -------- | ----- |",
        "| Queue | <!-- TODO --> |",
        "| Concurrency | <!-- TODO --> |",
        "| Timeout | <!-- TODO --> |",
        "| Retry Policy | <!-- TODO --> |",
    ]

    if manifest.slos:
        lines.extend(["", "## SLO Expectations", ""])
        for slo in manifest.slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")

    lines.append("")
    return "\n".join(lines)


def _api_docs_stream(manifest: ReliabilityManifest) -> str:
    """Event stream documentation scaffold."""
    lines = [
        f"# Event Documentation — {manifest.name}",
        "",
        "## Events",
        "",
        "<!-- TODO: Document event schemas -->",
        "",
        "### Example Event",
        "",
        "```json",
        "{",
        '  "type": "example.event",',
        '  "data": {}',
        "}",
        "```",
    ]

    if manifest.slos:
        lines.extend(["", "## SLO Expectations", ""])
        for slo in manifest.slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")

    lines.append("")
    return "\n".join(lines)


def _api_docs_database(manifest: ReliabilityManifest) -> str:
    """Database documentation scaffold."""
    lines = [
        f"# Database Documentation — {manifest.name}",
        "",
        "## Schema",
        "",
        "<!-- TODO: Document database schema -->",
        "",
        "## Access Patterns",
        "",
        "<!-- TODO: Document primary access patterns and queries -->",
    ]

    if manifest.slos:
        lines.extend(["", "## SLO Expectations", ""])
        for slo in manifest.slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")

    lines.append("")
    return "\n".join(lines)


def _api_docs_ai_gate(manifest: ReliabilityManifest) -> str:
    """AI gate documentation scaffold."""
    lines = [
        f"# AI Gate Documentation — {manifest.name}",
        "",
        "## Decision Endpoints",
        "",
        "<!-- TODO: Document decision API endpoints -->",
        "",
        "### Example Decision Request",
        "",
        "```json",
        "{",
        '  "input": {},',
        '  "context": {}',
        "}",
        "```",
        "",
        "## Judgment SLOs",
        "",
    ]

    judgment_slos = manifest.get_judgment_slos()
    if judgment_slos:
        for slo in judgment_slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")
    else:
        lines.append("<!-- TODO: Define judgment SLOs -->")

    standard_slos = manifest.get_standard_slos()
    if standard_slos:
        lines.extend(["", "## Standard SLOs", ""])
        for slo in standard_slos:
            lines.append(f"- **{slo.name}:** {slo.target} ({slo.window} window)")

    lines.append("")
    return "\n".join(lines)
