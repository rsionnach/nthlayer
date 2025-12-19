"""
SLO metrics collector.

Collects SLI metrics from Prometheus and calculates error budgets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from nthlayer.providers.prometheus import PrometheusProvider, PrometheusProviderError
from nthlayer.slos.calculator import ErrorBudgetCalculator
from nthlayer.slos.models import SLO, ErrorBudget
from nthlayer.slos.storage import SLORepository

logger = structlog.get_logger()


class SLOCollector:
    """Collects SLI metrics and calculates error budgets."""

    def __init__(
        self,
        prometheus_provider: PrometheusProvider,
        repository: SLORepository,
    ) -> None:
        self.prometheus = prometheus_provider
        self.repository = repository

    async def collect_slo_budget(
        self,
        slo: SLO,
        period_end: datetime | None = None,
        period_start: datetime | None = None,
    ) -> ErrorBudget:
        """
        Collect metrics for an SLO and calculate error budget.

        Args:
            slo: SLO to collect metrics for
            period_end: End of evaluation period (defaults to now)
            period_start: Start of evaluation period (defaults to time_window ago)

        Returns:
            Calculated error budget

        Raises:
            PrometheusProviderError: If metrics collection fails
        """
        # Set default time range
        if period_end is None:
            period_end = datetime.utcnow()

        if period_start is None:
            period_start = slo.time_window.get_start_time(period_end)

        logger.info(
            "collecting_slo_metrics",
            slo_id=slo.id,
            service=slo.service,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )

        try:
            # Query Prometheus for SLI time series
            measurements = await self.prometheus.get_sli_time_series(
                query=slo.query,
                start=period_start,
                end=period_end,
                step="5m",  # 5-minute resolution
            )

            logger.info(
                "collected_measurements",
                slo_id=slo.id,
                measurement_count=len(measurements),
            )

            # Calculate error budget
            calculator = ErrorBudgetCalculator(slo)
            budget = calculator.calculate_budget(
                period_start=period_start,
                period_end=period_end,
                sli_measurements=measurements,
            )

            logger.info(
                "calculated_budget",
                slo_id=slo.id,
                total_minutes=budget.total_budget_minutes,
                burned_minutes=budget.burned_minutes,
                percent_consumed=budget.percent_consumed,
                status=budget.status.value,
            )

            # Store in database
            await self.repository.create_or_update_error_budget(budget)

            # Store history records (optional, for time series tracking)
            await self._store_measurement_history(slo, measurements)

            logger.info(
                "stored_budget",
                slo_id=slo.id,
                budget_id=budget.id if hasattr(budget, "id") else None,
            )

            return budget

        except PrometheusProviderError as exc:
            logger.error(
                "prometheus_query_failed",
                slo_id=slo.id,
                error=str(exc),
            )
            raise

    async def collect_service_budgets(
        self,
        service: str,
        period_end: datetime | None = None,
        period_start: datetime | None = None,
    ) -> list[ErrorBudget]:
        """
        Collect budgets for all SLOs of a service.

        Args:
            service: Service name
            period_end: End of evaluation period
            period_start: Start of evaluation period

        Returns:
            List of calculated error budgets
        """
        # Get all SLOs for service
        slos = await self.repository.get_slos_by_service(service)

        if not slos:
            logger.warning("no_slos_found", service=service)
            return []

        logger.info(
            "collecting_service_budgets",
            service=service,
            slo_count=len(slos),
        )

        # Collect budget for each SLO
        budgets = []
        for slo in slos:
            try:
                budget = await self.collect_slo_budget(
                    slo,
                    period_end=period_end,
                    period_start=period_start,
                )
                budgets.append(budget)
            except PrometheusProviderError as exc:
                logger.error(
                    "failed_to_collect_slo",
                    slo_id=slo.id,
                    error=str(exc),
                )
                # Continue with other SLOs

        return budgets

    async def _store_measurement_history(
        self,
        slo: SLO,
        measurements: list[dict[str, Any]],
    ) -> None:
        """
        Store SLI measurement history (optional).

        This stores individual measurements for historical tracking.
        Can be used later for trend analysis.
        """
        # For now, we'll skip storing every measurement to keep it simple
        # In production, you might want to downsample or store aggregates
        pass


async def collect_and_store_budget(
    slo_id: str,
    prometheus_url: str,
    repository: SLORepository,
) -> ErrorBudget:
    """
    Convenience function to collect budget for a single SLO.

    Args:
        slo_id: SLO identifier
        prometheus_url: Prometheus server URL
        repository: SLO repository

    Returns:
        Calculated error budget

    Raises:
        ValueError: If SLO not found
        PrometheusProviderError: If metrics collection fails
    """
    # Get SLO from database
    slo = await repository.get_slo(slo_id)
    if slo is None:
        raise ValueError(f"SLO not found: {slo_id}")

    # Create Prometheus provider
    prometheus = PrometheusProvider(prometheus_url)

    # Create collector and collect
    collector = SLOCollector(prometheus, repository)
    budget = await collector.collect_slo_budget(slo)

    return budget


async def collect_service_budgets(
    service: str,
    prometheus_url: str,
    repository: SLORepository,
) -> list[ErrorBudget]:
    """
    Convenience function to collect budgets for all SLOs of a service.

    Args:
        service: Service name
        prometheus_url: Prometheus server URL
        repository: SLO repository

    Returns:
        List of calculated error budgets
    """
    # Create Prometheus provider
    prometheus = PrometheusProvider(prometheus_url)

    # Create collector and collect
    collector = SLOCollector(prometheus, repository)
    budgets = await collector.collect_service_budgets(service)

    return budgets


# ---------------------------------------------------------------------------
# Stateless CLI metric collection (for deployment gate checks)
# ---------------------------------------------------------------------------


@dataclass
class SLOResult:
    """Result of collecting metrics for a single SLO (stateless CLI use)."""

    name: str
    objective: float
    window: str
    total_budget_minutes: float
    current_sli: float | None = None
    burned_minutes: float | None = None
    percent_consumed: float | None = None
    status: str = "UNKNOWN"
    error: str | None = None


@dataclass
class BudgetSummary:
    """Aggregate budget summary across all SLOs."""

    total_budget_minutes: float
    burned_budget_minutes: float
    remaining_percent: float
    consumed_percent: float
    valid_slo_count: int


class SLOMetricCollector:
    """Stateless SLO metric collector for CLI deployment gate checks."""

    def __init__(self, prometheus_url: str | None = None):
        """Initialize collector with Prometheus connection details."""
        self.prometheus_url = prometheus_url
        self._username = os.environ.get("PROMETHEUS_USERNAME") or os.environ.get(
            "NTHLAYER_METRICS_USER"
        )
        self._password = os.environ.get("PROMETHEUS_PASSWORD") or os.environ.get(
            "NTHLAYER_METRICS_PASSWORD"
        )

    async def collect(self, slo_resources: list[Any], service_name: str) -> list[SLOResult]:
        """Collect SLO metrics from Prometheus (stateless)."""
        if not self.prometheus_url:
            raise ValueError("Prometheus URL is required for metric collection")

        provider = PrometheusProvider(
            self.prometheus_url, username=self._username, password=self._password
        )
        results = []

        for slo in slo_resources:
            result = await self._collect_single_slo(slo, service_name, provider)
            results.append(result)

        return results

    async def _collect_single_slo(
        self, slo: Any, service_name: str, provider: PrometheusProvider
    ) -> SLOResult:
        """Collect metrics for a single SLO."""
        spec = slo.spec or {}
        objective = spec.get("objective", 99.9)
        window = spec.get("window", "30d")
        indicator = spec.get("indicator", {})

        window_minutes = self._parse_window_minutes(window)
        error_budget_percent = (100 - objective) / 100
        total_budget_minutes = window_minutes * error_budget_percent

        result = SLOResult(
            name=slo.name,
            objective=objective,
            window=window,
            total_budget_minutes=total_budget_minutes,
        )

        query = self._build_slo_query(spec, indicator, service_name)

        if query is None:
            indicators = spec.get("indicators", [])
            if indicators and indicators[0].get("latency_query"):
                result.error = "Latency SLOs not yet supported for gating"
                result.status = "NO_DATA"
            else:
                result.error = "No query defined"
                result.status = "NO_DATA"
            return result

        try:
            sli_value = await provider.get_sli_value(query)

            if sli_value > 0:
                result.current_sli = sli_value * 100
                error_rate = 1.0 - sli_value
                result.burned_minutes = window_minutes * error_rate
                result.percent_consumed = (
                    (result.burned_minutes / total_budget_minutes) * 100
                    if total_budget_minutes > 0
                    else 0
                )
                result.status = self._determine_status(result.percent_consumed)
            else:
                result.error = "No data returned"
                result.status = "NO_DATA"

        except PrometheusProviderError as e:
            result.error = str(e)
            result.status = "ERROR"

        return result

    def _build_slo_query(
        self, spec: dict[str, Any], indicator: dict[str, Any], service_name: str
    ) -> str | None:
        """Build PromQL query from SLO specification."""
        query = indicator.get("query")

        if not query:
            indicators = spec.get("indicators", [])
            if indicators:
                ind = indicators[0]
                if ind.get("success_ratio"):
                    sr = ind["success_ratio"]
                    total_query = sr.get("total_query")
                    good_query = sr.get("good_query")
                    if total_query and good_query:
                        query = f"({good_query}) / ({total_query})"

        if query:
            query = query.replace("${service}", service_name)
            query = query.replace("$service", service_name)

        return query

    def _determine_status(self, percent_consumed: float) -> str:
        """Determine SLO status based on budget consumption."""
        if percent_consumed >= 100:
            return "EXHAUSTED"
        elif percent_consumed >= 80:
            return "CRITICAL"
        elif percent_consumed >= 50:
            return "WARNING"
        return "HEALTHY"

    def _parse_window_minutes(self, window: str) -> float:
        """Parse window string like '30d' into minutes."""
        if window.endswith("d"):
            days = int(window[:-1])
            return days * 24 * 60
        elif window.endswith("h"):
            hours = int(window[:-1])
            return hours * 60
        elif window.endswith("w"):
            weeks = int(window[:-1])
            return weeks * 7 * 24 * 60
        return 30 * 24 * 60  # Default 30 days

    def calculate_aggregate_budget(self, results: list[SLOResult]) -> BudgetSummary:
        """Calculate aggregate budget across all SLOs."""
        valid_results = [r for r in results if r.burned_minutes is not None]

        if not valid_results:
            return BudgetSummary(
                total_budget_minutes=0,
                burned_budget_minutes=0,
                remaining_percent=100,
                consumed_percent=0,
                valid_slo_count=0,
            )

        total_budget = sum(r.total_budget_minutes for r in valid_results)
        burned_budget = sum(r.burned_minutes or 0 for r in valid_results)

        remaining_pct = (
            (total_budget - burned_budget) / total_budget * 100 if total_budget > 0 else 100
        )

        return BudgetSummary(
            total_budget_minutes=total_budget,
            burned_budget_minutes=burned_budget,
            remaining_percent=remaining_pct,
            consumed_percent=100 - remaining_pct,
            valid_slo_count=len(valid_results),
        )
