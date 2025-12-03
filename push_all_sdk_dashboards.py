#!/usr/bin/env python3
"""Push all SDK-generated dashboards to Grafana Cloud."""

import json
import os
import requests
from pathlib import Path

# Grafana Cloud configuration from environment
GRAFANA_URL = os.getenv('NTHLAYER_GRAFANA_URL', 'https://nthlayer.grafana.net')
GRAFANA_API_KEY = os.getenv('NTHLAYER_GRAFANA_API_KEY')

if not GRAFANA_API_KEY:
    print("❌ NTHLAYER_GRAFANA_API_KEY not set")
    exit(1)

SERVICES = [
    "payment-api",
    "checkout-service",
    "notification-worker",
    "analytics-stream",
    "identity-service",
    "search-api"
]

print("=" * 70)
print("  Pushing All SDK Dashboards to Grafana Cloud")
print("=" * 70)
print(f"\nGrafana URL: {GRAFANA_URL}")
print(f"Services: {len(SERVICES)}")
print()

headers = {
    "Authorization": f"Bearer {GRAFANA_API_KEY}",
    "Content-Type": "application/json"
}

results = []

for service in SERVICES:
    print(f"{'='*70}")
    print(f"  {service}")
    print(f"{'='*70}")
    
    # Load dashboard JSON
    dashboard_file = f"generated/{service}/dashboard-sdk.json"
    
    if not os.path.exists(dashboard_file):
        print(f"   ❌ Dashboard file not found: {dashboard_file}")
        results.append({
            "service": service,
            "success": False,
            "error": "File not found"
        })
        continue
    
    print(f"   Loading: {dashboard_file}")
    with open(dashboard_file) as f:
        payload = json.load(f)
    
    dashboard_json = payload.get('dashboard', payload)
    print(f"   Title: {dashboard_json.get('title')}")
    print(f"   UID: {dashboard_json.get('uid')}")
    print(f"   Panels: {len(dashboard_json.get('panels', []))}")
    
    # Prepare payload for Grafana API
    grafana_payload = {
        "dashboard": dashboard_json,
        "overwrite": True,
        "message": f"Updated {service} dashboard with SDK (auto-generated)"
    }
    
    # Push to Grafana
    print(f"   Pushing to Grafana Cloud...")
    try:
        response = requests.post(
            f"{GRAFANA_URL}/api/dashboards/db",
            headers=headers,
            json=grafana_payload,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            dashboard_url = f"{GRAFANA_URL}/d/{result.get('uid', dashboard_json.get('uid'))}"
            print(f"   ✅ SUCCESS")
            print(f"   URL: {dashboard_url}")
            results.append({
                "service": service,
                "success": True,
                "url": dashboard_url
            })
        else:
            print(f"   ❌ FAILED: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            results.append({
                "service": service,
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:100]}"
            })
    
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        results.append({
            "service": service,
            "success": False,
            "error": str(e)
        })
    
    print()

# Summary
print("=" * 70)
print("  SUMMARY")
print("=" * 70)
print()

successful = [r for r in results if r["success"]]
failed = [r for r in results if not r["success"]]

print(f"Total: {len(results)}")
print(f"Successful: {len(successful)}")
print(f"Failed: {len(failed)}")
print()

if successful:
    print("✅ Successfully pushed:")
    for r in successful:
        print(f"   • {r['service']}")
        print(f"     {r['url']}")

if failed:
    print()
    print("❌ Failed:")
    for r in failed:
        print(f"   • {r['service']}: {r['error']}")

print()
print("=" * 70)

if len(successful) == len(SERVICES):
    print("  🎉 ALL DASHBOARDS PUSHED SUCCESSFULLY!")
else:
    print(f"  ⚠️  {len(failed)} dashboard(s) failed to push")
print("=" * 70)
