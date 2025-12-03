"""
SLO metrics collector.

Collects SLI metrics from Prometheus and calculates error budgets.
"""

from __future__ import annotations

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
