#!/usr/bin/env python3
"""Test script to push a dashboard with explicit env vars"""
import os
import sys

# You need to set these before running
os.environ['NTHLAYER_GRAFANA_URL'] = 'https://nthlayer.grafana.net'
os.environ['NTHLAYER_GRAFANA_API_KEY'] = 'YOUR_API_KEY_HERE'  # Replace with actual key

from pathlib import Path
from nthlayer.orchestrator import ServiceOrchestrator

service_file = Path("examples/services/payment-api.yaml")
orchestrator = ServiceOrchestrator(service_file, push_to_grafana=True)
result = orchestrator.apply(verbose=True)

print("\n" + "="*60)
if result.errors:
    print("❌ Errors:")
    for error in result.errors:
        print(f"  - {error}")
else:
    print("✅ Success!")
    print(f"Resources: {result.resources_created}")
