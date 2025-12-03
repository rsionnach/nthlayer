"""Alert generator from awesome-prometheus-alerts.

Automatically generates production-ready alert rules based on service dependencies.
"""

from pathlib import Path
from typing import List

import yaml

from nthlayer.alerts import AlertRule, AlertTemplateLoader
from nthlayer.specs.models import Resource
from nthlayer.specs.parser import parse_service_file


def extract_dependencies(resources: List[Resource]) -> List[str]:
    """Extract dependency technologies from service resources.
    
    Parses Dependencies resources to find databases, services, etc.
    
    Args:
        resources: List of Resource objects from service definition
        
    Returns:
        List of technology names (e.g., ["postgres", "redis", "nginx"])
        
    Example:
        >>> resources = [
        ...     Resource(kind="Dependencies", spec={
        ...         "databases": [{"type": "postgres"}, {"type": "redis"}]
        ...     })
        ... ]
        >>> extract_dependencies(resources)
        ['postgres', 'redis']
    """
    dependencies = []
    
    for resource in resources:
        if resource.kind != "Dependencies":
            continue
        
        spec = resource.spec
        
        # Extract databases
        for db in spec.get("databases", []):
            # Try to get type explicitly, or infer from name
            db_type = db.get("type", "")
            if not db_type:
                # Try to infer from name (e.g., "postgres-main" -> "postgres")
                name = db.get("name", "")
                if name:
                    db_type = name.split("-")[0].lower()
            
            if db_type:
                dependencies.append(db_type.lower())
        
        # Extract services (might have tech info)
        for svc in spec.get("services", []):
            # Check if service has explicit type
            svc_type = svc.get("type", "")
            if svc_type:
                dependencies.append(svc_type.lower())
                continue
            
            # Try to infer tech from name
            name = svc.get("name", "").lower()
            tech_keywords = {
                "redis": "redis",
                "postgres": "postgres",
                "mysql": "mysql",
                "mongo": "mongodb",
                "kafka": "kafka",
                "rabbit": "rabbitmq",
                "nginx": "nginx",
                "haproxy": "haproxy",
                "elasticsearch": "elasticsearch",
                "elastic": "elasticsearch",
            }
            
            for keyword, tech in tech_keywords.items():
                if keyword in name:
                    dependencies.append(tech)
                    break
        
        # Extract external APIs (might have tech info)
        for api in spec.get("external_apis", []):
            api_type = api.get("type", "")
            if api_type:
                dependencies.append(api_type.lower())
    
    # Return unique dependencies
    return list(set(dependencies))


def filter_by_tier(alerts: List[AlertRule], tier: str) -> List[AlertRule]:
    """Filter alerts based on service tier.
    
    Different tiers get different alert coverage:
    - critical: All alerts (comprehensive monitoring)
    - standard: Critical + warning alerts
    - low: Only critical alerts (minimal noise)
    
    Args:
        alerts: List of AlertRule objects
        tier: Service tier (critical, standard, low)
        
    Returns:
        Filtered list of alerts
        
    Example:
        >>> alerts = [
        ...     AlertRule(name="Critical", severity="critical"),
        ...     AlertRule(name="Warning", severity="warning"),
        ...     AlertRule(name="Info", severity="info"),
        ... ]
        >>> filter_by_tier(alerts, "low")
        [AlertRule(name="Critical", severity="critical")]
    """
    tier_lower = tier.lower()
    
    if tier_lower == "critical":
        # Critical services get all alerts
        return alerts
    elif tier_lower == "standard":
        # Standard services get critical + warning
        return [a for a in alerts if a.severity in ["critical", "warning"]]
    elif tier_lower == "low":
        # Low tier services get only critical alerts
        return [a for a in alerts if a.severity == "critical"]
    else:
        # Unknown tier, return all alerts
        return alerts


def generate_alerts_for_service(
    service_file: Path,
    output_file: Path | None = None,
    environment: str | None = None,
    runbook_url: str = "",
    notification_channel: str = ""
) -> List[AlertRule]:
    """Generate alerts for a service based on its dependencies.
    
    Main function that:
    1. Parses service definition
    2. Extracts dependencies
    3. Loads appropriate alerts
    4. Filters by tier
    5. Customizes for service
    6. Optionally writes output
    
    Args:
        service_file: Path to service YAML
        output_file: Optional output path for generated alerts
        environment: Optional environment name (dev, staging, prod)
        runbook_url: Base URL for runbooks
        notification_channel: Notification channel (pagerduty, slack, etc.)
        
    Returns:
        List of generated AlertRule objects
        
    Example:
        >>> alerts = generate_alerts_for_service(
        ...     Path("payment-api.yaml"),
        ...     Path("generated/alerts/payment-api.yaml")
        ... )
        >>> len(alerts) > 0
        True
    """
    # Parse service definition with optional environment overrides
    context, resources = parse_service_file(service_file, environment=environment)
    
    # Extract dependencies
    deps = extract_dependencies(resources)
    
    if not deps:
        print("⚠️  No dependencies found in service definition")
        print("   Add a Dependencies resource to enable alert generation")
        return []
    
    print(f"📊 Loading alerts for dependencies: {', '.join(sorted(deps))}")
    
    # Load alerts for each dependency
    loader = AlertTemplateLoader()
    all_alerts = []
    stats = {}
    
    for dep in sorted(deps):
        try:
            alerts = loader.load_technology(dep)
            if not alerts:
                print(f"   ⚠️  {dep}: No alerts found")
                stats[dep] = 0
                continue
            
            # Filter by tier
            filtered = filter_by_tier(alerts, context.tier)
            
            # Customize for service
            customized = [
                alert.customize_for_service(
                    service_name=context.name,
                    team=context.team,
                    tier=context.tier,
                    notification_channel=notification_channel,
                    runbook_url=runbook_url
                )
                for alert in filtered
            ]
            
            all_alerts.extend(customized)
            stats[dep] = len(customized)
            print(f"   ✓ {dep}: {len(customized)} alerts")
            
        except Exception as e:
            print(f"   ❌ {dep}: Error loading alerts - {e}")
            stats[dep] = 0
    
    if not all_alerts:
        print("\n⚠️  No alerts generated")
        return []
    
    print(f"\n✅ Generated {len(all_alerts)} total alerts")
    print(f"   Breakdown: {', '.join(f'{k}={v}' for k, v in stats.items() if v > 0)}")
    
    # Write output if specified
    if output_file:
        write_prometheus_yaml(all_alerts, output_file, context.name)
        print(f"   Written to: {output_file}")
    
    return all_alerts


def write_prometheus_yaml(alerts: List[AlertRule], output_file: Path, service_name: str):
    """Write alerts to Prometheus YAML format.
    
    Groups alerts by technology for better organization.
    
    Args:
        alerts: List of AlertRule objects
        output_file: Path to output file
        service_name: Name of service (for group naming)
    """
    # Group by technology
    groups_dict = {}
    for alert in alerts:
        tech = alert.technology or "general"
        if tech not in groups_dict:
            groups_dict[tech] = []
        groups_dict[tech].append(alert.to_prometheus())
    
    # Create output structure
    output = {
        "groups": [
            {
                "name": f"{service_name}-{tech}",
                "rules": rules
            }
            for tech, rules in sorted(groups_dict.items())
        ]
    }
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to file with attribution header
    with open(output_file, "w") as f:
        # Add attribution header as comment
        f.write("# Alert rules generated by NthLayer\n")
        f.write("# Templates sourced from awesome-prometheus-alerts\n")
        f.write("# https://github.com/samber/awesome-prometheus-alerts\n")
        f.write("# Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n")
        f.write("#\n")
        f.write(f"# Customized for service: {service_name}\n")
        f.write("# Customizations: service labels, runbook URLs, tier filtering\n")
        f.write("#\n\n")
        
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, width=120)
