"""
Contract Verification module for NthLayer.

Verifies that declared metrics in service.yaml actually exist in a target
Prometheus instance before promoting to production.

This implements the "Contract Verification" pattern:
- Generation is static (Shift Left)
- Verification is runtime (before promotion)
"""

from .extractor import extract_metric_contract
from .models import MetricContract, MetricSource, VerificationResult
from .verifier import MetricVerifier

__all__ = [
    "MetricContract",
    "MetricSource",
    "VerificationResult",
    "MetricVerifier",
    "extract_metric_contract",
]
