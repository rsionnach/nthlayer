"""
PagerDuty setup command.
"""

from __future__ import annotations

import os

from nthlayer.integrations.pagerduty import PagerDutyClient
from nthlayer.specs.parser import parse_service_file


def setup_pagerduty_command(
    service_file: str,
    api_key: str | None = None,
    environment: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    Setup PagerDuty integration for a service.
    
    Args:
        service_file: Path to service YAML file
        api_key: PagerDuty API key (or use PAGERDUTY_API_KEY env var)
        environment: Optional environment name (dev, staging, prod)
        dry_run: Preview what would be created without making changes
    
    Returns:
        Exit code (0 = success, 1 = error)
    """
    print("=" * 70)
    print("  NthLayer: Setup PagerDuty Integration")
    print("=" * 70)
    print()
    
    if environment:
        print(f"🌍 Environment: {environment}")
        print()
    
    # Get API key
    api_key = api_key or os.environ.get("PAGERDUTY_API_KEY")
    if not api_key:
        print("❌ PagerDuty API key required")
        print()
        print("Provide via:")
        print("  • --api-key flag")
        print("  • PAGERDUTY_API_KEY environment variable")
        print()
        print("Get your API key at: https://support.pagerduty.com/docs/api-access-keys")
        print()
        return 1
    
    # Parse service file with optional environment overrides
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        print(f"❌ Error parsing service file: {e}")
        print()
        return 1
    
    # Find PagerDuty resource
    pagerduty_resources = [r for r in resources if r.kind == "PagerDuty"]
    
    if not pagerduty_resources:
        print(f"❌ No PagerDuty resource found in {service_file}")
        print()
        print("Add a PagerDuty resource to your service definition:")
        print("  resources:")
        print("    - kind: PagerDuty")
        print("      name: primary")
        print("      spec:")
        print("        escalation_policy: my-policy")
        print("        urgency: high")
        print()
        return 1
    
    pagerduty_resource = pagerduty_resources[0]
    spec = pagerduty_resource.spec
    
    print(f"📋 Service: {service_context.name}")
    print(f"   Team: {service_context.team}")
    print(f"   Tier: {service_context.tier}")
    print()
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
        print("Would create/verify:")
        print(f"  • PagerDuty service: {service_context.name}")
        
        if spec.get("escalation_policy"):
            print(f"  • Escalation policy: {spec['escalation_policy']}")
        
        if service_context.team:
            print(f"  • Team mapping: {service_context.team}")
        
        print()
        return 0
    
    # Setup PagerDuty
    print("🔧 Setting up PagerDuty integration...")
    print()
    
    try:
        with PagerDutyClient(api_key) as client:
            # Prepare config
            escalation_policy_name = spec.get("escalation_policy")
            escalation_policy_id = spec.get("escalation_policy_id")
            urgency = spec.get("urgency", "high")
            auto_resolve_timeout = spec.get("auto_resolve_timeout")
            
            # Check if we should create escalation policy
            create_ep_config = None
            if spec.get("create_escalation_policy"):
                create_ep_config = spec["create_escalation_policy"]
            
            result = client.setup_service(
                service_name=service_context.name,
                team_name=service_context.team,
                escalation_policy_name=escalation_policy_name,
                escalation_policy_id=escalation_policy_id,
                urgency=urgency,
                auto_resolve_timeout=auto_resolve_timeout,
                create_escalation_policy_config=create_ep_config,
            )
        
        if not result.success:
            print(f"❌ Setup failed: {result.error}")
            print()
            return 1
        
        # Display results
        if result.created_service:
            print("✅ Created PagerDuty service")
        else:
            print("✅ PagerDuty service already exists")
        
        print(f"   Service ID: {result.service_id}")
        print(f"   Service URL: {result.service_url}")
        print()
        
        if result.created_escalation_policy:
            print("✅ Created escalation policy")
            print(f"   Policy ID: {result.escalation_policy_id}")
            print()
        
        if result.team_id:
            if result.created_team:
                print(f"✅ Created team: {service_context.team}")
            else:
                print(f"✅ Added to existing team: {service_context.team}")
            print(f"   Team ID: {result.team_id}")
            print()
        
        if result.warnings:
            print("⚠️  Warnings:")
            for warning in result.warnings:
                print(f"   • {warning}")
            print()
        
        print("✅ PagerDuty setup complete!")
        print()
        print("💡 Next steps:")
        print(f"   1. Visit: {result.service_url}")
        print("   2. Configure integrations (email, webhooks, etc.)")
        print(f"   3. Test alerting with: nthlayer reslayer test-alert {service_context.name}")
        print()
        
        return 0
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print()
        return 1
