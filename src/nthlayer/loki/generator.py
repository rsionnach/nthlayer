"""
Loki Alert Generator

Generates LogQL alert rules from service definitions.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from nthlayer.specs.helpers import extract_dependency_technologies
from nthlayer.specs.manifest import ReliabilityManifest
from nthlayer.specs.models import Resource

from .models import LogQLAlert
from .templates import LogPattern, get_patterns_for_technology

logger = logging.getLogger(__name__)


class LokiAlertGenerator:
    """Generate LogQL alert rules from service definitions.

    Usage:
        generator = LokiAlertGenerator()
        alerts = generator.generate_for_service(
            service_name="payment-api",
            service_type="api",
            dependencies=["postgresql", "redis"],
            tier="critical"
        )
    """

    def __init__(self, namespace: str = "nthlayer"):
        """Initialize generator.

        Args:
            namespace: Namespace for alert rules (used in Loki ruler)
        """
        self.namespace = namespace

    def generate_for_service(
        self,
        service_name: str,
        service_type: str = "api",
        dependencies: list[str] | None = None,
        tier: str = "standard",
        labels: dict[str, str] | None = None,
    ) -> list[LogQLAlert]:
        """Generate LogQL alerts for a service.

        Args:
            service_name: Name of the service
            service_type: Type of service (api, worker, stream)
            dependencies: List of technology dependencies
            tier: Service tier (critical, standard, low)
            labels: Additional labels to add to alerts

        Returns:
            List of LogQLAlert objects
        """
        alerts = []
        dependencies = dependencies or []
        labels = labels or {}

        # Add service labels
        base_labels = {
            "service": service_name,
            "tier": tier,
            **labels,
        }

        # Generate alerts for the service itself
        service_alerts = self._generate_service_alerts(
            service_name=service_name,
            service_type=service_type,
            tier=tier,
            labels=base_labels,
        )
        alerts.extend(service_alerts)

        # Generate alerts for each dependency
        for dep in dependencies:
            dep_alerts = self._generate_dependency_alerts(
                service_name=service_name,
                dependency=dep,
                tier=tier,
                labels=base_labels,
            )
            alerts.extend(dep_alerts)

        logger.info(
            f"Generated {len(alerts)} Loki alerts for {service_name} "
            f"(type={service_type}, deps={dependencies})"
        )
        return alerts

    def generate_from_manifest(
        self,
        manifest: ReliabilityManifest,
        labels: dict[str, str] | None = None,
    ) -> list[LogQLAlert]:
        """Generate LogQL alerts from ReliabilityManifest.

        Args:
            manifest: ReliabilityManifest instance
            labels: Additional labels to add to alerts

        Returns:
            List of LogQLAlert objects
        """
        dependencies = extract_dependency_technologies(manifest)

        return self.generate_for_service(
            service_name=manifest.name,
            service_type=manifest.type,
            dependencies=dependencies,
            tier=manifest.tier,
            labels={"team": manifest.team, **(labels or {})},
        )

    def _generate_service_alerts(
        self,
        service_name: str,
        service_type: str,
        tier: str,
        labels: dict[str, str],
    ) -> list[LogQLAlert]:
        """Generate alerts for the service's own logs."""
        alerts = []
        patterns = get_patterns_for_technology(service_type)

        for pattern in patterns:
            # Adjust severity based on tier
            severity = self._adjust_severity(pattern.severity, tier)

            # Build LogQL expression
            expr = self._build_logql_expr(
                service_name=service_name,
                pattern=pattern,
                labels=labels,
            )

            alert = LogQLAlert(
                name=f"{service_name}_{pattern.name}",
                expr=expr,
                severity=severity,
                for_duration=pattern.for_duration,
                summary=f"[{service_name}] {pattern.summary}",
                description=pattern.description,
                technology=service_type,
                category="service",
                labels={"source": "service", **labels},
            )
            alerts.append(alert)

        return alerts

    def _generate_dependency_alerts(
        self,
        service_name: str,
        dependency: str,
        tier: str,
        labels: dict[str, str],
    ) -> list[LogQLAlert]:
        """Generate alerts for a dependency's logs."""
        alerts = []
        patterns = get_patterns_for_technology(dependency)

        for pattern in patterns:
            severity = self._adjust_severity(pattern.severity, tier)

            expr = self._build_logql_expr(
                service_name=service_name,
                pattern=pattern,
                labels=labels,
                dependency=dependency,
            )

            alert = LogQLAlert(
                name=f"{service_name}_{dependency}_{pattern.name}",
                expr=expr,
                severity=severity,
                for_duration=pattern.for_duration,
                summary=f"[{service_name}/{dependency}] {pattern.summary}",
                description=pattern.description,
                technology=dependency,
                category="dependency",
                labels={"source": "dependency", "dependency": dependency, **labels},
            )
            alerts.append(alert)

        return alerts

    def _build_logql_expr(
        self,
        service_name: str,
        pattern: LogPattern,
        labels: dict[str, str],
        dependency: str | None = None,
    ) -> str:
        """Build a LogQL expression from a pattern.

        Args:
            service_name: Service name for label filtering
            pattern: Log pattern to match
            labels: Additional labels
            dependency: Optional dependency name

        Returns:
            LogQL query string
        """
        # Build label selector
        if dependency:
            label_selector = f'{{app="{dependency}", service="{service_name}"}}'
        else:
            label_selector = f'{{app="{service_name}"}}'

        # Build the LogQL expression
        if pattern.threshold > 0:
            # Rate-based alert (count errors over time window)
            expr = (
                f"sum(count_over_time({label_selector} "
                f"{pattern.pattern} [{pattern.window}])) > {pattern.threshold}"
            )
        else:
            # Existence-based alert (any match triggers)
            expr = f"count_over_time({label_selector} {pattern.pattern} [1m]) > 0"

        return expr

    def _adjust_severity(self, base_severity: str, tier: str) -> str:
        """Adjust alert severity based on service tier.

        Critical tier services get elevated severity.
        Low tier services get reduced severity.
        """
        if tier == "critical":
            # Elevate warnings to critical for critical services
            if base_severity == "warning":
                return "warning"  # Keep warnings as warnings
            return base_severity
        elif tier == "low":
            # Downgrade critical to warning for low-tier services
            if base_severity == "critical":
                return "warning"
            return base_severity
        return base_severity

    def to_ruler_yaml(
        self,
        alerts: list[LogQLAlert],
        group_name: str | None = None,
    ) -> str:
        """Convert alerts to Grafana Loki Ruler YAML format.

        Args:
            alerts: List of LogQLAlert objects
            group_name: Optional group name (defaults to namespace)

        Returns:
            YAML string in Loki ruler format
        """
        group_name = group_name or self.namespace

        rules = [alert.to_ruler_format() for alert in alerts]

        ruler_config = {
            "groups": [
                {
                    "name": group_name,
                    "rules": rules,
                }
            ]
        }

        return yaml.dump(ruler_config, default_flow_style=False, sort_keys=False)

    def write_ruler_file(
        self,
        alerts: list[LogQLAlert],
        output_path: Path | str,
        group_name: str | None = None,
    ) -> Path:
        """Write alerts to a Loki ruler YAML file.

        Args:
            alerts: List of LogQLAlert objects
            output_path: Path to output file
            group_name: Optional group name

        Returns:
            Path to the written file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_content = self.to_ruler_yaml(alerts, group_name)

        with open(output_path, "w") as f:
            f.write(yaml_content)

        logger.info(f"Wrote {len(alerts)} Loki alerts to {output_path}")
        return output_path


def extract_dependencies_from_resources(resources: list[Resource]) -> list[str]:
    """Extract technology dependencies from service resources.

    Args:
        resources: List of Resource objects from service definition

    Returns:
        List of technology names
    """
    dependencies = []

    for resource in resources:
        if resource.kind != "Dependencies":
            continue

        spec = resource.spec

        for db in spec.get("databases", []):
            db_type = db.get("type", "")
            if not db_type:
                name = db.get("name", "")
                if name:
                    db_type = name.split("-")[0].lower()
            if db_type:
                dependencies.append(db_type.lower())

        for svc in spec.get("services", []):
            svc_type = svc.get("type", "")
            if svc_type:
                dependencies.append(svc_type.lower())

    return list(set(dependencies))


def generate_loki_alerts_from_manifest(
    manifest: ReliabilityManifest,
    output_dir: str | Path | None = None,
) -> tuple[list[LogQLAlert], Path | None]:
    """Generate Loki alerts from ReliabilityManifest.

    Args:
        manifest: ReliabilityManifest instance
        output_dir: Optional output directory for ruler file

    Returns:
        Tuple of (alerts list, output file path or None)
    """
    generator = LokiAlertGenerator()
    alerts = generator.generate_from_manifest(manifest)

    output_path = None
    if output_dir:
        output_dir = Path(output_dir)
        output_path = output_dir / manifest.name / "loki-alerts.yaml"
        generator.write_ruler_file(alerts, output_path, group_name=manifest.name)

    return alerts, output_path


def generate_loki_alerts_for_service_file(
    service_file: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[list[LogQLAlert], Path | None]:
    """Generate Loki alerts from a service.yaml file.

    Args:
        service_file: Path to service.yaml
        output_dir: Optional output directory for ruler file

    Returns:
        Tuple of (alerts list, output file path or None)
    """
    from nthlayer.specs.parser import parse_service_file

    service_file = Path(service_file)
    context, resources = parse_service_file(str(service_file))

    generator = LokiAlertGenerator()

    dependencies = extract_dependencies_from_resources(resources)

    alerts = generator.generate_for_service(
        service_name=context.name,
        service_type=context.type,
        dependencies=dependencies,
        tier=context.tier,
        labels={"team": context.team} if context.team else {},
    )

    output_path = None
    if output_dir:
        output_dir = Path(output_dir)
        output_path = output_dir / context.name / "loki-alerts.yaml"
        generator.write_ruler_file(alerts, output_path, group_name=context.name)

    return alerts, output_path
