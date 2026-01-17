"""
CLI command for planning (dry-run) service resource generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from nthlayer.cli.formatters import (
    CheckResult,
    CheckStatus,
    ReliabilityReport,
    format_report,
)
from nthlayer.cli.ux import console, error, header, warning
from nthlayer.orchestrator import PlanResult, ServiceOrchestrator


def print_plan_summary(plan: PlanResult) -> None:
    """Print beautiful plan summary (table format)."""
    console.print()
    header(f"Plan: {plan.service_name}")
    console.print()

    if plan.errors:
        error("Errors:")
        for err in plan.errors:
            console.print(f"   [error]•[/error] {err}")
        console.print()
        return

    if not plan.resources:
        warning("No resources detected in service definition")
        console.print()
        return

    console.print("[bold]The following resources will be created:[/bold]")
    console.print()

    # SLOs
    if "slos" in plan.resources:
        slos = plan.resources["slos"]
        console.print(f"  [success]✓ SLOs[/success]         {len(slos)} defined")
        for slo in slos[:5]:  # Show first 5
            obj = slo.get("objective", "?")
            window = slo.get("window", "30d")
            console.print(f"     [muted]└[/muted] {slo['name']} ({obj}%, {window})")
        if len(slos) > 5:
            console.print(f"     [muted]└ ... and {len(slos) - 5} more[/muted]")
        console.print()

    # Alerts
    if "alerts" in plan.resources:
        alerts = plan.resources["alerts"]
        total_count = sum(a.get("count", 0) for a in alerts)
        console.print(f"  [success]✓ Alerts[/success]       {total_count} generated")
        for alert in alerts:
            tech = alert.get("technology", "unknown")
            count = alert.get("count", 0)
            console.print(f"     [muted]└[/muted] {tech.capitalize()} ({count} alerts)")
        console.print()

    # Dashboard
    if "dashboard" in plan.resources:
        dashboards = plan.resources["dashboard"]
        console.print(f"  [success]✓ Dashboard[/success]    {len(dashboards)} generated")
        for dashboard in dashboards:
            panels = dashboard.get("panels", "?")
            console.print(f"     [muted]└[/muted] {dashboard['name']} ({panels} panels)")
        console.print()

    # Recording Rules
    if "recording-rules" in plan.resources:
        rules = plan.resources["recording-rules"]
        total_count = sum(r.get("count", 0) for r in rules)
        console.print(f"  [success]✓ Recording[/success]    {total_count} rules")
        for rule in rules:
            rule_type = rule.get("type", "unknown")
            count = rule.get("count", 0)
            console.print(f"     [muted]└[/muted] {rule_type} ({count} rules)")
        console.print()

    # PagerDuty
    if "pagerduty" in plan.resources:
        pd_resources = plan.resources["pagerduty"]
        console.print("  [success]✓ PagerDuty[/success]    configured")
        for resource in pd_resources:
            res_type = resource.get("type", "unknown")
            if res_type == "team":
                console.print(f"     [muted]└[/muted] Team: {resource.get('name')}")
            elif res_type == "schedules":
                names = resource.get("names", [])
                console.print(f"     [muted]└[/muted] Schedules: {', '.join(names)}")
            elif res_type == "escalation_policy":
                console.print(f"     [muted]└[/muted] Escalation: {resource.get('name')}")
            elif res_type == "service":
                tier = resource.get("tier", "medium")
                model = resource.get("support_model", "self")
                console.print(
                    f"     [muted]└[/muted] Service: {resource.get('name')} "
                    f"(tier={tier}, support={model})"
                )
        console.print()

    # Summary
    console.print(f"[bold]Total:[/bold] {plan.total_resources} resources")
    console.print()
    console.print("[muted]To apply these changes, run:[/muted]")
    console.print(f"  [info]nthlayer apply {plan.service_yaml}[/info]")
    console.print()


def plan_to_report(plan: PlanResult) -> ReliabilityReport:
    """Convert PlanResult to ReliabilityReport for formatting."""
    checks = []

    # Check for errors
    if plan.errors:
        for err in plan.errors:
            checks.append(
                CheckResult(
                    name="Configuration Error",
                    status=CheckStatus.FAIL,
                    message=err,
                    rule_id="NTHLAYER001",
                    location=str(plan.service_yaml),
                )
            )
    else:
        # SLOs check
        if "slos" in plan.resources:
            slos = plan.resources["slos"]
            checks.append(
                CheckResult(
                    name="SLO Definition",
                    status=CheckStatus.PASS,
                    message=f"{len(slos)} SLOs defined",
                    details={"slo_count": len(slos)},
                )
            )

        # Alerts check
        if "alerts" in plan.resources:
            alerts = plan.resources["alerts"]
            total_count = sum(a.get("count", 0) for a in alerts)
            checks.append(
                CheckResult(
                    name="Alert Generation",
                    status=CheckStatus.PASS,
                    message=f"{total_count} alerts will be generated",
                    details={"alert_count": total_count},
                )
            )

        # Dashboard check
        if "dashboard" in plan.resources:
            dashboards = plan.resources["dashboard"]
            checks.append(
                CheckResult(
                    name="Dashboard Generation",
                    status=CheckStatus.PASS,
                    message=f"{len(dashboards)} dashboards will be generated",
                    details={"dashboard_count": len(dashboards)},
                )
            )

        # Recording rules check
        if "recording-rules" in plan.resources:
            rules = plan.resources["recording-rules"]
            total_count = sum(r.get("count", 0) for r in rules)
            checks.append(
                CheckResult(
                    name="Recording Rules",
                    status=CheckStatus.PASS,
                    message=f"{total_count} recording rules will be generated",
                    details={"rule_count": total_count},
                )
            )

        # No resources warning
        if not plan.resources:
            checks.append(
                CheckResult(
                    name="Resource Detection",
                    status=CheckStatus.WARN,
                    message="No resources detected in service definition",
                )
            )

    # Add warnings
    for warn in plan.warnings:
        checks.append(
            CheckResult(
                name="Warning",
                status=CheckStatus.WARN,
                message=warn,
            )
        )

    return ReliabilityReport(
        service=plan.service_name,
        command="plan",
        checks=checks,
        summary={"total_resources": plan.total_resources},
        metadata={
            "service_yaml": str(plan.service_yaml),
            "resources": plan.resources,
        },
    )


def plan_command(
    service_yaml: str,
    env: Optional[str] = None,
    output_format: str = "table",
    output_file: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """
    Preview what resources would be generated (dry-run).

    Args:
        service_yaml: Path to service YAML file
        env: Environment name (dev, staging, prod)
        output_format: Output format (table, json, sarif, junit, markdown)
        output_file: Optional file path to write output
        verbose: Show detailed information

    Returns:
        Exit code (0 for success, 1 for error)
    """
    orchestrator = ServiceOrchestrator(Path(service_yaml), env=env)
    result = orchestrator.plan()

    # Use table format with rich console output
    if output_format == "table" and not output_file:
        print_plan_summary(result)
    else:
        # Convert to report and use formatter
        report = plan_to_report(result)
        output = format_report(
            report,
            output_format=output_format,
            output_file=output_file,
        )

        # Print to stdout if not writing to file
        if not output_file:
            print(output)
        else:
            console.print(f"[success]Output written to {output_file}[/success]")

    return 0 if result.success else 1
