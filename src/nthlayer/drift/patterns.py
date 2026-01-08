"""
Pattern detection for drift analysis.

Classifies drift patterns beyond simple linear trends:
- Gradual decline/improvement
- Step changes (sudden drops or improvements)
- Volatile patterns
- Stable (no significant trend)
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from nthlayer.drift.models import DriftPattern


class PatternDetector:
    """Detect drift patterns beyond simple linear trends."""

    def __init__(
        self,
        step_change_threshold: float = 0.05,
        volatility_variance_threshold: float = 0.01,
        volatility_r_squared_threshold: float = 0.3,
        slope_significance_threshold: float = 0.001,
    ):
        """Initialize pattern detector.

        Args:
            step_change_threshold: Minimum change to consider a step change (default 5%)
            volatility_variance_threshold: Variance threshold for volatile classification
            volatility_r_squared_threshold: R² below this with high variance = volatile
            slope_significance_threshold: Weekly slope below this is considered stable
        """
        self.step_change_threshold = step_change_threshold
        self.volatility_variance_threshold = volatility_variance_threshold
        self.volatility_r_squared_threshold = volatility_r_squared_threshold
        self.slope_significance_threshold = slope_significance_threshold

    def detect(
        self,
        data: list[tuple[datetime, float]],
        slope_per_second: float,
        r_squared: float,
    ) -> DriftPattern:
        """Classify the drift pattern.

        Args:
            data: Time series data as (timestamp, value) tuples
            slope_per_second: Linear regression slope (change per second)
            r_squared: Fit quality from regression (0-1)

        Returns:
            Classified DriftPattern
        """
        if len(data) < 2:
            return DriftPattern.STABLE

        values = np.array([d[1] for d in data])
        variance = float(np.var(values))

        # Check for step change first (highest priority)
        step_change = self._detect_step_change(data)
        if step_change is not None:
            return step_change

        # High variance + low r_squared = volatile
        if (
            r_squared < self.volatility_r_squared_threshold
            and variance > self.volatility_variance_threshold
        ):
            return DriftPattern.VOLATILE

        # Classify by slope direction and significance
        # Convert slope from per-second to per-week
        seconds_per_week = 7 * 24 * 60 * 60
        weekly_slope = slope_per_second * seconds_per_week

        if abs(weekly_slope) < self.slope_significance_threshold:
            return DriftPattern.STABLE
        elif weekly_slope < 0:
            return DriftPattern.GRADUAL_DECLINE
        else:
            return DriftPattern.GRADUAL_IMPROVEMENT

    def _detect_step_change(
        self,
        data: list[tuple[datetime, float]],
    ) -> DriftPattern | None:
        """Detect sudden step changes in the data.

        Looks for changes exceeding the threshold within a ~24-hour window.

        Args:
            data: Time series data

        Returns:
            STEP_CHANGE_DOWN, STEP_CHANGE_UP, or None
        """
        if len(data) < 2:
            return None

        max_time_window = 86400 * 1.5  # 1.5 days tolerance

        for i in range(1, len(data)):
            time_diff = (data[i][0] - data[i - 1][0]).total_seconds()
            value_diff = data[i][1] - data[i - 1][1]

            # Check if change exceeds threshold within time window
            if time_diff < max_time_window:
                if value_diff < -self.step_change_threshold:
                    return DriftPattern.STEP_CHANGE_DOWN
                elif value_diff > self.step_change_threshold:
                    return DriftPattern.STEP_CHANGE_UP

        return None

    def detect_seasonal(
        self,
        data: list[tuple[datetime, float]],
        min_periods: int = 2,
    ) -> bool:
        """Detect seasonal patterns in the data.

        This is a simple detection that looks for weekly patterns.
        Requires at least 2 full periods (14 days) of data.

        Args:
            data: Time series data
            min_periods: Minimum number of periods to detect seasonality

        Returns:
            True if seasonal pattern detected
        """
        if len(data) < min_periods * 7 * 24:  # Assuming hourly data
            return False

        # Group values by day of week
        day_values: dict[int, list[float]] = {i: [] for i in range(7)}
        for timestamp, value in data:
            day_of_week = timestamp.weekday()
            day_values[day_of_week].append(value)

        # Check if there's significant variance between days
        day_means = np.array([float(np.mean(v)) if v else 0.0 for v in day_values.values()])
        if len(day_means) == 0:
            return False

        # If variance between day means is significantly higher than
        # within-day variance, we have a weekly pattern
        between_day_var = float(np.var(day_means))
        within_day_vars = np.array(
            [float(np.var(v)) if len(v) > 1 else 0.0 for v in day_values.values()]
        )
        avg_within_day_var = float(np.mean(within_day_vars))

        # Seasonal if between-day variance is at least 2x within-day
        return bool(between_day_var > 2 * avg_within_day_var)
