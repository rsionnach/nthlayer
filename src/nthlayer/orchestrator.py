"""
Service orchestrator for unified apply workflow.

Coordinates generation of all resources (SLOs, alerts, dashboards, etc.)
from a single service definition file.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nthlayer.alertmanager import generate_alertmanager_config
from nthlayer.pagerduty import EventOrchestrationManager, PagerDutyResourceManager


@dataclass
class ApplyResult:
    """Result of applying a service configuration."""

    service_name: str
    resources_created: Dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    output_dir: Path = Path(".")
    errors: List[str] = field(default_factory=list)

    @property
    def total_resources(self) -> int:
        """Total number of resources created."""
        return sum(self.resources_created.values())

    @property
    def success(self) -> bool:
        """Whether apply succeeded without errors."""
        return len(self.errors) == 0


@dataclass
class PlanResult:
    """Result of planning (dry-run) a service configuration."""

    service_name: str
    service_yaml: Path
    resources: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def total_resources(self) -> int:
        """Total number of resources that would be created."""
        return sum(len(items) for items in self.resources.values())

    @property
    def success(self) -> bool:
        """Whether plan succeeded without errors."""
        return len(self.errors) == 0


class ResourceDetector:
    """Detects what resources should be generated from a service definition."""

    def __init__(self, service_def: Dict[str, Any]):
        self.service_def = service_def

    def detect(self) -> List[str]:
        """Returns list of resource types to generate."""
        resources = []

        # Always generate SLOs if defined
        if self._has_slos():
            resources.append("slos")
            # Auto-add recording rules if SLOs exist
            resources.append("recording-rules")

        # Auto-generate alerts if dependencies defined
        if self._has_dependencies():
            resources.append("alerts")

        # Auto-generate dashboard if observability config or dependencies
        if self._has_observability_config() or self._has_dependencies():
            resources.append("dashboard")

        # Generate PagerDuty if resource defined
        if self._has_pagerduty():
            resources.append("pagerduty")

        return resources

    def _has_slos(self) -> bool:
        """Check if service has SLO resources defined."""
        resources = self.service_def.get("resources", [])
        return any(r.get("kind") == "SLO" for r in resources)

    def _has_dependencies(self) -> bool:
        """Check if service has dependencies (for alert generation)."""
        resources = self.service_def.get("resources", [])
        deps_resource = next((r for r in resources if r.get("kind") == "Dependencies"), None)

        if not deps_resource:
            return False

        spec = deps_resource.get("spec", {})
        return bool(spec.get("databases") or spec.get("services") or spec.get("external_apis"))

    def _has_observability_config(self) -> bool:
        """Check if service has observability configuration."""
        resources = self.service_def.get("resources", [])
        return any(r.get("kind") == "Observability" for r in resources)

    def _has_pagerduty(self) -> bool:
        """Check if service has PagerDuty resource defined."""
        resources = self.service_def.get("resources", [])
        return any(r.get("kind") == "PagerDuty" for r in resources)


class ServiceOrchestrator:
    """Orchestrates generation of all resources for a service."""

    # Dispatch table mapping resource types to (generator_method, display_name)
    GENERATORS: Dict[str, tuple[str, str]] = {
        "slos": ("_generate_slos", "SLOs"),
        "alerts": ("_generate_alerts", "alerts"),
        "dashboard": ("_generate_dashboard", "dashboard"),
        "recording-rules": ("_generate_recording_rules", "recording rules"),
        "pagerduty": ("_generate_pagerduty", "PagerDuty"),
    }

    def __init__(
        self, service_yaml: Path, env: Optional[str] = None, push_to_grafana: bool = False
    ):
        self.service_yaml = service_yaml
        self.env = env
        self.push_to_grafana = push_to_grafana
        self.service_def: Optional[Dict[str, Any]] = None
        self.service_name: Optional[str] = None
        self.output_dir: Optional[Path] = None

    def _load_service(self) -> None:
        """Load and parse service YAML file."""
        if self.service_def is not None:
            return  # Already loaded

        with open(self.service_yaml, "r") as f:
            self.service_def = yaml.safe_load(f)

        # Get service name
        service_section = self.service_def.get("service", {})
        self.service_name = service_section.get("name") or self.service_yaml.stem

        # Set default output directory
        if self.output_dir is None:
            self.output_dir = Path("generated") / self.service_name

        # TODO: Apply environment-specific config if env is set
        if self.env:
            self._apply_environment_config()

    def _apply_environment_config(self) -> None:
        """Apply environment-specific configuration."""
        # TODO: Load environment config and merge with service def
        # For now, this is a placeholder
        pass

    def plan(self) -> PlanResult:
        """Preview what resources would be generated (dry-run)."""
        try:
            self._load_service()
        except Exception as e:
            return PlanResult(
                service_name=self.service_yaml.stem,
                service_yaml=self.service_yaml,
                errors=[f"Failed to load service: {e}"],
            )

        # After _load_service(), these are guaranteed to be set
        assert self.service_name is not None
        assert self.service_def is not None

        result = PlanResult(service_name=self.service_name, service_yaml=self.service_yaml)

        # Detect what resources to generate
        detector = ResourceDetector(self.service_def)
        resource_types = detector.detect()

        # Plan each resource type
        try:
            if "slos" in resource_types:
                result.resources["slos"] = self._plan_slos()

            if "alerts" in resource_types:
                result.resources["alerts"] = self._plan_alerts()

            if "dashboard" in resource_types:
                result.resources["dashboard"] = self._plan_dashboard()

            if "recording-rules" in resource_types:
                result.resources["recording-rules"] = self._plan_recording_rules()

            if "pagerduty" in resource_types:
                result.resources["pagerduty"] = self._plan_pagerduty()
        except Exception as e:
            result.errors.append(f"Planning failed: {e}")

        return result

    def apply(
        self,
        skip: Optional[List[str]] = None,
        only: Optional[List[str]] = None,
        force: bool = False,
        verbose: bool = False,
    ) -> ApplyResult:
        """Generate all resources for the service."""
        start = time.time()

        try:
            self._load_service()
        except Exception as e:
            return ApplyResult(
                service_name=self.service_yaml.stem, errors=[f"Failed to load service: {e}"]
            )

        # After _load_service(), these are guaranteed to be set
        assert self.service_name is not None
        assert self.service_def is not None
        assert self.output_dir is not None

        result = ApplyResult(service_name=self.service_name, output_dir=self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Get filtered resource types
        resource_types = self._get_filtered_resources(skip, only)
        total_steps = len(resource_types)

        # Generate each resource type using dispatch table
        for step, resource_type in enumerate(resource_types, 1):
            method_name, display_name = self.GENERATORS[resource_type]

            if verbose:
                print(f"[{step}/{total_steps}] Generating {display_name}...")

            try:
                generator = getattr(self, method_name)
                # Dashboard generator needs push_to_grafana arg
                if resource_type == "dashboard":
                    count = generator(push_to_grafana=self.push_to_grafana)
                else:
                    count = generator()
                result.resources_created[resource_type] = count
                if verbose:
                    self._log_success(resource_type, count, display_name)
            except Exception as e:
                result.errors.append(f"{display_name.capitalize()} generation failed: {e}")

        result.duration_seconds = time.time() - start
        return result

    def _get_filtered_resources(
        self, skip: Optional[List[str]], only: Optional[List[str]]
    ) -> List[str]:
        """Detect and filter resource types to generate."""
        service_def = self.service_def or {}
        detector = ResourceDetector(service_def)
        resource_types = detector.detect()

        if only:
            resource_types = [r for r in resource_types if r in only]
        if skip:
            resource_types = [r for r in resource_types if r not in skip]

        return resource_types

    def _log_success(self, resource_type: str, count: int, display_name: str) -> None:
        """Log success message for a generated resource."""
        if resource_type == "dashboard":
            if self.push_to_grafana:
                print("✅ Dashboard created and pushed to Grafana")
            else:
                print("✅ Dashboard created")
        elif resource_type == "pagerduty":
            print("✅ PagerDuty service created")
        else:
            print(f"✅ {count} {display_name} created")

    # Planning methods (return summaries, don't generate files)

    def _plan_slos(self) -> List[Dict[str, Any]]:
        """Plan SLO generation."""
        service_def = self.service_def or {}
        slo_resources = [r for r in service_def.get("resources", []) if r.get("kind") == "SLO"]
        return [
            {
                "name": r.get("name"),
                "objective": r.get("spec", {}).get("objective"),
                "window": r.get("spec", {}).get("window", "30d"),
            }
            for r in slo_resources
        ]

    def _plan_alerts(self) -> List[Dict[str, Any]]:
        """Plan alert generation."""
        service_def = self.service_def or {}
        # Get dependencies
        deps_resource = next(
            (r for r in service_def.get("resources", []) if r.get("kind") == "Dependencies"),
            None,
        )

        if not deps_resource:
            return []

        spec = deps_resource.get("spec", {})
        alerts = []

        # Count alerts by technology
        for db in spec.get("databases", []):
            db_type = db.get("type", "unknown")
            # Rough estimate of alerts per technology
            count = {"postgresql": 12, "redis": 8, "mysql": 10, "mongodb": 8}.get(db_type, 5)
            alerts.append({"technology": db_type, "count": count})

        return alerts

    def _plan_dashboard(self) -> List[Dict[str, Any]]:
        """Plan dashboard generation."""
        service_name = self.service_name or "unknown"
        return [
            {
                "name": f"{service_name}-dashboard",
                "panels": "12+",
                "description": "Auto-generated monitoring dashboard",
            }
        ]

    def _plan_recording_rules(self) -> List[Dict[str, Any]]:
        """Plan recording rule generation."""
        service_def = self.service_def or {}
        slo_count = len([r for r in service_def.get("resources", []) if r.get("kind") == "SLO"])
        # Roughly 7 rules per SLO
        return [{"type": "SLO metrics", "count": slo_count * 7}]

    def _plan_pagerduty(self) -> List[Dict[str, Any]]:
        """Plan PagerDuty service creation."""
        service_def = self.service_def or {}
        service_name = self.service_name or "unknown"
        pd_resource = next(
            (r for r in service_def.get("resources", []) if r.get("kind") == "PagerDuty"), None
        )

        if not pd_resource:
            return []

        service = service_def.get("service", {})
        team = service.get("team", "unknown")
        tier = service.get("tier", "medium")
        support_model = service.get("support_model", "self")

        # Resources that will be created based on tier
        from nthlayer.pagerduty.defaults import get_schedules_for_tier

        schedules = get_schedules_for_tier(tier)

        return [
            {
                "type": "team",
                "name": team,
            },
            {
                "type": "schedules",
                "names": [f"{team}-{s}" for s in schedules],
            },
            {
                "type": "escalation_policy",
                "name": f"{team}-escalation",
            },
            {
                "type": "service",
                "name": service_name,
                "tier": tier,
                "support_model": support_model,
            },
        ]

    # Generation methods (actually create files)

    def _generate_slos(self) -> int:
        """Generate SLO files."""
        # TODO: Implement actual SLO generation
        # For now, return count
        service_def = self.service_def or {}
        output_dir = self.output_dir or Path("generated")
        slo_resources = [r for r in service_def.get("resources", []) if r.get("kind") == "SLO"]

        # Write placeholder file
        output_file = output_dir / "slos.yaml"
        with open(output_file, "w") as f:
            yaml.dump({"slos": slo_resources}, f)

        return len(slo_resources)

    def _generate_alerts(self) -> int:
        """Generate alert files."""
        # TODO: Implement actual alert generation using AlertGenerator
        # For now, return estimated count
        service_def = self.service_def or {}
        output_dir = self.output_dir or Path("generated")
        deps_resource = next(
            (r for r in service_def.get("resources", []) if r.get("kind") == "Dependencies"),
            None,
        )

        if not deps_resource:
            return 0

        # Write placeholder
        output_file = output_dir / "alerts.yaml"
        with open(output_file, "w") as f:
            f.write("# Alerts would be generated here\n")

        # Estimate count
        spec = deps_resource.get("spec", {})
        count = 0
        for db in spec.get("databases", []):
            db_type = db.get("type", "unknown")
            count += {"postgresql": 12, "redis": 8, "mysql": 10, "mongodb": 8}.get(db_type, 5)

        return count

    def _generate_dashboard(self, push_to_grafana: bool = False) -> int:
        """Generate dashboard file and optionally push to Grafana.

        Args:
            push_to_grafana: If True, push dashboard to Grafana via API

        Returns:
            Number of dashboards created
        """
        from nthlayer.cli.dashboard import generate_dashboard_command

        output_dir = self.output_dir or Path("generated")
        # Generate dashboard JSON file
        output_file = output_dir / "dashboard.json"
        generate_dashboard_command(
            str(self.service_yaml),
            output=str(output_file),
            environment=self.env,
            dry_run=False,
            full_panels=False,
            quiet=True,
        )

        # If push to Grafana is enabled, use the provider
        if push_to_grafana:
            self._push_dashboard_to_grafana(output_file)

        return 1

    def _push_dashboard_to_grafana(self, dashboard_file: Path) -> None:
        """Push generated dashboard to Grafana via API.

        Args:
            dashboard_file: Path to generated dashboard JSON
        """
        import asyncio
        import json
        import os

        from nthlayer.providers.grafana import GrafanaProvider

        service_name = self.service_name or "unknown"

        # Get configuration directly from environment (simpler and more reliable)
        grafana_url = os.getenv("NTHLAYER_GRAFANA_URL")
        grafana_api_key = os.getenv("NTHLAYER_GRAFANA_API_KEY")
        grafana_org_id = int(os.getenv("NTHLAYER_GRAFANA_ORG_ID", "1"))

        # Check if Grafana is configured
        if not grafana_url or not grafana_api_key:
            print("⚠️  Grafana not configured. Skipping push to Grafana.")
            print("   Set NTHLAYER_GRAFANA_URL and NTHLAYER_GRAFANA_API_KEY to enable auto-push.")
            return

        # Load generated dashboard
        with open(dashboard_file) as f:
            dashboard_data = json.load(f)

        # Extract dashboard JSON (the 'dashboard' key from wrapper)
        dashboard_json = dashboard_data.get("dashboard", {})

        if not dashboard_json:
            print("⚠️  Dashboard JSON is empty, skipping push")
            return

        # Create Grafana provider
        provider = GrafanaProvider(url=grafana_url, token=grafana_api_key, org_id=grafana_org_id)

        # Get dashboard UID from JSON
        dashboard_uid = dashboard_json.get("uid", service_name)

        # Push dashboard
        print("📤 Pushing dashboard to Grafana...")

        async def do_push():
            """Async function to push dashboard."""
            dashboard_resource = provider.dashboard(dashboard_uid)
            await dashboard_resource.apply(
                {
                    "dashboard": dashboard_json,
                    "folderUid": None,  # Use default folder
                    "title": dashboard_json.get("title", f"{service_name} Dashboard"),
                }
            )

        try:
            # Check if there's already an event loop running
            try:
                _ = asyncio.get_running_loop()
                # If we're already in an async context, create a task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, do_push())
                    future.result()
            except RuntimeError:
                # No loop running, safe to use asyncio.run()
                asyncio.run(do_push())

            print(f"✅ Dashboard pushed to Grafana: {grafana_url}/d/{dashboard_uid}")
        except Exception as e:
            print(f"⚠️  Failed to push dashboard to Grafana: {e}")
            print(f"   Error type: {type(e).__name__}")
            import traceback

            traceback.print_exc()
            print("   Dashboard file saved locally, you can import manually.")

    def _generate_recording_rules(self) -> int:
        """Generate recording rule files."""
        # TODO: Implement actual recording rule generation
        service_def = self.service_def or {}
        output_dir = self.output_dir or Path("generated")
        output_file = output_dir / "recording-rules.yaml"
        with open(output_file, "w") as f:
            f.write("# Recording rules would be generated here\n")

        # Estimate count
        slo_count = len([r for r in service_def.get("resources", []) if r.get("kind") == "SLO"])
        return slo_count * 7

    def _generate_pagerduty(self) -> int:
        """Generate PagerDuty service with tier-based defaults."""
        # Get PagerDuty API key from environment
        api_key = os.environ.get("PAGERDUTY_API_KEY")
        default_from = os.environ.get("PAGERDUTY_FROM_EMAIL", "nthlayer@example.com")

        service_def = self.service_def or {}
        service_name = self.service_name or "unknown"
        output_dir = self.output_dir or Path("generated")
        service = service_def.get("service", {})
        team = service.get("team", "unknown")
        tier = service.get("tier", "medium")
        support_model = service.get("support_model", "self")
        timezone = service.get("pagerduty", {}).get("timezone", "America/New_York")

        # Get SRE escalation policy ID for shared/sre support models
        sre_ep_id = service.get("pagerduty", {}).get("sre_escalation_policy_id")

        # If no API key, generate config file only (dry-run mode)
        if not api_key:
            output_file = output_dir / "pagerduty-config.json"
            config = {
                "service_name": service_name,
                "team": team,
                "tier": tier,
                "support_model": support_model,
                "timezone": timezone,
                "resources_to_create": {
                    "team": team,
                    "schedules": [f"{team}-primary", f"{team}-secondary", f"{team}-manager"],
                    "escalation_policy": f"{team}-escalation",
                    "service": service_name,
                },
                "note": "Set PAGERDUTY_API_KEY to create resources in PagerDuty",
            }
            with open(output_file, "w") as f:
                json.dump(config, f, indent=2)
            return 1

        # Create resources in PagerDuty
        with PagerDutyResourceManager(
            api_key=api_key,
            default_from=default_from,
        ) as manager:
            result = manager.setup_service(
                service_name=service_name,
                team=team,
                tier=tier,
                support_model=support_model,
                tz=timezone,
                sre_escalation_policy_id=sre_ep_id,
            )

        if not result.success:
            raise RuntimeError(f"PagerDuty setup failed: {', '.join(result.errors)}")

        # Save result to file
        output_file = output_dir / "pagerduty-result.json"
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
            json.dump(result_data, f, indent=2)

        # Set up Event Orchestration for routing overrides if needed
        if support_model in ("shared", "sre") and sre_ep_id and result.service_id:
            self._setup_event_orchestration(
                api_key=api_key,
                default_from=default_from,
                service_id=result.service_id,
                sre_escalation_policy_id=sre_ep_id,
            )

        # Generate Alertmanager config if integration key available
        pd_resource = next(
            (r for r in service_def.get("resources", []) if r.get("kind") == "PagerDuty"),
            None,
        )
        integration_key = None
        sre_integration_key = None
        if pd_resource:
            spec = pd_resource.get("spec", {})
            integration_key = spec.get("integration_key")
            sre_integration_key = spec.get("sre_integration_key")

        if integration_key:
            self._generate_alertmanager_config(
                team=team,
                tier=tier,
                support_model=support_model,
                integration_key=integration_key,
                sre_integration_key=sre_integration_key,
            )

        return len(result.created_resources) or 1

    def _setup_event_orchestration(
        self,
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
            # Create SRE routing rule
            sre_rule = orchestration.create_sre_routing_rule(sre_escalation_policy_id)
            result = orchestration.setup_service_orchestration(
                service_id=service_id,
                routing_rules=[sre_rule],
            )
            if not result.success:
                print(f"⚠️  Event Orchestration setup failed: {result.error}")
            elif result.rules_created > 0:
                print(f"✅ Event Orchestration: {result.rules_created} routing rule(s) created")

    def _generate_alertmanager_config(
        self,
        team: str,
        tier: str,
        support_model: str,
        integration_key: str,
        sre_integration_key: str | None = None,
    ) -> None:
        """Generate Alertmanager configuration with PagerDuty receiver."""
        service_name = self.service_name or "unknown"
        output_dir = self.output_dir or Path("generated")
        config = generate_alertmanager_config(
            service_name=service_name,
            team=team,
            pagerduty_integration_key=integration_key,
            support_model=support_model,
            tier=tier,
            sre_integration_key=sre_integration_key,
        )

        # Write Alertmanager config
        output_file = output_dir / "alertmanager.yaml"
        config.write(output_file)
        print(f"✅ Alertmanager config: {output_file}")
