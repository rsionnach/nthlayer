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
    warnings: List[str] = field(default_factory=list)

    @property
    def total_resources(self) -> int:
        """Total number of resources that would be created."""
        return sum(len(items) for items in self.resources.values())

    @property
    def success(self) -> bool:
        """Whether plan succeeded without errors."""
        return len(self.errors) == 0


class ResourceDetector:
    """Detects what resources should be generated from a service definition.

    Uses single-pass indexing to avoid redundant list scans.
    """

    def __init__(self, service_def: Dict[str, Any]):
        self.service_def = service_def
        self._resource_index: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def _build_index(self) -> Dict[str, List[Dict[str, Any]]]:
        """Build single-pass resource index by kind.

        Indexes all resources in one O(N) pass instead of scanning
        multiple times for each resource type check.
        """
        if self._resource_index is not None:
            return self._resource_index

        index: Dict[str, List[Dict[str, Any]]] = {
            "SLO": [],
            "Dependencies": [],
            "Observability": [],
            "PagerDuty": [],
        }

        for resource in self.service_def.get("resources", []):
            kind = resource.get("kind", "")
            if kind in index:
                index[kind].append(resource)

        self._resource_index = index
        return index

    def detect(self) -> List[str]:
        """Returns list of resource types to generate."""
        index = self._build_index()
        resources = []

        # Always generate SLOs if defined
        if index["SLO"]:
            resources.append("slos")
            # Auto-add recording rules if SLOs exist
            resources.append("recording-rules")

        # Auto-generate alerts if dependencies defined
        if self._has_dependencies(index):
            resources.append("alerts")

        # Auto-generate dashboard if observability config or dependencies
        if index["Observability"] or self._has_dependencies(index):
            resources.append("dashboard")

        # Generate PagerDuty if resource defined
        if index["PagerDuty"]:
            resources.append("pagerduty")

        return resources

    def _has_dependencies(self, index: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Check if service has dependencies (for alert generation)."""
        deps_resources = index["Dependencies"]
        if not deps_resources:
            return False

        # Check first Dependencies resource for actual dependency content
        spec = deps_resources[0].get("spec", {})
        return bool(spec.get("databases") or spec.get("services") or spec.get("external_apis"))

    def get_resources_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        """Get all resources of a specific kind (cached)."""
        index = self._build_index()
        return index.get(kind, [])


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
        self,
        service_yaml: Path,
        env: Optional[str] = None,
        push_to_grafana: bool = False,
        prometheus_url: Optional[str] = None,
    ):
        self.service_yaml = service_yaml
        self.env = env
        self.push_to_grafana = push_to_grafana
        self.prometheus_url = prometheus_url
        self.service_def: Optional[Dict[str, Any]] = None
        self.service_name: Optional[str] = None
        self.output_dir: Optional[Path] = None
        self._detector: Optional[ResourceDetector] = None

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

        # Note: Environment-specific config is applied by individual generators
        # when they call parse_service_file() with environment=self.env.
        # This allows each generator to get the merged config appropriate
        # for the target environment.

    def _get_detector(self) -> ResourceDetector:
        """Get cached resource detector, creating if needed."""
        if self._detector is None:
            self._detector = ResourceDetector(self.service_def or {})
        return self._detector

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

        # Detect what resources to generate (uses cached detector)
        resource_types = self._get_detector().detect()

        # Warn if no resources detected (non-fatal)
        if not resource_types:
            result.warnings.append(
                "No resources detected. Service YAML may be missing SLO, "
                "Dependencies, Observability, or PagerDuty resources."
            )

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

        # Create output directory and verify writability
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # Verify directory is writable by attempting to create a test file
            test_file = self.output_dir / ".nthlayer_write_test"
            test_file.touch()
            test_file.unlink()
        except OSError as e:
            return ApplyResult(
                service_name=self.service_name,
                output_dir=self.output_dir,
                errors=[f"Output directory not writable: {e}"],
            )

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
        """Detect and filter resource types to generate (uses cached detector)."""
        resource_types = self._get_detector().detect()

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
        slo_resources = self._get_detector().get_resources_by_kind("SLO")
        return [
            {
                "name": r.get("name"),
                "objective": r.get("spec", {}).get("objective"),
                "window": r.get("spec", {}).get("window", "30d"),
            }
            for r in slo_resources
        ]

    def _plan_alerts(self) -> List[Dict[str, Any]]:
        """Plan alert generation using actual alert generator."""
        from nthlayer.generators.alerts import generate_alerts_for_service

        try:
            # Generate alerts without writing to get actual count
            # Use quiet=True to suppress progress output (avoids polluting JSON output)
            alerts = generate_alerts_for_service(
                service_file=self.service_yaml,
                output_file=None,  # Don't write during plan
                environment=self.env,
                quiet=True,
            )

            # Group by severity for summary
            severity_counts: Dict[str, int] = {}
            for alert in alerts:
                severity = getattr(alert, "severity", "unknown")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

            return [
                {"severity": sev, "count": count} for sev, count in sorted(severity_counts.items())
            ]
        except Exception:
            # Fall back to empty list on error
            return []

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
        """Plan recording rule generation using actual builder."""
        from nthlayer.recording_rules.builder import build_recording_rules
        from nthlayer.specs.parser import parse_service_file

        # Parse service file to get context and resources
        context, resources = parse_service_file(self.service_yaml, environment=self.env)

        # Build recording rules (dry run - just to get counts)
        groups = build_recording_rules(context, resources)

        if not groups:
            return []

        # Return breakdown by group
        return [
            {"type": group.name, "count": len(group.rules), "interval": group.interval}
            for group in groups
        ]

    def _plan_pagerduty(self) -> List[Dict[str, Any]]:
        """Plan PagerDuty service creation."""
        service_def = self.service_def or {}
        service_name = self.service_name or "unknown"
        pd_resources = self._get_detector().get_resources_by_kind("PagerDuty")

        if not pd_resources:
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
        """Generate SLO files using Sloth generator."""
        from nthlayer.generators.sloth import generate_sloth_spec

        output_dir = self.output_dir or Path("generated")
        sloth_output_dir = output_dir / "sloth"

        # Generate Sloth specification
        result = generate_sloth_spec(
            service_file=self.service_yaml,
            output_dir=sloth_output_dir,
            environment=self.env,
        )

        if not result.success:
            if result.error and "No SLO resources found" in result.error:
                # No SLOs defined - not an error, just nothing to generate
                return 0
            # Log error but don't fail the whole apply
            print(f"   ⚠️  SLO generation warning: {result.error}")
            return 0

        return result.slo_count

    def _generate_alerts(self) -> int:
        """Generate alert files using actual alert generator."""
        from nthlayer.generators.alerts import generate_alerts_for_service

        output_dir = self.output_dir or Path("generated")
        output_file = output_dir / "alerts.yaml"

        # Use quiet=True to suppress progress output (avoids polluting JSON output)
        alerts = generate_alerts_for_service(
            service_file=self.service_yaml,
            output_file=output_file,
            environment=self.env,
            quiet=True,
        )

        return len(alerts)

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
            prometheus_url=self.prometheus_url,
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
        """Generate recording rule files using actual builder."""
        from nthlayer.recording_rules.builder import build_recording_rules
        from nthlayer.recording_rules.models import create_rule_groups
        from nthlayer.specs.parser import parse_service_file

        output_dir = self.output_dir or Path("generated")
        output_file = output_dir / "recording-rules.yaml"

        # Parse service file to get context and resources
        context, resources = parse_service_file(self.service_yaml, environment=self.env)

        # Build recording rules
        groups = build_recording_rules(context, resources)

        if not groups:
            # No SLOs or other rule sources, write empty file
            with open(output_file, "w") as f:
                f.write("# No recording rules generated (no SLOs defined)\n")
            return 0

        # Generate YAML and write to file
        yaml_output = create_rule_groups(groups)
        with open(output_file, "w") as f:
            f.write("# Recording rules generated by NthLayer\n")
            f.write("# Pre-computed SLO metrics for dashboard and alert performance\n")
            f.write("#\n\n")
            f.write(yaml_output)

        # Return actual count of rules
        return sum(len(group.rules) for group in groups)

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

        # Extract pagerduty config once (avoid repeated dict creation)
        pagerduty_config = service.get("pagerduty", {})
        timezone = pagerduty_config.get("timezone", "America/New_York")

        # Get SRE escalation policy ID for shared/sre support models
        sre_ep_id = pagerduty_config.get("sre_escalation_policy_id")

        # Get PagerDuty resource from cached detector (avoid rescanning resources list)
        pd_resources = self._get_detector().get_resources_by_kind("PagerDuty")
        pd_resource = pd_resources[0] if pd_resources else None
        integration_key = None
        sre_integration_key = None
        if pd_resource:
            spec = pd_resource.get("spec", {})
            integration_key = spec.get("integration_key")
            sre_integration_key = spec.get("sre_integration_key")

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
                json.dump(config, f, indent=2, sort_keys=True)
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
            json.dump(result_data, f, indent=2, sort_keys=True)

        # Set up Event Orchestration for routing overrides if needed
        if support_model in ("shared", "sre") and sre_ep_id and result.service_id:
            self._setup_event_orchestration(
                api_key=api_key,
                default_from=default_from,
                service_id=result.service_id,
                sre_escalation_policy_id=sre_ep_id,
            )

        # Generate Alertmanager config if integration key available (uses values extracted earlier)
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
