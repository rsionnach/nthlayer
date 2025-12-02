#!/usr/bin/env python3
"""
Regenerate all dashboards using the Enhanced Hybrid Model.

This script:
1. Uses intent-based templates for metric resolution
2. Generates dashboards that work with any exporter version
3. Pushes updated dashboards to Grafana Cloud
"""

import json
import os
import sys
import requests
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
from nthlayer.dashboards.resolver import MetricResolver
from nthlayer.specs.models import ServiceContext, Resource

# Grafana Cloud configuration
GRAFANA_URL = os.getenv('NTHLAYER_GRAFANA_URL', 'https://nthlayer.grafana.net')
GRAFANA_API_KEY = os.getenv('NTHLAYER_GRAFANA_API_KEY')

if not GRAFANA_API_KEY:
    print("❌ NTHLAYER_GRAFANA_API_KEY not set")
    sys.exit(1)

# Demo metrics (from fly-app/app.py)
DEMO_METRICS = {
    'http_requests_total', 'http_request_duration_seconds_bucket',
    'pg_stat_database_numbackends', 'pg_settings_max_connections',
    'pg_stat_database_blks_hit', 'pg_stat_database_blks_read',
    'pg_stat_statements_mean_exec_time_seconds_bucket',
    'pg_stat_activity_count', 'pg_stat_database_xact_commit',
    'pg_stat_database_xact_rollback', 'pg_database_size_bytes',
    'pg_stat_database_deadlocks', 'pg_replication_lag_seconds',
    'pg_stat_user_tables_n_dead_tup',
    'redis_connected_clients', 'redis_memory_used_bytes',
    'redis_db_keys', 'cache_hits_total', 'cache_misses_total',
    'mysql_global_status_threads_connected',
    'mysql_global_variables_max_connections',
    'mysql_global_status_queries_total',
    'events_processed_total', 'event_processing_duration_seconds_bucket',
    'notifications_sent_total', 'notification_processing_duration_seconds_bucket',
}

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
print(f"Services: {len(SERVICES)}")
print(f"Using intent-based templates: YES")
print()

# Create resolver with demo metrics
resolver = MetricResolver()
resolver.set_discovered_metrics(DEMO_METRICS)

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
    
    # Create resources
    resources = [
        Resource(
            kind='SLO',
            name='availability',
            spec={'objective': 99.9, 'window': '30d'}
        ),
        Resource(
            kind='SLO',
            name='latency-p95',
            spec={'objective': 99.0, 'percentile': 95, 'threshold_ms': 500}
        ),
        Resource(
            kind='SLO',
            name='latency-p99',
            spec={'objective': 95.0, 'percentile': 99, 'threshold_ms': 1000}
        ),
    ]
    
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
