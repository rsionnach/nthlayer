#!/usr/bin/env python3
"""
Comprehensive dashboard audit - check ALL panels against actual metrics
"""
import json
import os
import subprocess
import sys

METRICS_PASSWORD = os.environ.get("METRICS_PASSWORD")
if not METRICS_PASSWORD:
    print("Error: METRICS_PASSWORD environment variable not set")
    sys.exit(1)

# Fetch all metrics from Fly.io
print("Fetching metrics from Fly.io...")
result = subprocess.run([
    'curl', '-s', '-u', f'nthlayer:{METRICS_PASSWORD}',
    'https://nthlayer-demo.fly.dev/metrics'
], capture_output=True, text=True)

metrics_output = result.stdout

# Parse metric names
metric_names = set()
for line in metrics_output.split('\n'):
    if line and not line.startswith('#'):
        metric_name = line.split('{')[0] if '{' in line else line.split()[0]
        if metric_name:
            metric_names.add(metric_name)

print(f"\n✅ Found {len(metric_names)} unique metric names\n")

# Audit each dashboard
services = ['analytics-stream', 'checkout-service', 'notification-worker', 'identity-service', 'payment-api']

for service in services:
    print(f"\n{'='*80}")
    print(f"AUDITING: {service}")
    print(f"{'='*80}\n")
    
    # Load dashboard
    dashboard_file = f'generated/{service}/dashboard.json'
    try:
        with open(dashboard_file) as f:
            dashboard = json.load(f)['dashboard']
    except FileNotFoundError:
        print(f"❌ Dashboard file not found: {dashboard_file}")
        continue
    
    # Check metrics for this service
    service_metrics = {m for m in metric_names if f'service="{service}"' in metrics_output and m in metrics_output}
    
    print(f"Available metrics for {service}:")
    for m in sorted(service_metrics):
        # Count how many times this metric appears for this service
        count = metrics_output.count(f'{m}{{')
        print(f"  - {m}")
    print()
    
    # Check each panel
    issues = []
    for panel in dashboard['panels']:
        if panel.get('type') == 'row':
            continue
        
        panel_id = panel.get('id')
        panel_title = panel.get('title', 'Unknown')
        targets = panel.get('targets', [])
        
        for target in targets:
            expr = target.get('expr', '')
            if not expr:
                continue
            
            # Extract metric names from expression
            # Look for patterns like: metric_name{...}
            import re
            metrics_in_query = set(re.findall(r'([a-z_][a-z0-9_]*)\{', expr))
            
            # Check if metrics exist
            missing = []
            for metric in metrics_in_query:
                if metric not in metric_names:
                    missing.append(metric)
            
            if missing:
                issues.append({
                    'panel_id': panel_id,
                    'panel_title': panel_title,
                    'query': expr[:100] + '...' if len(expr) > 100 else expr,
                    'missing_metrics': missing
                })
    
    if issues:
        print(f"❌ ISSUES FOUND ({len(issues)} panels):\n")
        for issue in issues:
            print(f"Panel {issue['panel_id']}: {issue['panel_title']}")
            print(f"  Query: {issue['query']}")
            print(f"  Missing metrics: {', '.join(issue['missing_metrics'])}")
            print()
    else:
        print(f"✅ All panel queries have matching metrics\n")

print(f"\n{'='*80}")
print("AUDIT COMPLETE")
print(f"{'='*80}\n")
