#!/usr/bin/env python3
"""
Regenerate all dashboards using the Enhanced Hybrid Model.

This script:
1. Uses LIVE metric discovery from Prometheus/metrics endpoint
2. Uses intent-based templates for metric resolution
3. Generates dashboards that work with any exporter version
4. Pushes updated dashboards to Grafana Cloud
5. Shows resolution summary for each service
"""

import json
import os
import sys
import requests
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
from nthlayer.dashboards.resolver import MetricResolver, create_resolver
from nthlayer.discovery.client import MetricDiscoveryClient
from nthlayer.specs.models import ServiceContext, Resource

# Grafana Cloud configuration
GRAFANA_URL = os.getenv('NTHLAYER_GRAFANA_URL', 'https://nthlayer.grafana.net')
GRAFANA_API_KEY = os.getenv('NTHLAYER_GRAFANA_API_KEY')

# Prometheus/Metrics endpoint for live discovery
METRICS_URL = os.getenv('METRICS_URL', 'https://nthlayer-demo.fly.dev')
METRICS_USER = os.getenv('METRICS_USER', 'nthlayer')
METRICS_PASSWORD = os.getenv('METRICS_PASSWORD')

if not GRAFANA_API_KEY:
    print("❌ NTHLAYER_GRAFANA_API_KEY not set")
    sys.exit(1)

if not METRICS_PASSWORD:
    print("⚠️  METRICS_PASSWORD not set - will use offline mode")
    USE_LIVE_DISCOVERY = False
else:
    USE_LIVE_DISCOVERY = True

# Service configurations
SERVICES = [
    {
        'name': 'payment-api',
        'team': 'payments',
        'tier': 'critical',
        'type': 'api',
        'databases': [{'type': 'postgresql', 'name': 'payments-db'}],
        'caches': [{'type': 'redis', 'name': 'payments-cache'}],
    },
    {
        'name': 'checkout-service',
        'team': 'commerce',
        'tier': 'critical',
        'type': 'api',
        'databases': [{'type': 'mysql', 'name': 'checkout-db'}],
        'caches': [{'type': 'redis', 'name': 'checkout-cache'}],
    },
    {
        'name': 'identity-service',
        'team': 'platform',
        'tier': 'critical',
        'type': 'api',
        'databases': [{'type': 'postgresql', 'name': 'identity-db'}],
        'caches': [{'type': 'redis', 'name': 'session-cache'}],
    },
    {
        'name': 'analytics-stream',
        'team': 'data',
        'tier': 'standard',
        'type': 'stream',
        'databases': [],
        'caches': [{'type': 'redis', 'name': 'stream-buffer'}],
    },
    {
        'name': 'notification-worker',
        'team': 'platform',
        'tier': 'standard',
        'type': 'worker',
        'databases': [],
        'caches': [{'type': 'redis', 'name': 'notification-queue'}],
    },
    {
        'name': 'search-api',
        'team': 'search',
        'tier': 'standard',
        'type': 'api',
        'databases': [{'type': 'elasticsearch', 'name': 'search-index'}],
        'caches': [{'type': 'redis', 'name': 'search-cache'}],
    },
]

print("=" * 70)
print("  Regenerating Dashboards with Enhanced Hybrid Model")
print("=" * 70)
print(f"\nGrafana URL: {GRAFANA_URL}")
print(f"Metrics URL: {METRICS_URL}")
print(f"Services: {len(SERVICES)}")
print(f"Using intent-based templates: YES")
print(f"Live discovery: {'YES' if USE_LIVE_DISCOVERY else 'NO (offline mode)'}")
print()

# Create discovery client for live metric discovery
discovery_client = None
discovered_metrics = set()

if USE_LIVE_DISCOVERY:
    print("🔍 Discovering metrics from live endpoint...")
    try:
        discovery_client = MetricDiscoveryClient(
            prometheus_url=METRICS_URL,
            username=METRICS_USER,
            password=METRICS_PASSWORD
        )
        # Discover all metrics (no service filter)
        result = discovery_client.discover('{}')
        discovered_metrics = {m.name for m in result.metrics}
        print(f"   Found {len(discovered_metrics)} metrics")
        
        # Show metric categories
        by_tech = result.metrics_by_technology
        for tech, metrics in by_tech.items():
            print(f"   - {tech}: {len(metrics)} metrics")
        print()
    except Exception as e:
        print(f"   ⚠️ Discovery failed: {e}")
        print("   Continuing without live discovery...")
        USE_LIVE_DISCOVERY = False

# Create resolver with discovered metrics
resolver = MetricResolver(discovery_client=discovery_client)
if discovered_metrics:
    resolver.set_discovered_metrics(discovered_metrics)

headers = {
    "Authorization": f"Bearer {GRAFANA_API_KEY}",
    "Content-Type": "application/json"
}

results = []

for svc in SERVICES:
    print(f"{'='*70}")
    print(f"  {svc['name']}")
    print(f"{'='*70}")
    
    # Create context
    context = ServiceContext(
        name=svc['name'],
        team=svc['team'],
        tier=svc['tier'],
        type=svc['type'],
    )
    
    # Create resources with service-type-appropriate SLO queries
    service_type = svc['type']
    
    if service_type == 'stream':
        # Stream processors use events_processed_total, not http_requests
        slo_resources = [
            Resource(
                kind='SLO',
                name='availability',
                spec={
                    'objective': 99.9, 
                    'window': '30d',
                    'query': 'sum(rate(events_processed_total{service="$service",status="success"}[5m])) / sum(rate(events_processed_total{service="$service"}[5m])) * 100'
                }
            ),
            Resource(
                kind='SLO',
                name='processing-latency-p95',
                spec={
                    'objective': 99.0, 
                    'query': 'histogram_quantile(0.95, sum by (le) (rate(event_processing_duration_seconds_bucket{service="$service"}[5m]))) * 1000'
                }
            ),
        ]
    elif service_type == 'worker':
        # Workers use notifications_sent_total or jobs_processed_total
        slo_resources = [
            Resource(
                kind='SLO',
                name='availability',
                spec={
                    'objective': 99.9, 
                    'window': '30d',
                    'query': 'sum(rate(notifications_sent_total{service="$service",status="success"}[5m])) / sum(rate(notifications_sent_total{service="$service"}[5m])) * 100'
                }
            ),
            Resource(
                kind='SLO',
                name='processing-latency-p95',
                spec={
                    'objective': 99.0, 
                    'query': 'histogram_quantile(0.95, sum by (le) (rate(notification_processing_duration_seconds_bucket{service="$service"}[5m]))) * 1000'
                }
            ),
        ]
    else:
        # API/web services use HTTP metrics
        slo_resources = [
            Resource(
                kind='SLO',
                name='availability',
                spec={
                    'objective': 99.9, 
                    'window': '30d',
                    'query': 'sum(rate(http_requests_total{service="$service",status!~"5.."}[5m])) / sum(rate(http_requests_total{service="$service"}[5m])) * 100'
                }
            ),
            Resource(
                kind='SLO',
                name='latency-p95',
                spec={
                    'objective': 99.0, 
                    'query': 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m]))) * 1000'
                }
            ),
            Resource(
                kind='SLO',
                name='latency-p99',
                spec={
                    'objective': 95.0, 
                    'query': 'histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{service="$service"}[5m]))) * 1000'
                }
            ),
        ]
    
    resources = slo_resources
    
    if svc['databases'] or svc['caches']:
        resources.append(Resource(
            kind='Dependencies',
            name='deps',
            spec={
                'databases': svc['databases'],
                'caches': svc['caches'],
            }
        ))
    
    print(f"   Building with Hybrid Model...")
    
    try:
        # Clear resolution cache for fresh resolution per service
        resolver._resolution_cache.clear()
        
        # Build with hybrid model
        builder = DashboardBuilderSDK(
            service_context=context,
            resources=resources,
            use_intent_templates=True,
        )
        
        # Set resolver with discovered metrics
        builder.resolver = resolver
        
        result = builder.build()
        dashboard_json = result.get('dashboard', result)
        
        # CRITICAL: Add template variables (required for $service to work)
        dashboard_json['templating'] = {
            'list': [
                {
                    'name': 'service',
                    'type': 'constant',
                    'current': {
                        'value': svc['name'],
                        'text': svc['name']
                    },
                    'hide': 2,  # Hide variable (it's constant)
                    'label': 'Service',
                    'query': svc['name']
                }
            ]
        }
        
        panel_count = len(dashboard_json.get('panels', []))
        print(f"   Title: {dashboard_json.get('title')}")
        print(f"   UID: {dashboard_json.get('uid')}")
        print(f"   Panels: {panel_count}")
        
        # Show resolution summary
        if resolver:
            summary = resolver.get_resolution_summary()
            resolved = summary.get('resolved', 0)
            fallback = summary.get('fallback', 0)
            unresolved = summary.get('unresolved', 0)
            
            if resolved + fallback + unresolved > 0:
                print(f"   Resolution: ✓{resolved} resolved, ↩{fallback} fallback, ✗{unresolved} unresolved")
            
            if unresolved > 0:
                unresolved_list = resolver.get_unresolved_intents()
                for ur in unresolved_list[:3]:  # Show first 3
                    print(f"      - {ur.intent}: {ur.message[:50]}...")
                if len(unresolved_list) > 3:
                    print(f"      ... and {len(unresolved_list) - 3} more")
        
        # Save to file
        output_dir = Path(f"generated/{svc['name']}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "dashboard-sdk.json"
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"   Saved: {output_file}")
        
        # Push to Grafana
        print(f"   Pushing to Grafana Cloud...")
        
        grafana_payload = {
            "dashboard": dashboard_json,
            "overwrite": True,
            "message": f"Updated with Enhanced Hybrid Model (intent-based)"
        }
        
        response = requests.post(
            f"{GRAFANA_URL}/api/dashboards/db",
            headers=headers,
            json=grafana_payload,
            timeout=30
        )
        
        if response.status_code in (200, 201):
            resp_data = response.json()
            url = resp_data.get('url', f"/d/{dashboard_json.get('uid')}")
            full_url = f"{GRAFANA_URL}{url}"
            print(f"   ✅ SUCCESS")
            print(f"   URL: {full_url}")
            results.append({
                'service': svc['name'],
                'success': True,
                'url': full_url,
                'panels': panel_count
            })
        else:
            print(f"   ❌ FAILED: {response.status_code}")
            print(f"   {response.text[:200]}")
            results.append({
                'service': svc['name'],
                'success': False,
                'error': response.text[:200]
            })
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        results.append({
            'service': svc['name'],
            'success': False,
            'error': str(e)
        })
    
    print()

# Summary
print("=" * 70)
print("  SUMMARY")
print("=" * 70)

successful = [r for r in results if r.get('success')]
failed = [r for r in results if not r.get('success')]

print(f"\nTotal: {len(results)}")
print(f"Successful: {len(successful)}")
print(f"Failed: {len(failed)}")

if successful:
    print("\n✅ Successfully updated:")
    total_panels = 0
    for r in successful:
        print(f"   • {r['service']} ({r.get('panels', 0)} panels)")
        print(f"     {r['url']}")
        total_panels += r.get('panels', 0)
    print(f"\n   Total panels: {total_panels}")

if failed:
    print("\n❌ Failed:")
    for r in failed:
        print(f"   • {r['service']}: {r.get('error', 'Unknown error')}")

if len(successful) == len(results):
    print("\n" + "=" * 70)
    print("  🎉 ALL DASHBOARDS UPDATED WITH HYBRID MODEL!")
    print("=" * 70)
