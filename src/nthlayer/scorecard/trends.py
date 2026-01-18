"""
Score trend analysis.

Analyzes reliability score trends over time.
MVP: Stub implementation for future historical data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TrendData:
    """Historical score data point."""

    timestamp: datetime
    score: float
    components: dict[str, float]


class TrendAnalyzer:
    """Analyzes score trends over time."""

    def __init__(self, prometheus_url: str | None = None):
        """
        Initialize trend analyzer.

        Args:
            prometheus_url: Optional Prometheus URL for historical queries
        """
        self.prometheus_url = prometheus_url
        self._score_cache: dict[str, list[TrendData]] = {}

    def get_historical_score(
        self,
        service: str,
        days_ago: int,
    ) -> float | None:
        """
        Get historical score from N days ago.

        For MVP, this returns None (no historical data).
        Future: Query Prometheus for historical SLO compliance.

        Args:
            service: Service name
            days_ago: Number of days in the past

        Returns:
            Historical score or None if not available
        """
        # MVP: No historical data stored yet
        # Future implementation will query Prometheus or a time-series store
        return None

    def calculate_trend_direction(
        self,
        current_score: float,
        previous_score: float | None,
        threshold: float = 5.0,
    ) -> str:
        """
        Determine trend direction.

        Args:
            current_score: Current score
            previous_score: Score from previous period
            threshold: Minimum change to count as improving/degrading

        Returns:
            "improving", "degrading", or "stable"
        """
        if previous_score is None:
            return "stable"

        delta = current_score - previous_score

        if delta >= threshold:
            return "improving"
        elif delta <= -threshold:
            return "degrading"
        else:
            return "stable"

    def get_trend_symbol(self, direction: str) -> str:
        """
        Get symbol for trend direction.

        Args:
            direction: Trend direction

        Returns:
            Unicode symbol
        """
        symbols = {
            "improving": "\u2191",  # ↑
            "degrading": "\u2193",  # ↓
            "stable": "\u2192",  # →
        }
        return symbols.get(direction, "-")
