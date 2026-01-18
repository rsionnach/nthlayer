"""
API (HTTP/REST) service type metric template.

Based on OpenTelemetry HTTP Server semantic conventions (stable v1.23+).
Reference: https://opentelemetry.io/docs/specs/semconv/http/http-metrics/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)
from nthlayer.metrics.standards.otel_semconv import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
    HTTP_SERVER_ACTIVE_REQUESTS,
    HTTP_SERVER_REQUEST_DURATION,
    HTTP_SERVER_REQUEST_SIZE,
    HTTP_SERVER_RESPONSE_SIZE,
    URL_SCHEME,
)

API_TEMPLATE = ServiceTypeTemplate(
    name="api",
    required=[
        MetricDefinition(
            name=HTTP_SERVER_REQUEST_DURATION,
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of HTTP server requests",
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
                    examples=["200", "404", "500"],
                ),
                AttributeDefinition(
                    name=URL_SCHEME,
                    examples=["http", "https"],
                ),
                AttributeDefinition(
                    name=HTTP_ROUTE,
                    examples=["/api/users/{id}", "/health"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["latency", "availability"],
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
            name=HTTP_SERVER_ACTIVE_REQUESTS,
            type=MetricType.UPDOWN_COUNTER,
            unit="{request}",
            description="Number of active HTTP server requests",
            attributes=[
                AttributeDefinition(name=HTTP_REQUEST_METHOD),
                AttributeDefinition(name=URL_SCHEME),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
            slo_usage=["saturation"],
        ),
        MetricDefinition(
            name=HTTP_SERVER_REQUEST_SIZE,
            type=MetricType.HISTOGRAM,
            unit="bytes",
            description="Size of HTTP server request bodies",
            attributes=[
                AttributeDefinition(name=HTTP_REQUEST_METHOD),
                AttributeDefinition(name=HTTP_ROUTE),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name=HTTP_SERVER_RESPONSE_SIZE,
            type=MetricType.HISTOGRAM,
            unit="bytes",
            description="Size of HTTP server response bodies",
            attributes=[
                AttributeDefinition(name=HTTP_REQUEST_METHOD),
                AttributeDefinition(name=HTTP_RESPONSE_STATUS_CODE, type="int"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "availability": (
            "1 - ("
            "sum(rate(http_server_request_duration_seconds_count"
            "{http_response_status_code=~'5..'}[5m])) / "
            "sum(rate(http_server_request_duration_seconds_count[5m]))"
            ")"
        ),
        "latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
        "latency_p95": (
            "histogram_quantile(0.95, "
            "sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
    },
)
