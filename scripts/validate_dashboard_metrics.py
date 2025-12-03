#!/usr/bin/env python3
"""
CI Validation Script for Dashboard Metrics.

This script validates that all dashboard panels have resolvable metrics
before deployment. It can be run in CI/CD pipelines to catch metric
gaps early.

Usage:
    python scripts/validate_dashboard_metrics.py [--strict] [--service SERVICE]

Options:
    --strict    Fail if any metrics are unresolved (exit code 1)
    --service   Validate only a specific service
    --prometheus-url  Use live discovery from a Prometheus endpoint
    --output    Output format: text, json, github (for PR annotations)

Exit codes:
    0 - All metrics resolved (or no strict mode)
    1 - Some metrics unresolved (strict mode)
    2 - Configuration error
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nthlayer.dashboards.resolver import MetricResolver, ResolutionStatus, create_resolver
from nthlayer.dashboards.intents import get_intents_for_technology, list_technologies
from nthlayer.discovery.client import MetricDiscoveryClient


# Default service configurations (same as regenerate script)
SERVICES = [
    {
        'name': 'payment-api',
        'type': 'api',
        'technologies': ['postgresql', 'redis'],
    },
    {
        'name': 'checkout-service',
        'type': 'api',
        'technologies': ['mysql', 'redis'],
    },
    {
        'name': 'identity-service',
        'type': 'api',
        'technologies': ['postgresql', 'redis'],
    },
    {
        'name': 'analytics-stream',
        'type': 'stream',
        'technologies': ['mongodb', 'redis', 'kafka'],
    },
    {
        'name': 'notification-worker',
        'type': 'worker',
        'technologies': ['redis', 'kafka'],
    },
    {
        'name': 'search-api',
        'type': 'api',
        'technologies': ['elasticsearch', 'redis'],
    },
]


def get_intents_for_service(service: Dict[str, Any]) -> List[str]:
    """Get all intents that a service dashboard would use."""
    intents = []
    
    # Add service-type intents
    service_type = service['type']
    if service_type == 'stream':
        intents.extend(['stream.events_processed', 'stream.event_duration'])
    elif service_type == 'worker':
        intents.extend(['worker.jobs_processed', 'worker.job_duration'])
    else:  # api, web, service
        intents.extend(['http.requests_total', 'http.request_duration', 'http.requests_in_flight'])
    
    # Add technology-specific intents
    for tech in service.get('technologies', []):
        tech_intents = get_intents_for_technology(tech)
        intents.extend(tech_intents.keys())
    
    return intents


def validate_service(
    service: Dict[str, Any],
    resolver: MetricResolver,
    verbose: bool = False
) -> Dict[str, Any]:
    """Validate metrics for a single service."""
    intents = get_intents_for_service(service)
    
    results = {
        'service': service['name'],
        'type': service['type'],
        'total_intents': len(intents),
        'resolved': 0,
        'fallback': 0,
        'unresolved': 0,
        'details': []
    }
    
    for intent in intents:
        result = resolver.resolve(intent)
        
        detail = {
            'intent': intent,
            'status': result.status.value,
            'metric': result.metric_name,
            'message': result.message
        }
        
        if result.status == ResolutionStatus.RESOLVED:
            results['resolved'] += 1
        elif result.status == ResolutionStatus.FALLBACK:
            results['fallback'] += 1
        elif result.status == ResolutionStatus.CUSTOM:
            results['resolved'] += 1
        else:
            results['unresolved'] += 1
            detail['needs_action'] = True
        
        results['details'].append(detail)
    
    # Calculate health score
    total = results['total_intents']
    if total > 0:
        results['health_score'] = round(
            (results['resolved'] + results['fallback']) / total * 100, 1
        )
    else:
        results['health_score'] = 100.0
    
    return results


def format_text_output(results: List[Dict[str, Any]], verbose: bool = False) -> str:
    """Format results as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  Dashboard Metrics Validation Report")
    lines.append("=" * 70)
    lines.append("")
    
    total_resolved = 0
    total_fallback = 0
    total_unresolved = 0
    
    for result in results:
        status_icon = "✅" if result['unresolved'] == 0 else "⚠️"
        lines.append(f"{status_icon} {result['service']} ({result['type']})")
        lines.append(f"   Health: {result['health_score']}%")
        lines.append(f"   Intents: {result['total_intents']} total")
        lines.append(f"   ✓ Resolved: {result['resolved']}")
        lines.append(f"   ↩ Fallback: {result['fallback']}")
        lines.append(f"   ✗ Unresolved: {result['unresolved']}")
        
        if result['unresolved'] > 0 or verbose:
            for detail in result['details']:
                if detail.get('needs_action') or verbose:
                    status = "✗" if detail.get('needs_action') else "✓"
                    lines.append(f"      {status} {detail['intent']}: {detail['message'][:50]}")
        
        lines.append("")
        
        total_resolved += result['resolved']
        total_fallback += result['fallback']
        total_unresolved += result['unresolved']
    
    lines.append("=" * 70)
    lines.append("  Summary")
    lines.append("=" * 70)
    lines.append(f"  Total services: {len(results)}")
    lines.append(f"  Total intents: {total_resolved + total_fallback + total_unresolved}")
    lines.append(f"  ✓ Resolved: {total_resolved}")
    lines.append(f"  ↩ Fallback: {total_fallback}")
    lines.append(f"  ✗ Unresolved: {total_unresolved}")
    
    if total_unresolved > 0:
        lines.append("")
        lines.append("  ⚠️  Some metrics are not available. Dashboards will show guidance panels.")
        lines.append("     Run with --verbose for details on each unresolved intent.")
    else:
        lines.append("")
        lines.append("  ✅ All metrics are available. Dashboards will display data correctly.")
    
    return "\n".join(lines)


def format_github_output(results: List[Dict[str, Any]]) -> str:
    """Format results as GitHub Actions annotations."""
    lines = []
    
    for result in results:
        if result['unresolved'] > 0:
            # Create warning annotation
            unresolved_intents = [
                d['intent'] for d in result['details'] if d.get('needs_action')
            ]
            lines.append(
                f"::warning title=Dashboard Metrics ({result['service']})::"
                f"{result['unresolved']} unresolved metrics: {', '.join(unresolved_intents[:5])}"
            )
    
    if not lines:
        lines.append("::notice::All dashboard metrics validated successfully")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate dashboard metrics against available Prometheus metrics"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any metrics are unresolved"
    )
    parser.add_argument(
        "--service",
        type=str,
        help="Validate only a specific service"
    )
    parser.add_argument(
        "--prometheus-url",
        type=str,
        default=os.getenv('METRICS_URL', 'https://nthlayer-demo.fly.dev'),
        help="Prometheus/metrics URL for live discovery"
    )
    parser.add_argument(
        "--output",
        choices=['text', 'json', 'github'],
        default='text',
        help="Output format"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all intent details"
    )
    
    args = parser.parse_args()
    
    # Create resolver with live discovery if credentials available
    metrics_user = os.getenv('METRICS_USER', 'nthlayer')
    metrics_password = os.getenv('METRICS_PASSWORD')
    
    discovery_client = None
    discovered_metrics = set()
    
    if metrics_password:
        print(f"🔍 Discovering metrics from {args.prometheus_url}...", file=sys.stderr)
        try:
            discovery_client = MetricDiscoveryClient(
                prometheus_url=args.prometheus_url,
                username=metrics_user,
                password=metrics_password
            )
            result = discovery_client.discover('{}')
            discovered_metrics = {m.name for m in result.metrics}
            print(f"   Found {len(discovered_metrics)} metrics", file=sys.stderr)
        except Exception as e:
            print(f"   ⚠️ Discovery failed: {e}", file=sys.stderr)
    else:
        print("⚠️ METRICS_PASSWORD not set - running in offline mode", file=sys.stderr)
    
    resolver = MetricResolver(discovery_client=discovery_client)
    if discovered_metrics:
        resolver.set_discovered_metrics(discovered_metrics)
    
    # Filter services if requested
    services = SERVICES
    if args.service:
        services = [s for s in SERVICES if s['name'] == args.service]
        if not services:
            print(f"Error: Service '{args.service}' not found", file=sys.stderr)
            sys.exit(2)
    
    # Validate each service
    results = []
    for service in services:
        result = validate_service(service, resolver, args.verbose)
        results.append(result)
    
    # Output results
    if args.output == 'json':
        print(json.dumps(results, indent=2))
    elif args.output == 'github':
        print(format_github_output(results))
    else:
        print(format_text_output(results, args.verbose))
    
    # Exit code
    total_unresolved = sum(r['unresolved'] for r in results)
    if args.strict and total_unresolved > 0:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
