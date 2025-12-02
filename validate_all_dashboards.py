#!/usr/bin/env python3
"""
Comprehensive dashboard validation - check if ALL panels will actually show data
"""
import json
import subprocess
import re
from collections import defaultdict

# Fetch all metrics from Fly.io
print("Fetching metrics from Fly.io...")
result = subprocess.run([
    'curl', '-s', '-u', 'nthlayer:NthLayerDemo2025!',
    'https://nthlayer-demo.fly.dev/metrics'
], capture_output=True, text=True)

metrics_output = result.stdout

# Parse metrics by service
metrics_by_service = defaultdict(lambda: defaultdict(list))

for line in metrics_output.split('\n'):
    if line and not line.startswith('#') and 'service=' in line:
        # Extract metric name
        metric_name = line.split('{')[0] if '{' in line else line.split()[0]
        
        # Extract service name
        service_match = re.search(r'service="([^"]+)"', line)
        if service_match:
            service = service_match.group(1)
            
            # Extract value
            value_match = re.search(r'\}\s+([\d.e+-]+)', line)
            if value_match:
                try:
                    value = float(value_match.group(1))
                    metrics_by_service[service][metric_name].append(value)
                except:
                    pass

print(f"\n✅ Parsed metrics from {len(metrics_by_service)} services\n")

# Services to audit
services = ['payment-api', 'checkout-service', 'notification-worker', 'analytics-stream', 'identity-service']

all_issues = []

for service in services:
    print(f"\n{'='*80}")
    print(f"VALIDATING: {service}")
    print(f"{'='*80}\n")
    
    # Load dashboard
    dashboard_file = f'generated/{service}/dashboard.json'
    try:
        with open(dashboard_file) as f:
            dashboard = json.load(f)['dashboard']
    except FileNotFoundError:
        print(f"❌ Dashboard file not found: {dashboard_file}")
        continue
    
    service_metrics = metrics_by_service.get(service, {})
    
    if not service_metrics:
        print(f"⚠️  WARNING: No metrics found for {service}!\n")
        continue
    
    print(f"Metrics emitted by {service}:")
    for metric, values in sorted(service_metrics.items()):
        max_val = max(values) if values else 0
        count = len(values)
        print(f"  ✅ {metric}: {count} series, max value: {max_val:.2f}")
    print()
    
    # Check each panel
    issues = []
    warnings = []
    
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
            metrics_in_query = set(re.findall(r'([a-z_][a-z0-9_]*)\{', expr))
            
            # Check each metric
            missing_metrics = []
            zero_data_metrics = []
            
            for metric in metrics_in_query:
                if metric not in service_metrics:
                    missing_metrics.append(metric)
                else:
                    # Check if metric has any non-zero values
                    values = service_metrics[metric]
                    max_value = max(values) if values else 0
                    if max_value == 0:
                        zero_data_metrics.append(f"{metric} (all zeros)")
            
            if missing_metrics:
                issues.append({
                    'panel_id': panel_id,
                    'panel_title': panel_title,
                    'query': expr[:80] + '...' if len(expr) > 80 else expr,
                    'problem': f"Missing metrics: {', '.join(missing_metrics)}",
                    'severity': 'ERROR'
                })
            elif zero_data_metrics:
                warnings.append({
                    'panel_id': panel_id,
                    'panel_title': panel_title,
                    'query': expr[:80] + '...' if len(expr) > 80 else expr,
                    'problem': f"Metrics exist but have no data: {', '.join(zero_data_metrics)}",
                    'severity': 'WARNING'
                })
    
    if issues:
        print(f"❌ ERRORS ({len(issues)} panels will show NO DATA):\n")
        for issue in issues:
            print(f"  Panel {issue['panel_id']}: {issue['panel_title']}")
            print(f"    Query: {issue['query']}")
            print(f"    ❌ {issue['problem']}")
            print()
        all_issues.extend(issues)
    
    if warnings:
        print(f"⚠️  WARNINGS ({len(warnings)} panels may show empty data):\n")
        for warning in warnings:
            print(f"  Panel {warning['panel_id']}: {warning['panel_title']}")
            print(f"    Query: {warning['query']}")
            print(f"    ⚠️  {warning['problem']}")
            print()
        all_issues.extend(warnings)
    
    if not issues and not warnings:
        print(f"✅ All panels have metrics with data!\n")

print(f"\n{'='*80}")
print("VALIDATION COMPLETE")
print(f"{'='*80}\n")

if all_issues:
    errors = [i for i in all_issues if i['severity'] == 'ERROR']
    warnings = [i for i in all_issues if i['severity'] == 'WARNING']
    
    print(f"Summary:")
    print(f"  ❌ {len(errors)} panels with MISSING metrics")
    print(f"  ⚠️  {len(warnings)} panels with ZERO data")
    print(f"\nThese issues must be fixed in the Fly.io app simulation functions.")
else:
    print("✅ All dashboards validated successfully!")
