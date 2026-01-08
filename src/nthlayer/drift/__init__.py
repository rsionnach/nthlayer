"""
NthLayer Drift Detection Module.

Detects SLO reliability drift by analyzing error budget trends over time.
Identifies patterns (gradual decline, step changes, volatility) and projects
future budget exhaustion.

Example usage:
    from nthlayer.drift import DriftAnalyzer, DriftSeverity

    analyzer = DriftAnalyzer(prometheus_url="http://prometheus:9090")
    result = await analyzer.analyze(
        service_name="payment-api",
        tier="critical",
        slo="availability",
        window="30d",
    )

    if result.severity == DriftSeverity.CRITICAL:
        print(f"Critical drift detected: {result.summary}")
"""

from nthlayer.drift.analyzer import DriftAnalysisError, DriftAnalyzer
from nthlayer.drift.models import (
    DRIFT_DEFAULTS,
    DriftMetrics,
    DriftPattern,
    DriftProjection,
    DriftResult,
    DriftSeverity,
    get_drift_defaults,
)
from nthlayer.drift.patterns import PatternDetector

__all__ = [
    # Main analyzer
    "DriftAnalyzer",
    "DriftAnalysisError",
    # Data models
    "DriftResult",
    "DriftMetrics",
    "DriftProjection",
    "DriftSeverity",
    "DriftPattern",
    # Pattern detection
    "PatternDetector",
    # Configuration
    "DRIFT_DEFAULTS",
    "get_drift_defaults",
]
