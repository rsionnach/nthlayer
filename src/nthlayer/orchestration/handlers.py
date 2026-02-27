"""Concrete resource handlers for orchestration."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import structlog

from nthlayer.alertmanager import generate_alertmanager_config
from nthlayer.core.errors import ProviderError

logger = structlog.get_logger()
from nthlayer.orchestration.registry import OrchestratorContext, ResourceRegistry
from nthlayer.pagerduty import EventOrchestrationManager, PagerDutyResourceManager


class SloHandler:
    """Handles SLO generation via Sloth."""

    @property
    def name(self) -> str:
        return "slos"

    @property
    def display_name(self) -> str:
        return "SLOs"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        slo_resources = ctx.detector.get_resources_by_kind("SLO")
        return [
            {
                "name": r.get("name"),
                "objective": r.get("spec", {}).get("objective"),
                "window": r.get("spec", {}).get("window", "30d"),
            }
            for r in slo_resources
        ]

    def generate(self, ctx: OrchestratorContext) -> int:
        from nthlayer.generators.sloth import generate_sloth_spec

        sloth_output_dir = ctx.output_dir / "sloth"
        result = generate_sloth_spec(
            service_file=ctx.service_yaml,
            output_dir=sloth_output_dir,
            environment=ctx.env,
        )

        if not result.success:
            if result.error and "No SLO resources found" in result.error:
                return 0
            print(f"   ⚠️  SLO generation warning: {result.error}")
            return 0

        return result.slo_count


class AlertHandler:
    """Handles alert rule generation."""

    @property
    def name(self) -> str:
        return "alerts"

    @property
    def display_name(self) -> str:
        return "alerts"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        from nthlayer.generators.alerts import generate_alerts_for_service

        try:
            alerts = generate_alerts_for_service(
                service_file=ctx.service_yaml,
                output_file=None,
                environment=ctx.env,
                quiet=True,
            )
            severity_counts: Dict[str, int] = {}
            for alert in alerts:
                severity = getattr(alert, "severity", "unknown")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

            return [
                {"severity": sev, "count": count} for sev, count in sorted(severity_counts.items())
            ]
        except Exception as e:
            logger.warning("alert_plan_failed", err=str(e), exc_info=True)
            return []

    def generate(self, ctx: OrchestratorContext) -> int:
        from nthlayer.generators.alerts import generate_alerts_for_service

        output_file = ctx.output_dir / "alerts.yaml"
        alerts = generate_alerts_for_service(
            service_file=ctx.service_yaml,
            output_file=output_file,
            environment=ctx.env,
            quiet=True,
        )
        return len(alerts)


class DashboardHandler:
    """Handles dashboard generation and optional Grafana push."""

    @property
    def name(self) -> str:
        return "dashboard"

    @property
    def display_name(self) -> str:
        return "dashboard"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        return [
            {
                "name": f"{ctx.service_name}-dashboard",
                "panels": "12+",
                "description": "Auto-generated monitoring dashboard",
            }
        ]

    def generate(self, ctx: OrchestratorContext) -> int:
        from nthlayer.cli.dashboard import generate_dashboard_command

        output_file = ctx.output_dir / "dashboard.json"
        generate_dashboard_command(
            str(ctx.service_yaml),
            output=str(output_file),
            environment=ctx.env,
            dry_run=False,
            full_panels=False,
            quiet=True,
            prometheus_url=ctx.prometheus_url,
        )

        if ctx.push_to_grafana:
            _push_dashboard_to_grafana(output_file, ctx.service_name)

        return 1


class RecordingRulesHandler:
    """Handles recording rule generation from SLOs."""

    @property
    def name(self) -> str:
        return "recording-rules"

    @property
    def display_name(self) -> str:
        return "recording rules"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        from nthlayer.recording_rules.builder import build_recording_rules
        from nthlayer.specs.parser import parse_service_file

        context, resources = parse_service_file(ctx.service_yaml, environment=ctx.env)
        groups = build_recording_rules(context, resources)

        if not groups:
            return []

        return [
            {"type": group.name, "count": len(group.rules), "interval": group.interval}
            for group in groups
        ]

    def generate(self, ctx: OrchestratorContext) -> int:
        from nthlayer.recording_rules.builder import build_recording_rules
        from nthlayer.recording_rules.models import create_rule_groups
        from nthlayer.specs.parser import parse_service_file

        output_file = ctx.output_dir / "recording-rules.yaml"
        context, resources = parse_service_file(ctx.service_yaml, environment=ctx.env)
        groups = build_recording_rules(context, resources)

        if not groups:
            with open(output_file, "w") as f:
                f.write("# No recording rules generated (no SLOs defined)\n")
            return 0

        yaml_output = create_rule_groups(groups)
        with open(output_file, "w") as f:
            f.write("# Recording rules generated by NthLayer\n")
            f.write("# Pre-computed SLO metrics for dashboard and alert performance\n")
            f.write("#\n\n")
            f.write(yaml_output)

        return sum(len(group.rules) for group in groups)


class PagerDutyHandler:
    """Handles PagerDuty service creation with tier-based defaults."""

    @property
    def name(self) -> str:
        return "pagerduty"

    @property
    def display_name(self) -> str:
        return "PagerDuty"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        pd_resources = ctx.detector.get_resources_by_kind("PagerDuty")
        if not pd_resources:
            return []

        service = ctx.service_def.get("service", {})
        team = service.get("team", "unknown")
        tier = service.get("tier", "medium")
        support_model = service.get("support_model", "self")

        from nthlayer.pagerduty.defaults import get_schedules_for_tier

        schedules = get_schedules_for_tier(tier)

        return [
            {"type": "team", "name": team},
            {"type": "schedules", "names": [f"{team}-{s}" for s in schedules]},
            {"type": "escalation_policy", "name": f"{team}-escalation"},
            {
                "type": "service",
                "name": ctx.service_name,
                "tier": tier,
                "support_model": support_model,
            },
        ]

    def generate(self, ctx: OrchestratorContext) -> int:
        api_key = os.environ.get("PAGERDUTY_API_KEY")
        default_from = os.environ.get("PAGERDUTY_FROM_EMAIL", "nthlayer@example.com")

        service = ctx.service_def.get("service", {})
        team = service.get("team", "unknown")
        tier = service.get("tier", "medium")
        support_model = service.get("support_model", "self")

        pagerduty_config = service.get("pagerduty", {})
        timezone = pagerduty_config.get("timezone", "America/New_York")
        sre_ep_id = pagerduty_config.get("sre_escalation_policy_id")

        pd_resources = ctx.detector.get_resources_by_kind("PagerDuty")
        pd_resource = pd_resources[0] if pd_resources else None
        integration_key = None
        sre_integration_key = None
        if pd_resource:
            spec = pd_resource.get("spec", {})
            integration_key = spec.get("integration_key")
            sre_integration_key = spec.get("sre_integration_key")

        if not api_key:
            output_file = ctx.output_dir / "pagerduty-config.json"
            config = {
                "service_name": ctx.service_name,
                "team": team,
                "tier": tier,
                "support_model": support_model,
                "timezone": timezone,
                "resources_to_create": {
                    "team": team,
                    "schedules": [
                        f"{team}-primary",
                        f"{team}-secondary",
                        f"{team}-manager",
                    ],
                    "escalation_policy": f"{team}-escalation",
                    "service": ctx.service_name,
                },
                "note": "Set PAGERDUTY_API_KEY to create resources in PagerDuty",
            }
            with open(output_file, "w") as f:
                json.dump(config, f, indent=2, sort_keys=True)
            return 1

        with PagerDutyResourceManager(
            api_key=api_key,
            default_from=default_from,
        ) as manager:
            result = manager.setup_service(
                service_name=ctx.service_name,
                team=team,
                tier=tier,
                support_model=support_model,
                tz=timezone,
                sre_escalation_policy_id=sre_ep_id,
            )

        if not result.success:
            raise ProviderError(f"PagerDuty setup failed: {', '.join(result.errors)}")

        output_file = ctx.output_dir / "pagerduty-result.json"
        result_data = {
            "success": result.success,
            "team_id": result.team_id,
            "schedule_ids": result.schedule_ids,
            "escalation_policy_id": result.escalation_policy_id,
            "service_id": result.service_id,
            "service_url": result.service_url,
            "created_resources": result.created_resources,
            "warnings": result.warnings,
        }
        with open(output_file, "w") as f:
            json.dump(result_data, f, indent=2, sort_keys=True)

        if support_model in ("shared", "sre") and sre_ep_id and result.service_id:
            _setup_event_orchestration(
                api_key=api_key,
                default_from=default_from,
                service_id=result.service_id,
                sre_escalation_policy_id=sre_ep_id,
            )

        if integration_key:
            am_config = generate_alertmanager_config(
                service_name=ctx.service_name,
                team=team,
                pagerduty_integration_key=integration_key,
                support_model=support_model,
                tier=tier,
                sre_integration_key=sre_integration_key,
            )
            am_output = ctx.output_dir / "alertmanager.yaml"
            am_config.write(am_output)
            print(f"✅ Alertmanager config: {am_output}")

        return len(result.created_resources) or 1


class BackstageHandler:
    """Handles Backstage entity generation."""

    @property
    def name(self) -> str:
        return "backstage"

    @property
    def display_name(self) -> str:
        return "Backstage entity"

    def plan(self, ctx: OrchestratorContext) -> List[Dict[str, Any]]:
        slo_resources = ctx.detector.get_resources_by_kind("SLO")
        service = ctx.service_def.get("service", {})
        team = service.get("team", "unknown")
        tier = service.get("tier", "standard")

        return [
            {
                "type": "backstage_entity",
                "service": ctx.service_name,
                "team": team,
                "tier": tier,
                "slo_count": len(slo_resources),
                "output": "backstage.json",
            }
        ]

    def generate(self, ctx: OrchestratorContext) -> int:
        from nthlayer.generators.backstage import generate_backstage_entity

        result = generate_backstage_entity(
            service_file=ctx.service_yaml,
            output_dir=ctx.output_dir,
            environment=ctx.env,
        )

        if not result.success:
            print(f"   ⚠️  Backstage generation warning: {result.error}")
            return 0

        return 1


def _push_dashboard_to_grafana(dashboard_file: Path, service_name: str) -> None:
    """Push generated dashboard to Grafana via API."""
    import asyncio
    import json
    import os

    from nthlayer.providers.grafana import GrafanaProvider

    grafana_url = os.getenv("NTHLAYER_GRAFANA_URL")
    grafana_api_key = os.getenv("NTHLAYER_GRAFANA_API_KEY")
    grafana_org_id = int(os.getenv("NTHLAYER_GRAFANA_ORG_ID", "1"))

    if not grafana_url or not grafana_api_key:
        print("⚠️  Grafana not configured. Skipping push to Grafana.")
        print("   Set NTHLAYER_GRAFANA_URL and NTHLAYER_GRAFANA_API_KEY to enable auto-push.")
        return

    with open(dashboard_file) as f:
        dashboard_data = json.load(f)

    dashboard_json = dashboard_data.get("dashboard", {})

    if not dashboard_json:
        print("⚠️  Dashboard JSON is empty, skipping push")
        return

    provider = GrafanaProvider(url=grafana_url, token=grafana_api_key, org_id=grafana_org_id)
    dashboard_uid = dashboard_json.get("uid", service_name)

    print("📤 Pushing dashboard to Grafana...")

    async def do_push():
        """Push dashboard via async GrafanaProvider."""
        dashboard_resource = provider.dashboard(dashboard_uid)
        await dashboard_resource.apply(
            {
                "dashboard": dashboard_json,
                "folderUid": None,
                "title": dashboard_json.get("title", f"{service_name} Dashboard"),
            }
        )

    try:
        asyncio.run(do_push())
        print(f"✅ Dashboard pushed to Grafana: {grafana_url}/d/{dashboard_uid}")
    except Exception as e:
        logger.warning("grafana_push_failed", err=str(e), exc_info=True)
        print(f"⚠️  Failed to push dashboard to Grafana: {e}")
        print("   Dashboard file saved locally, you can import manually.")


def _setup_event_orchestration(
    api_key: str,
    default_from: str,
    service_id: str,
    sre_escalation_policy_id: str,
) -> None:
    """Set up Event Orchestration for alert routing overrides."""
    with EventOrchestrationManager(
        api_key=api_key,
        default_from=default_from,
    ) as orchestration:
        sre_rule = orchestration.create_sre_routing_rule(sre_escalation_policy_id)
        result = orchestration.setup_service_orchestration(
            service_id=service_id,
            routing_rules=[sre_rule],
        )
        if not result.success:
            print(f"⚠️  Event Orchestration setup failed: {result.error}")
        elif result.rules_created > 0:
            print(f"✅ Event Orchestration: {result.rules_created} routing rule(s) created")


def register_default_handlers(registry: ResourceRegistry) -> None:
    """Register all built-in resource handlers."""
    registry.register(SloHandler())
    registry.register(AlertHandler())
    registry.register(DashboardHandler())
    registry.register(RecordingRulesHandler())
    registry.register(PagerDutyHandler())
    registry.register(BackstageHandler())
