"""
API Gateway service type metric template.

For API gateways, reverse proxies, and load balancers.
Extends the API template with upstream/client metrics.
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)
from nthlayer.metrics.standards.otel_semconv import (
    HTTP_CLIENT_REQUEST_DURATION,
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    SERVER_ADDRESS,
)

GATEWAY_TEMPLATE = ServiceTypeTemplate(
    name="gateway",
    extends="api",  # Inherits all API metrics
    required=[
        # Gateway-specific: upstream request duration
        MetricDefinition(
            name=HTTP_CLIENT_REQUEST_DURATION,
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of upstream/backend requests",
            attributes=[
                AttributeDefinition(
                    name=HTTP_REQUEST_METHOD,
                    required=True,
                    examples=["GET", "POST", "PUT", "DELETE"],
                ),
                AttributeDefinition(
                    name=HTTP_RESPONSE_STATUS_CODE,
                    type="int",
                    required=True,
                ),
                AttributeDefinition(
                    name=SERVER_ADDRESS,
                    required=True,
                    examples=["payment-api", "user-service", "10.0.0.5"],
                ),
                AttributeDefinition(
                    name="server.port",
                    type="int",
                    examples=["80", "443", "8080"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["upstream_latency"],
            buckets=[
                0.005,
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1.0,
                2.5,
                5.0,
                7.5,
                10.0,
            ],
        ),
    ],
    recommended=[
        MetricDefinition(
            name="gateway.upstream.health",
            type=MetricType.GAUGE,
            unit="{status}",
            description="Health status of upstream services (1=healthy, 0=unhealthy)",
            attributes=[
                AttributeDefinition(
                    name=SERVER_ADDRESS,
                    required=True,
                ),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="gateway.circuit_breaker.state",
            type=MetricType.GAUGE,
            unit="{state}",
            description="Circuit breaker state (0=closed, 1=open, 2=half-open)",
            attributes=[
                AttributeDefinition(
                    name=SERVER_ADDRESS,
                    required=True,
                ),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="gateway.retry.total",
            type=MetricType.COUNTER,
            unit="{retry}",
            description="Number of upstream request retries",
            attributes=[
                AttributeDefinition(name=SERVER_ADDRESS),
                AttributeDefinition(name="retry.reason"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="gateway.rate_limit.total",
            type=MetricType.COUNTER,
            unit="{request}",
            description="Number of rate-limited requests",
            attributes=[
                AttributeDefinition(name="rate_limit.policy"),
                AttributeDefinition(name="client.id"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "upstream_availability": (
            "1 - ("
            "sum(rate(http_client_request_duration_seconds_count"
            "{http_response_status_code=~'5..'}[5m])) / "
            "sum(rate(http_client_request_duration_seconds_count[5m]))"
            ")"
        ),
        "upstream_latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(http_client_request_duration_seconds_bucket[5m])) "
            "by (le, server_address))"
        ),
    },
)
