"""
Python runtime metric definitions.

Based on OpenTelemetry Python runtime semantic conventions.
Reference: https://opentelemetry.io/docs/specs/semconv/runtime/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
)

PYTHON_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        name="process.runtime.cpython.gc_count",
        type=MetricType.COUNTER,
        unit="{collection}",
        description="Number of garbage collections",
        attributes=[
            AttributeDefinition(
                name="gc.generation",
                type="int",
                examples=["0", "1", "2"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.cpython.memory",
        type=MetricType.GAUGE,
        unit="bytes",
        description="Python process memory usage",
        attributes=[
            AttributeDefinition(
                name="type",
                examples=["rss", "vms", "shared"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.cpython.cpu_time",
        type=MetricType.COUNTER,
        unit="seconds",
        description="CPU time used by Python process",
        attributes=[
            AttributeDefinition(
                name="type",
                examples=["user", "system"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.cpython.thread_count",
        type=MetricType.GAUGE,
        unit="{thread}",
        description="Number of Python threads",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
]
