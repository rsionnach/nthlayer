"""CLI command for generating alerts from awesome-prometheus-alerts."""

from pathlib import Path

from nthlayer.generators.alerts import generate_alerts_for_service
from nthlayer.specs.environment_alerts import explain_alert_filtering


def generate_alerts_command(
    service_file: str,
    output: str | None = None,
    environment: str | None = None,
    dry_run: bool = False,
    runbook_url: str = "",
    notification_channel: str = ""
) -> int:
    """Generate alerts for a service based on dependencies.
    
    Automatically generates production-ready alert rules from awesome-prometheus-alerts
    based on the service's declared dependencies.
    
    Args:
        service_file: Path to service YAML file
        output: Output path (default: generated/alerts/{service}.yaml)
        environment: Optional environment name (dev, staging, prod)
        dry_run: Preview alerts without writing file
        runbook_url: Base URL for runbook links
        notification_channel: Notification channel (pagerduty, slack, etc.)
        
    Returns:
        Exit code (0 for success, 1 for error)
        
    Example:
        >>> generate_alerts_command("payment-api.yaml")
        0
    """
    service_path = Path(service_file)
    
    # Validate input file exists
    if not service_path.exists():
        print(f"❌ Service file not found: {service_file}")
        return 1
    
    # Determine output path
    if not output:
        service_name = service_path.stem
        output = f"generated/alerts/{service_name}.yaml"
    
    output_path = None if dry_run else Path(output)
    
    # Print header
    print("=" * 70)
    print("  NthLayer: Generate Alerts")
    print("=" * 70)
    print()
    print(f"Service: {service_path}")
    if environment:
        print(f"🌍 Environment: {environment}")
    if dry_run:
        print("Mode: Dry run (preview only)")
    else:
        print(f"Output: {output}")
    print()
    
    # Show alert filtering strategy if environment specified
    if environment:
        from nthlayer.specs.parser import parse_service_file
        try:
            context, _ = parse_service_file(service_path, environment=environment)
            explain_alert_filtering(environment, context.tier)
        except Exception:
            # If parsing fails, continue anyway
            pass
    
    try:
        # Generate alerts
        alerts = generate_alerts_for_service(
            service_path,
            output_path,
            environment=environment,
            runbook_url=runbook_url,
            notification_channel=notification_channel
        )
        
        if not alerts:
            print("\n💡 Tip: Add a Dependencies resource to your service YAML:")
            print("   resources:")
            print("     - kind: Dependencies")
            print("       name: upstream")
            print("       spec:")
            print("         databases:")
            print("           - type: postgres")
            print("           - type: redis")
            return 1
        
        if dry_run:
            print("\n📋 Dry run - alerts not written to file")
            print("\n📝 Sample alerts generated:")
            for i, alert in enumerate(alerts[:5], 1):
                print(f"   {i}. {alert.name} ({alert.severity}, {alert.technology})")
            
            if len(alerts) > 5:
                print(f"   ... and {len(alerts) - 5} more")
            
            print(f"\n💡 Run without --dry-run to write to {output}")
        else:
            print("\n💡 Next steps:")
            print(f"   1. Review generated alerts: cat {output}")
            print("   2. Deploy to Prometheus: kubectl apply -f", output)
            print("   3. Verify alerts are firing: check Prometheus UI")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Error generating alerts: {e}")
        import traceback
        traceback.print_exc()
        return 1
