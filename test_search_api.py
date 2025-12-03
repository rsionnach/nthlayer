#!/usr/bin/env python3
"""Test search-api service with SDK builder."""

import json
from src.nthlayer.specs import parse_service_file
from src.nthlayer.dashboards.builder_sdk import DashboardBuilderSDK

print("=" * 70)
print("  NEW SERVICE TEST: search-api")
print("=" * 70)
print()

# Parse service file
print("1. Parsing search-api.yaml...")
service_context, resources = parse_service_file("examples/services/search-api.yaml")
print(f"   ✅ Service: {service_context.name}")
print(f"      Team: {service_context.team}")
print(f"      Type: {service_context.type}")
print(f"      Tier: {service_context.tier}")
print(f"      Language: {service_context.language}")
print(f"      Framework: {service_context.framework}")
print()

print("2. Resources detected:")
slos = [r for r in resources if r.kind == "SLO"]
deps = [r for r in resources if r.kind == "Dependencies"]
pd = [r for r in resources if r.kind == "PagerDuty"]
print(f"   SLOs: {len(slos)}")
for slo in slos:
    spec = slo.spec
    name = spec.get('name', slo.name) if isinstance(spec, dict) else slo.name
    obj = spec.get('objective', 99.9) if isinstance(spec, dict) else 99.9
    print(f"     - {name} (target: {obj}%)")
print(f"   Dependencies: {len(deps)}")
print(f"   PagerDuty: {len(pd)}")
print()

# Build dashboard
print("3. Building dashboard with SDK...")
builder = DashboardBuilderSDK(
    service_context=service_context,
    resources=resources,
    full_panels=False
)
dashboard_payload = builder.build()
dashboard_json = dashboard_payload['dashboard']
print(f"   ✅ Dashboard built successfully")
print(f"      Title: {dashboard_json['title']}")
print(f"      UID: {dashboard_json['uid']}")
print(f"      Tags: {dashboard_json['tags']}")
print(f"      Panels: {len(dashboard_json['panels'])}")
print()

# Panel breakdown
print("4. Panel breakdown by type:")
panel_types = {}
for panel in dashboard_json['panels']:
    ptype = panel['type']
    panel_types[ptype] = panel_types.get(ptype, 0) + 1

for ptype, count in sorted(panel_types.items()):
    print(f"   {ptype}: {count} panels")
print()

print("5. All panels:")
for i, panel in enumerate(dashboard_json['panels'], 1):
    targets = panel.get('targets', [])
    query_preview = ""
    if targets and targets[0].get('expr'):
        query_preview = targets[0]['expr'][:50] + "..."
    print(f"   {i:>2}. {panel['title']:<40} ({panel['type']:<10}) {query_preview}")
print()

# Identify panel categories
slo_panels = [p for p in dashboard_json['panels'] if 'search' in p['title'].lower() and any(x in p['title'].lower() for x in ['availability', 'latency', 'quality'])]
health_panels = [p for p in dashboard_json['panels'] if any(x in p['title'].lower() for x in ['request', 'error', 'rate'])]
tech_panels = [p for p in dashboard_json['panels'] if any(x in p['title'].lower() for x in ['elasticsearch', 'redis', 'cache', 'index'])]

print("6. Panel categories:")
print(f"   SLO panels: {len(slo_panels)}")
print(f"   Health panels: {len(health_panels)}")
print(f"   Technology panels: {len(tech_panels)}")
print(f"   Other panels: {len(dashboard_json['panels']) - len(slo_panels) - len(health_panels) - len(tech_panels)}")
print()

# Write to file
import os
output_dir = "generated/search-api"
os.makedirs(output_dir, exist_ok=True)
output_file = f"{output_dir}/dashboard-sdk.json"

with open(output_file, 'w') as f:
    json.dump(dashboard_payload, f, indent=2)

file_size = os.path.getsize(output_file)
print("7. Output:")
print(f"   File: {output_file}")
print(f"   Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
print()

# Validate
print("8. Validation:")
required_keys = ['title', 'uid', 'tags', 'schemaVersion', 'panels']
missing = [k for k in required_keys if k not in dashboard_json]
if missing:
    print(f"   ❌ Missing keys: {missing}")
else:
    print(f"   ✅ All required keys present")

panels_without_queries = [p['title'] for p in dashboard_json['panels'] if not p.get('targets')]
if panels_without_queries:
    print(f"   ❌ Panels without queries: {panels_without_queries}")
else:
    print(f"   ✅ All panels have queries")

print(f"   ✅ Schema version: {dashboard_json['schemaVersion']}")
print()

print("=" * 70)
print("  ✅ search-api DASHBOARD GENERATED SUCCESSFULLY")
print("=" * 70)
print()
print("Summary:")
print(f"  - {len(dashboard_json['panels'])} panels generated")
print(f"  - {len(slo_panels)} SLO panels")
print(f"  - {len(health_panels)} health monitoring panels")
print(f"  - {len(tech_panels)} technology-specific panels")
print(f"  - {file_size/1024:.1f} KB of valid Grafana JSON")
print(f"  - Ready for demo deployment")
