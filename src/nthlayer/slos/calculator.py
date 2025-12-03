"""
Error budget calculator.

Calculates error budget consumption from SLI measurements.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from nthlayer.slos.models import SLO, ErrorBudget, SLOStatus


class ErrorBudgetCalculator:
    """Calculator for error budget consumption."""

    def __init__(self, slo: SLO) -> None:
        self.slo = slo

    def calculate_budget(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        sli_measurements: list[dict[str, Any]] | None = None,
    ) -> ErrorBudget:
        """
        Calculate error budget for a time period.
        
        Args:
            period_start: Start of evaluation period (defaults to now - time_window)
            period_end: End of evaluation period (defaults to now)
            sli_measurements: List of SLI measurements with timestamp and value
            
        Returns:
            ErrorBudget with consumption details
        """
        # Set default period
        if period_end is None:
            period_end = datetime.utcnow()
        
        if period_start is None:
            period_start = self.slo.time_window.get_start_time(period_end)
        
        # Calculate total budget
        total_minutes = self.slo.error_budget_minutes()
        
        # Calculate burned budget from measurements
        burned_minutes = 0.0
        if sli_measurements:
            burned_minutes = self._calculate_burn_from_measurements(
                sli_measurements,
                period_start,
                period_end,
            )
        
        # Create budget object
        remaining_minutes = max(0.0, total_minutes - burned_minutes)
        
        budget = ErrorBudget(
            slo_id=self.slo.id,
            service=self.slo.service,
            period_start=period_start,
            period_end=period_end,
            total_budget_minutes=total_minutes,
            burned_minutes=burned_minutes,
            remaining_minutes=remaining_minutes,
        )
        
        # Determine status
        budget.status = budget.calculate_status()
        
        return budget

    def _calculate_burn_from_measurements(
        self,
        measurements: list[dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> float:
        """
        Calculate budget burn from SLI measurements.
        
        Assumes measurements have:
        - timestamp: datetime
        - sli_value: float (0.0-1.0, where 1.0 = 100% good)
        - duration_seconds: float (optional, defaults to interval between measurements)
        """
        if not measurements:
            return 0.0
        
        # Sort by timestamp
        measurements = sorted(measurements, key=lambda m: m["timestamp"])
        
        total_burn_minutes = 0.0
        
        for i, measurement in enumerate(measurements):
            timestamp = measurement["timestamp"]
            sli_value = measurement["sli_value"]
            
            # Skip measurements outside period
            if timestamp < period_start or timestamp > period_end:
                continue
            
            # Calculate duration for this measurement
            if "duration_seconds" in measurement:
                duration_seconds = measurement["duration_seconds"]
            elif i < len(measurements) - 1:
                # Use time until next measurement
                next_timestamp = measurements[i + 1]["timestamp"]
                duration_seconds = (next_timestamp - timestamp).total_seconds()
            else:
                # Last measurement: assume 5 minute interval
                duration_seconds = 300
            
            # Calculate error rate (1.0 - sli_value)
            error_rate = max(0.0, 1.0 - sli_value)
            
            # Budget burn = error_rate × duration
            duration_minutes = duration_seconds / 60
            burn_minutes = error_rate * duration_minutes
            
            total_burn_minutes += burn_minutes
        
        return total_burn_minutes

    def calculate_burn_rate(
        self,
        current_burn_minutes: float,
        period_start: datetime,
        period_end: datetime | None = None,
    ) -> float:
        """
        Calculate current burn rate as a multiplier of baseline.
        
        Burn rate of 1.0 means burning budget at expected rate.
        Burn rate > 1.0 means burning faster than expected (alert!)
        
        Args:
            current_burn_minutes: Total minutes burned so far
            period_start: Start of period
            period_end: End of period (defaults to now)
            
        Returns:
            Burn rate multiplier (e.g., 2.0 = burning 2x faster)
        """
        if period_end is None:
            period_end = datetime.utcnow()
        
        # Calculate how much time has elapsed
        elapsed = period_end - period_start
        elapsed_fraction = elapsed / self.slo.time_window.to_timedelta()
        
        if elapsed_fraction <= 0:
            return 0.0
        
        # Calculate expected burn at this point
        total_budget = self.slo.error_budget_minutes()
        expected_burn = total_budget * elapsed_fraction
        
        if expected_burn <= 0:
            return 0.0
        
        # Burn rate = actual / expected
        burn_rate = current_burn_minutes / expected_burn
        
        return burn_rate

    def project_budget_exhaustion(
        self,
        current_burn_minutes: float,
        period_start: datetime,
    ) -> datetime | None:
        """
        Project when error budget will be exhausted at current burn rate.
        
        Args:
            current_burn_minutes: Total minutes burned so far
            period_start: Start of period
            
        Returns:
            Projected exhaustion time, or None if budget won't be exhausted
        """
        total_budget = self.slo.error_budget_minutes()
        remaining_budget = total_budget - current_burn_minutes
        
        if remaining_budget <= 0:
            # Already exhausted
            return datetime.utcnow()
        
        # Calculate current burn rate
        now = datetime.utcnow()
        elapsed = now - period_start
        elapsed_seconds = elapsed.total_seconds()
        
        if elapsed_seconds <= 0 or current_burn_minutes <= 0:
            return None
        
        # Minutes per second currently
        burn_rate_per_second = current_burn_minutes / elapsed_seconds
        
        if burn_rate_per_second <= 0:
            return None
        
        # Seconds until exhaustion
        seconds_until_exhaustion = remaining_budget / burn_rate_per_second
        
        # Projected time
        exhaustion_time = now + timedelta(seconds=seconds_until_exhaustion)
        
        return exhaustion_time

    def should_alert(
        self,
        budget: ErrorBudget,
        threshold_percent: float = 75.0,
        burn_rate_threshold: float = 2.0,
    ) -> tuple[bool, str]:
        """
        Determine if an alert should be sent.
        
        Args:
            budget: Current error budget
            threshold_percent: Alert if consumed % exceeds this
            burn_rate_threshold: Alert if burn rate exceeds this
            
        Returns:
            (should_alert, reason)
        """
        # Check budget consumption
        if budget.percent_consumed >= threshold_percent:
            return (
                True,
                f"Error budget {budget.percent_consumed:.1f}% consumed (threshold: {threshold_percent}%)"
            )
        
        # Check burn rate
        burn_rate = self.calculate_burn_rate(
            budget.burned_minutes,
            budget.period_start,
            budget.period_end,
        )
        
        if burn_rate >= burn_rate_threshold:
            return (
                True,
                f"Burn rate {burn_rate:.1f}x baseline (threshold: {burn_rate_threshold}x)"
            )
        
        return (False, "")

    def format_budget_status(self, budget: ErrorBudget) -> str:
        """
        Format error budget status for display.
        
        Returns:
            Formatted string with budget details
        """
        status_emoji = {
            SLOStatus.HEALTHY: "✅",
            SLOStatus.WARNING: "⚠️ ",
            SLOStatus.CRITICAL: "🚨",
            SLOStatus.EXHAUSTED: "❌",
        }
        
        emoji = status_emoji.get(budget.status, "❓")
        
        lines = [
            f"Error Budget Status: {budget.service}",
            "━" * 60,
            f"SLO: {self.slo.name}",
            f"Target: {self.slo.target * 100:.2f}%",
            f"Period: {self.slo.time_window.duration} ({self.slo.time_window.type.value})",
            "",
            "Budget:",
            f"  Total: {budget.total_budget_minutes:.1f} minutes",
            f"  Burned: {budget.burned_minutes:.1f} minutes ({budget.percent_consumed:.1f}%)",
            f"  Remaining: {budget.remaining_minutes:.1f} minutes ({budget.percent_remaining:.1f}%)",
            f"  Status: {emoji} {budget.status.value.upper()}",
            "",
            "Burn Sources:",
            f"  Incidents: {budget.incident_burn_minutes:.1f} min",
            f"  Deployments: {budget.deployment_burn_minutes:.1f} min",
            f"  SLO Breaches: {budget.slo_breach_burn_minutes:.1f} min",
        ]
        
        # Add burn rate if available
        if budget.burn_rate > 0:
            lines.append("")
            lines.append(f"Burn Rate: {budget.burn_rate:.2f}x baseline")
            
            if budget.burn_rate > 1.0:
                exhaustion = self.project_budget_exhaustion(
                    budget.burned_minutes,
                    budget.period_start,
                )
                if exhaustion:
                    lines.append(f"Projected Exhaustion: {exhaustion.strftime('%Y-%m-%d %H:%M UTC')}")
        
        return "\n".join(lines)
