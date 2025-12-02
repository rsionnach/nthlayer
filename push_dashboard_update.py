import os
import json
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, 'src')
from nthlayer.providers.grafana import GrafanaProvider

grafana_url = os.getenv('NTHLAYER_GRAFANA_URL')
grafana_api_key = os.getenv('NTHLAYER_GRAFANA_API_KEY')

print(f"📤 Pushing to {grafana_url}")

with open('generated/dashboards/payment-api.json') as f:
    data = json.load(f)

dashboard = data['dashboard']
provider = GrafanaProvider(url=grafana_url, token=grafana_api_key, org_id=1)

async def push():
    await provider.dashboard('payment-api-overview').apply({
        'dashboard': dashboard,
        'folderUid': None,
        'title': dashboard['title']
    })

asyncio.run(push())
print(f"✅ Updated: {grafana_url}/d/payment-api-overview")
