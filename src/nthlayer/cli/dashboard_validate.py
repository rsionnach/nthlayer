"""CLI command for validating dashboard metric resolution."""

from typing import Optional

from nthlayer.dashboards.intents import (
    ALL_INTENTS,
    get_intents_for_technology,
    list_technologies,
)
from nthlayer.dashboards.resolver import ResolutionStatus, create_resolver
from nthlayer.specs.parser import parse_service_file


def validate_dashboard_command(
    service_file: str,
    prometheus_url: Optional[str] = None,
    technology: Optional[str] = None,
    show_all: bool = False,
) -> int:
    """Validate dashboard metric resolution for a service.
    
    This command discovers metrics from Prometheus and shows how each
    intent would be resolved, including fallbacks and guidance.
    
    Args:
        service_file: Path to service YAML file
        prometheus_url: Prometheus URL for metric discovery
        technology: Specific technology to validate (postgresql, redis, etc.)
        show_all: Show all intents, not just those for service dependencies
        
    Returns:
        Exit code (0 for success, 1 for errors, 2 for warnings)
    """
    print("=" * 70)
    print("  NthLayer: Dashboard Metric Validation")
    print("=" * 70)
    print()
    
    try:
        # Parse service file
        print(f"Service: {service_file}")
        context, resources = parse_service_file(service_file)
        
        print(f"   Name: {context.name}")
        print(f"   Team: {context.team}")
        print()
        
        # Extract dependencies
        dependencies = [r for r in resources if r.kind == "Dependencies"]
        technologies = set()
        
        for dep in dependencies:
            spec = dep.spec if hasattr(dep, 'spec') else {}
            databases = spec.get('databases', []) if isinstance(spec, dict) else []
            caches = spec.get('caches', []) if isinstance(spec, dict) else []
            
            for db in databases:
                db_type = db.get('type', '') if isinstance(db, dict) else getattr(db, 'type', '')
                if db_type:
                    technologies.add(db_type)
            for cache in caches:
                cache_type = cache.get('type', 'redis') if isinstance(cache, dict) else getattr(cache, 'type', 'redis')
                technologies.add(cache_type)
        
        # Always include HTTP for API services
        if context.type in ('api', 'service', 'web'):
            technologies.add('http')
        
        # Filter by technology if specified
        if technology:
            technologies = {technology}
        
        print(f"Technologies to validate: {', '.join(sorted(technologies)) or 'none detected'}")
        print()
        
        # Create resolver
        custom_overrides = {}
        for resource in resources:
            if hasattr(resource, 'spec') and isinstance(resource.spec, dict):
                metrics = resource.spec.get('metrics', {})
                if isinstance(metrics, dict):
                    custom_overrides.update(metrics)
        
        resolver = create_resolver(
            prometheus_url=prometheus_url,
            custom_overrides=custom_overrides
        )
        
        # Discover metrics if Prometheus URL provided
        if prometheus_url:
            print(f"Discovering metrics from {prometheus_url}...")
            try:
                count = resolver.discover_for_service(context.name)
                print(f"   Found {count} metrics")
                print()
            except Exception as e:
                print(f"   Warning: Discovery failed: {e}")
                print("   Continuing without discovery (all intents will be unresolved)")
                print()
        else:
            print("No Prometheus URL provided - showing intent structure only")
            print("   Tip: Add --prometheus-url to validate against real metrics")
            print()
        
        # Collect intents to validate
        intents_to_check = []
        if show_all:
            intents_to_check = list(ALL_INTENTS.keys())
        else:
            for tech in technologies:
                tech_intents = get_intents_for_technology(tech)
                intents_to_check.extend(tech_intents.keys())
        
        if not intents_to_check:
            print("No intents to validate. Add --technology or --show-all")
            return 0
        
        # Resolve all intents
        print("Resolving intents:")
        print("-" * 60)
        
        resolved_count = 0
        fallback_count = 0
        unresolved_count = 0
        custom_count = 0
        
        for intent_name in sorted(intents_to_check):
            result = resolver.resolve(intent_name)
            
            if result.status == ResolutionStatus.RESOLVED:
                print(f"  ✅ {intent_name}")
                print(f"     Resolved: {result.metric_name}")
                resolved_count += 1
            elif result.status == ResolutionStatus.CUSTOM:
                print(f"  🔧 {intent_name}")
                print(f"     Custom: {result.metric_name}")
                custom_count += 1
            elif result.status == ResolutionStatus.FALLBACK:
                print(f"  ⚠️  {intent_name}")
                print(f"     Fallback: {result.metric_name}")
                print(f"     Note: {result.message}")
                fallback_count += 1
            elif result.status == ResolutionStatus.SYNTHESIZED:
                print(f"  🔄 {intent_name}")
                print(f"     Synthesized: {result.metric_name}")
                print(f"     Expression: {result.synthesis_expr}")
                resolved_count += 1
            else:
                print(f"  ❌ {intent_name}")
                print(f"     {result.message}")
                unresolved_count += 1
            
            print()
        
        # Summary
        print("-" * 60)
        print("Summary:")
        total = resolved_count + fallback_count + unresolved_count + custom_count
        print(f"   Total intents: {total}")
        print(f"   ✅ Resolved: {resolved_count}")
        if custom_count:
            print(f"   🔧 Custom: {custom_count}")
        if fallback_count:
            print(f"   ⚠️  Fallback: {fallback_count}")
        print(f"   ❌ Unresolved: {unresolved_count}")
        print()
        
        # Exit code based on results
        if unresolved_count > 0:
            if prometheus_url:
                print("Some intents could not be resolved. Dashboard will include guidance panels.")
                print("See exporter recommendations above for how to enable missing metrics.")
                return 2  # Warning
            else:
                print("Run with --prometheus-url to validate against real metrics.")
                return 0
        else:
            print("✅ All intents resolved successfully!")
            return 0
        
    except FileNotFoundError:
        print(f"❌ Error: Service file not found: {service_file}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def list_intents_command(technology: Optional[str] = None) -> int:
    """List all available metric intents.
    
    Args:
        technology: Filter by technology (postgresql, redis, etc.)
        
    Returns:
        Exit code (0 for success)
    """
    print("=" * 70)
    print("  NthLayer: Available Metric Intents")
    print("=" * 70)
    print()
    
    if technology:
        intents = get_intents_for_technology(technology)
        print(f"Intents for {technology}:")
    else:
        intents = ALL_INTENTS
        print(f"All intents ({len(intents)} total):")
    
    print()
    
    current_tech = None
    for name, intent in sorted(intents.items()):
        tech = name.split('.')[0]
        if tech != current_tech:
            current_tech = tech
            print(f"  [{tech.upper()}]")
        
        print(f"    {name}")
        print(f"      Type: {intent.metric_type.value}")
        print(f"      Candidates: {', '.join(intent.candidates[:3])}", end="")
        if len(intent.candidates) > 3:
            print(f" (+{len(intent.candidates) - 3} more)")
        else:
            print()
        print()
    
    print(f"Supported technologies: {', '.join(list_technologies())}")
    return 0
