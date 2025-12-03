#!/usr/bin/env python3
"""Compare old builder vs SDK builder output."""

import json
import os

SERVICES = [
    "payment-api",
    "checkout-service", 
    "notification-worker",
    "analytics-stream",
    "identity-service"
]

print("=" * 70)
print("  Comparing Old Builder vs SDK Builder")
print("=" * 70)
print()

for service in SERVICES:
    old_file = f"generated/{service}/dashboard.json"
    sdk_file = f"generated/{service}/dashboard-sdk.json"
    
    print(f"{service}:")
    
    # Check if files exist
    old_exists = os.path.exists(old_file)
    sdk_exists = os.path.exists(sdk_file)
    
    if not old_exists:
        print(f"  ⚠️  Old dashboard not found")
    if not sdk_exists:
        print(f"  ❌ SDK dashboard not found")
    
    if not (old_exists and sdk_exists):
        print()
        continue
    
    # Load and compare
    with open(old_file) as f:
        old_data = json.load(f)
    with open(sdk_file) as f:
        sdk_data = json.load(f)
    
    # Extract dashboard JSON
    old_dash = old_data.get('dashboard', old_data)
    sdk_dash = sdk_data.get('dashboard', sdk_data)
    
    # Compare
    old_panels = len(old_dash.get('panels', []))
    sdk_panels = len(sdk_dash.get('panels', []))
    
    old_size = os.path.getsize(old_file)
    sdk_size = os.path.getsize(sdk_file)
    
    print(f"  Old: {old_panels:>2} panels, {old_size:>7,} bytes")
    print(f"  SDK: {sdk_panels:>2} panels, {sdk_size:>7,} bytes")
    
    if sdk_panels >= old_panels:
        print(f"  ✅ SDK has same or more panels")
    else:
        print(f"  ⚠️  SDK has fewer panels ({old_panels - sdk_panels} less)")
    
    print()

print("=" * 70)
