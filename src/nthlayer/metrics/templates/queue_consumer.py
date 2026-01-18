"""
Queue consumer service type metric template.

For message queue consumers (Kafka, RabbitMQ, SQS, etc.).
Based on OpenTelemetry Messaging semantic conventions (experimental).
Reference: https://opentelemetry.io/docs/specs/semconv/messaging/messaging-metrics/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)

QUEUE_CONSUMER_TEMPLATE = ServiceTypeTemplate(
    name="queue-consumer",
    required=[
        MetricDefinition(
            name="messaging.receive.duration",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of message processing",
            attributes=[
                AttributeDefinition(
                    name="messaging.system",
                    required=True,
                    examples=["kafka", "rabbitmq", "sqs", "redis"],
                ),
                AttributeDefinition(
                    name="messaging.destination.name",
                    required=True,
                    examples=["orders", "notifications", "events"],
                ),
                AttributeDefinition(
                    name="messaging.operation",
                    examples=["receive", "process"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["latency"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        ),
        MetricDefinition(
            name="messaging.receive.messages",
            type=MetricType.COUNTER,
            unit="{message}",
            description="Number of messages received",
            attributes=[
                AttributeDefinition(
                    name="messaging.system",
                    required=True,
                ),
                AttributeDefinition(
                    name="messaging.destination.name",
                    required=True,
                ),
                AttributeDefinition(
                    name="messaging.operation.status",
                    examples=["success", "failure"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["availability"],
        ),
    ],
    recommended=[
        MetricDefinition(
            name="messaging.consumer.lag",
            type=MetricType.GAUGE,
            unit="{message}",
            description="Consumer lag (messages behind)",
            attributes=[
                AttributeDefinition(name="messaging.destination.name"),
                AttributeDefinition(name="messaging.consumer.group"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
            slo_usage=["saturation"],
        ),
        MetricDefinition(
            name="messaging.dlq.messages",
            type=MetricType.COUNTER,
            unit="{message}",
            description="Messages sent to dead letter queue",
            attributes=[
                AttributeDefinition(name="messaging.destination.name"),
                AttributeDefinition(name="error.type"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="messaging.batch.size",
            type=MetricType.HISTOGRAM,
            unit="{message}",
            description="Number of messages in received batch",
            attributes=[
                AttributeDefinition(name="messaging.system"),
                AttributeDefinition(name="messaging.destination.name"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "processing_success_rate": (
            "sum(rate(messaging_receive_messages_total"
            "{messaging_operation_status='success'}[5m])) / "
            "sum(rate(messaging_receive_messages_total[5m]))"
        ),
        "latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(messaging_receive_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
    },
)
