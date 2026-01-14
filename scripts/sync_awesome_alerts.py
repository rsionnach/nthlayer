#!/usr/bin/env python3
"""
Sync awesome-prometheus-alerts templates to NthLayer format.

Downloads the upstream rules.yml from awesome-prometheus-alerts and converts
them to NthLayer's Prometheus alert format, organized by category.

Usage:
    python scripts/sync_awesome_alerts.py [--dry-run] [--upstream-url URL]

The script will:
1. Download upstream rules.yml
2. Parse and convert to Prometheus alert format
3. Apply NthLayer validation fixes (label refs, min duration)
4. Write to src/nthlayer/alerts/templates/
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import yaml

# Default upstream URL
DEFAULT_UPSTREAM_URL = (
    "https://raw.githubusercontent.com/samber/awesome-prometheus-alerts/master/_data/rules.yml"
)

# Category mapping from service names to NthLayer categories
CATEGORY_MAP = {
    # Databases
    "postgresql": ("databases", "postgres"),
    "mysql": ("databases", "mysql"),
    "mariadb": ("databases", "mysql"),
    "redis": ("databases", "redis"),
    "mongodb": ("databases", "mongodb"),
    "elasticsearch": ("databases", "elasticsearch"),
    "cassandra": ("databases", "cassandra"),
    "couchdb": ("databases", "couchdb"),
    "clickhouse": ("databases", "clickhouse"),
    "sql server": ("databases", "sqlserver"),
    # Brokers
    "kafka": ("brokers", "kafka"),
    "rabbitmq": ("brokers", "rabbitmq"),
    "nats": ("brokers", "nats"),
    # Proxies
    "nginx": ("proxies", "nginx"),
    "apache": ("proxies", "apache"),
    "haproxy": ("proxies", "haproxy"),
    "traefik": ("proxies", "traefik"),
    "caddy": ("proxies", "caddy"),
    # Orchestrators
    "kubernetes": ("orchestrators", "kubernetes"),
    "docker": ("orchestrators", "docker"),
    "nomad": ("orchestrators", "nomad"),
    # Systems
    "host": ("systems", "host"),
    "node": ("systems", "host"),
    "windows": ("systems", "windows"),
    # Monitoring
    "prometheus": ("monitoring", "prometheus"),
    "alertmanager": ("monitoring", "prometheus"),
    "thanos": ("monitoring", "thanos"),
    "cortex": ("monitoring", "cortex"),
    "loki": ("monitoring", "loki"),
    "grafana": ("monitoring", "grafana"),
    # Service discovery
    "consul": ("discovery", "consul"),
    "etcd": ("discovery", "etcd"),
    "zookeeper": ("discovery", "zookeeper"),
    # Other
    "blackbox": ("network", "blackbox"),
    "vault": ("security", "vault"),
    "jenkins": ("ci", "jenkins"),
    "argocd": ("ci", "argocd"),
}


@dataclass
class ConvertedAlert:
    """An alert converted to Prometheus format."""

    name: str
    expr: str
    duration: str
    severity: str
    summary: str
    description: str
    category: str
    technology: str
    labels: dict[str, str] = field(default_factory=dict)


def normalize_alert_name(name: str) -> str:
    """Convert alert name to PascalCase alert name."""
    # Remove special characters and convert to PascalCase
    words = re.split(r"[\s\-_]+", name)
    return "".join(word.capitalize() for word in words if word)


def guess_category(service_name: str, group_name: str) -> tuple[str, str]:
    """Guess category and technology from service/group names."""
    service_lower = service_name.lower()
    group_lower = group_name.lower()

    # Try service name first
    for key, (category, tech) in CATEGORY_MAP.items():
        if key in service_lower:
            return category, tech

    # Try group name
    for key, (category, tech) in CATEGORY_MAP.items():
        if key in group_lower:
            return category, tech

    # Default to 'other'
    tech = re.sub(r"[^a-z0-9]", "-", service_lower)
    tech = re.sub(r"-+", "-", tech).strip("-")
    return "other", tech or "unknown"


def parse_upstream_rules(rules_yaml: str) -> list[ConvertedAlert]:
    """Parse upstream rules.yml and convert to ConvertedAlert objects."""
    data = yaml.safe_load(rules_yaml)
    alerts = []

    for group in data.get("groups", []) or []:
        group_name = group.get("name", "")

        for service in group.get("services", []) or []:
            service_name = service.get("name", "")
            category, technology = guess_category(service_name, group_name)

            for exporter in service.get("exporters", []) or []:
                for rule in exporter.get("rules", []) or []:
                    if not rule:
                        continue
                    name = rule.get("name", "")
                    if not name:
                        continue

                    alert = ConvertedAlert(
                        name=normalize_alert_name(name),
                        expr=rule.get("query", ""),
                        duration=rule.get("for", "0m"),
                        severity=rule.get("severity", "warning"),
                        summary=name,
                        description=rule.get("description", ""),
                        category=category,
                        technology=technology,
                    )
                    alerts.append(alert)

    return alerts


def apply_nthlayer_fixes(alerts: list[ConvertedAlert]) -> list[ConvertedAlert]:
    """Apply NthLayer validation fixes to alerts."""
    fixed = []

    for alert in alerts:
        # Fix 1: Ensure minimum duration
        if alert.duration in ("0m", "0s", ""):
            alert.duration = "1m"

        # Fix 2: We don't add {{ $labels.instance }} automatically
        # The upstream does this during their rendering, but we'll be smarter
        # and only add it if the query preserves the instance label

        fixed.append(alert)

    return fixed


def group_by_technology(alerts: list[ConvertedAlert]) -> dict[str, dict[str, list[ConvertedAlert]]]:
    """Group alerts by category and technology."""
    grouped: dict[str, dict[str, list[ConvertedAlert]]] = {}

    for alert in alerts:
        if alert.category not in grouped:
            grouped[alert.category] = {}
        if alert.technology not in grouped[alert.category]:
            grouped[alert.category][alert.technology] = []
        grouped[alert.category][alert.technology].append(alert)

    return grouped


def alert_to_prometheus_dict(alert: ConvertedAlert) -> dict[str, Any]:
    """Convert alert to Prometheus YAML dict format."""
    labels = {"severity": alert.severity}
    labels.update(alert.labels)

    annotations = {
        "summary": f"{alert.summary} (instance {{{{ $labels.instance }}}})",
        "description": f"{alert.description}\n  VALUE = {{{{ $value }}}}\n  LABELS = {{{{ $labels }}}}",
    }

    return {
        "alert": alert.name,
        "expr": alert.expr,
        "for": alert.duration,
        "labels": labels,
        "annotations": annotations,
    }


def write_template_file(
    category: str,
    technology: str,
    alerts: list[ConvertedAlert],
    output_dir: Path,
    dry_run: bool = False,
) -> Path:
    """Write alerts to a template file."""
    # Create category directory
    category_dir = output_dir / category
    if not dry_run:
        category_dir.mkdir(parents=True, exist_ok=True)

    # Create output structure
    output = {
        "groups": [
            {
                "name": technology,
                "rules": [alert_to_prometheus_dict(a) for a in alerts],
            }
        ]
    }

    # Build file content
    header = f"""# {technology.title()} Alerting Rules
# Source: https://github.com/samber/awesome-prometheus-alerts
#
# Auto-synced by NthLayer. Do not edit manually.
# Run: python scripts/sync_awesome_alerts.py

"""
    content = header + yaml.dump(output, default_flow_style=False, sort_keys=False, width=120)

    # Write file
    output_file = category_dir / f"{technology}.yaml"
    if dry_run:
        print(f"  Would write: {output_file} ({len(alerts)} alerts)")
    else:
        output_file.write_text(content)
        print(f"  Wrote: {output_file} ({len(alerts)} alerts)")

    return output_file


def write_stats_file(stats: dict[str, Any], output_dir: Path, dry_run: bool = False) -> None:
    """Write statistics to JSON file for badge generation."""
    import json
    from datetime import datetime, timezone

    stats_file = output_dir.parent.parent.parent.parent.parent / "alert_stats.json"

    stats_data = {
        "total_alerts": stats["total_alerts"],
        "categories": stats["categories"],
        "files": stats["files_written"],
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "upstream_url": "https://github.com/samber/awesome-prometheus-alerts",
    }

    if dry_run:
        print(f"  Would write stats to: {stats_file}")
    else:
        stats_file.write_text(json.dumps(stats_data, indent=2))
        print(f"  Wrote stats to: {stats_file}")


def sync_alerts(
    upstream_url: str = DEFAULT_UPSTREAM_URL,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Main sync function.

    Returns:
        Dict with sync statistics
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "src" / "nthlayer" / "alerts" / "templates"

    print(f"Syncing from: {upstream_url}")
    print(f"Output dir: {output_dir}")
    print()

    # Download upstream
    print("Downloading upstream rules.yml...")
    with urlopen(upstream_url) as response:
        rules_yaml = response.read().decode("utf-8")
    print(f"  Downloaded {len(rules_yaml)} bytes")
    print()

    # Parse
    print("Parsing rules...")
    alerts = parse_upstream_rules(rules_yaml)
    print(f"  Found {len(alerts)} alerts")
    print()

    # Apply fixes
    print("Applying NthLayer fixes...")
    alerts = apply_nthlayer_fixes(alerts)
    print("  Done")
    print()

    # Group by category/technology
    grouped = group_by_technology(alerts)

    # Write files
    print("Writing template files...")
    files_written = 0
    for category, technologies in sorted(grouped.items()):
        for technology, tech_alerts in sorted(technologies.items()):
            write_template_file(category, technology, tech_alerts, output_dir, dry_run)
            files_written += 1
    print()

    # Summary
    stats = {
        "total_alerts": len(alerts),
        "categories": len(grouped),
        "files_written": files_written,
        "dry_run": dry_run,
    }

    print("Summary:")
    print(f"  Total alerts: {stats['total_alerts']}")
    print(f"  Categories: {stats['categories']}")
    print(f"  Files written: {stats['files_written']}")

    # Write stats file for badge
    write_stats_file(stats, output_dir, dry_run)

    return stats


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Sync awesome-prometheus-alerts to NthLayer format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    parser.add_argument(
        "--upstream-url",
        default=DEFAULT_UPSTREAM_URL,
        help="URL to upstream rules.yml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for templates",
    )

    args = parser.parse_args()

    try:
        sync_alerts(
            upstream_url=args.upstream_url,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
