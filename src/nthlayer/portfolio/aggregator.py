"""
Portfolio aggregator.

Scans service files and collects SLO information.
Optionally queries Prometheus for live SLO data.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from nthlayer.portfolio.models import (
    HealthStatus,
    Insight,
    InsightType,
    PortfolioHealth,
    ServiceHealth,
    SLOHealth,
    TierHealth,
    get_tier_name,
)
from nthlayer.specs.parser import parse_service_file


class PortfolioAggregator:
    """Aggregates SLO health across all services."""

    def __init__(
        self,
        search_paths: list[Path] | None = None,
        prometheus_url: str | None = None,
    ):
        """
        Initialize aggregator.

        Args:
            search_paths: Directories to search for service files.
                         Defaults to ["services", "examples/services"]
            prometheus_url: Optional Prometheus URL for live SLO queries
        """
        self.search_paths = search_paths or [
            Path("services"),
            Path("examples/services"),
        ]
        self.prometheus_url = prometheus_url

    def collect(self) -> PortfolioHealth:
        """
        Collect SLO health from all service files.

        If prometheus_url is configured, queries Prometheus for live SLO data.

        Returns:
            PortfolioHealth with aggregated data
        """
        services: list[ServiceHealth] = []
        slo_specs: list[tuple[ServiceHealth, Path]] = []

        # Scan for service files
        for search_path in self.search_paths:
            if not search_path.exists():
                continue

            for service_file in search_path.glob("*.yaml"):
                service_health = self._parse_service_file(service_file)
                if service_health:
                    services.append(service_health)
                    slo_specs.append((service_health, service_file))

        # If Prometheus URL provided, enrich with live data
        if self.prometheus_url:
            asyncio.run(self._enrich_with_live_data(slo_specs))

        # Calculate tier health
        by_tier = self._calculate_tier_health(services)

        # Generate insights
        insights = self._generate_insights(services)

        # Count services with SLOs
        services_with_slos = sum(1 for svc in services if svc.slos)
        healthy_services = sum(1 for svc in services if svc.slos and svc.is_healthy)

        return PortfolioHealth(
            timestamp=datetime.now(UTC),
            total_services=len(services),
            services_with_slos=services_with_slos,
            healthy_services=healthy_services,
            by_tier=by_tier,
            services=services,
            insights=insights,
        )

    async def _enrich_with_live_data(
        self,
        slo_specs: list[tuple[ServiceHealth, Path]],
    ) -> None:
        """
        Enrich SLO health with live data from Prometheus.

        Updates SLO status, current_value, and budget_consumed_percent in place.
        """
        from nthlayer.providers.prometheus import PrometheusProvider

        # Get auth credentials from environment
        username = os.environ.get("NTHLAYER_METRICS_USER")
        password = os.environ.get("NTHLAYER_METRICS_PASSWORD")

        if not self.prometheus_url:
            raise ValueError("Prometheus URL is required for collecting metrics")
        provider = PrometheusProvider(self.prometheus_url, username=username, password=password)

        for service_health, service_file in slo_specs:
            try:
                context, resources = parse_service_file(str(service_file))
            except Exception:
                continue

            slo_resources = [r for r in resources if r.kind == "SLO"]

            # Match SLO resources to health objects (use strict=False for robustness)
            for slo_resource, slo_health in zip(slo_resources, service_health.slos, strict=False):
                spec = slo_resource.spec or {}
                indicator = spec.get("indicator", {})
                query = indicator.get("query")

                if not query:
                    continue

                # Substitute service name in query
                query = query.replace("${service}", context.name)
                query = query.replace("$service", context.name)

                try:
                    result = await provider.query(query)
                    if result and result.get("result"):
                        value_data = result["result"][0].get("value", [])
                        if len(value_data) >= 2:
                            current_value = float(value_data[1])
                            slo_health.current_value = current_value

                            # Calculate status based on objective
                            objective = slo_health.objective
                            if current_value >= objective:
                                slo_health.status = HealthStatus.HEALTHY
                            elif current_value >= objective * 0.99:  # Within 1%
                                slo_health.status = HealthStatus.WARNING
                            elif current_value >= objective * 0.95:  # Within 5%
                                slo_health.status = HealthStatus.CRITICAL
                            else:
                                slo_health.status = HealthStatus.EXHAUSTED

                            # Estimate budget consumed
                            error_budget = 100 - objective
                            error_rate = 100 - current_value
                            if error_budget > 0:
                                budget_consumed = (error_rate / error_budget) * 100
                                slo_health.budget_consumed_percent = min(budget_consumed, 100)
                except Exception:
                    # Keep UNKNOWN status on query failure
                    pass

            # Recalculate overall status after enrichment
            service_health.__post_init__()

    def _parse_service_file(self, file_path: Path) -> ServiceHealth | None:
        """Parse a service file and extract health information."""
        try:
            context, resources = parse_service_file(str(file_path))
        except Exception:
            return None

        # Extract SLOs
        slo_resources = [r for r in resources if r.kind == "SLO"]
        slos = []

        for slo in slo_resources:
            spec = slo.spec or {}
            slos.append(
                SLOHealth(
                    name=slo.name or "unnamed",
                    objective=spec.get("objective", 99.9),
                    window=spec.get("window", "30d"),
                    status=HealthStatus.UNKNOWN,  # No live data in basic mode
                )
            )

        # Parse tier (handle both int and string formats)
        tier_str = context.tier
        tier_num: int = 2  # default to standard
        if isinstance(tier_str, str):
            # Handle "tier-1", "tier-2", etc.
            if tier_str.startswith("tier-"):
                tier_num = int(tier_str.split("-")[1])
            elif tier_str.isdigit():
                tier_num = int(tier_str)
            else:
                # Map string names to numbers
                tier_map = {"critical": 1, "standard": 2, "low": 3}
                tier_num = tier_map.get(tier_str.lower(), 2)
        elif isinstance(tier_str, int):
            tier_num = tier_str

        return ServiceHealth(
            service=context.name,
            tier=tier_num,
            team=context.team,
            service_type=context.type,
            slos=slos,
        )

    def _calculate_tier_health(self, services: list[ServiceHealth]) -> list[TierHealth]:
        """Calculate health statistics per tier."""
        tier_stats: dict[int, dict[str, int]] = {}

        for svc in services:
            if not svc.slos:  # Skip services without SLOs
                continue

            tier = svc.tier
            if tier not in tier_stats:
                tier_stats[tier] = {"total": 0, "healthy": 0}

            tier_stats[tier]["total"] += 1
            if svc.is_healthy:
                tier_stats[tier]["healthy"] += 1

        # Convert to TierHealth objects, sorted by tier
        return [
            TierHealth(
                tier=tier,
                tier_name=get_tier_name(tier),
                total_services=stats["total"],
                healthy_services=stats["healthy"],
            )
            for tier, stats in sorted(tier_stats.items())
        ]

    def _generate_insights(self, services: list[ServiceHealth]) -> list[Insight]:
        """Generate actionable insights from portfolio data."""
        insights = []

        for svc in services:
            # No SLOs defined
            if not svc.slos:
                insights.append(
                    Insight(
                        type=InsightType.NO_SLO,
                        service=svc.service,
                        message="No SLOs defined - add reliability targets",
                        severity="warning",
                    )
                )
                continue

            # Check for very aggressive SLOs on lower tiers
            for slo in svc.slos:
                if svc.tier >= 2 and slo.objective >= 99.99:
                    msg = (
                        f"SLO {slo.name} ({slo.objective}%) "
                        f"may be too aggressive for tier-{svc.tier}"
                    )
                    insights.append(
                        Insight(
                            type=InsightType.UNREALISTIC,
                            service=svc.service,
                            message=msg,
                            severity="info",
                        )
                    )

            # Check for services that might be under-tiered
            if svc.tier >= 2:
                all_high = all(slo.objective >= 99.9 for slo in svc.slos)
                if all_high and len(svc.slos) >= 2:
                    msg = f"High SLO targets for tier-{svc.tier} - consider tier promotion"
                    insights.append(
                        Insight(
                            type=InsightType.PROMOTION,
                            service=svc.service,
                            message=msg,
                            severity="info",
                        )
                    )

        return insights


def collect_portfolio(
    search_paths: list[str] | None = None,
    prometheus_url: str | None = None,
) -> PortfolioHealth:
    """
    Convenience function to collect portfolio health.

    Args:
        search_paths: Optional list of directories to search
        prometheus_url: Optional Prometheus URL for live SLO data

    Returns:
        PortfolioHealth with aggregated data
    """
    paths = [Path(p) for p in search_paths] if search_paths else None
    aggregator = PortfolioAggregator(search_paths=paths, prometheus_url=prometheus_url)
    return aggregator.collect()
