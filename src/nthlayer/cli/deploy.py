"""
Deployment gate check command.
"""

from __future__ import annotations

from nthlayer.slos.gates import DeploymentGate
from nthlayer.specs.environment_gates import (
    explain_thresholds,
    get_deployment_gate_thresholds,
)
from nthlayer.specs.parser import parse_service_file


def check_deploy_command(
    service_file: str,
    environment: str | None = None,
    budget_consumed: int | None = None,
    budget_total: int | None = None,
) -> int:
    """
    Check if deployment should be allowed based on error budget.
    
    Exit codes:
    - 0 = Approved (proceed with deploy)
    - 1 = Warning (advisory, proceed with caution)
    - 2 = Blocked (do not deploy)
    
    Args:
        service_file: Path to service YAML file
        environment: Optional environment name (dev, staging, prod)
        budget_consumed: Minutes of error budget consumed (for testing)
        budget_total: Total error budget in minutes (for testing)
    
    Returns:
        Exit code (0, 1, or 2)
    """
    print("=" * 70)
    print("  NthLayer: Deployment Gate Check")
    print("=" * 70)
    print()
    
    if environment:
        print(f"🌍 Environment: {environment}")
        print()
    
    # Parse service file with optional environment overrides
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        print(f"❌ Error parsing service file: {e}")
        print()
        return 2  # Block on parse errors
    
    print(f"📋 Service: {service_context.name}")
    print(f"   Team: {service_context.team}")
    print(f"   Tier: {service_context.tier}")
    print()
    
    # Show environment-specific thresholds
    if environment:
        explain_thresholds(service_context.tier, environment)
    else:
        explain_thresholds(service_context.tier, "prod")
    
    # Get dependencies for blast radius
    dep_resources = [r for r in resources if r.kind == "Dependencies"]
    downstream_services = []
    
    if dep_resources:
        deps_spec = dep_resources[0].spec
        for svc in deps_spec.get("services", []):
            downstream_services.append({
                "name": svc["name"],
                "criticality": svc.get("criticality", "medium"),
            })
    
    # Get error budget (from DB in real scenario, use test values for now)
    if budget_total is None or budget_consumed is None:
        # In real implementation, fetch from database
        # For now, show what would happen with example values
        print("ℹ️  No error budget data available")
        print("   (In production, this would fetch from database)")
        print()
        print(f"Example scenarios for {service_context.tier} in {environment or 'prod'}:")
        print()
        
        gate = DeploymentGate()
        
        # Get environment-specific thresholds
        thresholds = get_deployment_gate_thresholds(service_context.tier, environment)
        
        # Calculate example budgets based on thresholds
        total_budget = 1440  # 30 days at 99.9% = 43.2 min, let's use 1440 for examples
        
        scenarios = []
        if "block" in thresholds:
            # Show just under block threshold
            scenarios.append((
                "Pass (Just Safe)",
                total_budget,
                int(total_budget * (thresholds["block"] - 0.05))
            ))
            # Show over block threshold
            scenarios.append((
                "Blocked",
                total_budget,
                int(total_budget * (thresholds["block"] + 0.05))
            ))
        
        if "warn" in thresholds:
            # Show warning scenario
            scenarios.append((
                "Warning",
                total_budget,
                int(total_budget * (thresholds["warn"] + 0.05))
            ))
        
        # Always show healthy scenario
        scenarios.insert(0, ("Healthy", total_budget, int(total_budget * 0.05)))
        
        for scenario_name, total, consumed in scenarios:
            result = gate.check_deployment(
                service_context.name,
                service_context.tier,
                total,
                consumed,
                downstream_services,
            )
            
            print(f"Scenario: {scenario_name}")
            print(f"  {result.message}")
            print(f"  Exit code: {result.result}")
            print()
        
        return 0
    
    # Run gate check
    gate = DeploymentGate()
    result = gate.check_deployment(
        service_context.name,
        service_context.tier,
        budget_total,
        budget_consumed,
        downstream_services,
    )
    
    # Display result
    print(result.message)
    print()
    
    print("📊 Error Budget Status:")
    print(f"   Total: {result.budget_total_minutes} minutes")
    print(f"   Consumed: {result.budget_consumed_minutes} minutes")
    print(f"   Remaining: {result.budget_remaining_minutes} minutes ({result.budget_remaining_percentage:.1f}%)")
    print()
    
    print("🎚️  Thresholds:")
    print(f"   Warning: <{result.warning_threshold}%")
    if result.blocking_threshold:
        print(f"   Blocking: <{result.blocking_threshold}%")
    else:
        print("   Blocking: None (advisory only)")
    print()
    
    if result.high_criticality_downstream:
        print("⚡ Blast Radius:")
        print(f"   High-criticality downstream: {len(result.high_criticality_downstream)}")
        for svc in result.high_criticality_downstream:
            print(f"     • {svc}")
        print()
    
    if result.recommendations:
        print("💡 Recommendations:")
        for rec in result.recommendations:
            print(f"   • {rec}")
        print()
    
    # Exit with appropriate code
    if result.is_blocked:
        print("❌ Deployment BLOCKED")
        print("   Exit code: 2")
        print()
        return 2
    
    elif result.is_warning:
        print("⚠️  Deployment allowed with WARNING")
        print("   Exit code: 1")
        print()
        return 1
    
    else:
        print("✅ Deployment APPROVED")
        print("   Exit code: 0")
        print()
        return 0
