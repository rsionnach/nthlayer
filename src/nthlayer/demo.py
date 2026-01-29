"""
Demo CLI for NthLayer - Test workflows without real services

Usage:
    nthlayer <command> [args]

Includes reconciliation walkthroughs plus Grafana and Prometheus demos.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from importlib.metadata import version as get_version
from typing import Any, Sequence

import structlog
import yaml

from nthlayer.alerts import AlertTemplateLoader
from nthlayer.alerts.models import AlertRule
from nthlayer.cli.blast_radius import (
    handle_blast_radius_command,
    register_blast_radius_parser,
)
from nthlayer.cli.deps import handle_deps_command, register_deps_parser
from nthlayer.cli.drift import handle_drift_command, register_drift_parser
from nthlayer.cli.migrate import handle_migrate_command, register_migrate_parser
from nthlayer.cli.generate_loki import handle_loki_command, register_loki_parser
from nthlayer.cli.identity import handle_identity_command, register_identity_parser
from nthlayer.cli.ownership import handle_ownership_command, register_ownership_parser
from nthlayer.cli.portfolio import handle_portfolio_command, register_portfolio_parser
from nthlayer.cli.recommend_metrics import (
    handle_recommend_metrics_command,
    register_recommend_metrics_parser,
)
from nthlayer.cli.scorecard import (
    handle_scorecard_command,
    register_scorecard_parser,
)
from nthlayer.cli.setup import handle_setup_command, register_setup_parser
from nthlayer.cli.slo import handle_slo_command, register_slo_parser
from nthlayer.cli.ux import print_banner
from nthlayer.cli.validate_metadata import (
    handle_validate_metadata_command,
    register_validate_metadata_parser,
)
from nthlayer.cli.validate_slo import (
    handle_validate_slo_command,
    register_validate_slo_parser,
)
from nthlayer.cli.validate_spec import (
    handle_validate_spec_command,
    register_validate_spec_parser,
)
from nthlayer.cli.verify import handle_verify_command, register_verify_parser
from nthlayer.providers.grafana import GrafanaProvider, GrafanaProviderError

# Version from package metadata (single source of truth: pyproject.toml)
__version__ = get_version("nthlayer")

logger = structlog.get_logger()

DEFAULT_GRAFANA_URL = os.environ.get("NTHLAYER_GRAFANA_BASE_URL", "http://localhost:8001/grafana")
DEFAULT_GRAFANA_TOKEN = os.environ.get("NTHLAYER_GRAFANA_TOKEN")


def _default_org_id() -> int | None:
    raw = os.environ.get("NTHLAYER_GRAFANA_ORG_ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def load_demo_data() -> dict[str, Any]:
    try:
        with open("tests/fixtures/demo_data.yaml") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Demo data not found. Run from project root.")
        sys.exit(1)


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print()


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")
    print()


async def demo_reconcile_team(team_id: str) -> None:
    print_header(f"🔄 Team Reconciliation Demo: {team_id}")

    data = load_demo_data()

    team = next((t for t in data["teams"] if t["id"] == team_id), None)
    if not team:
        print(f"❌ Team '{team_id}' not found in demo data")
        print(f"Available teams: {', '.join(t['id'] for t in data['teams'])}")
        return

    print_section("1. Input: Team Definition")
    print(yaml.dump(team, default_flow_style=False))

    print_section("2. Fetching Current State")
    print("📥 GET Cortex:     /api/teams/team-platform")
    print("📥 GET PagerDuty:  /teams/TEAM123")
    print("📥 GET PagerDuty:  /teams/TEAM123/members")
    await asyncio.sleep(0.5)
    print("✅ Fetched current state from all sources")

    print_section("3. Computing Differences")
    print("Comparing desired vs actual state...")
    await asyncio.sleep(0.3)

    print("\nChanges detected:")
    print("  • PagerDuty: Add 1 manager (alice@example.com)")
    print("  • PagerDuty: Update 1 member role (bob@example.com → responder)")
    print("  • Slack: Create user group @platform-oncall")

    print_section("4. Applying Changes")
    print("📤 POST PagerDuty: /teams/TEAM123/users")
    print("   Idempotency-Key: nthlayer-team-platform-20250104-abc123")
    print("   Body: { members: [...] }")
    await asyncio.sleep(0.5)
    print("✅ Updated PagerDuty team membership")

    print("📤 POST Slack: /usergroups.create")
    print("   Body: { name: 'platform-oncall', users: [...] }")
    await asyncio.sleep(0.3)
    print("✅ Created Slack user group")

    print_section("5. Recording Audit Trail")
    print("💾 Writing to database:")
    print("   - Run ID: run-20250104-xyz789")
    print("   - Changes: 2")
    print("   - Status: success")
    print("   - Duration: 1.2s")
    await asyncio.sleep(0.2)
    print("✅ Audit trail recorded")

    print_section("6. Sending Notifications")
    print("📨 POST Slack: /chat.postMessage")
    print("   Channel: #team-platform")
    print("   Message: Team reconciliation completed. 2 changes applied.")
    print("✅ Notification sent")

    print_header("✅ Reconciliation Complete")
    print("Summary:")
    print("  • Duration: 1.8s")
    print("  • Changes: 2 applied")
    print("  • API calls: 6 (3 reads, 3 writes)")
    print("  • Status: SUCCESS")
    print()


async def demo_reconcile_service(service_id: str) -> None:
    print_header(f"🔄 Service Reconciliation Demo: {service_id}")

    data = load_demo_data()

    service = next((s for s in data["services"] if s["id"] == service_id), None)
    if not service:
        print(f"❌ Service '{service_id}' not found in demo data")
        print(f"Available services: {', '.join(s['id'] for s in data['services'])}")
        return

    print_section("1. Input: Service Definition")
    print(yaml.dump(service, default_flow_style=False))

    print_section("2. Generating Operational Configs")

    print("📊 Generating alerts based on tier...")
    tier = service["tier"]
    templates = data["alert_templates"].get(f"tier_{tier}", [])
    print(f"   Using {len(templates)} alert templates for tier-{tier}")
    for alert in templates:
        print(f"   • {alert['name']}: {alert['query']}")
    await asyncio.sleep(0.5)
    print("✅ Generated alert definitions")

    print("\n📈 Generating Grafana dashboard...")
    print("   Template: golden_signals")
    print("   Panels: Latency, Traffic, Errors, Saturation")
    await asyncio.sleep(0.5)
    print("✅ Generated dashboard definition")

    print("\n🔔 Configuring PagerDuty escalation...")
    team = next((t for t in data["teams"] if t["id"] == service["team"]), None)
    if team:
        print(f"   Team: {team['name']}")
        print(f"   Schedule: {team['pagerduty_schedule']}")
        print(f"   Escalation: {team['members'][0]['email']} → {team['members'][1]['email']}")
    await asyncio.sleep(0.3)
    print("✅ Generated escalation policy")

    print_section("3. Applying to Target Systems")

    print("📤 POST Datadog: /api/v1/monitor")
    for alert in templates:
        print(f"   • Creating: {alert['name']}")
    await asyncio.sleep(0.6)
    print("✅ Created Datadog monitors")

    print("\n📤 POST Grafana: /api/dashboards/db")
    print("   • Creating: Search API - Golden Signals")
    await asyncio.sleep(0.4)
    print("✅ Created Grafana dashboard")

    print("\n📤 POST PagerDuty: /escalation_policies")
    print("   • Creating: Search API - Escalation")
    await asyncio.sleep(0.3)
    print("✅ Created PagerDuty escalation policy")

    print_header("✅ Service Operationalized")
    print("Summary:")
    print(f"  • Service: {service['name']}")
    print(f"  • Tier: {tier}")
    print(f"  • Alerts created: {len(templates)}")
    print("  • Dashboards created: 1")
    print("  • Escalation policies: 1")
    print("  • Duration: 2.4s")
    print()


def list_services() -> None:
    print_header("📋 Available Demo Services")

    data = load_demo_data()

    print("Services:")
    for service in data["services"]:
        print(f"\n  • {service['id']}")
        print(f"    Name: {service['name']}")
        print(f"    Tier: {service['tier']}")
        print(f"    Team: {service['team']}")
        print(f"    Description: {service['description']}")


def list_teams() -> None:
    print_header("👥 Available Demo Teams")

    data = load_demo_data()

    print("Teams:")
    for team in data["teams"]:
        print(f"\n  • {team['id']}")
        print(f"    Name: {team['name']}")
        print(f"    Members: {len(team['members'])}")
        print(f"    Slack: {team['slack_channel']}")
        print(f"    Schedule: {team['pagerduty_schedule']}")


def _format_change(details: dict[str, Any]) -> str:
    if not details:
        return "(no details)"
    return ", ".join(f"{k}={v}" for k, v in details.items())


def _serialize_plan(plan_changes: list[Any]) -> list[dict[str, Any]]:
    serialized = []
    for change in plan_changes:
        serialized.append(
            {
                "action": getattr(change, "action", "unknown"),
                "details": getattr(change, "details", {}),
            }
        )
    return serialized


async def _plan_and_apply(
    resource: Any, desired_state: dict[str, Any], *, idempotency_key: str | None
) -> dict[str, Any]:
    plan = await resource.plan(desired_state)
    outcome = {
        "changes": _serialize_plan(plan.changes),
        "applied": False,
        "error": None,
    }
    try:
        await resource.apply(desired_state, idempotency_key=idempotency_key)
        outcome["applied"] = True
    except GrafanaProviderError as exc:
        outcome["error"] = str(exc)
    return outcome


async def run_grafana_demo(provider: GrafanaProvider) -> dict[str, dict[str, Any]]:
    folder_uid = "nthlayer-demo"
    dashboard_uid = "nthlayer-demo-dashboard"
    datasource_name = "prometheus-demo"

    folder_state = {"title": "NthLayer Demo Dashboards"}
    dashboard_state = {
        "title": "NthLayer Demo - Golden Signals",
        "folderUid": folder_uid,
        "dashboard": {
            "uid": dashboard_uid,
            "title": "NthLayer Demo - Golden Signals",
            "panels": [
                {"title": "Request Rate", "type": "timeseries"},
                {"title": "Error Rate", "type": "timeseries"},
                {"title": "Latency", "type": "timeseries"},
            ],
        },
    }
    datasource_state = {
        "name": datasource_name,
        "type": "prometheus",
        "url": "http://prometheus:9090",
        "isDefault": True,
    }

    try:
        folder_result = await _plan_and_apply(
            provider.folder(folder_uid),
            folder_state,
            idempotency_key=f"nthlayer-demo-folder-{folder_uid}",
        )
        dashboard_result = await _plan_and_apply(
            provider.dashboard(dashboard_uid),
            dashboard_state,
            idempotency_key=f"nthlayer-demo-dashboard-{dashboard_uid}",
        )
        datasource_result = await _plan_and_apply(
            provider.datasource(datasource_name),
            datasource_state,
            idempotency_key=f"nthlayer-demo-datasource-{datasource_name}",
        )
    finally:
        await provider.aclose()

    return {
        "folder": folder_result,
        "dashboard": dashboard_result,
        "datasource": datasource_result,
    }


def demo_prometheus_alerts(technology: str, limit: int) -> None:
    print_header(f"📡 Prometheus Alerts Demo: {technology}")
    alerts = build_prometheus_alerts_demo(technology, limit)
    if not alerts:
        print(f"No alert templates found for '{technology}'.")
        return

    for idx, alert in enumerate(alerts, start=1):
        print_section(f"Alert {idx}: {alert['name']} ({alert['severity']})")
        print(yaml.dump(alert["prometheus"], default_flow_style=False))

    print(f"Displayed {len(alerts)} alert(s).")


def build_prometheus_alerts_demo(technology: str, limit: int) -> list[dict[str, Any]]:
    loader = AlertTemplateLoader()
    alerts = loader.load_technology(technology)
    if limit > 0:
        alerts = alerts[:limit]

    formatted: list[dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, AlertRule):
            continue
        formatted.append(
            {
                "name": alert.name,
                "severity": alert.severity,
                "prometheus": alert.to_prometheus(),
            }
        )
    return formatted


async def demo_grafana(
    base_url: str, token: str | None, org_id: int | None, timeout: float
) -> None:
    print_header("📊 Grafana Provider Demo")
    print(f"Base URL: {base_url}")
    if org_id is not None:
        print(f"Org ID: {org_id}")
    if token:
        print("Authentication: Bearer token provided")
    else:
        print("Authentication: (none provided)")

    provider = GrafanaProvider(
        base_url,
        token,
        timeout=timeout,
        org_id=org_id,
    )

    results = await run_grafana_demo(provider)

    for label, outcome in (
        ("Grafana Folder", results["folder"]),
        ("Grafana Dashboard", results["dashboard"]),
        ("Grafana Datasource", results["datasource"]),
    ):
        print_section(label)
        if outcome["changes"]:
            for change in outcome["changes"]:
                details = _format_change(change["details"])
                print(f"  • {change['action'].upper()}: {details}")
        else:
            print("  • No changes required")
        if outcome["applied"]:
            print("✅ Apply succeeded")
        elif outcome["error"]:
            print(f"⚠️ Apply failed: {outcome['error']}")
        else:
            print("ℹ️ Apply skipped")


def build_parser() -> argparse.ArgumentParser:
    from rich_argparse import RichHelpFormatter

    parser = argparse.ArgumentParser(
        prog="nthlayer",
        description="NthLayer CLI - Reliability requirements as code",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="store_true", help="Show version and exit")
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # === NEW: Unified apply workflow ===

    # plan command (dry-run)
    plan_parser = subparsers.add_parser(
        "plan", help="Preview what resources would be generated (dry-run)"
    )
    plan_parser.add_argument("service_yaml", help="Path to service YAML file")
    plan_parser.add_argument("--env", help="Environment (dev, staging, prod)")
    plan_parser.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "sarif", "junit", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    plan_parser.add_argument(
        "--output",
        "-o",
        help="Write output to file instead of stdout",
    )
    plan_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed information"
    )

    # apply command (unified generation)
    apply_parser = subparsers.add_parser("apply", help="Generate all resources for a service")
    apply_parser.add_argument("service_yaml", help="Path to service YAML file")
    apply_parser.add_argument("--env", help="Environment (dev, staging, prod)")
    apply_parser.add_argument("--output-dir", help="Output directory for generated files")
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing files"
    )
    apply_parser.add_argument(
        "--skip", nargs="+", help="Resource types to skip (e.g., alerts pagerduty)"
    )
    apply_parser.add_argument("--only", nargs="+", help="Only generate specific resource types")
    apply_parser.add_argument(
        "--force", action="store_true", help="Force regeneration, ignore cache"
    )
    apply_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed progress")
    apply_parser.add_argument(
        "--output", choices=["text", "json"], default="text", help="Output format"
    )
    apply_parser.add_argument(
        "--push-grafana",
        action="store_true",
        help="Push dashboard to Grafana via API (requires NTHLAYER_GRAFANA_URL)",
    )
    apply_parser.add_argument(
        "--push-ruler",
        action="store_true",
        help="Push alerts to Mimir/Cortex Ruler API (requires MIMIR_RULER_URL)",
    )
    apply_parser.add_argument(
        "--lint",
        action="store_true",
        help="Validate generated alerts with pint (requires pint to be installed)",
    )
    apply_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL for metric discovery (or set NTHLAYER_PROMETHEUS_URL)",
    )

    # === EXISTING COMMANDS ===

    # New top-level commands
    generate_parser = subparsers.add_parser(
        "generate-slo", help="Generate SLOs from service definition"
    )
    generate_parser.add_argument("service_file", help="Path to service YAML file")
    generate_parser.add_argument(
        "--output", dest="output_dir", default="generated", help="Output directory"
    )
    generate_parser.add_argument(
        "--format",
        choices=["sloth", "prometheus", "openslo"],
        default="sloth",
        help="Output format",
    )
    generate_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    generate_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    generate_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing files"
    )

    generate_alerts_parser = subparsers.add_parser(
        "generate-alerts", help="Generate alerts from awesome-prometheus-alerts"
    )
    generate_alerts_parser.add_argument("service_file", help="Path to service YAML file")
    generate_alerts_parser.add_argument(
        "--output", "-o", help="Output file path (default: generated/alerts/{service}.yaml)"
    )
    generate_alerts_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    generate_alerts_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    generate_alerts_parser.add_argument(
        "--dry-run", action="store_true", help="Preview alerts without writing file"
    )
    generate_alerts_parser.add_argument("--runbook-url", help="Base URL for runbook links")
    generate_alerts_parser.add_argument(
        "--notification-channel", help="Notification channel (pagerduty, slack, etc.)"
    )

    validate_parser = subparsers.add_parser("validate", help="Validate service definition")
    validate_parser.add_argument("service_file", help="Path to service YAML file")
    validate_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    validate_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    validate_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")

    lint_parser = subparsers.add_parser("lint", help="Lint Prometheus alert rules with pint")
    lint_parser.add_argument("file_path", help="Path to alerts YAML file or directory")
    lint_parser.add_argument("--config", help="Path to .pint.hcl configuration file")
    lint_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed output")

    pagerduty_parser = subparsers.add_parser("setup-pagerduty", help="Setup PagerDuty integration")
    pagerduty_parser.add_argument("service_file", help="Path to service YAML file")
    pagerduty_parser.add_argument(
        "--api-key", help="PagerDuty API key (or use PAGERDUTY_API_KEY env var)"
    )
    pagerduty_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    pagerduty_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    pagerduty_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )

    deploy_parser = subparsers.add_parser(
        "check-deploy", help="Check deployment gate (error budget validation)"
    )
    deploy_parser.add_argument("service_file", help="Path to service YAML file")
    deploy_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL (or use PROMETHEUS_URL env var)",
    )
    deploy_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    deploy_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    deploy_parser.add_argument(
        "--demo",
        action="store_true",
        help="Show demo output with sample data (for VHS recordings)",
    )
    deploy_parser.add_argument(
        "--demo-blocked",
        action="store_true",
        help="Show demo output with BLOCKED scenario (for VHS recordings)",
    )
    deploy_parser.add_argument(
        "--include-drift",
        action="store_true",
        help="Include drift analysis in deployment gate check",
    )
    deploy_parser.add_argument(
        "--drift-window",
        help="Drift analysis window (e.g., 30d, 14d). Uses tier default if not specified",
    )

    init_parser = subparsers.add_parser("init", help="Initialize new NthLayer service")
    init_parser.add_argument(
        "service_name", nargs="?", help="Service name (lowercase-with-hyphens)"
    )
    init_parser.add_argument("--team", help="Team name")
    init_parser.add_argument("--template", help="Template name (e.g., critical-api)")

    subparsers.add_parser("list-templates", help="List available service templates")

    # Environment management commands
    list_envs_parser = subparsers.add_parser(
        "list-environments", help="List available environments"
    )
    list_envs_parser.add_argument("--service", dest="service_file", help="Service YAML file")
    list_envs_parser.add_argument("--directory", help="Directory to search for environments")

    diff_envs_parser = subparsers.add_parser(
        "diff-envs", help="Compare configurations between environments"
    )
    diff_envs_parser.add_argument("service_file", help="Path to service YAML file")
    diff_envs_parser.add_argument("env1", help="First environment name")
    diff_envs_parser.add_argument("env2", help="Second environment name")
    diff_envs_parser.add_argument(
        "--show-all", action="store_true", help="Show all fields, not just differences"
    )

    validate_env_parser = subparsers.add_parser(
        "validate-env", help="Validate an environment configuration"
    )
    validate_env_parser.add_argument("environment", help="Environment name to validate")
    validate_env_parser.add_argument(
        "--service", dest="service_file", help="Service file to test against"
    )
    validate_env_parser.add_argument("--directory", help="Directory containing environments")
    validate_env_parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )

    # Dashboard generation
    dashboard_parser = subparsers.add_parser(
        "generate-dashboard", help="Generate Grafana dashboard from service spec"
    )
    dashboard_parser.add_argument("service_file", help="Path to service YAML file")
    dashboard_parser.add_argument(
        "--output", "-o", help="Output file path (default: generated/dashboards/{service}.json)"
    )
    dashboard_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    dashboard_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    dashboard_parser.add_argument(
        "--dry-run", action="store_true", help="Print dashboard JSON without writing file"
    )
    dashboard_parser.add_argument(
        "--full", action="store_true", help="Include all template panels (default: overview only)"
    )
    dashboard_parser.add_argument(
        "--prometheus-url",
        "-p",
        help="Prometheus URL for metric discovery (or set NTHLAYER_PROMETHEUS_URL)",
    )

    # Recording rules generation
    recording_parser = subparsers.add_parser(
        "generate-recording-rules", help="Generate Prometheus recording rules from service spec"
    )
    recording_parser.add_argument("service_file", help="Path to service YAML file")
    recording_parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: generated/recording-rules/{service}.yaml)",
    )
    recording_parser.add_argument(
        "--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)"
    )
    recording_parser.add_argument(
        "--auto-env",
        action="store_true",
        help="Auto-detect environment from context (CI/CD env vars)",
    )
    recording_parser.add_argument(
        "--dry-run", action="store_true", help="Print YAML without writing file"
    )

    # Configuration commands
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_show_parser = config_subparsers.add_parser("show", help="Show current configuration")
    config_show_parser.add_argument(
        "--reveal-secrets", action="store_true", help="Show secret values (redacted by default)"
    )

    config_set_parser = config_subparsers.add_parser("set", help="Set a configuration value")
    config_set_parser.add_argument("key", help="Configuration key (e.g., grafana.url)")
    config_set_parser.add_argument("value", nargs="?", help="Value to set")
    config_set_parser.add_argument("--secret", action="store_true", help="Prompt for secret value")

    config_subparsers.add_parser("init", help="Interactive configuration wizard")

    # Secrets commands
    secrets_parser = subparsers.add_parser("secrets", help="Secrets management")
    secrets_subparsers = secrets_parser.add_subparsers(dest="secrets_command")

    secrets_subparsers.add_parser("list", help="List available secrets")

    secrets_verify_parser = secrets_subparsers.add_parser(
        "verify", help="Verify required secrets exist"
    )
    secrets_verify_parser.add_argument("--secrets", nargs="+", help="Specific secrets to verify")

    secrets_set_parser = secrets_subparsers.add_parser("set", help="Set a secret")
    secrets_set_parser.add_argument("path", help="Secret path (e.g., grafana/api_key)")
    secrets_set_parser.add_argument(
        "value", nargs="?", help="Secret value (will prompt if not provided)"
    )
    secrets_set_parser.add_argument("--backend", help="Backend to use (env, file, vault, aws)")

    secrets_get_parser = secrets_subparsers.add_parser("get", help="Get a secret value")
    secrets_get_parser.add_argument("path", help="Secret path")
    secrets_get_parser.add_argument(
        "--reveal", action="store_true", help="Show full value (redacted by default)"
    )

    secrets_migrate_parser = secrets_subparsers.add_parser(
        "migrate", help="Migrate secrets between backends"
    )
    secrets_migrate_parser.add_argument(
        "source", help="Source backend (env, file, vault, aws, azure, gcp, doppler)"
    )
    secrets_migrate_parser.add_argument("target", help="Target backend")
    secrets_migrate_parser.add_argument("--secrets", nargs="+", help="Specific secrets to migrate")
    secrets_migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )

    subparsers.add_parser("list-services", help="List available services")
    subparsers.add_parser("list-teams", help="List available teams")

    team_parser = subparsers.add_parser("reconcile-team", help="Run team reconciliation demo")
    team_parser.add_argument("team_id")

    service_parser = subparsers.add_parser(
        "reconcile-service", help="Run service reconciliation demo"
    )
    service_parser.add_argument("service_id")

    grafana_parser = subparsers.add_parser("grafana", help="Run Grafana provider demo")
    grafana_parser.add_argument("--base-url", default=DEFAULT_GRAFANA_URL)
    grafana_parser.add_argument("--token", default=DEFAULT_GRAFANA_TOKEN)
    grafana_parser.add_argument("--org-id", type=int, default=_default_org_id())
    grafana_parser.add_argument("--timeout", type=float, default=15.0)

    prom_parser = subparsers.add_parser("prometheus-alerts", help="Show Prometheus alert templates")
    prom_parser.add_argument("--technology", default="postgres")
    prom_parser.add_argument("--limit", type=int, default=3)

    # SLO commands (new unified interface)
    register_slo_parser(subparsers)

    # Portfolio command
    register_portfolio_parser(subparsers)

    # Setup command
    register_setup_parser(subparsers)

    # Verify command (contract verification)
    register_verify_parser(subparsers)

    # Loki alerts command
    register_loki_parser(subparsers)

    # Validate metadata command
    register_validate_metadata_parser(subparsers)

    # Validate spec command (conftest/OPA)
    register_validate_spec_parser(subparsers)

    # Drift detection command
    register_drift_parser(subparsers)

    # Dependency discovery commands
    register_deps_parser(subparsers)
    register_blast_radius_parser(subparsers)

    # Ownership command
    register_ownership_parser(subparsers)

    # Identity command
    register_identity_parser(subparsers)

    # Validate SLO command
    register_validate_slo_parser(subparsers)

    # Recommend metrics command
    register_recommend_metrics_parser(subparsers)

    # Scorecard command
    register_scorecard_parser(subparsers)

    # Migrate command (legacy to OpenSRM)
    register_migrate_parser(subparsers)

    return parser


def _print_welcome() -> None:
    """Print styled welcome message for first-time users."""
    from nthlayer.cli.ux import console

    print_banner()
    console.print(f"  [muted]Version: {__version__}[/muted]")
    console.print()

    console.print("  [bold]Quick Start:[/bold]")
    console.print("    [info]nthlayer setup[/info]              Interactive first-time setup")
    console.print("    [info]nthlayer init[/info]               Create a new service.yaml")
    console.print("    [info]nthlayer apply service.yaml[/info] Generate dashboards, alerts, SLOs")
    console.print()

    console.print("  [bold]Key Commands:[/bold]")
    console.print("    [info]nthlayer verify[/info]             Verify metrics exist in Prometheus")
    console.print(
        "    [info]nthlayer check-deploy[/info]       Check error budget before deploying"
    )
    console.print("    [info]nthlayer portfolio[/info]          View org-wide SLO health")
    console.print()

    console.print("  [muted]Run 'nthlayer --help' for all commands[/muted]")
    console.print("  [muted]Run 'nthlayer <command> --help' for command details[/muted]")
    console.print()
    console.print("  [muted]Docs: https://rsionnach.github.io/nthlayer/[/muted]")
    console.print()


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Show version with banner
    if args.version:
        print_banner()
        print(f"nthlayer version {__version__}")
        return

    # Show styled welcome when no command provided
    if args.command is None:
        _print_welcome()
        return

    # Handle unified apply commands
    if args.command == "plan":
        from nthlayer.cli.plan import plan_command

        sys.exit(
            plan_command(
                service_yaml=args.service_yaml,
                env=args.env,
                output_format=args.format,
                output_file=args.output,
                verbose=args.verbose,
            )
        )

    if args.command == "apply":
        from nthlayer.cli.apply import apply_command

        prom_url = getattr(args, "prometheus_url", None) or os.environ.get(
            "NTHLAYER_PROMETHEUS_URL"
        )
        sys.exit(
            apply_command(
                service_yaml=args.service_yaml,
                env=args.env,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                skip=args.skip,
                only=args.only,
                force=args.force,
                verbose=args.verbose,
                output_format=args.output,
                push_grafana=args.push_grafana,
                push_ruler=getattr(args, "push_ruler", False),
                lint=args.lint,
                prometheus_url=prom_url,
            )
        )

    # Handle existing commands
    if args.command == "generate-slo":
        from nthlayer.cli.generate import generate_slo_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            generate_slo_command(
                args.service_file,
                output_dir=args.output_dir,
                format=args.format,
                environment=env,
                dry_run=args.dry_run,
            )
        )

    if args.command == "generate-alerts":
        from nthlayer.cli.generate_alerts import generate_alerts_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            generate_alerts_command(
                args.service_file,
                output=args.output,
                environment=env,
                dry_run=args.dry_run,
                runbook_url=args.runbook_url or "",
                notification_channel=args.notification_channel or "",
            )
        )

    if args.command == "validate":
        from nthlayer.cli.validate import validate_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            validate_command(
                args.service_file,
                environment=env,
                strict=args.strict,
            )
        )

    if args.command == "lint":
        from nthlayer.cli.lint import lint_command

        sys.exit(
            lint_command(
                file_path=args.file_path,
                config=args.config,
                verbose=args.verbose,
            )
        )

    if args.command == "setup-pagerduty":
        from nthlayer.cli.pagerduty import setup_pagerduty_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            setup_pagerduty_command(
                args.service_file,
                api_key=args.api_key,
                environment=env,
                dry_run=args.dry_run,
            )
        )

    if args.command == "check-deploy":
        from nthlayer.cli.deploy import check_deploy_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            check_deploy_command(
                args.service_file,
                prometheus_url=getattr(args, "prometheus_url", None),
                environment=env,
                demo=getattr(args, "demo", False),
                demo_blocked=getattr(args, "demo_blocked", False),
                include_drift=getattr(args, "include_drift", False),
                drift_window=getattr(args, "drift_window", None),
            )
        )

    if args.command == "init":
        from nthlayer.cli.init import init_command

        sys.exit(
            init_command(
                service_name=args.service_name,
                team=args.team,
                template=args.template,
                interactive=True,
            )
        )

    if args.command == "list-templates":
        from nthlayer.cli.templates import list_templates_command

        sys.exit(list_templates_command())

    if args.command == "list-environments":
        from nthlayer.cli.environments import list_environments_command

        sys.exit(
            list_environments_command(
                service_file=args.service_file,
                directory=args.directory,
            )
        )

    if args.command == "diff-envs":
        from nthlayer.cli.environments import diff_envs_command

        sys.exit(
            diff_envs_command(
                args.service_file,
                args.env1,
                args.env2,
                show_all=args.show_all,
            )
        )

    if args.command == "validate-env":
        from nthlayer.cli.environments import validate_env_command

        sys.exit(
            validate_env_command(
                args.environment,
                service_file=args.service_file,
                directory=args.directory,
                strict=args.strict,
            )
        )

    if args.command == "config":
        from nthlayer.config.cli import (
            config_init_command,
            config_set_command,
            config_show_command,
        )

        if args.config_command == "show":
            sys.exit(config_show_command(reveal_secrets=args.reveal_secrets))
        elif args.config_command == "set":
            sys.exit(config_set_command(args.key, args.value, secret=args.secret))
        elif args.config_command == "init":
            sys.exit(config_init_command())
        else:
            print("Usage: nthlayer config [show|set|init]")
            sys.exit(1)

    if args.command == "secrets":
        from nthlayer.config.cli import (
            secrets_get_command,
            secrets_list_command,
            secrets_migrate_command,
            secrets_set_command,
            secrets_verify_command,
        )

        if args.secrets_command == "list":
            sys.exit(secrets_list_command())
        elif args.secrets_command == "verify":
            sys.exit(secrets_verify_command(secrets=args.secrets))
        elif args.secrets_command == "set":
            sys.exit(secrets_set_command(args.path, args.value, backend=args.backend))
        elif args.secrets_command == "get":
            sys.exit(secrets_get_command(args.path, reveal=args.reveal))
        elif args.secrets_command == "migrate":
            sys.exit(
                secrets_migrate_command(
                    args.source, args.target, secrets=args.secrets, dry_run=args.dry_run
                )
            )
        else:
            print("Usage: nthlayer secrets [list|verify|set|get|migrate]")
            sys.exit(1)

    if args.command == "generate-dashboard":
        from nthlayer.cli.dashboard import generate_dashboard_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        # Get Prometheus URL from args or environment
        prom_url = getattr(args, "prometheus_url", None) or os.environ.get(
            "NTHLAYER_PROMETHEUS_URL"
        )

        sys.exit(
            generate_dashboard_command(
                args.service_file,
                output=args.output,
                environment=env,
                dry_run=args.dry_run,
                full_panels=getattr(args, "full", False),
                prometheus_url=prom_url,
            )
        )

    if args.command == "generate-recording-rules":
        from nthlayer.cli.recording_rules import generate_recording_rules_command
        from nthlayer.specs.environment_detection import get_environment

        env = get_environment(
            explicit_env=getattr(args, "environment", None),
            auto_detect=getattr(args, "auto_env", False),
        )

        sys.exit(
            generate_recording_rules_command(
                args.service_file,
                output=args.output,
                environment=env,
                dry_run=args.dry_run,
            )
        )

    if args.command == "list-services":
        list_services()
        return

    if args.command == "list-teams":
        list_teams()
        return

    if args.command == "reconcile-team":
        asyncio.run(demo_reconcile_team(args.team_id))
        return

    if args.command == "reconcile-service":
        asyncio.run(demo_reconcile_service(args.service_id))
        return

    if args.command == "grafana":
        asyncio.run(demo_grafana(args.base_url, args.token, args.org_id, args.timeout))
        return

    if args.command == "prometheus-alerts":
        demo_prometheus_alerts(args.technology, args.limit)
        return

    if args.command == "slo":
        sys.exit(handle_slo_command(args))

    if args.command == "portfolio":
        sys.exit(handle_portfolio_command(args))

    if args.command == "setup":
        sys.exit(handle_setup_command(args))

    if args.command == "verify":
        sys.exit(handle_verify_command(args))

    if args.command == "generate-loki-alerts":
        sys.exit(handle_loki_command(args))

    if args.command == "validate-metadata":
        sys.exit(handle_validate_metadata_command(args))

    if args.command == "validate-spec":
        sys.exit(handle_validate_spec_command(args))

    if args.command == "drift":
        sys.exit(handle_drift_command(args))

    if args.command == "deps":
        sys.exit(handle_deps_command(args))

    if args.command == "blast-radius":
        sys.exit(handle_blast_radius_command(args))

    if args.command == "ownership":
        sys.exit(handle_ownership_command(args))

    if args.command == "identity":
        sys.exit(handle_identity_command(args))

    if args.command == "validate-slo":
        sys.exit(handle_validate_slo_command(args))

    if args.command == "recommend-metrics":
        sys.exit(handle_recommend_metrics_command(args))

    if args.command == "scorecard":
        sys.exit(handle_scorecard_command(args))

    if args.command == "migrate":
        sys.exit(handle_migrate_command(args))

    parser.print_help()
