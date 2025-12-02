#!/bin/bash
# Push updated dashboard to Grafana

cd "$(dirname "$0")"

# Copy the dashboard to the location nthlayer expects
cp generated/dashboards/payment-api.json generated/payment-api/dashboard.json

# Use Python to push directly
python3 << 'PYTHON'
import os
import json
import asyncio
from pathlib import Path
from nthlayer.providers.grafana import GrafanaProvider

# Get credentials
grafana_url = os.getenv('NTHLAYER_GRAFANA_URL')
grafana_api_key = os.getenv('NTHLAYER_GRAFANA_API_KEY')

if not grafana_url or not grafana_api_key:
    print("❌ NTHLAYER_GRAFANA_URL and NTHLAYER_GRAFANA_API_KEY must be set")
    exit(1)

print(f"📤 Pushing updated dashboard to {grafana_url}")

# Load dashboard
with open('generated/dashboards/payment-api.json') as f:
    dashboard_data = json.load(f)

dashboard_json = dashboard_data.get('dashboard', {})
dashboard_uid = dashboard_json.get('uid', 'payment-api-overview')

# Push
provider = GrafanaProvider(url=grafana_url, token=grafana_api_key, org_id=1)

async def push():
    resource = provider.dashboard(dashboard_uid)
    await resource.apply({
        'dashboard': dashboard_json,
        'folderUid': None,
        'title': dashboard_json.get('title', 'payment-api Dashboard')
    })

asyncio.run(push())
print(f"✅ Dashboard updated: {grafana_url}/d/{dashboard_uid}")
PYTHON
