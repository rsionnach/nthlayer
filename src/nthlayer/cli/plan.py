"""
CLI command for planning (dry-run) service resource generation.
"""

import json
from pathlib import Path
from typing import Optional

from nthlayer.cli.ux import console, error, header, warning
from nthlayer.orchestrator import PlanResult, ServiceOrchestrator


def print_plan_summary(plan: PlanResult) -> None:
    """Print beautiful plan summary."""
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


def print_plan_json(plan: PlanResult) -> None:
    """Print plan in JSON format."""
    output = {
        "service_name": plan.service_name,
        "service_yaml": str(plan.service_yaml),
        "resources": plan.resources,
        "total_resources": plan.total_resources,
        "errors": plan.errors,
        "success": plan.success,
    }
    print(json.dumps(output, indent=2))


def plan_command(
    service_yaml: str, env: Optional[str] = None, output_format: str = "text", verbose: bool = False
) -> int:
    """
    Preview what resources would be generated (dry-run).

    Args:
        service_yaml: Path to service YAML file
        env: Environment name (dev, staging, prod)
        output_format: Output format (text, json, yaml)
        verbose: Show detailed information

    Returns:
        Exit code (0 for success, 1 for error)
    """
    orchestrator = ServiceOrchestrator(Path(service_yaml), env=env)
    result = orchestrator.plan()

    if output_format == "json":
        print_plan_json(result)
    else:  # text (default)
        print_plan_summary(result)

    return 0 if result.success else 1
