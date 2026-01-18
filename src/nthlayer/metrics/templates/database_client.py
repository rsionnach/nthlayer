"""
Database client service type metric template.

For database connection pools and clients.
Based on OpenTelemetry Database semantic conventions (experimental).
Reference: https://opentelemetry.io/docs/specs/semconv/database/database-metrics/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)
from nthlayer.metrics.standards.otel_semconv import (
    DB_CLIENT_CONNECTIONS_USAGE,
    DB_CLIENT_OPERATION_DURATION,
    DB_OPERATION_NAME,
    DB_SYSTEM,
)

DATABASE_CLIENT_TEMPLATE = ServiceTypeTemplate(
    name="database-client",
    required=[
        MetricDefinition(
            name=DB_CLIENT_OPERATION_DURATION,
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of database operations",
            attributes=[
                AttributeDefinition(
                    name=DB_SYSTEM,
                    required=True,
                    examples=["postgresql", "mysql", "mongodb", "redis"],
                ),
                AttributeDefinition(
                    name=DB_OPERATION_NAME,
                    required=True,
                    examples=["SELECT", "INSERT", "UPDATE", "DELETE", "findOne"],
                ),
                AttributeDefinition(
                    name="db.collection.name",
                    examples=["users", "orders", "products"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["latency"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        ),
    ],
    recommended=[
        MetricDefinition(
            name=DB_CLIENT_CONNECTIONS_USAGE,
            type=MetricType.UPDOWN_COUNTER,
            unit="{connection}",
            description="Current number of connections in pool by state",
            attributes=[
                AttributeDefinition(name=DB_SYSTEM),
                AttributeDefinition(
                    name="state",
                    examples=["idle", "used"],
                ),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
            slo_usage=["saturation"],
        ),
        MetricDefinition(
            name="db.client.connection.create_time",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Time to establish new connections",
            attributes=[
                AttributeDefinition(name=DB_SYSTEM),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="db.client.connection.wait_time",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Time spent waiting for a connection from pool",
            attributes=[
                AttributeDefinition(name=DB_SYSTEM),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="db.client.connection.max",
            type=MetricType.GAUGE,
            unit="{connection}",
            description="Maximum number of connections allowed in pool",
            attributes=[
                AttributeDefinition(name=DB_SYSTEM),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(db_client_operation_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
        "connection_utilization": (
            "sum(db_client_connections_usage{state='used'}) / " "sum(db_client_connection_max)"
        ),
    },
)
