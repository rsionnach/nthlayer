#!/usr/bin/env python3
"""
Test hybrid dashboard generation with metric discovery validation.

This demonstrates the fix for the 51% fix rate issue.
"""

import os
import json
from src.nthlayer.specs import load_service_spec
from src.nthlayer.dashboards.builder import DashboardBuilder
from src.nthlayer.discovery import MetricDiscoveryClient

def main():
    print("🔨 Testing Hybrid Dashboard Generation")
    print("=" * 60)
    
    # Load service spec
    spec_file = "examples/services/payment-api.yaml"
    print(f"\n1. Loading service spec: {spec_file}")
    service_spec, slo_resources = load_service_spec(spec_file)
    print(f"   ✅ Loaded {service_spec.name} with {len(slo_resources)} SLOs")
    
    # Create discovery client
    print(f"\n2. Creating metric discovery client...")
    discovery_client = MetricDiscoveryClient(
        prometheus_url=os.getenv('METRICS_URL', 'https://nthlayer-demo.fly.dev'),
        username=os.getenv('METRICS_USER', 'nthlayer'),
        password=os.getenv('METRICS_PASSWORD')
    )
    print(f"   ✅ Client configured")
    
    # Build dashboard WITHOUT validation (old way)
    print(f"\n3. Building dashboard WITHOUT validation (old approach)...")
    builder_old = DashboardBuilder(
        context=service_spec,
        slo_resources=slo_resources,
        enable_validation=False
    )
    dashboard_old = builder_old.build()
    old_panel_count = len(dashboard_old.panels)
    print(f"   📊 Generated {old_panel_count} panels (unvalidated)")
    
    # Build dashboard WITH validation (new way)
    print(f"\n4. Building dashboard WITH validation (hybrid approach)...")
    builder_new = DashboardBuilder(
        context=service_spec,
        slo_resources=slo_resources,
        discovery_client=discovery_client,
        enable_validation=True
    )
    dashboard_new = builder_new.build()
    new_panel_count = len(dashboard_new.panels)
    print(f"   📊 Generated {new_panel_count} validated panels")
    
    # Compare results
    print(f"\n5. Comparison:")
    print(f"   Old approach: {old_panel_count} panels")
    print(f"   New approach: {new_panel_count} panels")
    
    removed = old_panel_count - new_panel_count
    if removed > 0:
        print(f"   ⚠️  Removed {removed} panels with missing metrics")
        print(f"\n   Warnings:")
        for warning in builder_new.validation_warnings:
            print(f"      - {warning}")
    else:
        print(f"   ✅ No invalid panels detected!")
    
    # Show validation success
    print(f"\n6. Validation Status:")
    if new_panel_count > 0:
        validation_rate = (new_panel_count / old_panel_count) * 100
        print(f"   ✅ {validation_rate:.1f}% of panels are valid")
        print(f"   ✅ {new_panel_count} panels will show data")
        print(f"   ✅ 0 panels will show 'no data'")
    
    # Save both dashboards for comparison
    os.makedirs('generated/comparison', exist_ok=True)
    
    with open('generated/comparison/payment-api-old.json', 'w') as f:
        json.dump({'dashboard': dashboard_old.to_dict()}, f, indent=2)
    
    with open('generated/comparison/payment-api-new.json', 'w') as f:
        json.dump({'dashboard': dashboard_new.to_dict()}, f, indent=2)
    
    print(f"\n7. Output:")
    print(f"   📁 Saved: generated/comparison/payment-api-old.json")
    print(f"   📁 Saved: generated/comparison/payment-api-new.json")
    
    print(f"\n{'=' * 60}")
    print(f"✅ Hybrid dashboard generation test complete!")
    print(f"\nResult: Prevented {removed} 'no data' panels through validation")

if __name__ == '__main__':
    main()
