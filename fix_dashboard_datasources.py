#!/usr/bin/env python3
"""Fix all SDK dashboards to use correct Prometheus datasource."""

import json
import os

DATASOURCE_UID = "grafanacloud-prom"
SERVICES = [
    "payment-api",
    "checkout-service", 
    "notification-worker",
    "analytics-stream",
    "identity-service",
    "search-api"
]

print("=" * 70)
print("  Fixing Dashboard Datasources")
print("=" * 70)
print()
print(f"Setting datasource UID: {DATASOURCE_UID}")
print()

for service in SERVICES:
    dashboard_file = f"generated/{service}/dashboard-sdk.json"
    
    if not os.path.exists(dashboard_file):
        print(f"⚠️  {service}: File not found")
        continue
    
    print(f"Processing: {service}")
    
    # Load dashboard
    with open(dashboard_file) as f:
        payload = json.load(f)
    
    dashboard = payload.get('dashboard', payload)
    
    # Fix datasource in all panels
    panels_fixed = 0
    for panel in dashboard.get('panels', []):
        for target in panel.get('targets', []):
            if 'datasource' not in target or not target.get('datasource'):
                target['datasource'] = {
                    "type": "prometheus",
                    "uid": DATASOURCE_UID
                }
                panels_fixed += 1
            elif isinstance(target.get('datasource'), dict):
                target['datasource']['uid'] = DATASOURCE_UID
                panels_fixed += 1
    
    # Save back
    with open(dashboard_file, 'w') as f:
        json.dump(payload, f, indent=2)
    
    print(f"  ✅ Fixed {panels_fixed} targets")

print()
print("=" * 70)
print("  All dashboards updated with datasource configuration")
print("="  * 70)
