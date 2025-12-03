"""
CLI command for planning (dry-run) service resource generation.
"""

import json
from pathlib import Path
from typing import Optional

from nthlayer.orchestrator import PlanResult, ServiceOrchestrator


def print_plan_summary(plan: PlanResult) -> None:
    """Print beautiful plan summary."""
    print()
    print("╔" + "═" * 62 + "╗")
    print(f"║  📋 Plan: {plan.service_name:<50} ║")
    print("╚" + "═" * 62 + "╝")
    print()
    
    if plan.errors:
        print("❌ Errors:")
        for error in plan.errors:
            print(f"   • {error}")
        print()
        return
    
    if not plan.resources:
        print("⚠️  No resources detected in service definition")
        print()
        return
    
    print("The following resources will be created:")
    print()
    
    # SLOs
    if "slos" in plan.resources:
        slos = plan.resources["slos"]
        print(f"✅ SLOs ({len(slos)})")
        for slo in slos[:5]:  # Show first 5
            obj = slo.get("objective", "?")
            window = slo.get("window", "30d")
            print(f"   + {slo['name']} ({obj}%, {window})")
        if len(slos) > 5:
            print(f"   ... and {len(slos) - 5} more")
        print()
    
    # Alerts
    if "alerts" in plan.resources:
        alerts = plan.resources["alerts"]
        total_count = sum(a.get("count", 0) for a in alerts)
        print(f"✅ Alerts ({total_count})")
        for alert in alerts:
            tech = alert.get("technology", "unknown")
            count = alert.get("count", 0)
            print(f"   + {tech.capitalize()} ({count} alerts)")
        print()
    
    # Dashboard
    if "dashboard" in plan.resources:
        dashboards = plan.resources["dashboard"]
        print(f"✅ Dashboard ({len(dashboards)})")
        for dashboard in dashboards:
            panels = dashboard.get("panels", "?")
            print(f"   + {dashboard['name']} ({panels} panels)")
        print()
    
    # Recording Rules
    if "recording-rules" in plan.resources:
        rules = plan.resources["recording-rules"]
        total_count = sum(r.get("count", 0) for r in rules)
        print(f"✅ Recording Rules ({total_count})")
        for rule in rules:
            rule_type = rule.get("type", "unknown")
            count = rule.get("count", 0)
            print(f"   + {rule_type} ({count} rules)")
        print()
    
    # PagerDuty
    if "pagerduty" in plan.resources:
        pd_services = plan.resources["pagerduty"]
        print(f"✅ PagerDuty Service ({len(pd_services)})")
        for service in pd_services:
            urgency = service.get("urgency", "high")
            print(f"   + {service['name']} ({urgency} urgency)")
        print()
    
    # Summary
    print(f"📊 Total: {plan.total_resources} resources")
    print()
    print("To apply these changes, run:")
    print(f"  nthlayer apply {plan.service_yaml}")
    print()


def print_plan_json(plan: PlanResult) -> None:
    """Print plan in JSON format."""
    output = {
        "service_name": plan.service_name,
        "service_yaml": str(plan.service_yaml),
        "resources": plan.resources,
        "total_resources": plan.total_resources,
        "errors": plan.errors,
        "success": plan.success
    }
    print(json.dumps(output, indent=2))


def plan_command(
    service_yaml: str,
    env: Optional[str] = None,
    output_format: str = "text",
    verbose: bool = False
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
