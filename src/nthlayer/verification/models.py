"""
Models for contract verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class MetricSource(Enum):
    """Source of a declared metric in service.yaml."""

    SLO_INDICATOR = "slo_indicator"  # From SLO indicator queries (critical)
    OBSERVABILITY = "observability"  # From Observability.metrics (optional)
    ALERT = "alert"  # From alert rules (critical)


@dataclass
class DeclaredMetric:
    """A metric declared in service.yaml."""

    name: str
    source: MetricSource
    query: Optional[str] = None  # Original query if from SLO
    resource_name: Optional[str] = None  # e.g., "availability", "latency-p99"

    @property
    def is_critical(self) -> bool:
        """SLO and alert metrics are critical for service reliability."""
        return self.source in (MetricSource.SLO_INDICATOR, MetricSource.ALERT)


@dataclass
class MetricContract:
    """
    The metric contract for a service.

    Contains all metrics that the service declares it will emit,
    extracted from service.yaml.
    """

    service_name: str
    metrics: List[DeclaredMetric] = field(default_factory=list)

    @property
    def critical_metrics(self) -> List[DeclaredMetric]:
        """Metrics that must exist (SLO indicators, alerts)."""
        return [m for m in self.metrics if m.is_critical]

    @property
    def optional_metrics(self) -> List[DeclaredMetric]:
        """Metrics that are nice to have (observability)."""
        return [m for m in self.metrics if not m.is_critical]

    @property
    def unique_metric_names(self) -> set[str]:
        """Unique metric names in the contract."""
        return {m.name for m in self.metrics}


@dataclass
class VerificationResult:
    """Result of verifying a single metric."""

    metric: DeclaredMetric
    exists: bool
    error: Optional[str] = None  # Error message if verification failed
    sample_labels: Optional[dict] = None  # Sample labels if metric exists

    @property
    def is_critical_failure(self) -> bool:
        """True if a critical metric is missing."""
        return not self.exists and self.metric.is_critical


@dataclass
class ContractVerificationResult:
    """Result of verifying the entire metric contract."""

    service_name: str
    target_url: str
    results: List[VerificationResult] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        """True if all metrics exist."""
        return all(r.exists for r in self.results)

    @property
    def critical_verified(self) -> bool:
        """True if all critical metrics exist."""
        return all(r.exists for r in self.results if r.metric.is_critical)

    @property
    def missing_critical(self) -> List[VerificationResult]:
        """Critical metrics that are missing."""
        return [r for r in self.results if r.is_critical_failure]

    @property
    def missing_optional(self) -> List[VerificationResult]:
        """Optional metrics that are missing."""
        return [r for r in self.results if not r.exists and not r.metric.is_critical]

    @property
    def verified_count(self) -> int:
        """Number of metrics that exist."""
        return sum(1 for r in self.results if r.exists)

    @property
    def exit_code(self) -> int:
        """
        Exit code for CI/CD pipelines.

        0 = All verified
        1 = Optional metrics missing (warning)
        2 = Critical metrics missing (block)
        """
        if self.missing_critical:
            return 2
        if self.missing_optional:
            return 1
        return 0
