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
from datetime import datetime
from typing import Any, Sequence

import structlog
import yaml

from nthlayer.alerts import AlertTemplateLoader
from nthlayer.alerts.models import AlertRule
from nthlayer.providers.grafana import GrafanaProvider, GrafanaProviderError
from nthlayer.slos.cli_helpers import (
    get_cli_session,
    get_current_budget_from_db,
    get_slos_by_service_from_db,
    list_all_slos_from_db,
    run_async,
    save_slo_to_db,
)
from nthlayer.slos.collector import collect_service_budgets
from nthlayer.slos.correlator import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, DeploymentCorrelator
from nthlayer.slos.deployment import DeploymentRecorder
from nthlayer.slos.parser import OpenSLOParserError, parse_slo_file
from nthlayer.slos.storage import SLORepository

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
        serialized.append({
            "action": getattr(change, "action", "unknown"),
            "details": getattr(change, "details", {}),
        })
    return serialized


async def _plan_and_apply(resource: Any, desired_state: dict[str, Any], *, idempotency_key: str | None) -> dict[str, Any]:
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


async def demo_grafana(base_url: str, token: str | None, org_id: int | None, timeout: float) -> None:
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
    parser = argparse.ArgumentParser(prog="nthlayer", description="NthLayer CLI")
    subparsers = parser.add_subparsers(dest="command")

    # === NEW: Unified apply workflow ===
    
    # plan command (dry-run)
    plan_parser = subparsers.add_parser(
        "plan",
        help="Preview what resources would be generated (dry-run)"
    )
    plan_parser.add_argument("service_yaml", help="Path to service YAML file")
    plan_parser.add_argument("--env", help="Environment (dev, staging, prod)")
    plan_parser.add_argument("--output", choices=["text", "json"], default="text", 
                            help="Output format")
    plan_parser.add_argument("-v", "--verbose", action="store_true",
                            help="Show detailed information")
    
    # apply command (unified generation)
    apply_parser = subparsers.add_parser(
        "apply",
        help="Generate all resources for a service"
    )
    apply_parser.add_argument("service_yaml", help="Path to service YAML file")
    apply_parser.add_argument("--env", help="Environment (dev, staging, prod)")
    apply_parser.add_argument("--output-dir", help="Output directory for generated files")
    apply_parser.add_argument("--dry-run", action="store_true",
                             help="Preview without writing files")
    apply_parser.add_argument("--skip", nargs="+",
                             help="Resource types to skip (e.g., alerts pagerduty)")
    apply_parser.add_argument("--only", nargs="+",
                             help="Only generate specific resource types")
    apply_parser.add_argument("--force", action="store_true",
                             help="Force regeneration, ignore cache")
    apply_parser.add_argument("-v", "--verbose", action="store_true",
                             help="Show detailed progress")
    apply_parser.add_argument("--output", choices=["text", "json"], default="text",
                             help="Output format")
    apply_parser.add_argument("--push-grafana", action="store_true",
                             help="Automatically push dashboard to Grafana via API (requires NTHLAYER_GRAFANA_URL and NTHLAYER_GRAFANA_API_KEY)")

    # === EXISTING COMMANDS ===
    
    # New top-level commands
    generate_parser = subparsers.add_parser("generate-slo", help="Generate SLOs from service definition")
    generate_parser.add_argument("service_file", help="Path to service YAML file")
    generate_parser.add_argument("--output", dest="output_dir", default="generated", help="Output directory")
    generate_parser.add_argument("--format", choices=["sloth", "prometheus", "openslo"], default="sloth", help="Output format")
    generate_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    generate_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    generate_parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    
    generate_alerts_parser = subparsers.add_parser("generate-alerts", help="Generate alerts from awesome-prometheus-alerts")
    generate_alerts_parser.add_argument("service_file", help="Path to service YAML file")
    generate_alerts_parser.add_argument("--output", "-o", help="Output file path (default: generated/alerts/{service}.yaml)")
    generate_alerts_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    generate_alerts_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    generate_alerts_parser.add_argument("--dry-run", action="store_true", help="Preview alerts without writing file")
    generate_alerts_parser.add_argument("--runbook-url", help="Base URL for runbook links")
    generate_alerts_parser.add_argument("--notification-channel", help="Notification channel (pagerduty, slack, etc.)")
    
    validate_parser = subparsers.add_parser("validate", help="Validate service definition")
    validate_parser.add_argument("service_file", help="Path to service YAML file")
    validate_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    validate_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    validate_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    
    pagerduty_parser = subparsers.add_parser("setup-pagerduty", help="Setup PagerDuty integration")
    pagerduty_parser.add_argument("service_file", help="Path to service YAML file")
    pagerduty_parser.add_argument("--api-key", help="PagerDuty API key (or use PAGERDUTY_API_KEY env var)")
    pagerduty_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    pagerduty_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    pagerduty_parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    
    deploy_parser = subparsers.add_parser("check-deploy", help="Check deployment gate (error budget validation)")
    deploy_parser.add_argument("service_file", help="Path to service YAML file")
    deploy_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    deploy_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    deploy_parser.add_argument("--budget-consumed", type=int, help="Error budget consumed in minutes (for testing)")
    deploy_parser.add_argument("--budget-total", type=int, help="Total error budget in minutes (for testing)")
    
    init_parser = subparsers.add_parser("init", help="Initialize new NthLayer service")
    init_parser.add_argument("service_name", nargs="?", help="Service name (lowercase-with-hyphens)")
    init_parser.add_argument("--team", help="Team name")
    init_parser.add_argument("--template", help="Template name (e.g., critical-api)")
    
    subparsers.add_parser("list-templates", help="List available service templates")
    
    # Environment management commands
    list_envs_parser = subparsers.add_parser("list-environments", help="List available environments")
    list_envs_parser.add_argument("--service", dest="service_file", help="Service YAML file")
    list_envs_parser.add_argument("--directory", help="Directory to search for environments")
    
    diff_envs_parser = subparsers.add_parser("diff-envs", help="Compare configurations between environments")
    diff_envs_parser.add_argument("service_file", help="Path to service YAML file")
    diff_envs_parser.add_argument("env1", help="First environment name")
    diff_envs_parser.add_argument("env2", help="Second environment name")
    diff_envs_parser.add_argument("--show-all", action="store_true", help="Show all fields, not just differences")
    
    validate_env_parser = subparsers.add_parser("validate-env", help="Validate an environment configuration")
    validate_env_parser.add_argument("environment", help="Environment name to validate")
    validate_env_parser.add_argument("--service", dest="service_file", help="Service file to test against")
    validate_env_parser.add_argument("--directory", help="Directory containing environments")
    validate_env_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    
    # Dashboard generation
    dashboard_parser = subparsers.add_parser("generate-dashboard", help="Generate Grafana dashboard from service spec")
    dashboard_parser.add_argument("service_file", help="Path to service YAML file")
    dashboard_parser.add_argument("--output", "-o", help="Output file path (default: generated/dashboards/{service}.json)")
    dashboard_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    dashboard_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    dashboard_parser.add_argument("--dry-run", action="store_true", help="Print dashboard JSON without writing file")
    dashboard_parser.add_argument("--full", action="store_true", help="Include all template panels (default: overview only)")
    
    # Recording rules generation
    recording_parser = subparsers.add_parser("generate-recording-rules", help="Generate Prometheus recording rules from service spec")
    recording_parser.add_argument("service_file", help="Path to service YAML file")
    recording_parser.add_argument("--output", "-o", help="Output file path (default: generated/recording-rules/{service}.yaml)")
    recording_parser.add_argument("--env", "--environment", dest="environment", help="Environment name (dev, staging, prod)")
    recording_parser.add_argument("--auto-env", action="store_true", help="Auto-detect environment from context (CI/CD env vars)")
    recording_parser.add_argument("--dry-run", action="store_true", help="Print YAML without writing file")

    # Configuration commands
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    
    config_show_parser = config_subparsers.add_parser("show", help="Show current configuration")
    config_show_parser.add_argument("--reveal-secrets", action="store_true", help="Show secret values (redacted by default)")
    
    config_set_parser = config_subparsers.add_parser("set", help="Set a configuration value")
    config_set_parser.add_argument("key", help="Configuration key (e.g., grafana.url)")
    config_set_parser.add_argument("value", nargs="?", help="Value to set")
    config_set_parser.add_argument("--secret", action="store_true", help="Prompt for secret value")
    
    config_subparsers.add_parser("init", help="Interactive configuration wizard")
    
    # Secrets commands
    secrets_parser = subparsers.add_parser("secrets", help="Secrets management")
    secrets_subparsers = secrets_parser.add_subparsers(dest="secrets_command")
    
    secrets_subparsers.add_parser("list", help="List available secrets")
    
    secrets_verify_parser = secrets_subparsers.add_parser("verify", help="Verify required secrets exist")
    secrets_verify_parser.add_argument("--secrets", nargs="+", help="Specific secrets to verify")
    
    secrets_set_parser = secrets_subparsers.add_parser("set", help="Set a secret")
    secrets_set_parser.add_argument("path", help="Secret path (e.g., grafana/api_key)")
    secrets_set_parser.add_argument("value", nargs="?", help="Secret value (will prompt if not provided)")
    secrets_set_parser.add_argument("--backend", help="Backend to use (env, file, vault, aws)")
    
    secrets_get_parser = secrets_subparsers.add_parser("get", help="Get a secret value")
    secrets_get_parser.add_argument("path", help="Secret path")
    secrets_get_parser.add_argument("--reveal", action="store_true", help="Show full value (redacted by default)")
    
    secrets_migrate_parser = secrets_subparsers.add_parser("migrate", help="Migrate secrets between backends")
    secrets_migrate_parser.add_argument("source", help="Source backend (env, file, vault, aws, azure, gcp, doppler)")
    secrets_migrate_parser.add_argument("target", help="Target backend")
    secrets_migrate_parser.add_argument("--secrets", nargs="+", help="Specific secrets to migrate")
    secrets_migrate_parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    subparsers.add_parser("list-services", help="List available services")
    subparsers.add_parser("list-teams", help="List available teams")

    team_parser = subparsers.add_parser("reconcile-team", help="Run team reconciliation demo")
    team_parser.add_argument("team_id")

    service_parser = subparsers.add_parser("reconcile-service", help="Run service reconciliation demo")
    service_parser.add_argument("service_id")

    grafana_parser = subparsers.add_parser("grafana", help="Run Grafana provider demo")
    grafana_parser.add_argument("--base-url", default=DEFAULT_GRAFANA_URL)
    grafana_parser.add_argument("--token", default=DEFAULT_GRAFANA_TOKEN)
    grafana_parser.add_argument("--org-id", type=int, default=_default_org_id())
    grafana_parser.add_argument("--timeout", type=float, default=15.0)

    prom_parser = subparsers.add_parser("prometheus-alerts", help="Show Prometheus alert templates")
    prom_parser.add_argument("--technology", default="postgres")
    prom_parser.add_argument("--limit", type=int, default=3)

    # ResLayer commands
    reslayer_parser = subparsers.add_parser("reslayer", help="ResLayer error budget commands")
    reslayer_subparsers = reslayer_parser.add_subparsers(dest="reslayer_command")
    
    # reslayer init
    init_parser = reslayer_subparsers.add_parser("init", help="Initialize SLO from OpenSLO file")
    init_parser.add_argument("service", help="Service name")
    init_parser.add_argument("file", help="Path to OpenSLO YAML file")
    
    # reslayer show
    show_parser = reslayer_subparsers.add_parser("show", help="Show SLO details")
    show_parser.add_argument("service", help="Service name")
    
    # reslayer list
    reslayer_subparsers.add_parser("list", help="List all SLOs")
    
    # reslayer collect
    collect_parser = reslayer_subparsers.add_parser("collect", help="Collect metrics and calculate error budget")
    collect_parser.add_argument("service", help="Service name")
    collect_parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus server URL")
    
    # reslayer record-deploy
    record_parser = reslayer_subparsers.add_parser("record-deploy", help="Record a deployment manually")
    record_parser.add_argument("service", help="Service name")
    record_parser.add_argument("--commit", required=True, help="Git commit SHA")
    record_parser.add_argument("--author", help="Deploy author email")
    record_parser.add_argument("--pr", help="Pull request number")
    
    # reslayer correlate
    correlate_parser = reslayer_subparsers.add_parser("correlate", help="Correlate deployments with error budget burns")
    correlate_parser.add_argument("service", help="Service name")
    correlate_parser.add_argument("--hours", type=int, default=24, help="Lookback period in hours")
    
    # reslayer blame
    blame_parser = reslayer_subparsers.add_parser("blame", help="Show which deployments burned error budget")
    blame_parser.add_argument("service", help="Service name")
    blame_parser.add_argument("--days", type=int, default=7, help="Lookback period in days")
    blame_parser.add_argument("--min-confidence", type=float, default=0.5, help="Minimum confidence threshold")
    
    # reslayer alert-config
    alert_parser = reslayer_subparsers.add_parser("alert-config", help="Configure alert rules")
    alert_parser.add_argument("service", help="Service name")
    alert_parser.add_argument("--threshold", type=float, default=0.75, help="Budget threshold (0-1)")
    alert_parser.add_argument("--burn-rate", type=float, help="Burn rate threshold (e.g., 3.0 for 3x)")
    alert_parser.add_argument("--slack-webhook", help="Slack webhook URL")
    alert_parser.add_argument("--pagerduty-key", help="PagerDuty integration key")
    alert_parser.add_argument("--list", action="store_true", help="List current alert rules")
    
    # reslayer test-alert
    test_alert_parser = reslayer_subparsers.add_parser("test-alert", help="Test alert notifications")
    test_alert_parser.add_argument("service", help="Service name")
    test_alert_parser.add_argument("--slack-webhook", help="Slack webhook URL")
    test_alert_parser.add_argument("--pagerduty-key", help="PagerDuty integration key")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle unified apply commands
    if args.command == "plan":
        from nthlayer.cli.plan import plan_command
        sys.exit(plan_command(
            service_yaml=args.service_yaml,
            env=args.env,
            output_format=args.output,
            verbose=args.verbose
        ))
    
    if args.command == "apply":
        from nthlayer.cli.apply import apply_command
        sys.exit(apply_command(
            service_yaml=args.service_yaml,
            env=args.env,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            skip=args.skip,
            only=args.only,
            force=args.force,
            verbose=args.verbose,
            output_format=args.output,
            push_grafana=args.push_grafana
        ))

    # Handle existing commands
    if args.command == "generate-slo":
        from nthlayer.cli.generate import generate_slo_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(generate_slo_command(
            args.service_file,
            output_dir=args.output_dir,
            format=args.format,
            environment=env,
            dry_run=args.dry_run,
        ))
    
    if args.command == "generate-alerts":
        from nthlayer.cli.generate_alerts import generate_alerts_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(generate_alerts_command(
            args.service_file,
            output=args.output,
            environment=env,
            dry_run=args.dry_run,
            runbook_url=args.runbook_url or "",
            notification_channel=args.notification_channel or ""
        ))
    
    if args.command == "validate":
        from nthlayer.cli.validate import validate_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(validate_command(
            args.service_file,
            environment=env,
            strict=args.strict,
        ))
    
    if args.command == "setup-pagerduty":
        from nthlayer.cli.pagerduty import setup_pagerduty_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(setup_pagerduty_command(
            args.service_file,
            api_key=args.api_key,
            environment=env,
            dry_run=args.dry_run,
        ))
    
    if args.command == "check-deploy":
        from nthlayer.cli.deploy import check_deploy_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(check_deploy_command(
            args.service_file,
            environment=env,
            budget_consumed=args.budget_consumed,
            budget_total=args.budget_total,
        ))
    
    if args.command == "init":
        from nthlayer.cli.init import init_command
        sys.exit(init_command(
            service_name=args.service_name,
            team=args.team,
            template=args.template,
            interactive=True,
        ))
    
    if args.command == "list-templates":
        from nthlayer.cli.templates import list_templates_command
        sys.exit(list_templates_command())
    
    if args.command == "list-environments":
        from nthlayer.cli.environments import list_environments_command
        sys.exit(list_environments_command(
            service_file=args.service_file,
            directory=args.directory,
        ))
    
    if args.command == "diff-envs":
        from nthlayer.cli.environments import diff_envs_command
        sys.exit(diff_envs_command(
            args.service_file,
            args.env1,
            args.env2,
            show_all=args.show_all,
        ))
    
    if args.command == "validate-env":
        from nthlayer.cli.environments import validate_env_command
        sys.exit(validate_env_command(
            args.environment,
            service_file=args.service_file,
            directory=args.directory,
            strict=args.strict,
        ))
    
    if args.command == "config":
        from nthlayer.config.cli import (
            config_show_command,
            config_set_command,
            config_init_command,
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
            secrets_list_command,
            secrets_verify_command,
            secrets_set_command,
            secrets_get_command,
            secrets_migrate_command,
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
            sys.exit(secrets_migrate_command(
                args.source, args.target,
                secrets=args.secrets,
                dry_run=args.dry_run
            ))
        else:
            print("Usage: nthlayer secrets [list|verify|set|get|migrate]")
            sys.exit(1)
    
    if args.command == "generate-dashboard":
        from nthlayer.cli.dashboard import generate_dashboard_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(generate_dashboard_command(
            args.service_file,
            output=args.output,
            environment=env,
            dry_run=args.dry_run,
            full_panels=getattr(args, 'full', False),
        ))
    
    if args.command == "generate-recording-rules":
        from nthlayer.cli.recording_rules import generate_recording_rules_command
        from nthlayer.specs.environment_detection import get_environment
        
        env = get_environment(
            explicit_env=getattr(args, 'environment', None),
            auto_detect=getattr(args, 'auto_env', False)
        )
        
        sys.exit(generate_recording_rules_command(
            args.service_file,
            output=args.output,
            environment=env,
            dry_run=args.dry_run,
        ))

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

    if args.command == "reslayer":
        demo_reslayer(args)
        return

    parser.print_help()


def demo_reslayer(args: argparse.Namespace) -> None:
    """ResLayer error budget demo commands."""
    command = args.reslayer_command
    
    if command == "init":
        demo_reslayer_init(args.service, args.file)
    elif command == "show":
        demo_reslayer_show(args.service)
    elif command == "list":
        demo_reslayer_list()
    elif command == "collect":
        demo_reslayer_collect(args.service, args.prometheus_url)
    elif command == "record-deploy":
        demo_reslayer_record_deploy(args.service, args.commit, args.author, args.pr)
    elif command == "correlate":
        demo_reslayer_correlate(args.service, args.hours)
    elif command == "blame":
        demo_reslayer_blame(args.service, args.days, args.min_confidence)
    elif command == "alert-config":
        demo_reslayer_alert_config(args)
    elif command == "test-alert":
        demo_reslayer_test_alert(args.service, args.slack_webhook, args.pagerduty_key)
    elif command == "blame-original":
        demo_reslayer_blame(args.service, args.days, args.min_confidence)
    else:
        print("Usage: nthlayer reslayer {init|show|list|collect|record-deploy|correlate|blame}")


def demo_reslayer_init(service: str, file_path: str) -> None:
    """Initialize SLO from OpenSLO file."""
    print()
    print("=" * 70)
    print("  ResLayer: Initialize SLO")
    print("=" * 70)
    print()
    
    try:
        # Parse SLO file
        slo = parse_slo_file(file_path)
        
        print(f"✅ Parsed SLO: {slo.name}")
        print(f"   Service: {slo.service}")
        print(f"   Target: {slo.target * 100:.2f}%")
        print(f"   Time Window: {slo.time_window.duration} ({slo.time_window.type.value})")
        print(f"   Error Budget: {slo.error_budget_minutes():.1f} minutes")
        print()
        
        # Save to database
        print("💾 Saving to database...")
        action = run_async(save_slo_to_db(slo))
        
        print(f"✅ SLO {action} successfully!")
        print(f"   ID: {slo.id}")
        print()
        
        print("Next steps:")
        print(f"  1. View SLO details: nthlayer reslayer show {service}")
        print("  2. List all SLOs: nthlayer reslayer list")
        
    except OpenSLOParserError as exc:
        print(f"❌ Error parsing SLO file: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_show(service: str) -> None:
    """Show SLO details for a service."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Show SLO - {service}")
    print("=" * 70)
    print()
    
    try:
        # Get SLOs for service from database
        slos = run_async(get_slos_by_service_from_db(service))
        
        if not slos:
            print(f"❌ No SLOs found for service: {service}")
            print()
            print("To create an SLO:")
            print(f"  nthlayer reslayer init {service} <slo-file.yaml>")
            return
        
        # Show each SLO
        for slo in slos:
            print(f"📊 SLO: {slo.name}")
            print(f"   ID: {slo.id}")
            print(f"   Service: {slo.service}")
            print(f"   Target: {slo.target * 100:.2f}%")
            print(f"   Time Window: {slo.time_window.duration} ({slo.time_window.type.value})")
            print(f"   Error Budget: {slo.error_budget_minutes():.1f} minutes")
            
            if slo.owner:
                print(f"   Owner: {slo.owner}")
            
            if slo.labels:
                print(f"   Labels: {', '.join(f'{k}={v}' for k, v in slo.labels.items())}")
            
            print()
            
            # Try to get current budget (may not exist yet)
            budget = run_async(get_current_budget_from_db(slo.id))
            
            if budget:
                print("📈 Current Error Budget:")
                print(f"   Total: {budget['budget']['total_minutes']:.1f} minutes")
                print(f"   Burned: {budget['budget']['burned_minutes']:.1f} minutes ({budget['budget']['percent_consumed']:.1f}%)")
                print(f"   Remaining: {budget['budget']['remaining_minutes']:.1f} minutes ({budget['budget']['percent_remaining']:.1f}%)")
                print(f"   Status: {budget['status']}")
                print()
            else:
                print("📈 No error budget data yet")
                print("   Start collecting metrics to track budget")
                print()
        
    except Exception as exc:
        print(f"❌ Error retrieving SLO: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_list() -> None:
    """List all SLOs."""
    print()
    print("=" * 70)
    print("  ResLayer: List SLOs")
    print("=" * 70)
    print()
    
    try:
        # Get all SLOs from database
        slos = run_async(list_all_slos_from_db())
        
        if not slos:
            print("No SLOs found in database.")
            print()
            print("To create an SLO:")
            print("  nthlayer reslayer init <service> <slo-file.yaml>")
            print()
            print("Example:")
            print("  nthlayer reslayer init payment-api examples/slos/payment-api-availability.yaml")
            return
        
        # Display table header
        print(f"{'SLO ID':<35} {'Service':<20} {'Target':<10} {'Budget':<15}")
        print("-" * 85)
        
        # Display each SLO
        for slo in slos:
            target_str = f"{slo.target * 100:.2f}%"
            budget_str = f"{slo.error_budget_minutes():.1f} min"
            
            print(f"{slo.id:<35} {slo.service:<20} {target_str:<10} {budget_str:<15}")
        
        print()
        print(f"Total: {len(slos)} SLOs")
        print()
        
    except Exception as exc:
        print(f"❌ Error listing SLOs: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_collect(service: str, prometheus_url: str) -> None:
    """Collect metrics from Prometheus and calculate error budget."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Collect Metrics - {service}")
    print("=" * 70)
    print()
    
    try:
        print(f"🔗 Connecting to Prometheus: {prometheus_url}")
        print()
        
        # Collect budgets for all SLOs of the service
        async def collect():
            async with get_cli_session() as session:
                repo = SLORepository(session)
                budgets = await collect_service_budgets(service, prometheus_url, repo)
                await session.commit()
                return budgets
        
        budgets = run_async(collect())
        
        if not budgets:
            print(f"❌ No SLOs found for service: {service}")
            print()
            print("To create an SLO:")
            print(f"  nthlayer reslayer init {service} <slo-file.yaml>")
            return
        
        print(f"✅ Collected metrics for {len(budgets)} SLO(s)")
        print()
        
        # Display budget details
        for budget in budgets:
            status_emoji = {
                "healthy": "✅",
                "warning": "⚠️ ",
                "critical": "🔥",
                "exhausted": "💀",
            }.get(budget.status.value, "❓")
            
            print(f"{status_emoji} SLO: {budget.slo_id}")
            print(f"   Service: {budget.service}")
            print(f"   Period: {budget.period_start.strftime('%Y-%m-%d')} to {budget.period_end.strftime('%Y-%m-%d')}")
            print(f"   Total Budget: {budget.total_budget_minutes:.1f} minutes")
            print(f"   Burned: {budget.burned_minutes:.1f} minutes ({budget.percent_consumed:.1f}%)")
            print(f"   Remaining: {budget.remaining_minutes:.1f} minutes ({budget.percent_remaining:.1f}%)")
            print(f"   Status: {budget.status.value.upper()}")
            
            if budget.burn_rate:
                print(f"   Burn Rate: {budget.burn_rate:.2f}x")
            
            print()
        
        print("💾 Budgets saved to database")
        print()
        print("Next steps:")
        print(f"  • View details: nthlayer reslayer show {service}")
        print("  • List all SLOs: nthlayer reslayer list")
        
    except Exception as exc:
        print(f"❌ Error collecting metrics: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


__all__ = [
    "build_prometheus_alerts_demo",
    "demo_prometheus_alerts",
    "run_grafana_demo",
    "demo_grafana",
    "demo_reslayer",
    "main",
]


if __name__ == "__main__":
    main()


def demo_reslayer_record_deploy(
    service: str,
    commit: str,
    author: str | None,
    pr: str | None,
) -> None:
    """Record a deployment manually."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Record Deployment - {service}")
    print("=" * 70)
    print()
    
    try:
        # Record deployment
        async def record():
            async with get_cli_session() as session:
                repo = SLORepository(session)
                recorder = DeploymentRecorder(repo)
                
                deployment = await recorder.record_manual(
                    service=service,
                    commit_sha=commit,
                    author=author,
                    pr_number=pr,
                )
                
                await session.commit()
                return deployment
        
        deployment = run_async(record())
        
        print("✅ Deployment recorded")
        print(f"   ID: {deployment.id}")
        print(f"   Service: {deployment.service}")
        print(f"   Commit: {deployment.commit_sha}")
        if deployment.author:
            print(f"   Author: {deployment.author}")
        if deployment.pr_number:
            print(f"   PR: #{deployment.pr_number}")
        print(f"   Time: {deployment.deployed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        print("Next steps:")
        print(f"  • Run correlation: nthlayer reslayer correlate {service}")
        print(f"  • View blame: nthlayer reslayer blame {service}")
        
    except Exception as exc:
        print(f"❌ Error recording deployment: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_correlate(service: str, hours: int) -> None:
    """Correlate deployments with error budget burns."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Correlate Deployments - {service}")
    print("=" * 70)
    print()
    
    try:
        print(f"🔄 Running correlation analysis (last {hours} hours)...")
        print()
        
        # Run correlation
        async def correlate():
            async with get_cli_session() as session:
                repo = SLORepository(session)
                correlator = DeploymentCorrelator(repo)
                
                results = await correlator.correlate_service(
                    service=service,
                    lookback_hours=hours,
                )
                
                await session.commit()
                return results
        
        results = run_async(correlate())
        
        if not results:
            print(f"No correlation results found for {service}")
            print()
            print("Possible reasons:")
            print("  • No deployments recorded in time window")
            print("  • No SLOs defined for service")
            print("  • No error budget burns detected")
            print()
            print("Try:")
            print(f"  1. Record a deployment: nthlayer reslayer record-deploy {service} --commit <sha>")
            print(f"  2. Create an SLO: nthlayer reslayer init {service} <slo-file.yaml>")
            return
        
        # Group by confidence level
        high = [r for r in results if r.confidence >= HIGH_CONFIDENCE]
        medium = [r for r in results if MEDIUM_CONFIDENCE <= r.confidence < HIGH_CONFIDENCE]
        low = [r for r in results if r.confidence < MEDIUM_CONFIDENCE]
        
        print(f"✅ Analyzed {len(results)} deployment(s)")
        print()
        
        if high:
            print(f"🔴 HIGH Confidence ({len(high)}):")
            for r in high:
                print(f"   • {r.deployment_id}: {r.burn_minutes:.1f} min burned ({r.confidence*100:.0f}%)")
            print()
        
        if medium:
            print(f"🟡 MEDIUM Confidence ({len(medium)}):")
            for r in medium:
                print(f"   • {r.deployment_id}: {r.burn_minutes:.1f} min burned ({r.confidence*100:.0f}%)")
            print()
        
        if low:
            print(f"✅ LOW/No Correlation ({len(low)}):")
            for r in low:
                print(f"   • {r.deployment_id}: {r.burn_minutes:.1f} min burned ({r.confidence*100:.0f}%)")
            print()
        
        print("💾 Updated correlation data in database")
        print()
        print("Next steps:")
        print(f"  • View blame report: nthlayer reslayer blame {service}")
        print("  • Investigate high-confidence deploys")
        
    except Exception as exc:
        print(f"❌ Error running correlation: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_blame(service: str, days: int, min_confidence: float) -> None:
    """Show which deployments burned error budget."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Deployment Blame - {service}")
    print("=" * 70)
    print()
    
    try:
        print(f"🔍 Analyzing deployments from last {days} days...")
        print()
        
        # Get deployments with correlation data
        async def get_blamed_deploys():
            async with get_cli_session() as session:
                repo = SLORepository(session)
                
                # Get all recent deployments
                deployments = await repo.get_recent_deployments(
                    service=service,
                    hours=days * 24,
                )
                
                # Filter by confidence threshold
                blamed = [
                    d for d in deployments
                    if d.correlation_confidence and d.correlation_confidence >= min_confidence
                ]
                
                # Sort by confidence (highest first)
                blamed.sort(key=lambda d: d.correlation_confidence or 0, reverse=True)
                
                return blamed, deployments
        
        blamed, all_deployments = run_async(get_blamed_deploys())
        
        if not blamed:
            print(f"No deployments found with confidence >= {min_confidence*100:.0f}%")
            print()
            if all_deployments:
                print(f"Found {len(all_deployments)} total deployment(s), but none correlated to burns.")
                print()
                print("Try:")
                print(f"  • Lower threshold: nthlayer reslayer blame {service} --min-confidence 0.3")
                print(f"  • Run correlation: nthlayer reslayer correlate {service}")
            else:
                print("No deployments found in time window.")
                print()
                print("Try:")
                print(f"  • Record a deployment: nthlayer reslayer record-deploy {service} --commit <sha>")
                print(f"  • Increase lookback: nthlayer reslayer blame {service} --days 14")
            return
        
        # Categorize by confidence
        high = [d for d in blamed if d.correlation_confidence >= HIGH_CONFIDENCE]
        medium = [d for d in blamed if MEDIUM_CONFIDENCE <= d.correlation_confidence < HIGH_CONFIDENCE]
        
        # Display results
        if high:
            print("Top Culprits (High Confidence):")
            print(f"{'Commit':<12} {'Deployed':<20} {'Burned':<10} {'Confidence':<12} {'Author':<25}")
            print("-" * 85)
            
            for d in high:
                commit = d.commit_sha[:7] if d.commit_sha else d.id[:7]
                deployed = d.deployed_at.strftime("%b %d, %I:%M%p")
                burned = f"{d.correlated_burn_minutes:.1f}h" if d.correlated_burn_minutes else "N/A"
                conf = f"{d.correlation_confidence*100:.0f}% 🔴"
                author = (d.author or "unknown")[:24]
                
                print(f"{commit:<12} {deployed:<20} {burned:<10} {conf:<12} {author:<25}")
            
            print()
        
        if medium:
            print("Possible Culprits (Medium Confidence):")
            print(f"{'Commit':<12} {'Deployed':<20} {'Burned':<10} {'Confidence':<12} {'Author':<25}")
            print("-" * 85)
            
            for d in medium:
                commit = d.commit_sha[:7] if d.commit_sha else d.id[:7]
                deployed = d.deployed_at.strftime("%b %d, %I:%M%p")
                burned = f"{d.correlated_burn_minutes:.1f}h" if d.correlated_burn_minutes else "N/A"
                conf = f"{d.correlation_confidence*100:.0f}% 🟡"
                author = (d.author or "unknown")[:24]
                
                print(f"{commit:<12} {deployed:<20} {burned:<10} {conf:<12} {author:<25}")
            
            print()
        
        # Show clean deployments
        clean = [d for d in all_deployments if not d.correlation_confidence or d.correlation_confidence < min_confidence]
        if clean and len(clean) <= 5:
            print(f"Clean Deployments (No Impact): {len(clean)}")
            for d in clean[:5]:
                commit = d.commit_sha[:7] if d.commit_sha else d.id[:7]
                deployed = d.deployed_at.strftime("%b %d, %I:%M%p")
                author = (d.author or "unknown")[:24]
                print(f"  • {commit} ({deployed}) - {author} ✅")
            print()
        
        # Summary
        print("Summary:")
        print(f"  Total Deploys: {len(all_deployments)}")
        print(f"  High Impact: {len(high)} ({len(high)*100//len(all_deployments) if all_deployments else 0}%)")
        print(f"  Medium Impact: {len(medium)} ({len(medium)*100//len(all_deployments) if all_deployments else 0}%)")
        print(f"  Clean: {len(clean)} ({len(clean)*100//len(all_deployments) if all_deployments else 0}%)")
        
        if high:
            total_burn = sum(d.correlated_burn_minutes or 0 for d in high)
            print(f"  Total Burn (High): {total_burn:.1f} hours")
        
        print()
        print("💡 Recommendation: Review deploy process for high-impact deployments")
        
    except Exception as exc:
        print(f"❌ Error generating blame report: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_alert_config(args: argparse.Namespace) -> None:
    """Configure alert rules for a service."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Alert Configuration - {args.service}")
    print("=" * 70)
    print()
    
    try:
        from nthlayer.slos.alerts import AlertRule, AlertSeverity, AlertType, get_alert_storage
        
        storage = get_alert_storage()
        
        # List mode
        if args.list:
            rules = storage.get_rules(args.service)
            
            if not rules:
                print(f"No alert rules configured for {args.service}")
                print()
                print("To add a rule:")
                print(f"  nthlayer reslayer alert-config {args.service} --threshold 0.75 --slack-webhook <url>")
                return
            
            print(f"Alert Rules for {args.service}:")
            print()
            
            for rule in rules:
                print(f"📋 Rule: {rule.id}")
                print(f"   Type: {rule.alert_type.value}")
                print(f"   Severity: {rule.severity.value}")
                print(f"   Threshold: {rule.threshold}")
                if rule.slack_webhook:
                    print("   Slack: configured")
                if rule.pagerduty_key:
                    print("   PagerDuty: configured")
                print()
            
            return
        
        # Configure threshold alert
        if args.threshold:
            # Determine severity based on threshold
            if args.threshold >= 0.9:
                severity = AlertSeverity.CRITICAL
            elif args.threshold >= 0.75:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO
            
            rule = AlertRule(
                id=f"{args.service}-threshold-{int(args.threshold*100)}",
                service=args.service,
                slo_id=f"{args.service}-*",  # Apply to all SLOs
                alert_type=AlertType.BUDGET_THRESHOLD,
                severity=severity,
                threshold=args.threshold,
                slack_webhook=args.slack_webhook,
                pagerduty_key=args.pagerduty_key,
            )
            
            storage.add_rule(rule)
            
            print("✅ Threshold alert configured")
            print(f"   Threshold: {args.threshold*100:.0f}%")
            print(f"   Severity: {severity.value.upper()}")
            if args.slack_webhook:
                print("   Slack: enabled")
            if args.pagerduty_key:
                print("   PagerDuty: enabled")
            print()
        
        # Configure burn rate alert
        if args.burn_rate:
            # Determine severity based on burn rate
            if args.burn_rate >= 6:
                severity = AlertSeverity.CRITICAL
            elif args.burn_rate >= 3:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO
            
            rule = AlertRule(
                id=f"{args.service}-burn-rate-{int(args.burn_rate)}x",
                service=args.service,
                slo_id=f"{args.service}-*",
                alert_type=AlertType.BURN_RATE,
                severity=severity,
                threshold=args.burn_rate,
                slack_webhook=args.slack_webhook,
                pagerduty_key=args.pagerduty_key,
            )
            
            storage.add_rule(rule)
            
            print("✅ Burn rate alert configured")
            print(f"   Threshold: {args.burn_rate}x baseline")
            print(f"   Severity: {severity.value.upper()}")
            if args.slack_webhook:
                print("   Slack: enabled")
            if args.pagerduty_key:
                print("   PagerDuty: enabled")
            print()
        
        print("Next steps:")
        print(f"  • Test alert: nthlayer reslayer test-alert {args.service} --pagerduty-key <key>")
        print(f"  • View rules: nthlayer reslayer alert-config {args.service} --list")
        
    except Exception as exc:
        print(f"❌ Error configuring alerts: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def demo_reslayer_test_alert(service: str, slack_webhook: str | None, pagerduty_key: str | None) -> None:
    """Test alert notifications."""
    print()
    print("=" * 70)
    print(f"  ResLayer: Test Alert - {service}")
    print("=" * 70)
    print()
    
    try:
        from nthlayer.slos.alerts import AlertEvent, AlertSeverity
        from nthlayer.slos.notifiers import AlertNotifier
        
        if not slack_webhook and not pagerduty_key:
            print("❌ Error: Must provide --slack-webhook or --pagerduty-key")
            print()
            print("Examples:")
            print(f"  nthlayer reslayer test-alert {service} --slack-webhook https://hooks.slack.com/...")
            print(f"  nthlayer reslayer test-alert {service} --pagerduty-key R03XXXXXXXXX")
            sys.exit(1)
        
        channels = []
        if slack_webhook:
            channels.append("Slack")
        if pagerduty_key:
            channels.append("PagerDuty")
        
        print(f"🧪 Sending test alert to {' and '.join(channels)}...")
        print()
        
        # Create test alert event
        event = AlertEvent(
            id=f"test-{int(datetime.utcnow().timestamp())}",
            rule_id="test-rule",
            service=service,
            slo_id=f"{service}-test",
            severity=AlertSeverity.INFO,
            title=f"Test Alert: {service}",
            message=(
                "ℹ️ *This is a test alert*\n\n"
                f"*Service:* `{service}`\n"
                "*Status:* Test message\n\n"
                "If you see this, your alert configuration is working! ✅"
            ),
            details={
                "test": True,
                "service": service,
            },
        )
        
        # Setup notifier with configured channels
        notifier = AlertNotifier()
        if slack_webhook:
            notifier.add_slack(slack_webhook)
        if pagerduty_key:
            notifier.add_pagerduty(pagerduty_key)
        
        async def send():
            result = await notifier.send_alert(event)
            return result
        
        results = run_async(send())
        
        # Display results for each channel
        success_count = 0
        for channel, result in results.items():
            if result.get("status") == "sent":
                print(f"✅ {channel.title()} alert sent successfully!")
                if channel == "pagerduty" and result.get("dedup_key"):
                    print(f"   Dedup key: {result['dedup_key']}")
                success_count += 1
            elif result.get("status") == "skipped":
                print(f"ℹ️  {channel.title()} skipped: {result.get('reason')}")
            else:
                print(f"❌ {channel.title()} failed: {result.get('error', 'Unknown error')}")
        
        print()
        
        if success_count > 0:
            print("Check your channels to confirm receipt:")
            if slack_webhook:
                print("  • Slack: Check the configured channel")
            if pagerduty_key:
                print("  • PagerDuty: Check Incidents tab")
        
        print()
        print("If you didn't receive the alert:")
        print("  • Verify the integration keys are correct")
        print("  • Check channel permissions")
        print("  • Review the error logs above")
        
    except Exception as exc:
        print(f"❌ Error sending test alert: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
