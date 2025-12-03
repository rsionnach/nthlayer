"""
Service orchestrator for unified apply workflow.

Coordinates generation of all resources (SLOs, alerts, dashboards, etc.)
from a single service definition file.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# TODO: Import these when implementing actual generation
# from nthlayer.slos.parser import parse_slo_file
# from nthlayer.alerts.generator import AlertGenerator
# from nthlayer.dashboards.builder import DashboardBuilder
# from nthlayer.recording_rules.builder import RecordingRuleBuilder


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
    
    def __init__(self, service_yaml: Path, env: Optional[str] = None, push_to_grafana: bool = False):
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
        
        with open(self.service_yaml, 'r') as f:
            self.service_def = yaml.safe_load(f)
        
        # Get service name
        service_section = self.service_def.get("service", {})
        self.service_name = service_section.get("name", self.service_yaml.stem)
        
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
                errors=[f"Failed to load service: {e}"]
            )
        
        result = PlanResult(
            service_name=self.service_name,
            service_yaml=self.service_yaml
        )
        
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
    
    def apply(self,
              skip: Optional[List[str]] = None,
              only: Optional[List[str]] = None,
              force: bool = False,
              verbose: bool = False) -> ApplyResult:
        """Generate all resources for the service."""
        start = time.time()
        
        try:
            self._load_service()
        except Exception as e:
            return ApplyResult(
                service_name=self.service_yaml.stem,
                errors=[f"Failed to load service: {e}"]
            )
        
        result = ApplyResult(
            service_name=self.service_name,
            output_dir=self.output_dir
        )
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Detect what resources to generate
        detector = ResourceDetector(self.service_def)
        resource_types = detector.detect()
        
        # Apply filters
        if only:
            resource_types = [r for r in resource_types if r in only]
        if skip:
            resource_types = [r for r in resource_types if r not in skip]
        
        # Generate each resource type
        step = 1
        total_steps = len(resource_types)
        
        if "slos" in resource_types:
            if verbose:
                print(f"[{step}/{total_steps}] Generating SLOs...")
            try:
                count = self._generate_slos()
                result.resources_created["slos"] = count
                if verbose:
                    print(f"✅ {count} SLOs created")
            except Exception as e:
                result.errors.append(f"SLO generation failed: {e}")
            step += 1
        
        if "alerts" in resource_types:
            if verbose:
                print(f"[{step}/{total_steps}] Generating alerts...")
            try:
                count = self._generate_alerts()
                result.resources_created["alerts"] = count
                if verbose:
                    print(f"✅ {count} alerts created")
            except Exception as e:
                result.errors.append(f"Alert generation failed: {e}")
            step += 1
        
        if "dashboard" in resource_types:
            if verbose:
                print(f"[{step}/{total_steps}] Generating dashboard...")
            try:
                count = self._generate_dashboard(push_to_grafana=self.push_to_grafana)
                result.resources_created["dashboard"] = count
                if verbose:
                    if self.push_to_grafana:
                        print("✅ Dashboard created and pushed to Grafana")
                    else:
                        print("✅ Dashboard created")
            except Exception as e:
                result.errors.append(f"Dashboard generation failed: {e}")
            step += 1
        
        if "recording-rules" in resource_types:
            if verbose:
                print(f"[{step}/{total_steps}] Generating recording rules...")
            try:
                count = self._generate_recording_rules()
                result.resources_created["recording-rules"] = count
                if verbose:
                    print(f"✅ {count} recording rules created")
            except Exception as e:
                result.errors.append(f"Recording rule generation failed: {e}")
            step += 1
        
        if "pagerduty" in resource_types:
            if verbose:
                print(f"[{step}/{total_steps}] Setting up PagerDuty...")
            try:
                count = self._generate_pagerduty()
                result.resources_created["pagerduty"] = count
                if verbose:
                    print("✅ PagerDuty service created")
            except Exception as e:
                result.errors.append(f"PagerDuty setup failed: {e}")
            step += 1
        
        result.duration_seconds = time.time() - start
        return result
    
    # Planning methods (return summaries, don't generate files)
    
    def _plan_slos(self) -> List[Dict[str, Any]]:
        """Plan SLO generation."""
        slo_resources = [r for r in self.service_def.get("resources", []) if r.get("kind") == "SLO"]
        return [
            {
                "name": r.get("name"),
                "objective": r.get("spec", {}).get("objective"),
                "window": r.get("spec", {}).get("window", "30d")
            }
            for r in slo_resources
        ]
    
    def _plan_alerts(self) -> List[Dict[str, Any]]:
        """Plan alert generation."""
        # Get dependencies
        deps_resource = next(
            (r for r in self.service_def.get("resources", []) if r.get("kind") == "Dependencies"),
            None
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
        return [{
            "name": f"{self.service_name}-dashboard",
            "panels": "12+",
            "description": "Auto-generated monitoring dashboard"
        }]
    
    def _plan_recording_rules(self) -> List[Dict[str, Any]]:
        """Plan recording rule generation."""
        slo_count = len([r for r in self.service_def.get("resources", []) if r.get("kind") == "SLO"])
        # Roughly 7 rules per SLO
        return [{"type": "SLO metrics", "count": slo_count * 7}]
    
    def _plan_pagerduty(self) -> List[Dict[str, Any]]:
        """Plan PagerDuty service creation."""
        pd_resource = next(
            (r for r in self.service_def.get("resources", []) if r.get("kind") == "PagerDuty"),
            None
        )
        
        if not pd_resource:
            return []
        
        return [{
            "name": self.service_name,
            "urgency": pd_resource.get("spec", {}).get("urgency", "high")
        }]
    
    # Generation methods (actually create files)
    
    def _generate_slos(self) -> int:
        """Generate SLO files."""
        # TODO: Implement actual SLO generation
        # For now, return count
        slo_resources = [r for r in self.service_def.get("resources", []) if r.get("kind") == "SLO"]
        
        # Write placeholder file
        output_file = self.output_dir / "slos.yaml"
        with open(output_file, 'w') as f:
            yaml.dump({"slos": slo_resources}, f)
        
        return len(slo_resources)
    
    def _generate_alerts(self) -> int:
        """Generate alert files."""
        # TODO: Implement actual alert generation using AlertGenerator
        # For now, return estimated count
        deps_resource = next(
            (r for r in self.service_def.get("resources", []) if r.get("kind") == "Dependencies"),
            None
        )
        
        if not deps_resource:
            return 0
        
        # Write placeholder
        output_file = self.output_dir / "alerts.yaml"
        with open(output_file, 'w') as f:
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
        
        # Generate dashboard JSON file
        output_file = self.output_dir / "dashboard.json"
        generate_dashboard_command(
            str(self.service_yaml),
            output=str(output_file),
            environment=self.env,
            dry_run=False,
            full_panels=False
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
        
        # Get configuration directly from environment (simpler and more reliable)
        grafana_url = os.getenv('NTHLAYER_GRAFANA_URL')
        grafana_api_key = os.getenv('NTHLAYER_GRAFANA_API_KEY')
        grafana_org_id = int(os.getenv('NTHLAYER_GRAFANA_ORG_ID', '1'))
        
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
        provider = GrafanaProvider(
            url=grafana_url,
            token=grafana_api_key,
            org_id=grafana_org_id
        )
        
        # Get dashboard UID from JSON
        dashboard_uid = dashboard_json.get("uid", self.service_name)
        
        # Push dashboard
        print("📤 Pushing dashboard to Grafana...")
        
        async def do_push():
            """Async function to push dashboard."""
            dashboard_resource = provider.dashboard(dashboard_uid)
            await dashboard_resource.apply({
                "dashboard": dashboard_json,
                "folderUid": None,  # Use default folder
                "title": dashboard_json.get("title", f"{self.service_name} Dashboard")
            })
        
        try:
            # Check if there's already an event loop running
            try:
                loop = asyncio.get_running_loop()
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
        output_file = self.output_dir / "recording-rules.yaml"
        with open(output_file, 'w') as f:
            f.write("# Recording rules would be generated here\n")
        
        # Estimate count
        slo_count = len([r for r in self.service_def.get("resources", []) if r.get("kind") == "SLO"])
        return slo_count * 7
    
    def _generate_pagerduty(self) -> int:
        """Generate PagerDuty service."""
        # TODO: Implement actual PagerDuty setup
        output_file = self.output_dir / "pagerduty.json"
        with open(output_file, 'w') as f:
            f.write('{"pagerduty": "placeholder"}\n')
        
        return 1
