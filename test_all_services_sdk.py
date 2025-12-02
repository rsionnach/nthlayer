#!/usr/bin/env python3
"""Test all 5 demo services with SDK-based DashboardBuilder."""

import json
import os
from pathlib import Path

from src.nthlayer.specs import parse_service_file
from src.nthlayer.dashboards.builder_sdk import DashboardBuilderSDK

# Test services
SERVICES = [
    "payment-api",
    "checkout-service",
    "notification-worker",
    "analytics-stream",
    "identity-service"
]

def test_service(service_name: str) -> dict:
    """Test dashboard generation for a service."""
    print(f"\n{'='*70}")
    print(f"  Testing: {service_name}")
    print(f"{'='*70}")
    
    result = {
        "service": service_name,
        "success": False,
        "panels": 0,
        "file_size": 0,
        "errors": []
    }
    
    try:
        # Parse service file
        service_file = f"examples/services/{service_name}.yaml"
        print(f"\n1. Parsing {service_file}...")
        service_context, resources = parse_service_file(service_file)
        print(f"   ✅ Parsed: {service_context.name}")
        print(f"      Team: {service_context.team}")
        print(f"      Type: {service_context.type}")
        print(f"      Tier: {service_context.tier}")
        print(f"      Resources: {len(resources)}")
        
        # Build dashboard
        print(f"\n2. Building dashboard with SDK...")
        builder = DashboardBuilderSDK(
            service_context=service_context,
            resources=resources,
            full_panels=False
        )
        dashboard_payload = builder.build()
        
        # Extract dashboard JSON
        dashboard_json = dashboard_payload['dashboard']
        panel_count = len(dashboard_json.get('panels', []))
        result["panels"] = panel_count
        
        print(f"   ✅ Dashboard built")
        print(f"      Title: {dashboard_json['title']}")
        print(f"      UID: {dashboard_json['uid']}")
        print(f"      Panels: {panel_count}")
        print(f"      Schema: v{dashboard_json['schemaVersion']}")
        
        # List panel types
        print(f"\n3. Panel breakdown:")
        panel_types = {}
        for panel in dashboard_json.get('panels', []):
            ptype = panel['type']
            panel_types[ptype] = panel_types.get(ptype, 0) + 1
            print(f"   • {panel['title']} ({ptype})")
        
        print(f"\n   Summary:")
        for ptype, count in panel_types.items():
            print(f"   - {ptype}: {count} panels")
        
        # Write to file
        output_dir = f"generated/{service_name}"
        os.makedirs(output_dir, exist_ok=True)
        output_file = f"{output_dir}/dashboard-sdk.json"
        
        with open(output_file, 'w') as f:
            json.dump(dashboard_payload, f, indent=2)
        
        file_size = os.path.getsize(output_file)
        result["file_size"] = file_size
        
        print(f"\n4. Output:")
        print(f"   File: {output_file}")
        print(f"   Size: {file_size:,} bytes")
        
        # Validate JSON structure
        print(f"\n5. Validating JSON structure...")
        required_keys = ['title', 'uid', 'tags', 'schemaVersion', 'panels']
        missing = [k for k in required_keys if k not in dashboard_json]
        
        if missing:
            print(f"   ❌ Missing keys: {missing}")
            result["errors"].append(f"Missing keys: {missing}")
        else:
            print(f"   ✅ All required keys present")
        
        # Validate panels have queries
        panels_without_queries = [
            p['title'] for p in dashboard_json.get('panels', [])
            if not p.get('targets')
        ]
        
        if panels_without_queries:
            print(f"   ⚠️  Panels without queries: {panels_without_queries}")
            result["errors"].append(f"Panels without queries: {len(panels_without_queries)}")
        else:
            print(f"   ✅ All panels have queries")
        
        result["success"] = len(result["errors"]) == 0
        
        print(f"\n{'='*70}")
        print(f"  ✅ {service_name}: SUCCESS")
        print(f"{'='*70}")
        
    except Exception as e:
        print(f"\n{'='*70}")
        print(f"  ❌ {service_name}: FAILED")
        print(f"{'='*70}")
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        result["errors"].append(str(e))
    
    return result


def main():
    """Run tests for all services."""
    print("=" * 70)
    print("  Task 5: Test & Validate All Services with SDK Builder")
    print("=" * 70)
    print(f"\nTesting {len(SERVICES)} services...")
    
    results = []
    for service in SERVICES:
        result = test_service(service)
        results.append(result)
    
    # Summary
    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    print()
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"Services tested: {len(SERVICES)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print()
    
    # Detailed results
    print("Results by service:")
    print()
    for result in results:
        status = "✅" if result["success"] else "❌"
        print(f"{status} {result['service']:<25} {result['panels']:>2} panels  {result['file_size']:>8,} bytes")
        if result["errors"]:
            for error in result["errors"]:
                print(f"   ⚠️  {error}")
    
    print()
    
    # Total stats
    total_panels = sum(r["panels"] for r in results)
    total_size = sum(r["file_size"] for r in results)
    
    print(f"Total panels generated: {total_panels}")
    print(f"Total output size: {total_size:,} bytes ({total_size/1024:.1f} KB)")
    print()
    
    # Success rate
    success_rate = len(successful) / len(SERVICES) * 100
    print(f"Success rate: {success_rate:.0f}%")
    print()
    
    if success_rate == 100:
        print("=" * 70)
        print("  🎉 ALL TESTS PASSED!")
        print("=" * 70)
        return 0
    else:
        print("=" * 70)
        print("  ⚠️  SOME TESTS FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    exit(main())
