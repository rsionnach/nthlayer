"""
gRPC service type metric template.

Based on OpenTelemetry RPC semantic conventions (experimental).
Reference: https://opentelemetry.io/docs/specs/semconv/rpc/rpc-metrics/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)

GRPC_TEMPLATE = ServiceTypeTemplate(
    name="grpc",
    required=[
        MetricDefinition(
            name="rpc.server.duration",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of gRPC server calls",
            attributes=[
                AttributeDefinition(
                    name="rpc.system",
                    required=True,
                    examples=["grpc"],
                ),
                AttributeDefinition(
                    name="rpc.service",
                    required=True,
                    examples=["myservice.MyService"],
                ),
                AttributeDefinition(
                    name="rpc.method",
                    required=True,
                    examples=["GetUser", "CreateOrder"],
                ),
                AttributeDefinition(
                    name="rpc.grpc.status_code",
                    type="int",
                    required=True,
                    examples=["0", "2", "13"],  # OK, UNKNOWN, INTERNAL
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
            name="rpc.server.request.size",
            type=MetricType.HISTOGRAM,
            unit="bytes",
            description="Size of gRPC request messages",
            attributes=[
                AttributeDefinition(name="rpc.system"),
                AttributeDefinition(name="rpc.service"),
                AttributeDefinition(name="rpc.method"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="rpc.server.response.size",
            type=MetricType.HISTOGRAM,
            unit="bytes",
            description="Size of gRPC response messages",
            attributes=[
                AttributeDefinition(name="rpc.system"),
                AttributeDefinition(name="rpc.service"),
                AttributeDefinition(name="rpc.method"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="rpc.server.requests_per_rpc",
            type=MetricType.HISTOGRAM,
            unit="{count}",
            description="Number of messages per RPC (streaming)",
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="rpc.server.responses_per_rpc",
            type=MetricType.HISTOGRAM,
            unit="{count}",
            description="Number of response messages per RPC",
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "availability": (
            "1 - ("
            "sum(rate(rpc_server_duration_seconds_count{rpc_grpc_status_code!='0'}[5m])) / "
            "sum(rate(rpc_server_duration_seconds_count[5m]))"
            ")"
        ),
        "latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(rpc_server_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
    },
)
