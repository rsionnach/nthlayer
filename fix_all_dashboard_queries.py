#!/usr/bin/env python3
"""Fix ALL broken queries in ALL dashboards - properly with JSON parsing."""

import json
import os

SERVICES = ["payment-api", "checkout-service", "notification-worker", "analytics-stream", "identity-service", "search-api"]

print("=" * 80)
print("  FIXING ALL BROKEN QUERIES (JSON-SAFE)")
print("=" * 80)
print()

total_fixes = 0

for service in SERVICES:
    dashboard_file = f"generated/{service}/dashboard-sdk.json"
    
    if not os.path.exists(dashboard_file):
        continue
    
    print(f"Processing: {service}")
    
    with open(dashboard_file) as f:
        payload = json.load(f)
    
    dashboard = payload.get('dashboard', payload)
    service_fixes = []
    
    for panel in dashboard.get('panels', []):
        for target in panel.get('targets', []):
            expr = target.get('expr', '')
            if not expr:
                continue
            
            original_expr = expr
            
            # Fix 1: http_requests{ -> http_requests_total{
            if 'http_requests{' in expr and 'http_requests_total{' not in expr:
                expr = expr.replace('http_requests{', 'http_requests_total{')
                service_fixes.append(f"{panel.get('title')}: http_requests -> http_requests_total")
            
            # Fix 2: code!~ -> status!~
            if 'code!~' in expr:
                expr = expr.replace('code!~', 'status!~')
                service_fixes.append(f"{panel.get('title')}: code!~ -> status!~")
            
            # Fix 3: code=~ -> status=~
            if 'code=~' in expr:
                expr = expr.replace('code=~', 'status=~')
                service_fixes.append(f"{panel.get('title')}: code=~ -> status=~")
            
            # Fix 4: pg_table_bloat_ratio -> actual metric
            if 'pg_table_bloat_ratio' in expr:
                expr = expr.replace('pg_table_bloat_ratio', 'pg_stat_user_tables_n_dead_tup')
                service_fixes.append(f"{panel.get('title')}: Table bloat metric fixed")
            
            # Fix 5: Connection pool division
            if 'pg_stat_database_numbackends' in expr and 'pg_settings_max_connections' in expr and '/' in expr:
                # Simple fix: just use percentage of active connections
                if 'sum(pg_stat_database_numbackends' not in expr:
                    expr = expr.replace(
                        'pg_stat_database_numbackends',
                        'sum(pg_stat_database_numbackends'
                    ).replace('/ pg_settings_max_connections', '/ ignoring(datname) group_left pg_settings_max_connections) ')
                    service_fixes.append(f"{panel.get('title')}: Connection pool division fixed")
            
            if expr != original_expr:
                target['expr'] = expr
                total_fixes += 1
    
    # Save if any fixes made
    if service_fixes:
        with open(dashboard_file, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f"  ✅ Fixed {len(service_fixes)} queries")
        for fix in service_fixes[:5]:  # Show first 5
            print(f"     - {fix}")
        if len(service_fixes) > 5:
            print(f"     ... and {len(service_fixes) - 5} more")
    else:
        print(f"  ℹ️  No fixes needed")

print()
print("=" * 80)
print(f"Total fixes applied: {total_fixes}")
print("=" * 80)
