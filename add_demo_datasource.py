#!/usr/bin/env python3
"""Add nthlayer-demo.fly.dev as a Prometheus datasource in Grafana Cloud."""

import os
import sys
import requests
import json

GRAFANA_URL = os.environ.get("NTHLAYER_GRAFANA_URL", "https://nthlayer.grafana.net")
GRAFANA_API_KEY = os.environ.get("NTHLAYER_GRAFANA_API_KEY")
METRICS_PASSWORD = os.environ.get("METRICS_PASSWORD")

if not GRAFANA_API_KEY:
    print("Error: NTHLAYER_GRAFANA_API_KEY environment variable not set")
    sys.exit(1)

if not METRICS_PASSWORD:
    print("Error: METRICS_PASSWORD environment variable not set")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {GRAFANA_API_KEY}",
    "Content-Type": "application/json"
}

print("=" * 70)
print("  Adding Demo Prometheus Datasource to Grafana Cloud")
print("=" * 70)
print()

# Define datasource
datasource = {
    "name": "NthLayer Demo Metrics",
    "type": "prometheus",
    "url": "https://nthlayer-demo.fly.dev",
    "access": "proxy",
    "basicAuth": True,
    "basicAuthUser": "nthlayer",
    "secureJsonData": {
        "basicAuthPassword": METRICS_PASSWORD
    },
    "jsonData": {
        "httpMethod": "POST",
        "timeInterval": "30s"
    },
    "isDefault": False
}

print(f"Creating datasource: {datasource['name']}")
print(f"URL: {datasource['url']}")
print()

# Create datasource
response = requests.post(
    f"{GRAFANA_URL}/api/datasources",
    headers=headers,
    json=datasource,
    timeout=10
)

if response.status_code in [200, 201]:
    result = response.json()
    print(f"✅ Datasource created successfully!")
    print(f"   ID: {result.get('id')}")
    print(f"   UID: {result.get('uid')}")
    print(f"   Name: {result.get('name')}")
    print()
    print(f"Datasource UID to use: {result.get('uid')}")
elif response.status_code == 409:
    print("⚠️  Datasource already exists")
    print("   Fetching existing datasource...")
    
    # Get existing datasource
    response = requests.get(
        f"{GRAFANA_URL}/api/datasources/name/{datasource['name']}",
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"   Found: {result.get('name')}")
        print(f"   UID: {result.get('uid')}")
else:
    print(f"❌ Failed: {response.status_code}")
    print(f"   Response: {response.text}")

print()
print("=" * 70)
