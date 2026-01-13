"""Builder for generating Prometheus recording rules from SLO specifications."""

from typing import List

from nthlayer.recording_rules.models import RecordingRule, RecordingRuleGroup
from nthlayer.specs.models import Resource, ServiceContext


class RecordingRuleBuilder:
    """Builds Prometheus recording rules from service specifications.

    Recording rules pre-compute expensive SLO calculations to improve
    dashboard and alert performance.
    """

    def __init__(self, service_context: ServiceContext, resources: List[Resource]):
        """Initialize builder with service context and resources.

        Args:
            service_context: Service metadata (name, team, tier, etc.)
            resources: List of resources (SLOs, etc.)
        """
        self.context = service_context
        self.resources = resources
        self.slo_resources = [r for r in resources if r.kind == "SLO"]

    def build(self) -> List[RecordingRuleGroup]:
        """Build recording rule groups.

        Returns:
            List of RecordingRuleGroup objects
        """
        groups = []

        if self.slo_resources:
            # Create SLO recording rules group
            slo_group = RecordingRuleGroup(name=f"{self.context.name}_slo_metrics", interval="30s")

            # Add rules for each SLO
            for slo in self.slo_resources:
                rules = self._build_slo_rules(slo)
                for rule in rules:
                    slo_group.add_rule(rule)

            if slo_group.rules:
                groups.append(slo_group)

        # Create service health metrics group
        health_group = self._build_health_rules()
        if health_group.rules:
            groups.append(health_group)

        return groups

    def _build_slo_rules(self, slo: Resource) -> List[RecordingRule]:
        """Build recording rules for a specific SLO.

        Args:
            slo: SLO resource

        Returns:
            List of RecordingRule objects
        """
        rules: List[RecordingRule] = []
        slo_name = slo.name or "slo"
        slo_spec = slo.spec
        service = self.context.name

        # Determine SLO type and create appropriate rules
        if "availability" in slo_name.lower():
            rules.extend(self._build_availability_rules(service, slo_name, slo_spec))
        elif "latency" in slo_name.lower():
            rules.extend(self._build_latency_rules(service, slo_name, slo_spec))
        elif "error" in slo_name.lower() or "success" in slo_name.lower():
            rules.extend(self._build_error_rate_rules(service, slo_name, slo_spec))

        return rules

    def _build_availability_rules(
        self, service: str, slo_name: str, spec: dict
    ) -> List[RecordingRule]:
        """Build recording rules for availability SLO.

        Precomputes:
        - Total requests
        - Successful requests (non-5xx)
        - Availability percentage
        - Error budget
        """
        objective = spec.get("objective", 99.9)
        window = spec.get("window", "30d")

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

    def _build_latency_rules(self, service: str, slo_name: str, spec: dict) -> List[RecordingRule]:
        """Build recording rules for latency SLO.

        Precomputes:
        - Request count
        - Requests under threshold
        - Latency SLO percentage
        - p50, p95, p99 latencies
        """
        objective = spec.get("objective", 99.0)
        threshold_ms = spec.get("latency_threshold", 500)
        threshold_sec = threshold_ms / 1000
        window = spec.get("window", "30d")

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

        # Latency SLO compliance (percentage under threshold)
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

        # Precompute percentiles for dashboards
        for quantile in [0.50, 0.95, 0.99]:
            rules.append(
                RecordingRule(
                    record=f"slo:http_request_duration_seconds:p{int(quantile*100)}",
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
        self, service: str, slo_name: str, spec: dict
    ) -> List[RecordingRule]:
        """Build recording rules for error rate SLO.

        Precomputes:
        - Total requests
        - Error requests
        - Error rate percentage
        """
        objective = spec.get("objective", 99.9)
        window = spec.get("window", "30d")

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

    def _build_health_rules(self) -> RecordingRuleGroup:
        """Build recording rules for general service health metrics.

        Returns:
            RecordingRuleGroup with health metrics
        """
        service = self.context.name

        group = RecordingRuleGroup(name=f"{service}_health_metrics", interval="30s")

        # Request rate (requests per second)
        group.add_rule(
            RecordingRule(
                record="service:http_requests:rate5m",
                expr=f'sum(rate(http_requests_total{{service="{service}"}}[5m]))',
                labels={"service": service},
            )
        )

        # Error rate (percentage)
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

        # P95 latency
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

        # P99 latency
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


def build_recording_rules(
    service_context: ServiceContext, resources: List[Resource]
) -> List[RecordingRuleGroup]:
    """Convenience function to build recording rules.

    Args:
        service_context: Service metadata
        resources: List of resources (SLOs, etc.)

    Returns:
        List of RecordingRuleGroup objects

    Example:
        >>> from nthlayer.specs.parser import parse_service_file
        >>> context, resources = parse_service_file("payment-api.yaml")
        >>> groups = build_recording_rules(context, resources)
        >>> yaml_output = create_rule_groups(groups)
    """
    builder = RecordingRuleBuilder(service_context, resources)
    return builder.build()
