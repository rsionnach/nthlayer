"""Builder for generating Prometheus recording rules from ReliabilityManifest.

This module provides recording rule generation for:
- Standard SLOs (availability, latency, error_rate, throughput)
- AI Gate judgment SLOs (reversal_rate, high_confidence_failure, calibration, feedback_latency)

The generated metrics are compatible with Backstage plugins:
- SloCard expects: slo:error_budget_remaining:ratio{service="..."}
- JudgmentCard expects: ai_gate:reversal_rate:ratio{service="..."}
"""

from __future__ import annotations

from nthlayer.recording_rules.models import RecordingRule, RecordingRuleGroup
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition


class ManifestRecordingRuleBuilder:
    """Builds Prometheus recording rules from ReliabilityManifest.

    Supports both standard SLOs and AI gate judgment SLOs.
    """

    def __init__(self, manifest: ReliabilityManifest):
        """Initialize builder with manifest.

        Args:
            manifest: ReliabilityManifest instance
        """
        self.manifest = manifest

    def build(self) -> list[RecordingRuleGroup]:
        """Build recording rule groups.

        Returns:
            List of RecordingRuleGroup objects
        """
        groups = []

        # Standard SLO metrics
        standard_slos = self.manifest.get_standard_slos()
        if standard_slos:
            slo_group = RecordingRuleGroup(
                name=f"{self.manifest.name}_slo_metrics",
                interval="30s",
            )
            for slo in standard_slos:
                rules = self._build_standard_slo_rules(slo)
                for rule in rules:
                    slo_group.add_rule(rule)
            if slo_group.rules:
                groups.append(slo_group)

        # AI gate judgment SLO metrics
        if self.manifest.is_ai_gate():
            judgment_slos = self.manifest.get_judgment_slos()
            if judgment_slos:
                judgment_group = RecordingRuleGroup(
                    name=f"{self.manifest.name}_judgment_metrics",
                    interval="30s",
                )
                for slo in judgment_slos:
                    rules = self._build_judgment_slo_rules(slo)
                    for rule in rules:
                        judgment_group.add_rule(rule)
                if judgment_group.rules:
                    groups.append(judgment_group)

        # Service health metrics
        health_group = self._build_health_rules()
        if health_group.rules:
            groups.append(health_group)

        return groups

    def _build_standard_slo_rules(self, slo: SLODefinition) -> list[RecordingRule]:
        """Build recording rules for a standard SLO.

        Args:
            slo: SLO definition

        Returns:
            List of RecordingRule objects
        """
        rules: list[RecordingRule] = []
        service = self.manifest.name
        slo_name = slo.name

        # Determine SLO type by name or explicit type
        slo_type = slo.slo_type or slo.name

        if "availability" in slo_type.lower():
            rules.extend(self._build_availability_rules(service, slo_name, slo))
        elif "latency" in slo_type.lower():
            rules.extend(self._build_latency_rules(service, slo_name, slo))
        elif "error" in slo_type.lower():
            rules.extend(self._build_error_rate_rules(service, slo_name, slo))
        elif "throughput" in slo_type.lower():
            rules.extend(self._build_throughput_rules(service, slo_name, slo))

        return rules

    def _build_availability_rules(
        self, service: str, slo_name: str, slo: SLODefinition
    ) -> list[RecordingRule]:
        """Build recording rules for availability SLO."""
        objective = slo.target
        window = slo.window

        rules = []

        # Total requests over window
        rules.append(
            RecordingRule(
                record=f"slo:requests_total:{window}",
                expr=f'sum(increase(http_requests_total{{service="{service}"}}[{window}]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                },
            )
        )

        # Successful requests (non-5xx)
        rules.append(
            RecordingRule(
                record=f"slo:requests_success:{window}",
                expr=f'sum(increase(http_requests_total{{service="{service}",status!~"5.."}}[{window}]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                },
            )
        )

        # Availability percentage
        rules.append(
            RecordingRule(
                record="slo:availability:ratio",
                expr=(
                    f'slo:requests_success:{window}{{service="{service}",slo="{slo_name}"}} / '
                    f'slo:requests_total:{window}{{service="{service}",slo="{slo_name}"}}'
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "objective": str(objective),
                },
            )
        )

        # Error budget remaining (as ratio)
        rules.append(
            RecordingRule(
                record="slo:error_budget_remaining:ratio",
                expr=(
                    f'1 - ((1 - slo:availability:ratio{{service="{service}",slo="{slo_name}"}}) / '
                    f"(1 - {objective / 100}))"
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "objective": str(objective),
                },
            )
        )

        return rules

    def _build_latency_rules(
        self, service: str, slo_name: str, slo: SLODefinition
    ) -> list[RecordingRule]:
        """Build recording rules for latency SLO."""
        objective = slo.target  # Target percentage under threshold
        threshold_ms = slo.target if slo.unit == "ms" else 500
        threshold_sec = threshold_ms / 1000
        window = slo.window

        rules = []

        # Total requests
        rules.append(
            RecordingRule(
                record=f"slo:latency_requests_total:{window}",
                expr=f'sum(increase(http_request_duration_seconds_count{{service="{service}"}}[{window}]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                },
            )
        )

        # Requests under threshold
        rules.append(
            RecordingRule(
                record=f"slo:latency_requests_fast:{window}",
                expr=(
                    f'sum(increase(http_request_duration_seconds_bucket{{service="{service}",'
                    f'le="{threshold_sec}"}}[{window}]))'
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "threshold": f"{threshold_ms}ms",
                },
            )
        )

        # Latency SLO compliance
        rules.append(
            RecordingRule(
                record="slo:latency:ratio",
                expr=(
                    f'slo:latency_requests_fast:{window}{{service="{service}",slo="{slo_name}"}} / '
                    f'slo:latency_requests_total:{window}{{service="{service}",slo="{slo_name}"}}'
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "objective": str(objective),
                },
            )
        )

        # Percentiles for dashboards
        for quantile in [0.50, 0.95, 0.99]:
            rules.append(
                RecordingRule(
                    record=f"slo:http_request_duration_seconds:p{int(quantile * 100)}",
                    expr=(
                        f"histogram_quantile({quantile}, "
                        f'rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))'
                    ),
                    labels={
                        "service": service,
                        "slo": slo_name,
                    },
                )
            )

        return rules

    def _build_error_rate_rules(
        self, service: str, slo_name: str, slo: SLODefinition
    ) -> list[RecordingRule]:
        """Build recording rules for error rate SLO."""
        objective = slo.target
        window = slo.window

        rules = []

        # Total requests
        rules.append(
            RecordingRule(
                record=f"slo:error_requests_total:{window}",
                expr=f'sum(increase(http_requests_total{{service="{service}"}}[{window}]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                },
            )
        )

        # Error requests (5xx)
        rules.append(
            RecordingRule(
                record=f"slo:error_requests_failed:{window}",
                expr=f'sum(increase(http_requests_total{{service="{service}",status=~"5.."}}[{window}]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                },
            )
        )

        # Error rate
        rules.append(
            RecordingRule(
                record="slo:error_rate:ratio",
                expr=(
                    f'slo:error_requests_failed:{window}{{service="{service}",slo="{slo_name}"}} / '
                    f'slo:error_requests_total:{window}{{service="{service}",slo="{slo_name}"}}'
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "objective": str(objective),
                },
            )
        )

        return rules

    def _build_throughput_rules(
        self, service: str, slo_name: str, slo: SLODefinition
    ) -> list[RecordingRule]:
        """Build recording rules for throughput SLO."""
        minimum_rps = slo.target
        window = slo.window

        rules = []

        # Current throughput (requests per second)
        rules.append(
            RecordingRule(
                record="slo:throughput:rate5m",
                expr=f'sum(rate(http_requests_total{{service="{service}"}}[5m]))',
                labels={
                    "service": service,
                    "slo": slo_name,
                    "minimum": str(minimum_rps),
                },
            )
        )

        # Throughput SLO compliance (1 if above minimum, 0 otherwise)
        rules.append(
            RecordingRule(
                record="slo:throughput:compliance",
                expr=(
                    f'(slo:throughput:rate5m{{service="{service}",slo="{slo_name}"}} >= {minimum_rps}) '
                    f"or vector(0)"
                ),
                labels={
                    "service": service,
                    "slo": slo_name,
                    "minimum": str(minimum_rps),
                },
            )
        )

        return rules

    def _build_judgment_slo_rules(self, slo: SLODefinition) -> list[RecordingRule]:
        """Build recording rules for AI gate judgment SLOs.

        These metrics are expected by Backstage JudgmentCard:
        - ai_gate:reversal_rate:ratio{service="..."}
        - ai_gate:high_confidence_failure:ratio{service="..."}
        - ai_gate:calibration:ece{service="..."}
        - ai_gate:feedback_latency:bucket{service="..."}
        """
        rules: list[RecordingRule] = []
        service = self.manifest.name
        slo_name = slo.name
        target = slo.target
        window = slo.window

        if slo_name == "reversal_rate":
            rules.extend(self._build_reversal_rate_rules(service, target, window))
        elif slo_name == "high_confidence_failure":
            rules.extend(self._build_high_confidence_failure_rules(service, target, window))
        elif slo_name == "calibration":
            rules.extend(self._build_calibration_rules(service, target, window))
        elif slo_name == "feedback_latency":
            rules.extend(self._build_feedback_latency_rules(service, target, window))

        return rules

    def _build_reversal_rate_rules(
        self, service: str, target: float, window: str
    ) -> list[RecordingRule]:
        """Build rules for reversal rate (human override tracking).

        Measures how often AI decisions are reversed by humans.
        Lower is better - indicates AI decisions are trusted.
        """
        rules = []

        # Total AI decisions
        rules.append(
            RecordingRule(
                record=f"ai_gate:decisions_total:{window}",
                expr=f'sum(increase(ai_gate_decisions_total{{service="{service}"}}[{window}]))',
                labels={"service": service},
            )
        )

        # Reversed decisions (human overrides)
        rules.append(
            RecordingRule(
                record=f"ai_gate:decisions_reversed:{window}",
                expr=f'sum(increase(ai_gate_decisions_total{{service="{service}",reversed="true"}}[{window}]))',
                labels={"service": service},
            )
        )

        # Reversal rate ratio
        rules.append(
            RecordingRule(
                record="ai_gate:reversal_rate:ratio",
                expr=(
                    f'ai_gate:decisions_reversed:{window}{{service="{service}"}} / '
                    f'ai_gate:decisions_total:{window}{{service="{service}"}}'
                ),
                labels={
                    "service": service,
                    "target": str(target),
                    "slo": "reversal_rate",
                },
            )
        )

        return rules

    def _build_high_confidence_failure_rules(
        self, service: str, target: float, window: str
    ) -> list[RecordingRule]:
        """Build rules for high confidence failure rate.

        Measures failures in decisions where the model was highly confident.
        Critical indicator of model reliability.
        """
        rules = []

        # High confidence decisions
        rules.append(
            RecordingRule(
                record=f"ai_gate:high_confidence_decisions:{window}",
                expr=(
                    f'sum(increase(ai_gate_decisions_total{{service="{service}",'
                    f'confidence_bucket="high"}}[{window}]))'
                ),
                labels={"service": service},
            )
        )

        # High confidence failures
        rules.append(
            RecordingRule(
                record=f"ai_gate:high_confidence_failures:{window}",
                expr=(
                    f'sum(increase(ai_gate_decisions_total{{service="{service}",'
                    f'confidence_bucket="high",outcome="incorrect"}}[{window}]))'
                ),
                labels={"service": service},
            )
        )

        # High confidence failure ratio
        rules.append(
            RecordingRule(
                record="ai_gate:high_confidence_failure:ratio",
                expr=(
                    f'ai_gate:high_confidence_failures:{window}{{service="{service}"}} / '
                    f'ai_gate:high_confidence_decisions:{window}{{service="{service}"}}'
                ),
                labels={
                    "service": service,
                    "target": str(target),
                    "slo": "high_confidence_failure",
                },
            )
        )

        return rules

    def _build_calibration_rules(
        self, service: str, target: float, window: str
    ) -> list[RecordingRule]:
        """Build rules for calibration (Expected Calibration Error).

        Measures how well confidence scores match actual accuracy.
        E.g., predictions at 80% confidence should be correct ~80% of the time.
        """
        rules = []

        # ECE (Expected Calibration Error) - typically computed externally
        # This creates a recording rule that aggregates pre-computed ECE
        rules.append(
            RecordingRule(
                record="ai_gate:calibration:ece",
                expr=(f'avg(ai_gate_calibration_error{{service="{service}"}})'),
                labels={
                    "service": service,
                    "target": str(target),
                    "slo": "calibration",
                },
            )
        )

        # Calibration by confidence bucket (for detailed analysis)
        for bucket in ["low", "medium", "high"]:
            rules.append(
                RecordingRule(
                    record=f"ai_gate:calibration_bucket:{bucket}",
                    expr=(
                        f'avg(ai_gate_calibration_error{{service="{service}",'
                        f'confidence_bucket="{bucket}"}})'
                    ),
                    labels={
                        "service": service,
                        "confidence_bucket": bucket,
                    },
                )
            )

        return rules

    def _build_feedback_latency_rules(
        self, service: str, target: float, window: str
    ) -> list[RecordingRule]:
        """Build rules for feedback latency (time to ground truth).

        Measures how long until we know if a decision was correct.
        Important for model improvement and trust building.
        """
        rules = []

        # Feedback latency histogram (for percentiles)
        for quantile in [0.50, 0.95, 0.99]:
            rules.append(
                RecordingRule(
                    record=f"ai_gate:feedback_latency:p{int(quantile * 100)}",
                    expr=(
                        f"histogram_quantile({quantile}, "
                        f'rate(ai_gate_feedback_latency_seconds_bucket{{service="{service}"}}[5m]))'
                    ),
                    labels={
                        "service": service,
                        "slo": "feedback_latency",
                    },
                )
            )

        # Feedback latency bucket recording (for Backstage JudgmentCard)
        # Records what percentage of feedback arrives within target time
        target_seconds = target
        rules.append(
            RecordingRule(
                record="ai_gate:feedback_latency:bucket",
                expr=(
                    f'sum(rate(ai_gate_feedback_latency_seconds_bucket{{service="{service}",'
                    f'le="{target_seconds}"}}[5m])) / '
                    f'sum(rate(ai_gate_feedback_latency_seconds_count{{service="{service}"}}[5m]))'
                ),
                labels={
                    "service": service,
                    "target": str(target),
                    "slo": "feedback_latency",
                },
            )
        )

        return rules

    def _build_health_rules(self) -> RecordingRuleGroup:
        """Build recording rules for general service health metrics."""
        service = self.manifest.name
        group = RecordingRuleGroup(name=f"{service}_health_metrics", interval="30s")

        # For AI gates, add AI-specific health metrics
        if self.manifest.is_ai_gate():
            # Decision rate
            group.add_rule(
                RecordingRule(
                    record="service:ai_gate_decisions:rate5m",
                    expr=f'sum(rate(ai_gate_decisions_total{{service="{service}"}}[5m]))',
                    labels={"service": service},
                )
            )

            # Average confidence
            group.add_rule(
                RecordingRule(
                    record="service:ai_gate_confidence:avg",
                    expr=f'avg(ai_gate_confidence_score{{service="{service}"}})',
                    labels={"service": service},
                )
            )

        # Standard HTTP metrics (applicable to all service types)
        group.add_rule(
            RecordingRule(
                record="service:http_requests:rate5m",
                expr=f'sum(rate(http_requests_total{{service="{service}"}}[5m]))',
                labels={"service": service},
            )
        )

        group.add_rule(
            RecordingRule(
                record="service:http_errors:rate5m",
                expr=(
                    f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])) / '
                    f'sum(rate(http_requests_total{{service="{service}"}}[5m]))'
                ),
                labels={"service": service},
            )
        )

        group.add_rule(
            RecordingRule(
                record="service:http_request_duration_seconds:p95",
                expr=(
                    f"histogram_quantile(0.95, "
                    f'rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))'
                ),
                labels={"service": service},
            )
        )

        group.add_rule(
            RecordingRule(
                record="service:http_request_duration_seconds:p99",
                expr=(
                    f"histogram_quantile(0.99, "
                    f'rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))'
                ),
                labels={"service": service},
            )
        )

        return group


def build_recording_rules_from_manifest(
    manifest: ReliabilityManifest,
) -> list[RecordingRuleGroup]:
    """Convenience function to build recording rules from manifest.

    Args:
        manifest: ReliabilityManifest instance

    Returns:
        List of RecordingRuleGroup objects

    Example:
        >>> from nthlayer.specs import load_manifest
        >>> manifest = load_manifest("payment-api.yaml")
        >>> groups = build_recording_rules_from_manifest(manifest)
        >>> yaml_output = create_rule_groups(groups)
    """
    builder = ManifestRecordingRuleBuilder(manifest)
    return builder.build()
